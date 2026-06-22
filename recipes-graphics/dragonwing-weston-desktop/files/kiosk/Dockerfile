# Pinned, reproducible build of the Dragonwing marketplace kiosk browser.
#
# Base is pinned by digest; apt packages are frozen to a Debian snapshot so the
# exact mesa 26 (Adreno 623 support) and Chromium versions are reproducible.
# To refresh: bump BASE_DIGEST (docker inspect debian:sid) and SNAPSHOT, rebuild,
# re-verify GPU, and record the new digest in DEPLOY.md.
FROM debian:sid@sha256:d4b76cd3c767e81dbbeb88e1c252c85275c3fba518ad7d17a42c9eb0b6b5b9bb

# Debian snapshot timestamp -> frozen package set (mesa 26.0.8, Chromium
# 149.0.7827.102 at this date). snapshot.debian.org redirects to the nearest
# real snapshot, which apt follows.
ARG SNAPSHOT=20260612T000000Z
RUN rm -f /etc/apt/sources.list.d/*.sources /etc/apt/sources.list && \
    printf 'deb http://snapshot.debian.org/archive/debian/%s/ sid main\n' "$SNAPSHOT" > /etc/apt/sources.list && \
    printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\nAcquire::http::Timeout "120";\n' > /etc/apt/apt.conf.d/99snapshot && \
    apt-get update && apt-get install -y --no-install-recommends \
        chromium \
        libgl1-mesa-dri libegl1 libgles2 libgbm1 libwayland-egl1 \
        fonts-liberation ca-certificates dbus \
    && rm -rf /var/lib/apt/lists/*

COPY launch.sh /launch.sh
RUN chmod +x /launch.sh
ENV XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-1 HOME=/tmp
ENTRYPOINT ["/launch.sh"]
