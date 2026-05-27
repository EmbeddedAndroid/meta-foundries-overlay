"""Take the real Dragonwing logo and resize for overlay."""
import cv2, numpy as np
SRC = "/raw-assets/dragonwing-raw.png"
DST = "/assets/dragonwing.png"
TARGET_W = 280

img = cv2.imread(SRC, cv2.IMREAD_UNCHANGED)
if img is None:
    raise SystemExit(f"could not read {SRC}")
# Ensure 4 channels (BGRA)
if img.shape[2] == 3:
    img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    img[..., 3] = 255
h, w = img.shape[:2]
scale = TARGET_W / w
new_w = TARGET_W
new_h = int(h * scale)
out = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
cv2.imwrite(DST, out)
print(f"logo: {SRC} {w}x{h} -> {DST} {new_w}x{new_h}")

# Sunglasses: source is 8-bit colormap PNG with white background.
# Convert to BGRA with white pixels => alpha 0.
sg_in = "/raw-assets/sunglasses.png"
sg_out = "/assets/sunglasses.png"
if __import__("os").path.exists(sg_in):
    sg = cv2.imread(sg_in, cv2.IMREAD_UNCHANGED)
    if sg.ndim == 2:  # palettized -> grayscale
        sg = cv2.cvtColor(sg, cv2.COLOR_GRAY2BGR)
    if sg.shape[2] == 3:
        b, g, r = cv2.split(sg)
        # alpha = 0 for near-white, 255 otherwise
        white = (r > 235) & (g > 235) & (b > 235)
        alpha = np.where(white, 0, 255).astype(np.uint8)
        sg = cv2.merge([b, g, r, alpha])
    cv2.imwrite(sg_out, sg)
    print(f"sunglasses: {sg.shape} -> {sg_out}")
