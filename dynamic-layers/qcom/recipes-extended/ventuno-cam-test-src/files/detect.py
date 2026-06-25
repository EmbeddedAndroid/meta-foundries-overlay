#!/usr/bin/env python3
"""Deal With It — dual-model NPU pipeline on QCS8275 / Hexagon V75 HTP.

Pipeline (every model on the NPU, enforced):
  - FaceDet-Lite (480x640 gray, uint8)  -> faces + eye landmarks   ~2 ms
  - YOLOv8-det   (640x640 RGB,  uint8)  -> objects                 ~7 ms
Pixel sunglasses drop onto every face (position/scale/rotation from the
eye landmarks, EMA-smoothed tracks). CPU fallback is refused: if the HTP
delegate cannot load the process exits nonzero so docker retries.
"""
import os, sys, time, glob, math, signal, threading, queue
import numpy as np
import cv2

# ── Config ──────────────────────────────────────────────────────────────
YOLO_MODEL = os.environ.get("MODEL",      "/models/yolov8_det.tflite")
FACE_MODEL = os.environ.get("FACE_MODEL", "/models/face_det_lite.tflite")
LABELS     = os.environ.get("LABELS",     "/models/coco_labels.txt")
CAM        = os.environ.get("CAM_DEVICE", "/dev/video2")
W          = int(os.environ.get("WIDTH",  "1280"))
H          = int(os.environ.get("HEIGHT", "720"))
QNN_LIB    = os.environ.get("QNN_DELEGATE_LIB", "/opt/qnn/libQnnTFLiteDelegate.so")
BACKEND    = os.environ.get("QNN_BACKEND", "htp")
NPU_REQUIRED = os.environ.get("NPU_REQUIRED", "1").lower() in ("1", "true", "yes")
LOGO_PATH  = os.environ.get("LOGO_PATH",  "/assets/dragonwing.png")
SG_PATH    = os.environ.get("SUNGLASSES_PATH", "/assets/sunglasses.png")
FULLSCRN   = os.environ.get("FULLSCREEN", "false").lower() in ("1", "true", "yes")
FACE_THR   = float(os.environ.get("FACE_THRESH", "0.45"))
OBJ_THR    = float(os.environ.get("OBJ_THRESH",  "0.55"))
BANNER_T   = os.environ.get("BANNER_TEXT", "DEAL WITH IT")
FEED_PATH  = "/feeds/" + os.environ.get("APP_ID", "cam-detect") + ".jpg"
DROP_FRAMES = int(os.environ.get("DROP_FRAMES", "22"))   # glasses descent time
TAG_FRAMES  = int(os.environ.get("TAG_FRAMES",  "45"))   # caption hold time

def read_soc():
    try:
        return open("/sys/devices/soc0/machine").read().strip()
    except Exception:
        return os.environ.get("SOC", "QCS8275")

SOC      = read_soc()
NPU_NAME = os.environ.get("NPU",           "Hexagon V75 HTP")
QAIRT_V  = os.environ.get("QAIRT_VERSION", "2.43.0")

RUNNING = True
def _sigterm(_s, _f):
    global RUNNING
    RUNNING = False
signal.signal(signal.SIGTERM, _sigterm)
signal.signal(signal.SIGINT, _sigterm)

# ── TFLite on HTP — NPU mandatory ───────────────────────────────────────
try:
    from ai_edge_litert.interpreter import Interpreter, load_delegate
except ImportError:
    from tflite_runtime.interpreter import Interpreter, load_delegate

def load_on_npu(path, tag):
    if not os.path.exists(path):
        print(f"[detect] FATAL: model missing: {path}", flush=True)
        sys.exit(4)
    last = None
    for attempt in range(1, 6):
        try:
            d = load_delegate(QNN_LIB, options={"backend_type": BACKEND, **({"cache_dir": os.environ["QNN_CACHE_DIR"]} if os.environ.get("QNN_CACHE_DIR") else {})})
            it = Interpreter(model_path=path, experimental_delegates=[d])
            it.allocate_tensors()
            print(f"[detect] {tag}: on NPU ({BACKEND}, attempt {attempt})", flush=True)
            return it
        except Exception as e:
            last = e
            print(f"[detect] WARN {tag}: QNN attempt {attempt}/5 failed: {e!r}", flush=True)
            time.sleep(3)
    if NPU_REQUIRED:
        print(f"[detect] FATAL: NPU required but delegate failed: {last!r}", flush=True)
        sys.exit(3)
    it = Interpreter(model_path=path)
    it.allocate_tensors()
    return it

yolo = load_on_npu(YOLO_MODEL, "yolov8")
face = load_on_npu(FACE_MODEL, "facedet")

with open(LABELS) as f:
    labels = [ln.strip() for ln in f if ln.strip()]

y_in   = yolo.get_input_details()[0]
Y_H, Y_W = int(y_in["shape"][1]), int(y_in["shape"][2])
y_boxes = y_scores = y_classes = None
for o in yolo.get_output_details():
    if int(o["shape"][-1]) == 4 and len(o["shape"]) == 3:
        y_boxes = o
    elif o["quantization"][0] == 0.0:
        y_classes = o
    else:
        y_scores = o

f_in   = face.get_input_details()[0]
F_H, F_W = int(f_in["shape"][1]), int(f_in["shape"][2])
f_hm = f_box = f_lmk = None
for o in face.get_output_details():
    c = int(o["shape"][-1])
    if   c == 1:  f_hm  = o
    elif c == 4:  f_box = o
    elif c == 10: f_lmk = o
if None in (y_boxes, y_scores, y_classes, f_hm, f_box, f_lmk):
    print("[detect] FATAL: unexpected model output layout", flush=True)
    sys.exit(4)

def dequant(detail, q):
    scale, zp = detail["quantization"]
    if scale == 0.0:
        return q.astype(np.float32)
    return (q.astype(np.float32) - zp) * scale

SCALE   = W / float(Y_W)
LB_H    = int(H / SCALE)
yolo_buf = np.zeros((Y_H, Y_W, 3), dtype=np.uint8)
face_buf = np.zeros((F_H, F_W),    dtype=np.uint8)
DIL_K = np.ones((3, 3), np.uint8)

def iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    ua = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / ua if ua > 0 else 0.0

STAGE = {}
def stamp(key, t_start):
    now = time.perf_counter()
    ms = (now - t_start) * 1000.0
    STAGE[key] = 0.9 * STAGE.get(key, ms) + 0.1 * ms
    return now

def npu_infer(frame):
    """Both models on the HTP.
    faces:   [x1,y1,x2,y2,score,angle, lex,ley,rex,rey]  frame coords
    objects: [x1,y1,x2,y2,score,class_id]"""
    tp = time.perf_counter()
    if W == 2 * Y_W and H == 2 * LB_H:
        small = np.ascontiguousarray(frame[::2, ::2])
    else:
        small = cv2.resize(frame, (Y_W, LB_H), interpolation=cv2.INTER_LINEAR)
    yolo_buf[:LB_H] = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
    face_buf[:LB_H] = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    stamp("pre", tp)

    t0 = time.perf_counter()
    yolo.set_tensor(y_in["index"], yolo_buf[None, ...])
    yolo.invoke()
    boxes  = dequant(y_boxes,  yolo.get_tensor(y_boxes["index"]))[0]
    scores = dequant(y_scores, yolo.get_tensor(y_scores["index"]))[0]
    clss   = yolo.get_tensor(y_classes["index"])[0]
    t1 = time.perf_counter()
    face.set_tensor(f_in["index"], face_buf[None, ..., None])
    face.invoke()
    hm  = dequant(f_hm,  face.get_tensor(f_hm["index"]))[0, :, :, 0]
    fbx = dequant(f_box, face.get_tensor(f_box["index"]))[0]
    lmk = dequant(f_lmk, face.get_tensor(f_lmk["index"]))[0]
    t2 = time.perf_counter()
    td = t2

    objects = []
    keep = scores > OBJ_THR
    if keep.any():
        kb, ks, kc = boxes[keep], scores[keep], clss[keep]
        idx = cv2.dnn.NMSBoxes(
            [(float(b[0]), float(b[1]), float(b[2] - b[0]), float(b[3] - b[1])) for b in kb],
            [float(s) for s in ks], OBJ_THR, 0.45)
        for i in np.array(idx).flatten()[:12]:
            x1, y1, x2, y2 = kb[i] * SCALE
            objects.append((max(0, x1), max(0, y1), min(W - 1, x2), min(H - 1, y2),
                            float(ks[i]), int(kc[i])))

    faces_out = []
    prob = 1.0 / (1.0 + np.exp(-hm))
    peaks = (prob == cv2.dilate(prob, DIL_K)) & (prob > FACE_THR)
    for cy, cx in np.argwhere(peaks)[:8]:
        x, y, r, b = fbx[cy, cx]
        x1 = (cx - x) * 8 * SCALE; y1 = (cy - y) * 8 * SCALE
        x2 = (cx + r) * 8 * SCALE; y2 = (cy + b) * 8 * SCALE
        if x2 - x1 < 24 or y2 - y1 < 24:
            continue
        lx = (lmk[cy, cx, :5] + cx) * 8 * SCALE
        ly = (lmk[cy, cx, 5:] + cy) * 8 * SCALE
        # landmarks 0,1 are the eyes; order left-to-right
        if lx[0] <= lx[1]:
            lex, ley, rex, rey = lx[0], ly[0], lx[1], ly[1]
        else:
            lex, ley, rex, rey = lx[1], ly[1], lx[0], ly[0]
        ang = math.degrees(math.atan2(rey - ley, rex - lex))
        ang = max(-30.0, min(30.0, ang))
        faces_out.append((max(0, x1), max(0, y1), min(W - 1, x2), min(H - 1, y2),
                          float(prob[cy, cx]), ang, lex, ley, rex, rey))
    # uint8 heatmap plateaus tie at the quant ceiling — NMS the duplicates
    faces_out.sort(key=lambda d: -d[4])
    kept = []
    for d in faces_out:
        if all(iou(d, k) < 0.4 for k in kept):
            kept.append(d)
    stamp("decode", td)
    return kept, objects, (t1 - t0) * 1000.0, (t2 - t1) * 1000.0

# ── Warmup ──────────────────────────────────────────────────────────────
_warm = np.zeros((H, W, 3), np.uint8)
npu_infer(_warm)
_t = [npu_infer(_warm)[2:] for _ in range(5)]
print(f"[detect] warmup: yolo={np.mean([a for a,_ in _t]):.1f}ms "
      f"face={np.mean([b for _,b in _t]):.1f}ms on {NPU_NAME} ({SOC})", flush=True)

# ── Face tracks (EMA + hold + drop animation state) ─────────────────────
class Track:
    __slots__ = ("box", "angle", "eyes", "misses", "hits", "age", "score")
    def __init__(self, d):
        self.box = np.array(d[:4], np.float32)
        self.angle = d[5]
        self.eyes = np.array(d[6:10], np.float32)
        self.misses = 0
        self.hits = 1
        self.age = 0
        self.score = d[4]

tracks = []
def update_tracks(dets):
    used = set()
    for t in tracks:
        best, best_i = 0.25, -1
        for i, d in enumerate(dets):
            if i in used:
                continue
            v = iou(t.box, d)
            if v > best:
                best, best_i = v, i
        if best_i >= 0:
            d = dets[best_i]; used.add(best_i)
            t.box = 0.65 * t.box + 0.35 * np.array(d[:4], np.float32)
            t.angle = 0.7 * t.angle + 0.3 * d[5]
            t.eyes = 0.6 * t.eyes + 0.4 * np.array(d[6:10], np.float32)
            t.score = d[4]
            t.misses = 0
            t.hits += 1
        else:
            t.misses += 1
        t.age += 1
    tracks[:] = [t for t in tracks if t.misses <= 10]
    for i, d in enumerate(dets):
        if i not in used:
            tracks.append(Track(d))

# ── Assets ──────────────────────────────────────────────────────────────
def load_bgra(path):
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED) if os.path.exists(path) else None
    if img is None:
        return None
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
    elif img.shape[2] == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    return img

def premul(bgra):
    a = bgra[..., 3:4].astype(np.float32) / 255.0
    return bgra[..., :3].astype(np.float32) * a, 1.0 - a

def blit_premul(frame, pm, x0, y0):
    fg, inv_a = pm
    fh, fw = frame.shape[:2]; lh, lw = fg.shape[:2]
    sx1, sy1 = max(0, -x0), max(0, -y0)
    dx1, dy1 = max(0, x0), max(0, y0)
    dx2, dy2 = min(fw, x0 + lw), min(fh, y0 + lh)
    if dx2 <= dx1 or dy2 <= dy1:
        return
    cw, ch = dx2 - dx1, dy2 - dy1
    roi = frame[dy1:dy2, dx1:dx2].astype(np.float32)
    np.copyto(frame[dy1:dy2, dx1:dx2],
              (fg[sy1:sy1+ch, sx1:sx1+cw] + inv_a[sy1:sy1+ch, sx1:sx1+cw] * roi)
              .astype(np.uint8))

sg_src = load_bgra(SG_PATH)
if sg_src is None:
    print(f"[detect] WARN sunglasses not found at {SG_PATH}", flush=True)
logo = load_bgra(LOGO_PATH)
if logo is not None:
    tw = max(120, int(W * 0.20))
    if logo.shape[1] > tw:
        logo = cv2.resize(logo, (tw, max(1, int(logo.shape[0] * tw / logo.shape[1]))),
                          interpolation=cv2.INTER_AREA)
logo_pm = premul(logo) if logo is not None else None

_sg_cache = {}
def glasses_scaled(width_px, angle_deg):
    if sg_src is None:
        return None
    wb = max(60, int(round(width_px / 24.0)) * 24)
    ab = int(round(angle_deg / 6.0)) * 6
    key = (wb, ab)
    pm = _sg_cache.get(key)
    if pm is None:
        sh, sw = sg_src.shape[:2]
        hh = max(1, int(wb * sh / sw))
        img = cv2.resize(sg_src, (wb, hh), interpolation=cv2.INTER_NEAREST)
        if ab:
            diag = int(math.hypot(wb, hh)) + 2
            canvas = np.zeros((diag, diag, 4), np.uint8)
            ox, oy = (diag - wb) // 2, (diag - hh) // 2
            canvas[oy:oy+hh, ox:ox+wb] = img
            M = cv2.getRotationMatrix2D((diag / 2, diag / 2), -ab, 1.0)
            img = cv2.warpAffine(canvas, M, (diag, diag), flags=cv2.INTER_NEAREST)
        pm = premul(img)
        if len(_sg_cache) > 48:
            _sg_cache.clear()
        _sg_cache[key] = pm
    return pm

def place_glasses(frame, t):
    lex, ley, rex, rey = t.eyes
    d = math.hypot(rex - lex, rey - ley)
    if d < 16:
        return
    pm = glasses_scaled(d * 2.6, t.angle)
    if pm is None:
        return
    oh, ow = pm[0].shape[:2]
    mx, my = (lex + rex) / 2.0, (ley + rey) / 2.0
    # the meme: glasses descend from the top, then lock on
    p = min(1.0, t.age / float(DROP_FRAMES))
    ease = 1.0 - (1.0 - p) ** 2
    y_cur = (-oh) + (my - (-oh)) * ease
    blit_premul(frame, pm, int(mx - ow / 2), int(y_cur - oh / 2))
    if p >= 1.0 and t.age <= DROP_FRAMES + TAG_FRAMES:
        txt = "DEAL WITH IT"
        (tw_, th_), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_DUPLEX, 0.9, 2)
        bx = int(mx - tw_ / 2)
        by = int(min(H - 12, t.box[3] + th_ + 14))
        cv2.putText(frame, txt, (bx + 2, by + 2), cv2.FONT_HERSHEY_DUPLEX, 0.9,
                    (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(frame, txt, (bx, by), cv2.FONT_HERSHEY_DUPLEX, 0.9,
                    (250, 250, 250), 2, cv2.LINE_AA)

# ── HUD: glass title + gauge cluster ────────────────────────────────────
ACCENT  = (0, 40, 230)
INK     = (242, 242, 240)
MUTE    = (158, 158, 152)
GLASS   = (16, 14, 12)

def rounded_rect(img, x0, y0, x1, y1, r, color):
    cv2.rectangle(img, (x0 + r, y0), (x1 - r, y1), color, -1)
    cv2.rectangle(img, (x0, y0 + r), (x1, y1 - r), color, -1)
    for cx, cy in ((x0+r, y0+r), (x1-r, y0+r), (x0+r, y1-r), (x1-r, y1-r)):
        cv2.circle(img, (cx, cy), r, color, -1, cv2.LINE_AA)

def text_spaced(img, text, x, y, font, scale, color, thick, gap):
    for ch in text:
        cv2.putText(img, ch, (x, y), font, scale, color, thick, cv2.LINE_AA)
        x += cv2.getTextSize(ch, font, scale, thick)[0][0] + gap
    return x - gap

def spaced_width(text, font, scale, thick, gap):
    return sum(cv2.getTextSize(c, font, scale, thick)[0][0] + gap for c in text) - gap

def render_title():
    font = cv2.FONT_HERSHEY_DUPLEX
    t_sc, t_th, t_gap = 1.15, 2, 14
    title = BANNER_T.upper()
    sub = "QUALCOMM DRAGONWING  |  ON-DEVICE AI"
    s_sc, s_th, s_gap = 0.38, 1, 3
    tw = spaced_width(title, font, t_sc, t_th, t_gap)
    sw = spaced_width(sub, cv2.FONT_HERSHEY_SIMPLEX, s_sc, s_th, s_gap)
    w = max(tw, sw) + 96
    h = 92
    img = np.zeros((h, w, 4), np.uint8)
    img[..., :3] = GLASS
    alpha = np.full((h, w), 170, np.uint8)
    fade = np.linspace(0, 1, 72, dtype=np.float32)
    alpha[:, :72] = (alpha[:, :72] * fade).astype(np.uint8)
    alpha[:, -72:] = (alpha[:, -72:] * fade[::-1]).astype(np.uint8)
    img[..., 3] = alpha
    ty = 46
    tx = (w - tw) // 2
    text_spaced(img, title, tx, ty, font, t_sc, (*INK, 255), t_th, t_gap)
    ry = ty + 14
    cv2.line(img, (tx, ry), (tx + tw, ry), (90, 90, 88, 255), 1, cv2.LINE_AA)
    seg = max(48, tw // 5)
    cv2.line(img, ((w - seg)//2, ry), ((w + seg)//2, ry), (*ACCENT, 255), 2, cv2.LINE_AA)
    sx = (w - sw) // 2
    text_spaced(img, sub, sx, ry + 22, cv2.FONT_HERSHEY_SIMPLEX, s_sc, (*MUTE, 255), s_th, s_gap)
    return premul(img), w, h

CL_W, CL_H = 416, 198
G_X0, G_X1 = 178, 396
BAR_YO, BAR_FD = 56, 100
BAR_H = 10
TMP_Y = 142
BOT_Y = 180

def render_cluster():
    img = np.zeros((CL_H, CL_W, 4), np.uint8)
    img[..., :3] = GLASS
    mask = np.zeros((CL_H, CL_W, 3), np.uint8)
    rounded_rect(mask, 0, 0, CL_W - 1, CL_H - 1, 14, (255, 255, 255))
    img[..., 3] = (mask[..., 0].astype(np.uint16) * 178 // 255).astype(np.uint8)
    cv2.line(img, (20, 16), (CL_W - 20, 16), (60, 60, 58, 255), 1, cv2.LINE_AA)
    cv2.line(img, (20, 16), (96, 16), (*ACCENT, 255), 2, cv2.LINE_AA)
    f = cv2.FONT_HERSHEY_SIMPLEX
    text_spaced(img, "LIVE TELEMETRY", 20, 36, f, 0.38, (*MUTE, 255), 1, 2)
    text_spaced(img, "HEXAGON V75 NPU", G_X0, 36, f, 0.38, (*ACCENT, 255), 1, 2)
    cv2.putText(img, "FPS", (52, 128), f, 0.45, (*MUTE, 255), 1, cv2.LINE_AA)
    for label, ybar in (("YOLOV8-DET", BAR_YO), ("FACEDET-LITE", BAR_FD)):
        cv2.putText(img, label, (G_X0, ybar - 8), f, 0.40, (*INK, 255), 1, cv2.LINE_AA)
        rounded_rect(img, G_X0, ybar, G_X1, ybar + BAR_H, 4, (42, 42, 40, 255))
    spec = f"{SOC}  |  QAIRT {QAIRT_V}  |  30FPS CAM  |  {W}x{H}"
    cv2.putText(img, spec, (20, BOT_Y + 6), f, 0.40, (*MUTE, 255), 1, cv2.LINE_AA)
    return premul(img)

title_pm, title_w, title_h = render_title()
cluster_pm = render_cluster()
CL_X, CL_Y = 22, H - CL_H - 22
BUDGET_MS = 33.3

def gauge_fill(frame, x0, y0, frac, ms_txt):
    frac = max(0.02, min(1.0, frac))
    x1 = int(x0 + (G_X1 - G_X0) * frac)
    color = (96, 200, 80) if frac < 0.5 else ((60, 190, 235) if frac < 0.8 else ACCENT)
    cv2.rectangle(frame, (CL_X + x0, CL_Y + y0 + 2), (CL_X + x1, CL_Y + y0 + BAR_H - 2),
                  color, -1)
    cv2.putText(frame, ms_txt, (CL_X + G_X1 - 52, CL_Y + y0 - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, MUTE, 1, cv2.LINE_AA)

def temp_color(v):
    if v is None: return MUTE
    return (96, 200, 80) if v < 60 else ((60, 190, 235) if v < 80 else ACCENT)

def draw_cluster(frame, fps, y_ms, f_ms, temps, nfaces):
    blit_premul(frame, cluster_pm, CL_X, CL_Y)
    txt = f"{fps:.0f}"
    (tw_, _), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_DUPLEX, 1.9, 2)
    cv2.putText(frame, txt, (CL_X + 78 - tw_ // 2, CL_Y + 108),
                cv2.FONT_HERSHEY_DUPLEX, 1.9, INK, 2, cv2.LINE_AA)
    gauge_fill(frame, G_X0, BAR_YO, y_ms / BUDGET_MS, f"{y_ms:4.1f}ms")
    gauge_fill(frame, G_X0, BAR_FD, f_ms / BUDGET_MS, f"{f_ms:4.1f}ms")
    x = CL_X + 20
    for name, v in temps:
        c = temp_color(v)
        cv2.circle(frame, (x, CL_Y + TMP_Y), 4, c, -1, cv2.LINE_AA)
        s = f"{name} {v:.0f}C" if v is not None else f"{name} --"
        cv2.putText(frame, s, (x + 10, CL_Y + TMP_Y + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, INK, 1, cv2.LINE_AA)
        x += 10 + cv2.getTextSize(s, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)[0][0] + 22
    s = f"FACES {nfaces}"
    cv2.putText(frame, s, (CL_X + CL_W - 20 - cv2.getTextSize(s, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)[0][0],
                CL_Y + TMP_Y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                ACCENT if nfaces else MUTE, 1, cv2.LINE_AA)

# ── Thermals ────────────────────────────────────────────────────────────
def read_thermals():
    cpu_t, npu_t, gpu_t = [], None, None
    for z in glob.glob("/sys/class/thermal/thermal_zone*"):
        try:
            t = open(z + "/type").read().strip()
            v = int(open(z + "/temp").read().strip()) / 1000.0
        except Exception:
            continue
        if v <= 0:
            continue
        if t.startswith("cpu"):
            cpu_t.append(v)
        elif t.startswith(("nsp", "nspss")):
            npu_t = v if npu_t is None else max(npu_t, v)
        elif t.startswith("gpuss"):
            gpu_t = v if gpu_t is None else max(gpu_t, v)
    return (max(cpu_t) if cpu_t else None), npu_t, gpu_t

def read_loadavg():
    try:    return float(open("/proc/loadavg").read().split()[0])
    except: return None

# ── Async JPEG feed ─────────────────────────────────────────────────────
feed_q = queue.Queue(maxsize=1)
def feed_worker():
    tmp = FEED_PATH[:-4] + ".tmp.jpg"
    warned = False
    while True:
        frame = feed_q.get()
        if frame is None:
            return
        try:
            cv2.imwrite(tmp, frame, [cv2.IMWRITE_JPEG_QUALITY, 72])
            os.replace(tmp, FEED_PATH)
        except Exception as e:
            if not warned:
                warned = True
                print(f"[detect] WARN feed write failed: {e!r}", flush=True)
threading.Thread(target=feed_worker, daemon=True).start()

# ── Camera + display ────────────────────────────────────────────────────
def gst_in(dev):
    return (f"v4l2src device={dev} "
            f"extra-controls=\"c,exposure_dynamic_framerate=0\" ! "
            f"image/jpeg,width={W},height={H},framerate=30/1 ! "
            f"jpegdec ! videoconvert n-threads=4 ! video/x-raw,format=BGR ! "
            f"appsink drop=1 max-buffers=1 sync=false")

GST_OUT = (f"appsrc ! video/x-raw,format=BGR,width={W},height={H},framerate=30/1 ! "
           f"queue max-size-buffers=2 leaky=downstream ! videoconvert n-threads=4 ! "
           f"waylandsink fullscreen={'true' if FULLSCRN else 'false'} sync=false")

def open_camera():
    while RUNNING:
        cands = [CAM] + sorted(set(glob.glob("/dev/video[0-9]*")) - {CAM})
        for dev in cands:
            if not os.path.exists(dev):
                continue
            cap = cv2.VideoCapture(gst_in(dev), cv2.CAP_GSTREAMER)
            if cap.isOpened():
                print(f"[detect] camera open: {dev}", flush=True)
                return cap
            cap.release()
        print(f"[detect] no usable camera among {cands}, retrying ...", flush=True)
        time.sleep(2)
    return None

def open_display():
    out = cv2.VideoWriter(GST_OUT, cv2.CAP_GSTREAMER, 0, 30.0, (W, H), True)
    if out.isOpened():
        print("[detect] wayland display open", flush=True)
        return out
    out.release()
    return None

_disp = {"frame": None, "seq": 0}
_disp_cv = threading.Condition()
def display_worker():
    out = open_display()
    if out is None:
        print("[detect] WARN display unavailable, feed-only (will retry)", flush=True)
    seq = 0
    last_retry = time.time()
    while RUNNING:
        with _disp_cv:
            _disp_cv.wait_for(lambda: _disp["seq"] != seq or not RUNNING, timeout=0.5)
            frame, seq = _disp["frame"], _disp["seq"]
        if frame is None:
            continue
        if out is not None:
            if closebtn: closebtn.draw(frame)
            out.write(frame)
        elif time.time() - last_retry > 5.0:
            last_retry = time.time()
            out = open_display()
try:
    import closebtn
    closebtn.start(W, H)
except Exception as _cbe:
    closebtn = None
    print(f'[detect] closebtn unavailable: {_cbe!r}', flush=True)
threading.Thread(target=display_worker, daemon=True).start()

_grab = {"frame": None, "seq": 0}
_grab_cv = threading.Condition()
def grabber():
    cap = open_camera()
    fails = 0
    while RUNNING:
        ok, f = cap.read() if cap is not None else (False, None)
        if not ok:
            fails += 1
            if fails > 90 or cap is None:
                print("[detect] camera stalled — reopening", flush=True)
                if cap is not None:
                    cap.release()
                cap = open_camera()
                fails = 0
            time.sleep(0.01)
            continue
        fails = 0
        with _grab_cv:
            _grab["frame"] = f
            _grab["seq"] += 1
            _grab_cv.notify()
    if cap is not None:
        cap.release()
threading.Thread(target=grabber, daemon=True).start()

def next_frame(last_seq):
    with _grab_cv:
        _grab_cv.wait_for(lambda: _grab["seq"] != last_seq or not RUNNING, timeout=0.5)
        return _grab["frame"], _grab["seq"]

# ── Main loop ────────────────────────────────────────────────────────────
OBJ_COLOR  = (80, 220, 80)
SKIP_CLASS = {0}
frames = 0; fps = 0.0
t_fps = time.time(); n_fps = 0
yolo_ms = face_ms = 0.0
cpu_c = npu_c = gpu_c = load = None
last_feed = 0.0
seq = 0
render_ms = 0.0

while RUNNING:
    frame, seq_new = next_frame(seq)
    if frame is None or seq_new == seq:
        continue
    seq = seq_new
    t_r0 = time.perf_counter()

    dets_f, dets_o, ty, tf = npu_infer(frame)
    yolo_ms = 0.9 * yolo_ms + 0.1 * ty if frames else ty
    face_ms = 0.9 * face_ms + 0.1 * tf if frames else tf
    update_tracks(dets_f)
    t_dr = time.perf_counter()

    # COCO object boxes intentionally not drawn: the overlay effect is the show.

    n_conf = 0
    for t in tracks:
        if t.hits >= 2:
            n_conf += 1
            place_glasses(frame, t)
    t_dr = stamp("draw", t_dr)

    frames += 1; n_fps += 1
    now = time.time()
    if now - t_fps >= 0.5:
        fps = n_fps / (now - t_fps); n_fps = 0; t_fps = now
    if frames % 15 == 1:
        cpu_c, npu_c, gpu_c = read_thermals()
        load = read_loadavg()

    draw_cluster(frame, fps, yolo_ms, face_ms,
                 (("NPU", npu_c), ("CPU", cpu_c), ("GPU", gpu_c)), n_conf)
    blit_premul(frame, title_pm, (W - title_w) // 2, 10)
    if logo_pm is not None:
        blit_premul(frame, logo_pm,
                    W - logo_pm[0].shape[1] - 22, H - logo_pm[0].shape[0] - 22)
    stamp("hud", t_dr)

    with _disp_cv:
        _disp["frame"] = frame
        _disp["seq"] += 1
        _disp_cv.notify()

    if now - last_feed > 0.30:
        last_feed = now
        try:
            feed_q.put_nowait(frame.copy())
        except queue.Full:
            pass

    render_ms = 0.9 * render_ms + 0.1 * ((time.perf_counter() - t_r0) * 1000.0)
    if frames % 120 == 0:
        stages = "  ".join(f"{k}={v:.1f}" for k, v in STAGE.items())
        print(f"[detect] {frames} fr  {fps:.1f} fps  yolo={yolo_ms:.1f}ms "
              f"face={face_ms:.1f}ms  loop={render_ms:.1f}ms  [{stages}]  "
              f"tracks={len(tracks)}", flush=True)

print("[detect] stopped cleanly", flush=True)
