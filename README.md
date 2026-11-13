# Ontop runtime

A small extension of the official Ontop image: configure properties through
environment variables, with a finite database query execution timeout by default.
No Ontop Java code is patched. Dataset images supply their own data and mappings.

## Build and publish

```sh
make help
make build
# After docker login ghcr.io:
make publish
```

The default image is `ghcr.io/provider-project/ontop-fork:5.5.0-1`.
Tracked `build.conf` contains sourceable `VAR=VAL` version defaults: `VERSION`
for this image and `ONTOP_VERSION` for the upstream base. Override them on the
command line, through the environment or in a gitignored `.env` (precedence in
that order), for example:

```sh
make publish VERSION=5.5.0-2
make build REPOSITORY=local/ontop-fork
```

`build` freely replaces local tags. Only `publish` checks the remote tag before
building and known manifest digests before pushing. Existing tags/digests or
registry errors stop publication. If no local manifest digest is available,
the digest check is skipped with a message. Checks are best-effort and cannot
prevent races with concurrent publishers. Changing labels or attestations may
produce another digest even with otherwise equivalent image contents.

The base is `ontop/ontop:5.5.0`, the latest stable release checked on
[13 November 2026](https://github.com/ontop/ontop/releases/tag/ontop-5.5.0). Override `ONTOP_VERSION` at build time when upgrading.
A JDK compiles the configuration helper in a separate build stage; the final
image retains the upstream non-root user and runtime.

## Configure

Set `ONTOP_PROPERTIES` to a multiline Java properties block. Names are used
verbatim, with no environment-name encoding:

```yaml
environment:
  ONTOP_PROPERTIES_FILE: /opt/ontop/input/faostat.properties
  ONTOP_PROPERTIES: |
    ontop.query.defaultTimeout=60
    jdbc.property.jdbc_stream_results=true
    jdbc.property.memory_limit=1GB
```

The block overrides matching file entries and adds new properties. It accepts
standard Java properties syntax (comments, continuations and backslash escapes)
and Unicode text. For literal backslashes or newlines within a value, use the
usual properties escapes. Property values are never logged by the helper.
The earlier `ONTOP_PROPERTY_*` convention is rejected with migration guidance.

Omit `ONTOP_PROPERTIES_FILE` for environment-only configuration. An explicitly
selected missing or unreadable file fails startup, even if overrides are present.

Precedence: `ONTOP_PROPERTIES` > selected properties file > default
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
FROM ghcr.io/provider-project/ontop-fork:5.5.0-1 AS data-base
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

The Makefile checks use a fake Docker CLI and never push. Property tests require
a JDK. Docker smoke tests can be enabled with
`ONTOP_RUNTIME_IMAGE=ghcr.io/provider-project/ontop-fork:5.5.0-1`. Also set
`DUCKDB_JDBC_JAR=/path/to/duckdb_jdbc.jar` to test actual blocking-query
cancellation and endpoint recovery with DuckDB.

## Licence

Original project material is [Apache-2.0](LICENSE). [Licensing notes](LICENSING.md)
cover upstream components and the AI-assisted provenance of that information.
