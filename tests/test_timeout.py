"""Opt-in real Ontop/DuckDB cancellation check, using a bounded container."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from urllib.parse import urlencode

IMAGE = os.environ.get('ONTOP_RUNTIME_IMAGE')
JAR = Path(os.environ.get('DUCKDB_JDBC_JAR', '/nonexistent'))


@unittest.skipUnless(IMAGE and JAR.is_file() and shutil.which('docker'),
                     'Set ONTOP_RUNTIME_IMAGE and DUCKDB_JDBC_JAR for the cancellation test')
class TimeoutTests(unittest.TestCase):
    def test_blocking_query_is_cancelled_and_endpoint_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.chmod(0o755)
            (root / 'mapping.ttl').write_text('''@prefix rr: <http://www.w3.org/ns/r2rml#> .
<urn:map> a rr:TriplesMap;
 rr:logicalTable [ rr:sqlQuery "SELECT CAST(SUM(sin(i::DOUBLE)) AS VARCHAR) AS v FROM range(100000000000) r(i)" ];
 rr:subjectMap [ rr:constant <urn:slow> ];
 rr:predicateObjectMap [ rr:predicate <urn:value>; rr:objectMap [ rr:column "v"; rr:datatype <http://www.w3.org/2001/XMLSchema#string> ] ].
''')
            (root / 'db.properties').write_text('''jdbc.url=jdbc:duckdb:
jdbc.driver=org.duckdb.DuckDBDriver
jdbc.property.jdbc_stream_results=true
jdbc.property.memory_limit=128MB
jdbc.property.threads=1
jdbc.property.temp_directory=/tmp/duckdb
''')
            for file in root.iterdir():
                file.chmod(0o644)
            container = subprocess.check_output([
                'docker', 'run', '-d', '--network', 'none', '--read-only',
                '--memory', '1g', '--memory-swap', '1g', '--tmpfs', '/tmp:rw,exec,size=256m',
                '--mount', f'type=bind,src={root},dst=/input,readonly',
                '--mount', f'type=bind,src={JAR.resolve()},dst=/opt/ontop/jdbc/duckdb_jdbc.jar,readonly',
                '-e', 'ONTOP_MAPPING_FILE=/input/mapping.ttl',
                '-e', 'ONTOP_PROPERTIES_FILE=/input/db.properties',
                '-e', 'ONTOP_PROPERTIES=ontop.query.defaultTimeout=1',
                '-e', 'ONTOP_JAVA_ARGS=-Xms64m -Xmx256m',
                '-e', 'ONTOP_LOG_LEVEL=info', IMAGE], text=True).strip()
            try:
                def query(sparql, timeout=15):
                    return subprocess.run([
                        'docker', 'exec', container, 'wget', '-qO-',
                        '--header=Accept:application/sparql-results+json',
                        'http://localhost:8080/sparql?' + urlencode({'query': sparql})],
                        capture_output=True, text=True, timeout=timeout)
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    ready = query('ASK {}')
                    if ready.returncode == 0:
                        break
                    running = subprocess.check_output(
                        ['docker', 'inspect', '--format', '{{.State.Running}}', container],
                        text=True).strip()
                    if running != 'true':
                        logs = subprocess.check_output(['docker', 'logs', container],
                                                       text=True, stderr=subprocess.STDOUT)
                        self.fail('Endpoint exited during startup:\n' + logs[-6000:])
                    time.sleep(1)
                else:
                    self.fail('Endpoint did not become ready')
                start = time.monotonic()
                result = query('SELECT ?v WHERE { <urn:slow> <urn:value> ?v }')
                elapsed = time.monotonic() - start
                self.assertNotEqual(result.returncode, 0, 'Expensive query unexpectedly succeeded')
                self.assertLess(elapsed, 10, 'Database execution was not cancelled promptly')
                logs = subprocess.check_output(['docker', 'logs', container],
                                               text=True, stderr=subprocess.STDOUT)
                self.assertRegex(logs.lower(), r'interrupt|cancel|time.?out')
                self.assertEqual(query('ASK {}').returncode, 0)
                print(f'Blocking query cancelled after {elapsed:.2f}s; endpoint recovered')
            finally:
                subprocess.run(['docker', 'rm', '-f', '-v', container],
                               capture_output=True, check=True)
