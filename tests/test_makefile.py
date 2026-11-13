"""Image publishing checks with a fake Docker CLI; no daemon or registry needed."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('make'), 'Requires GNU Make')
class MakefileTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.log = self.root / 'calls.jsonl'
        self.docker = self.root / 'docker'
        self.docker.write_text('#!' + sys.executable + '\n' + '''import json, os, sys
args=sys.argv[1:]
with open(os.environ['CALL_LOG'], 'a') as out:
    out.write(json.dumps({'args':args,'cwd':os.getcwd()})+'\\n')
if args[:2]==['manifest','inspect']:
    prefix='DIGEST' if '@sha256:' in args[-1] else 'TAG'
    if os.environ.get(prefix+'_STATE')=='present':
        print('{}');sys.exit(0)
    print(os.environ.get(prefix+'_ERROR') or 'no such manifest: '+args[-1],file=sys.stderr)
    sys.exit(1)
if args[:2]==['image','inspect']:
    print(os.environ.get('REPO_DIGESTS',''));sys.exit(0)
if args[0]=='build':sys.exit(int(os.environ.get('BUILD_EXIT','0')))
''')
        self.docker.chmod(0o755)

    def make(self, *args, **env):
        environment = dict(os.environ)
        for key in ['VERSION', 'ONTOP_VERSION', 'REPOSITORY', 'IMAGE', 'MAKEFLAGS', 'MFLAGS']:
            environment.pop(key, None)
        environment.update(CALL_LOG=str(self.log), **env)
        return subprocess.run(['make', '--no-print-directory', '-f', str(ROOT / 'Makefile'),
                               'DOCKER=' + str(self.docker),
                               'ENV_FILE=' + str(self.root / 'absent.env'), *args],
                              cwd=self.root, env=environment, capture_output=True, text=True)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_default_help_is_descriptive_and_does_not_invoke_docker(self):
        result = self.make()
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ['help', 'build', 'publish']:
            self.assertRegex(result.stdout, 'make '+name+r'\s+#')
        self.assertFalse(self.log.exists())

    @unittest.skipUnless(shutil.which('bash'), 'Requires Bash')
    def test_build_conf_is_sourceable_and_drives_build(self):
        config = subprocess.run(['bash', '-eu', '-c',
            '. "$1"; printf "%s\\n%s\\n" "$VERSION" "$ONTOP_VERSION"',
            'bash', str(ROOT / 'build.conf')], capture_output=True, text=True, check=True)
        version, upstream = config.stdout.splitlines()
        result = self.make('build', TAG_STATE='present')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(self.calls()[0], {'cwd': str(ROOT), 'args': [
            'build', '--tag', 'ghcr.io/provider-project/provider-ontop:'+version,
            '--build-arg', 'ONTOP_VERSION='+upstream, '.']})

    def test_environment_and_command_line_overrides(self):
        result = self.make('build', 'VERSION=2.0.0', 'ONTOP_VERSION=5.4.0', VERSION='1.0.0')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('ghcr.io/provider-project/provider-ontop:2.0.0', self.calls()[0]['args'])
        self.assertIn('ONTOP_VERSION=5.4.0', self.calls()[0]['args'])

    def test_env_file_override(self):
        config = self.root / 'build.env'
        config.write_text('VERSION=3.0.0\nREPOSITORY=local/runtime\n')
        result = self.make('build', 'ENV_FILE='+str(config), VERSION='1.0.0')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('local/runtime:3.0.0', self.calls()[0]['args'])

    def test_publish_order_and_image_override(self):
        image = 'ghcr.io/example/runtime:1.0.0'
        result = self.make('--jobs=4', 'publish', 'IMAGE='+image)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([call['args'][0] for call in self.calls()],
                         ['manifest','build','image','push'])
        self.assertEqual(self.calls()[0]['args'], ['manifest','inspect',image])
        self.assertEqual(self.calls()[-1]['args'], ['push',image])

    def test_existing_tag_stops_before_build_and_explains_version(self):
        result = self.make('publish', TAG_STATE='present')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.calls()), 1)
        self.assertIn('build.conf', result.stderr)
        self.assertIn('VERSION=NEW_VERSION', result.stderr)

    def test_registry_failure_stops_before_build(self):
        for message in ['unauthorized: authentication required','dial tcp: i/o timeout']:
            with self.subTest(message=message):
                result = self.make('publish', TAG_ERROR=message)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Could not establish', result.stderr)
        self.assertEqual([call['args'][0] for call in self.calls()], ['manifest','manifest'])

    def test_failed_build_prevents_push(self):
        result = self.make('publish', BUILD_EXIT='7')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual([call['args'][0] for call in self.calls()], ['manifest','build'])

    def test_existing_digest_stops_before_push(self):
        digest = 'sha256:'+'a'*64
        result = self.make('publish', 'IMAGE=registry.example:5000/team/runtime:new',
                           REPO_DIGESTS='old.registry/runtime@'+digest, DIGEST_STATE='present')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual([call['args'][0] for call in self.calls()],
                         ['manifest','build','image','manifest'])
        self.assertEqual(self.calls()[-1]['args'][-1],
                         'registry.example:5000/team/runtime@'+digest)

    def test_missing_digest_allows_push(self):
        result = self.make('publish', REPO_DIGESTS='source/runtime@sha256:'+'b'*64)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([call['args'][0] for call in self.calls()],
                         ['manifest','build','image','manifest','push'])

    def test_digest_registry_failure_prevents_push(self):
        result = self.make('publish', REPO_DIGESTS='source/runtime@sha256:'+'c'*64,
                           DIGEST_ERROR='unauthorized: authentication required')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls()[-1]['args'][0], 'manifest')
        self.assertIn('nothing was pushed', result.stderr)

    def test_dry_run_never_calls_docker(self):
        result = self.make('--dry-run', 'publish')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.log.exists())
