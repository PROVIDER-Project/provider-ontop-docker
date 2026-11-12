import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

IMAGE = os.environ.get('ONTOP_RUNTIME_IMAGE')


@unittest.skipUnless(IMAGE and shutil.which('docker'), 'Set ONTOP_RUNTIME_IMAGE for Docker tests')
class ContainerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.root.chmod(0o755)
        self.source = self.root / 'input.properties'
        self.source.write_text('test.marker=original\nontop.query.defaultTimeout=30\n')
        self.source.chmod(0o644)
        self.delegate = self.root / 'upstream.sh'
        self.delegate.write_text('''#!/bin/bash
if [ "${1:-}" = sh ]; then exec "$@"; fi
printf 'uid=%s\\n' "$(id -u)"
printf 'mode=%s\\n' "$(stat -c %a "$ONTOP_PROPERTIES_FILE")"
cat "$ONTOP_PROPERTIES_FILE"
printf 'arg=%s\\n' "$@"
''')
        self.delegate.chmod(0o755)

    def run_image(self, env=None, args=None):
        command = ['docker', 'run', '--rm', '--network', 'none', '--read-only',
                   '--tmpfs', '/tmp:rw,size=32m',
                   '--mount', f'type=bind,src={self.root},dst=/input,readonly',
                   '--mount', f'type=bind,src={self.delegate},dst=/opt/ontop/entrypoint.sh,readonly']
        for key, value in (env or {}).items():
            command.extend(['-e', key + '=' + value])
        return subprocess.run(command + [IMAGE] + (args or []),
                              capture_output=True, text=True, timeout=30)

    def test_readonly_nonroot_environment_overrides(self):
        result = self.run_image({'ONTOP_PROPERTIES_FILE': '/input/input.properties',
                                'ONTOP_PROPERTY_ontop__query__defaultTimeout': '60'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('uid=999', result.stdout)
        self.assertIn('mode=600', result.stdout)
        self.assertIn('ontop.query.defaultTimeout=60', result.stdout)
        self.assertIn('test.marker=original', result.stdout)
        self.assertIn('ontop.query.defaultTimeout=30', self.source.read_text())

    def test_cli_properties_selection(self):
        for args in [['ontop', 'endpoint', '--properties', '/input/input.properties'],
                     ['ontop', 'endpoint', '-p', '/input/input.properties'],
                     ['ontop', 'endpoint', '--properties=/input/input.properties']]:
            with self.subTest(args=args):
                result = self.run_image({'ONTOP_PROPERTIES_FILE': '/input/missing.properties'}, args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('test.marker=original', result.stdout)
                self.assertIn('arg=', result.stdout)
                self.assertNotIn('arg=/input/input.properties', result.stdout)
                self.assertNotIn('arg=--properties=/input/input.properties', result.stdout)

    def test_arbitrary_command_passthrough(self):
        result = self.run_image({'ONTOP_PROPERTY_': 'invalid, but irrelevant to shell commands'},
                                ['sh', '-c', 'printf passthrough'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'passthrough')
