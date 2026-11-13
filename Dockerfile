ARG ONTOP_VERSION=5.5.0

FROM eclipse-temurin:11-jdk AS config-builder
WORKDIR /build
COPY PropertyOverrides.java .
RUN javac --release 11 -d classes PropertyOverrides.java

# Latest stable upstream release checked on 2026-11-13; pin for reproducible builds.
FROM ontop/ontop:${ONTOP_VERSION}
USER root
RUN mv /opt/ontop/entrypoint.sh /opt/ontop/entrypoint-original.sh
USER ontop

COPY --from=config-builder --chown=ontop:ontop /build/classes/ /opt/ontop/runtime/classes/
COPY --chown=ontop:ontop --chmod=0555 entrypoint.sh /opt/ontop/entrypoint.sh
COPY --chown=ontop:ontop LICENSE LICENSING.md README.md /opt/ontop/runtime/doc/
ENTRYPOINT ["/opt/ontop/entrypoint.sh"]
# Inherit the upstream non-root user, working directory, ports and healthcheck.
