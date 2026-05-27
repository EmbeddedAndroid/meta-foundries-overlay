# Dragonwing App Template

This is the canonical starting point for new on-device apps on this
Qualcomm Dragonwing platform (Thundercomm Rubik Pi 3, QCS6490).

## How to use this template
Copy the directory:

    cp -r /root/apps/_template /root/apps/<your-app-id>

Then edit `main.py` — the only function you typically touch is
`process_frame(frame)`. Everything else (camera capture, wayland
display, NPU delegate loading, status overlay, telemetry, logo) is
already wired.

## What the template guarantees works
The hard things have already been figured out and are baked in:

- **Base image is `ubuntu:24.04`.** Not Bookworm. Not Trixie. Ubuntu
  24.04 ships GLIBC 2.39, which is the minimum that loads the host's
  `/usr/lib/libcdsprpc.so` (built against GLIBC 2.38). Bookworm 2.36
  fails with `version GLIBC_2.38 not found`.
- **TFLite via `ai-edge-litert`** (PyPI, py3.12 wheel), not the legacy
  `tflite-runtime` (no wheel beyond py3.11). API is compatible.
- **`opencv-data` apt package** ships Haar cascade XMLs at
  `/usr/share/opencv4/haarcascades/` (Debian/Ubuntu `python3-opencv`
  does NOT include `cv2.data`, contrary to pip wheel).
- **`libyaml-0-2`** is installed — `libQnnHtp.so` HtpProvider dlopens
  it via `libcdsprpc.so`; without it the QNN delegate silently
  falls back to CPU with "Failed in loading stub: libyaml-0.so.2".
- **GStreamer pipeline pattern**: `v4l2src ! image/jpeg ! jpegdec !
  videoconvert ! BGR ! appsink` in, `appsrc ! BGR ! videoconvert !
  waylandsink` out. Avoids the dmabuf binding warning by giving
  waylandsink shm BGR frames.
- **Logo/overlay assets are big**: `assets/dragonwing.png` is 1585x550 —
  wider than the 1280 frame. The template resizes it to ~22% of frame
  width at load time so it sits as a corner badge. If you ship your
  own logo asset, keep that resize step (or pre-shrink the PNG).
- **Telemetry**: thermal zones at `/sys/class/thermal/thermal_zone*`,
  loadavg at `/proc/loadavg`. The runtime expects these bind-mounted
  read-only — see the runtime requirements below.

## Runtime requirements (the marketplace handles these automatically)
The marketplace launches your container with:

    docker run -d --restart=unless-stopped \
      --user 1000:1000 --group-add 44                              \  # weston:video
      --device=/dev/video2:/dev/video2                              \  # USB cam
      --device=/dev/fastrpc-cdsp:/dev/fastrpc-cdsp                  \  # NPU
      -v /run/user/1000:/run/user/1000:rw                           \  # wayland sockets
      -v /usr/lib/dsp:/usr/lib/dsp:ro                               \  # DSP user-PD shells + libc++
      -v /usr/lib/firmware:/usr/lib/firmware:ro                     \  # cdsp.mbn etc.
      -v /sys/class/thermal:/sys/class/thermal:ro                   \  # thermals
      -v /usr/lib/libcdsprpc.so*:/usr/lib/<same>:ro                 \  # fastrpc client lib
      -e XDG_RUNTIME_DIR=/run/user/1000                             \
      -e WAYLAND_DISPLAY=wayland-1                                  \  # or wayland-rdp
      -e ADSP_LIBRARY_PATH='/usr/lib/dsp;/usr/lib/dsp/cdsp'         \  # DSP search path
      -e CAM_DEVICE=/dev/video2 -e WIDTH=1280 -e HEIGHT=720         \
      -e MODEL=/models/<your>.tflite -e QNN_BACKEND=htp             \  # if using NPU
      <your-image>

So your Dockerfile must inherit this template's `Dockerfile` (or copy
its FROM + apt-get block verbatim) so the runtime mounts line up with
what's installed in the image.

## NPU offload
- Compile your model on Qualcomm AI Hub targeting `"Dragonwing RB3
  Gen 2 Vision Kit"` (the QCS6490 device), runtime `tflite`, precision
  `w8a8`. The output `.tflite` has all ops mapped to HTP.
- Set `MODEL=/models/<file>.tflite` and `QNN_BACKEND=htp`.
- If the delegate fails to apply (model has unsupported ops), the
  template falls back to CPU XNNPACK automatically.

### QCS6490 model picker (HTP = Hexagon V68, INT8-only)

The HTP NPU has no fp16 path. Check AI Hub's "supported precisions"
before committing to a model:

  - **✅ tflite + w8a8 — drops into this template, runs on NPU:**
    `yolov8_det`, `yolov11_det`, `posenet_mobilenet`,
    `mediapipe_selfie`, `ssd_mobilenet_v2`, `hrnet_pose`
    (the last needs `mmengine` added to the `qai-export` image)

  - **❌ Float-only — won't run on HTP via the tflite delegate:**
    `mediapipe_hand`, `mediapipe_pose`, `mediapipe_face`
    Use `--target-runtime qnn_context_binary` and load via the QNN
    SDK directly (bypassing this template's tflite path).

## Output target
- `WAYLAND_DISPLAY=wayland-1` → primary Weston, shown on HDMI
- `WAYLAND_DISPLAY=wayland-rdp` → headless Weston-RDP on port 3389
- Marketplace toggle exposes HDMI / RDP / BOTH per app.

## Registering the app in the marketplace
After `docker build -t <id>:latest .`, register via:

    curl -X POST http://127.0.0.1:8080/api/apps/install \
      -H 'content-type: application/json' \
      -d '{"id":"<id>","name":"...","description":"...","image":"<id>:latest","cover_image":"/static/..." }'

(Endpoint TBD — the agent's `install_app` tool wraps this.)
