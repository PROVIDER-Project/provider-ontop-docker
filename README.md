# Ontop runtime

A small extension of the official Ontop image: configure properties through
environment variables, with a finite database query execution timeout by default.
No Ontop Java code is patched. Dataset images supply their own data and mappings.

## Build

```sh
docker build -t provider/ontop-runtime:5.5.0-1 .
```

The base is `ontop/ontop:5.5.0`, the latest stable release checked on
[13 November 2026](https://github.com/ontop/ontop/releases/tag/ontop-5.5.0). Override `ONTOP_VERSION` at build time when upgrading.
A JDK compiles the configuration helper in a separate build stage; the final
image retains the upstream non-root user and runtime.

## Configure

Use `ONTOP_PROPERTY_` followed by the exact property name, with dots encoded as
**double underscores**. Case and single underscores are preserved:

```yaml
environment:
  ONTOP_PROPERTIES_FILE: /opt/ontop/input/faostat.properties
  ONTOP_PROPERTY_ontop__query__defaultTimeout: "60"
  ONTOP_PROPERTY_jdbc__property__jdbc_stream_results: "true"
  ONTOP_PROPERTY_jdbc__property__memory_limit: "1GB"
```

These become `ontop.query.defaultTimeout`, `jdbc.property.jdbc_stream_results`
and `jdbc.property.memory_limit`. Values are Java-properties escaped, including
Unicode, newlines and backslashes; they are never logged by the helper.

Precedence: property environment overrides > selected properties file > default
query timeout of **120 seconds**. Set the timeout to `0` to disable it. Existing
upstream variables such as `ONTOP_DB_URL` and `ONTOP_LOG_LEVEL` still work;
explicit upstream JDBC/CLI options retain their normal precedence. No engine
thread or memory limits are imposed unless you configure them.

The selected file is copied into a private generated properties file under
`/tmp` (or `TMPDIR`); the original stays unchanged. CLI `--properties`/`-p` and
`--properties=...` select the input file too. A read-only root filesystem works
with writable `/tmp` (executable too when a JDBC driver extracts native libraries). Arbitrary commands and CLI help pass through unchanged.

## Use as a base

Replace the upstream base in a dataset Dockerfile with your published runtime:

```dockerfile
FROM provider/ontop-runtime:5.5.0-1 AS data-base
# Add the database, JDBC driver, mappings and properties as before.
```

The existing dataset repos are not changed by this setup. Publish the runtime
image under your registry namespace before using it in remote builds.

## Timeout scope

`ontop.query.defaultTimeout` is a JDBC execution timeout, not a hard deadline
for the complete HTTP response. With DuckDB JDBC 1.5.6.0, its timer is cancelled
when `execute()` returns; later streamed fetching can outlive that limit.
The integration test verifies cancellation of a blocking aggregate and endpoint
recovery. A proxy/client timeout alone does not prove database work has stopped.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Tests require a JDK. Docker smoke tests can be enabled with
`ONTOP_RUNTIME_IMAGE=provider/ontop-runtime:5.5.0-1`. Also set
`DUCKDB_JDBC_JAR=/path/to/duckdb_jdbc.jar` to test actual blocking-query
cancellation and endpoint recovery with DuckDB.

## Licence

Original project material is [Apache-2.0](LICENSE). [Licensing notes](LICENSING.md)
cover upstream components and the AI-assisted provenance of that information.
