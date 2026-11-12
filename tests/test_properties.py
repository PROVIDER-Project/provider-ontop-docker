import base64
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('javac') and shutil.which('java'), 'Requires a JDK')
class PropertyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.classes.cleanup)
        probe = Path(cls.classes.name) / 'ReadProperties.java'
        probe.write_text('''import java.nio.file.*; import java.util.*;
public class ReadProperties {
 public static void main(String[] args) throws Exception {
  Properties p=new Properties();
  try(var input=Files.newInputStream(Path.of(args[0]))){p.load(input);}
  for(String key:p.stringPropertyNames()) {
   var b=Base64.getEncoder();
   System.out.println(b.encodeToString(key.getBytes("UTF-8"))+":"+
                      b.encodeToString(p.getProperty(key).getBytes("UTF-8")));
  }
 }
}''')
        subprocess.run(['javac', '--release', '11', '-d', cls.classes.name,
                        str(ROOT / 'PropertyOverrides.java'), str(probe)], check=True)

    def generate(self, content=None, overrides=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        env = {k: v for k, v in os.environ.items() if not k.startswith('ONTOP_PROPERTY_')}
        env.update(TMPDIR=directory.name)
        env.update(overrides or {})
        args = ['java', '-cp', self.classes.name, 'PropertyOverrides']
        if content is not None:
            source = Path(directory.name) / 'input.properties'
            source.write_bytes(content.encode('ascii'))
            args.append(str(source))
        result = subprocess.run(args, env=env, capture_output=True, text=True)
        if result.returncode:
            return result, None, None
        output = Path(result.stdout.strip())
        probe = subprocess.run(['java', '-cp', self.classes.name, 'ReadProperties', str(output)],
                               capture_output=True, text=True, check=True)
        properties = {}
        for line in probe.stdout.splitlines():
            key, value = line.split(':', 1)
            properties[base64.b64decode(key).decode()] = base64.b64decode(value).decode()
        if content is not None:
            self.assertEqual(source.read_bytes(), content.encode('ascii'))
        return result, properties, output

    def test_default_timeout_and_private_file(self):
        result, props, path = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(props['ontop.query.defaultTimeout'], '120')
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_file_settings_override_defaults(self):
        result, props, _ = self.generate('ontop.query.defaultTimeout=30\njdbc.url=jdbc:duckdb:\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(props['ontop.query.defaultTimeout'], '30')
        self.assertEqual(props['jdbc.url'], 'jdbc:duckdb:')

    def test_environment_overrides_preserve_case_and_underscores(self):
        result, props, _ = self.generate('ontop.query.defaultTimeout=30\n', {
            'ONTOP_PROPERTY_ontop__query__defaultTimeout': '60',
            'ONTOP_PROPERTY_jdbc__property__jdbc_stream_results': 'true',
            'ONTOP_LOG_LEVEL': 'debug'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(props['ontop.query.defaultTimeout'], '60')
        self.assertEqual(props['jdbc.property.jdbc_stream_results'], 'true')
        self.assertNotIn('LOG_LEVEL', props)

    def test_values_round_trip_without_injection_or_logging(self):
        secret = ' leading space\\path=foo:bar\nnew.property=not-injected\tGrüße ☕ '
        result, props, _ = self.generate(overrides={'ONTOP_PROPERTY_jdbc__password': secret})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(props['jdbc.password'], secret)
        self.assertNotIn('new.property', props)
        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_zero_disables_timeout(self):
        result, props, _ = self.generate(overrides={'ONTOP_PROPERTY_ontop__query__defaultTimeout': '0'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(props['ontop.query.defaultTimeout'], '0')

    def test_invalid_timeout_and_empty_key_fail(self):
        for overrides in [
            {'ONTOP_PROPERTY_ontop__query__defaultTimeout': v}
            for v in ['-1', 'abc', '2147483648', '']
        ] + [{'ONTOP_PROPERTY_': 'value'}]:
            with self.subTest(overrides=overrides):
                result, _, _ = self.generate(overrides=overrides)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')
