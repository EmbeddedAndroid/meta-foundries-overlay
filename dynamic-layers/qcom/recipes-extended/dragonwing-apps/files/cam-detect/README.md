# cam-detect (Deal With It)

YOLOv8 object detection running on the Hexagon NPU, drops Dragonwing
sunglasses on faces. The container, base libraries, and runtime are all
provided by the baked `rubikpi3-cam-test:npu` Yocto rootfs image.

## What this directory contains
- `Dockerfile` — `FROM rubikpi3-cam-test:npu`, then `COPY main.py /detect.py`
- `main.py`   — the detection pipeline (extracted from the running image)
- `run.sh`    — startup script (extracted)
- `assets/`   — overlay PNGs

## Forking
Click Fork on the cam-detect tile. That copies this directory to
`/root/apps/<new-id>/`, registers a new app, and kicks off a docker build
of `<new-id>:latest` against the same base. Edit `main.py` to change the
detection model, the overlay, or whatever.
