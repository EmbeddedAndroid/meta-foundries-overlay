#!/bin/sh
# Panel launcher: (re)start the marketplace kiosk browser as a Weston client.
# Runs as the weston user (member of the docker group). Chromium renders to
# wayland-1; closing the kiosk window stops the container. Re-run safely: the
# rm -f below clears any prior instance first.
docker rm -f marketplace-kiosk >/dev/null 2>&1
exec docker run -d --name marketplace-kiosk \
  --user 1000:1000 --group-add 44 \
  -v /dev/dri:/dev/dri --device-cgroup-rule='c 226:* rmw' \
  -v /run/user/1000:/run/user/1000:rw \
  -e XDG_RUNTIME_DIR=/run/user/1000 -e WAYLAND_DISPLAY=wayland-1 \
  --shm-size=512m \
  marketplace-kiosk:latest
