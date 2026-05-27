#!/bin/sh
# Boilerplate entrypoint. Logs env, then execs the Python main.
echo "[$(hostname)] starting at $(date)"
echo "[$(hostname)] WAYLAND_DISPLAY=$WAYLAND_DISPLAY  CAM=$CAM_DEVICE  MODEL=$MODEL"
exec python3 -u /main.py
