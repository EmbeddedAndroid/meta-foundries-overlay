#!/usr/bin/env python3
"""USB-cam YOLOv8 on NPU + Haar face/eye -> sunglasses PNG overlay."""
import os, sys, time, glob
import numpy as np
import cv2

MODEL    = os.environ.get("MODEL", "/models/yolov8_det.tflite")
LABELS   = os.environ.get("LABELS", "/models/coco_labels.txt")
CAM      = os.environ.get("CAM_DEVICE", "/dev/video2")
W        = int(os.environ.get("WIDTH", "1280"))
H        = int(os.environ.get("HEIGHT", "720"))
QNN_LIB  = os.environ.get("QNN_DELEGATE_LIB", "/opt/qnn/libQnnTFLiteDelegate.so")
BACKEND  = os.environ.get("QNN_BACKEND", "htp")
LOGO_PATH= os.environ.get("LOGO_PATH", "/assets/dragonwing.png")
SUNGLASSES_PATH = os.environ.get("SUNGLASSES_PATH", "/assets/sunglasses.png")
FULLSCRN = os.environ.get("FULLSCREEN", "false").lower() in ("1","true","yes")

# Static metadata for status overlay
SOC      = os.environ.get("SOC", "QCS6490")
NPU      = os.environ.get("NPU", "Hexagon V68 NPU")
QAIRT_V  = os.environ.get("QAIRT_VERSION", "2.36.0.250627")
META_URL = os.environ.get("META_QCOM_URL", "github.com/qualcomm-linux/meta-qcom")
YOCTO    = os.environ.get("YOCTO_DISTRO", "Qualcomm Linux Reference Distro 2.0")
MESA     = os.environ.get("MESA_VERSION", "26.0.5")
BANNER_T = os.environ.get("BANNER_TEXT", "QUALCOMM LINUX MAINLINE")
try:
    KERNEL_V = os.uname().release
except Exception:
    KERNEL_V = "?"

try:
    from ai_edge_litert.interpreter import Interpreter, load_delegate
except ImportError:
    from tflite_runtime.interpreter import Interpreter, load_delegate

with open(LABELS) as f:
    labels = [ln.strip() for ln in f if ln.strip()]

delegates = []
try:
    delegates.append(load_delegate(QNN_LIB, options={"backend_type": BACKEND}))
except Exception as e:
    print(f"[detect] WARN QNN load: {e!r}", flush=True)

try:
    interp = Interpreter(model_path=MODEL, experimental_delegates=delegates)
    using_npu = bool(delegates)
except RuntimeError as e:
    print(f"[detect] WARN delegate apply: {e}", flush=True)
    interp = Interpreter(model_path=MODEL); using_npu = False
interp.allocate_tensors()
inp = interp.get_input_details()[0]
outs = interp.get_output_details()
IN_H, IN_W = int(inp['shape'][1]), int(inp['shape'][2])
IN_DT = inp['dtype']
print(f"[detect] yolov8 on {'NPU' if using_npu else 'CPU'}", flush=True)

# Haar
HAAR = '/usr/share/opencv4/haarcascades/'
face_cas = cv2.CascadeClassifier(HAAR + 'haarcascade_frontalface_default.xml')
eye_cas  = cv2.CascadeClassifier(HAAR + 'haarcascade_eye.xml')
if face_cas.empty() or eye_cas.empty(): sys.exit("haar cascades missing")

# Assets
logo = cv2.imread(LOGO_PATH, cv2.IMREAD_UNCHANGED) if os.path.exists(LOGO_PATH) else None
if logo is not None and logo.shape[2] != 4: logo = None
# Scale logo down so it sits as a corner badge, not a centerpiece.
# Target ~22% of frame width — neatly tucked, still legible.
if logo is not None:
    target_lw = max(120, int(W * 0.22))
    lh0, lw0 = logo.shape[:2]
    if lw0 > target_lw:
        target_lh = max(1, int(lh0 * target_lw / lw0))
        logo = cv2.resize(logo, (target_lw, target_lh), interpolation=cv2.INTER_AREA)
        print(f"[detect] logo resized to {logo.shape}", flush=True)
sg_img = cv2.imread(SUNGLASSES_PATH, cv2.IMREAD_UNCHANGED) if os.path.exists(SUNGLASSES_PATH) else None
if sg_img is not None:
    if sg_img.shape[2] == 3:  # add white->transparent alpha at runtime fallback
        b, g, r = cv2.split(sg_img)
        white = (r > 235) & (g > 235) & (b > 235)
        a = np.where(white, 0, 255).astype(np.uint8)
        sg_img = cv2.merge([b, g, r, a])
    print(f"[detect] sunglasses {sg_img.shape}", flush=True)

def read_thermals():
    cpu_t=[]; npu=None; gpu=None
    for z in glob.glob('/sys/class/thermal/thermal_zone*'):
        try:
            t = open(z+'/type').read().strip()
            v = int(open(z+'/temp').read().strip())/1000.0
        except Exception: continue
        if t.startswith('cpu') and t.endswith('-thermal') and 'ss' not in t:
            cpu_t.append(v)
        elif t.startswith('nspss'):
            npu = v if npu is None else max(npu, v)
        elif t.startswith('gpuss'):
            gpu = v if gpu is None else max(gpu, v)
    return (max(cpu_t) if cpu_t else None), npu, gpu

def read_loadavg():
    try: return float(open('/proc/loadavg').read().split()[0])
    except Exception: return None

def overlay_alpha(frame, lg, x0, y0):
    """Alpha-blend BGRA `lg` into frame at top-left (x0, y0), cropping at edges."""
    fh, fw = frame.shape[:2]; lh, lw = lg.shape[:2]
    src_x1 = max(0, -x0); src_y1 = max(0, -y0)
    dst_x1 = max(0, x0);  dst_y1 = max(0, y0)
    dst_x2 = min(fw, x0 + lw); dst_y2 = min(fh, y0 + lh)
    w_c = dst_x2 - dst_x1; h_c = dst_y2 - dst_y1
    if w_c <= 0 or h_c <= 0: return
    crop = lg[src_y1:src_y1+h_c, src_x1:src_x1+w_c]
    bgr = crop[..., :3].astype(np.float32)
    a   = (crop[..., 3:4].astype(np.float32)) / 255.0
    roi = frame[dst_y1:dst_y2, dst_x1:dst_x2].astype(np.float32)
    frame[dst_y1:dst_y2, dst_x1:dst_x2] = (a*bgr + (1.0-a)*roi).astype(np.uint8)


def draw_metal_banner(frame, text):
    """Big spiky banner across the top, Metallica-ish."""
    h, w = frame.shape[:2]
    font = cv2.FONT_HERSHEY_TRIPLEX
    scale = 1.5
    thick = 3
    (tw, th), _ = cv2.getTextSize(text, font, scale, thick)
    cx = w // 2
    pad_x = 36; pad_y = 16
    by0 = 0
    by1 = th + pad_y * 2
    bx0 = cx - tw // 2 - pad_x
    bx1 = cx + tw // 2 + pad_x
    wing_w = int((by1 - by0) * 2.2)
    left_wing  = np.array([[bx0 - wing_w, (by0 + by1) // 2], [bx0, by0], [bx0, by1]], np.int32)
    right_wing = np.array([[bx1 + wing_w, (by0 + by1) // 2], [bx1, by0], [bx1, by1]], np.int32)

    # translucent black banner + wings
    overlay = frame.copy()
    cv2.rectangle(overlay, (bx0, by0), (bx1, by1), (0,0,0), -1)
    cv2.fillPoly(overlay, [left_wing, right_wing], (0,0,0))
    cv2.addWeighted(overlay, 0.78, frame, 0.22, 0, dst=frame)

    # Chrome edges
    cv2.polylines(frame, [left_wing, right_wing], True, (235,235,235), 1, cv2.LINE_AA)
    cv2.rectangle(frame, (bx0, by0), (bx1, by1-1), (235,235,235), 1, cv2.LINE_AA)
    # Inner spike highlights
    cv2.line(frame, (bx0 - wing_w, (by0+by1)//2), (bx0 - wing_w//3, (by0+by1)//2 - 3),
             (180,180,180), 1, cv2.LINE_AA)
    cv2.line(frame, (bx1 + wing_w, (by0+by1)//2), (bx1 + wing_w//3, (by0+by1)//2 - 3),
             (180,180,180), 1, cv2.LINE_AA)

    # Shadow + white text
    tx = cx - tw // 2
    ty = by0 + pad_y + th
    cv2.putText(frame, text, (tx+2, ty+2), font, scale, (0,0,0), thick+1, cv2.LINE_AA)
    cv2.putText(frame, text, (tx,   ty),   font, scale, (250,250,250), thick, cv2.LINE_AA)

def place_sunglasses(frame, eye_list):
    if sg_img is None or len(eye_list) < 2: return
    eyes = sorted(eye_list, key=lambda e: -e[2])[:2]
    eyes = sorted(eyes, key=lambda e: e[0])  # left to right
    (x1, y1, _), (x2, y2, _) = eyes
    dx, dy = x2 - x1, y2 - y1
    d = (dx*dx + dy*dy) ** 0.5
    if d < 20: return
    angle_deg = -np.degrees(np.arctan2(dy, dx))
    # Sunglasses width ~= 2.6x inter-eye distance
    target_w = int(d * 2.6)
    sh, sw = sg_img.shape[:2]
    target_h = max(1, int(sh * target_w / sw))
    sg = cv2.resize(sg_img, (target_w, target_h), interpolation=cv2.INTER_AREA)
    M = cv2.getRotationMatrix2D((target_w/2, target_h/2), angle_deg, 1.0)
    sg_rot = cv2.warpAffine(sg, M, (target_w, target_h),
                            flags=cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0,0))
    mid_x, mid_y = (x1 + x2) // 2, (y1 + y2) // 2
    overlay_alpha(frame, sg_rot, mid_x - target_w//2, mid_y - target_h//2)

# GST pipelines
gst_in = (f"v4l2src device={CAM} ! "
          f"image/jpeg,width={W},height={H},framerate=30/1 ! "
          f"jpegdec ! videoconvert ! video/x-raw,format=BGR ! "
          f"appsink drop=1 max-buffers=1 sync=false")
gst_out = (f"appsrc ! video/x-raw,format=BGR,width={W},height={H},framerate=30/1 ! "
           f"videoconvert ! waylandsink fullscreen={'true' if FULLSCRN else 'false'} sync=false")
cap = cv2.VideoCapture(gst_in, cv2.CAP_GSTREAMER)
out = cv2.VideoWriter(gst_out, cv2.CAP_GSTREAMER, 0, 30.0, (W, H), True)
print(f"[detect] pipelines open; using_npu={using_npu}", flush=True)

t0 = time.time(); frames = 0
fps_recent = 0.0; t_last = t0
cpu_c, npu_c, gpu_c, load = None, None, None, None
while True:
    ok, frame = cap.read()
    if not ok:
        time.sleep(0.01); continue
    # YOLOv8 NPU inference (kept active to demonstrate NPU usage)
    img = cv2.resize(frame, (IN_W, IN_H))
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    x = img.astype(IN_DT) if IN_DT == np.uint8 else (img.astype(np.float32)/255.0)
    interp.set_tensor(inp['index'], np.expand_dims(x, 0))
    interp.invoke()
    _ = [interp.get_tensor(o['index']) for o in outs]

    # Face + eyes
    gray = cv2.equalizeHist(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    faces = face_cas.detectMultiScale(gray, 1.2, 5, minSize=(80, 80))
    for (fx, fy, fw, fh) in faces:
        roi = gray[fy:fy+fh, fx:fx+fw]
        eyes_raw = eye_cas.detectMultiScale(roi, 1.1, 5,
                                            minSize=(fw//8, fh//8))
        eye_list = []
        for (ex, ey, ew, eh) in eyes_raw:
            if ey + eh/2 > fh * 0.6: continue
            cx, cy = fx + ex + ew//2, fy + ey + eh//2
            r = max(ew, eh) // 2
            eye_list.append((cx, cy, r))
        place_sunglasses(frame, eye_list)

    # Status overlay
    now = time.time(); frames += 1
    if now - t_last > 0.5:
        fps_recent = frames / (now - t0)
        t_last = now
    if frames % 15 == 0 or cpu_c is None:
        cpu_c, npu_c, gpu_c = read_thermals()
        load = read_loadavg()

    tag = f"YOLOv8 @ {'NPU' if using_npu else 'CPU'}"
    lines = []
    lines.append(f"{tag}   {fps_recent:.1f} fps")
    lines.append(f"SoC: {SOC}   |   {NPU}")
    lines.append(f"QAIRT {QAIRT_V}   |   kernel {KERNEL_V}")
    lines.append(f"Yocto: {YOCTO}")
    lines.append(f"Mesa/Freedreno {MESA}")
    therm_bits = []
    if cpu_c is not None: therm_bits.append(f"CPU {cpu_c:4.1f}C")
    if npu_c is not None: therm_bits.append(f"NPU {npu_c:4.1f}C")
    if gpu_c is not None: therm_bits.append(f"GPU {gpu_c:4.1f}C")
    if load is not None: therm_bits.append(f"load {load:.2f}")
    if therm_bits: lines.append("   ".join(therm_bits))
    lines.append(META_URL)

    font = cv2.FONT_HERSHEY_SIMPLEX
    fscale = 0.48; fth = 1
    x0, y0_base = 18, 100; line_h = 20
    for i, ln in enumerate(lines):
        y = y0_base + i * line_h
        cv2.putText(frame, ln, (x0+1, y+1), font, fscale, (0,0,0), fth+1, cv2.LINE_AA)
        cv2.putText(frame, ln, (x0,   y),   font, fscale, (255,255,255), fth, cv2.LINE_AA)

    draw_metal_banner(frame, BANNER_T)
    overlay_logo_pos = (frame.shape[1] - (logo.shape[1] if logo is not None else 0) - 22,
                       frame.shape[0] - (logo.shape[0] if logo is not None else 0) - 22)
    if logo is not None:
        overlay_alpha(frame, logo, *overlay_logo_pos)

    if frames % 60 == 0:
        print(f"[detect] {frames} fr {fps_recent:.1f} fps faces_this={len(faces)}", flush=True)
    out.write(frame)
    if frames % 4 == 0:
        try: cv2.imwrite(f"/feeds/{os.environ.get('APP_ID','app')}.jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        except Exception: pass
