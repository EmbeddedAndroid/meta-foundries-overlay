#!/bin/sh
echo "[run.sh] $(date)  container=$(hostname)"
echo "[run.sh] WAYLAND_DISPLAY=$WAYLAND_DISPLAY  cam=$CAM_DEVICE"
echo "[run.sh] QNN_BACKEND=${QNN_BACKEND:-htp}"
ls /opt/qnn /models | head -10
exec python3 -u /detect.py
