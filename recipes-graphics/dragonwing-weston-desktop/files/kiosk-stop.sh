#!/bin/sh
# Panel launcher: close the kiosk by killing its container.
docker rm -f marketplace-kiosk >/dev/null 2>&1
