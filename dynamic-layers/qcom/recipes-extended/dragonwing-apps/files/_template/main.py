#!/usr/bin/env python3
"""Dragonwing app template — camera ⇄ optional NPU inference ⇄ waylandsink.

Plug your inference + drawing in `process_frame(frame)`. Everything else
(camera pipeline, wayland output, NPU delegate loading, status overlay,
thermal/FPS telemetry, logo overlay) is already wired and battle-tested.
"""
import os, sys, time, glob
import numpy as np
import cv2

# ---- Knobs an app commonly tweaks --------------------------------------
APP_NAME   = os.environ.get("APP_NAME", "My App")
CAM        = os.environ.get("CAM_DEVICE", "/dev/video2")
W          = int(os.environ.get("WIDTH",  "1280"))
H          = int(os.environ.get("HEIGHT", "720"))
MODEL      = os.environ.get("MODEL", "")          # path to .tflite (optional)
QNN_LIB    = os.environ.get("QNN_DELEGATE_LIB", "/opt/qnn/libQnnTFLiteDelegate.so")
QNN_BACK   = os.environ.get("QNN_BACKEND", "htp")  # htp | gpu | cpu
LOGO_PATH  = os.environ.get("LOGO_PATH", "/assets/dragonwing.png")
FULLSCREEN = os.environ.get("FULLSCREEN", "false").lower() in ("1","true","yes")

# ---- Optional NPU/TFLite interpreter (load only if MODEL is set) -------
interp = None; inp = None; outs = None; using_npu = False
if MODEL:
    try:
        from ai_edge_litert.interpreter import Interpreter, load_delegate
    except ImportError:
        from tflite_runtime.interpreter import Interpreter, load_delegate
    delegates = []
    try:
        delegates.append(load_delegate(QNN_LIB, options={"backend_type": QNN_BACK}))
    except Exception as e:
        print(f"[app] WARN QNN load: {e!r}", flush=True)
    try:
        interp = Interpreter(model_path=MODEL, experimental_delegates=delegates)
        using_npu = bool(delegates)
    except RuntimeError as e:
        print(f"[app] WARN delegate apply: {e}; CPU fallback", flush=True)
        interp = Interpreter(model_path=MODEL); using_npu = False
    interp.allocate_tensors()
    inp  = interp.get_input_details()[0]
    outs = interp.get_output_details()
    print(f"[app] model: {MODEL}  in={inp['shape']}  on {'NPU' if using_npu else 'CPU'}", flush=True)

# ---- Telemetry readers (host /sys + /proc bind-mounted) ----------------
def read_thermals():
    cpu, npu, gpu = [], None, None
    for z in glob.glob('/sys/class/thermal/thermal_zone*'):
        try:
            t = open(z+'/type').read().strip()
            v = int(open(z+'/temp').read().strip())/1000.0
        except Exception: continue
        if t.startswith('cpu') and t.endswith('-thermal') and 'ss' not in t: cpu.append(v)
        elif t.startswith('nspss'): npu = v if npu is None else max(npu, v)
        elif t.startswith('gpuss'): gpu = v if gpu is None else max(gpu, v)
    return (max(cpu) if cpu else None), npu, gpu

def read_loadavg():
    try: return float(open('/proc/loadavg').read().split()[0])
    except Exception: return None

# ---- Logo overlay (BGRA → alpha-blended bottom-right) ------------------
logo = cv2.imread(LOGO_PATH, cv2.IMREAD_UNCHANGED) if os.path.exists(LOGO_PATH) else None
if logo is not None and logo.shape[2] != 4: logo = None
# Scale logo down so it sits as a corner badge, not a centerpiece.
# Target ~22% of frame width — neatly tucked, still legible. The shipped
# dragonwing.png is 1585x550, which without this resize would be wider than
# the frame itself.
if logo is not None:
    target_w = max(120, int(W * 0.22))
    lh, lw = logo.shape[:2]
    if lw > target_w:
        scale = target_w / lw
        logo = cv2.resize(logo, (target_w, max(1, int(lh*scale))), interpolation=cv2.INTER_AREA)
        print(f"[app] logo resized to {logo.shape}", flush=True)

def alpha_blit(frame, lg, x0, y0):
    if lg is None: return
    fh, fw = frame.shape[:2]; lh, lw = lg.shape[:2]
    sx1 = max(0, -x0); sy1 = max(0, -y0)
    dx1 = max(0, x0); dy1 = max(0, y0)
    dx2 = min(fw, x0+lw); dy2 = min(fh, y0+lh)
    if dx2 <= dx1 or dy2 <= dy1: return
    cw, ch = dx2-dx1, dy2-dy1
    crop = lg[sy1:sy1+ch, sx1:sx1+cw]
    a = crop[..., 3:4].astype(np.float32) / 255.0
    bgr = crop[..., :3].astype(np.float32)
    roi = frame[dy1:dy2, dx1:dx2].astype(np.float32)
    frame[dy1:dy2, dx1:dx2] = (a*bgr + (1.0-a)*roi).astype(np.uint8)

# ---- Status overlay (small white text, JetBrains-style) ----------------
cpu_c = npu_c = gpu_c = load = None
def draw_status(frame, fps, lines_extra=()):
    global cpu_c, npu_c, gpu_c, load
    cpu_c, npu_c, gpu_c = read_thermals(); load = read_loadavg()
    tag = "MODEL @ NPU" if using_npu else ("MODEL @ CPU" if interp else APP_NAME)
    lines = [f"{tag}   {fps:5.1f} fps", *lines_extra]
    bits = []
    if cpu_c is not None: bits.append(f"CPU {cpu_c:4.1f}C")
    if npu_c is not None: bits.append(f"NPU {npu_c:4.1f}C")
    if gpu_c is not None: bits.append(f"GPU {gpu_c:4.1f}C")
    if load is not None:  bits.append(f"load {load:.2f}")
    if bits: lines.append("   ".join(bits))
    font = cv2.FONT_HERSHEY_SIMPLEX; sc = 0.48; th = 1
    x0, y0 = 18, 30; lh = 20
    for i, ln in enumerate(lines):
        y = y0 + i*lh
        cv2.putText(frame, ln, (x0+1, y+1), font, sc, (0,0,0), th+1, cv2.LINE_AA)
        cv2.putText(frame, ln, (x0,   y),   font, sc, (255,255,255), th, cv2.LINE_AA)

# ---- THE ONE FUNCTION TO IMPLEMENT -------------------------------------
def process_frame(frame):
    """Mutate `frame` in place. Run your inference here, draw whatever.
    `frame` is BGR uint8, shape (H, W, 3).
    Globals available: interp, inp, outs, using_npu, logo, draw_status."""
    # === EXAMPLE: just pass the frame through ============================
    return frame

# ---- gstreamer pipelines (camera in, wayland out) ----------------------
GST_IN = (f"v4l2src device={CAM} ! "
          f"image/jpeg,width={W},height={H},framerate=30/1 ! "
          f"jpegdec ! videoconvert ! video/x-raw,format=BGR ! "
          f"appsink drop=1 max-buffers=1 sync=false")
GST_OUT = (f"appsrc ! video/x-raw,format=BGR,width={W},height={H},framerate=30/1 ! "
           f"videoconvert ! waylandsink fullscreen={'true' if FULLSCREEN else 'false'} sync=false")

cap = cv2.VideoCapture(GST_IN, cv2.CAP_GSTREAMER)
if not cap.isOpened(): sys.exit("camera open failed")
out = cv2.VideoWriter(GST_OUT, cv2.CAP_GSTREAMER, 0, 30.0, (W, H), True)
if not out.isOpened(): sys.exit("wayland output open failed")
print(f"[app] pipelines open; npu={using_npu}", flush=True)

t0 = time.time(); fcount = 0; fps_recent = 0.0; t_last = t0
while True:
    ok, frame = cap.read()
    if not ok: time.sleep(0.01); continue
    process_frame(frame)
    # Built-in status + logo overlays
    now = time.time(); fcount += 1
    if now - t_last > 0.5:
        fps_recent = fcount / (now - t0); t_last = now
    draw_status(frame, fps_recent)
    if logo is not None:
        fh, fw = frame.shape[:2]
        alpha_blit(frame, logo, fw - logo.shape[1] - 22, fh - logo.shape[0] - 22)
    out.write(frame)
    if fcount % 4 == 0:
        try: cv2.imwrite(f"/feeds/{os.environ.get('APP_ID','app')}.jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        except Exception: pass
