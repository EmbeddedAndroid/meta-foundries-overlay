#!/bin/sh
for i in $(seq 1 60); do
  [ -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ] && break
  sleep 0.5
done
URL="${KIOSK_URL:-http://172.17.0.1:8080}"
# GPU acceleration via the container's mesa (freedreno) talking to the host
# kernel msm DRM through /dev/dri. Set KIOSK_SOFTWARE=1 to fall back to software.
if [ "${KIOSK_SOFTWARE:-0}" = "1" ]; then
  GL="--disable-gpu --disable-gpu-compositing"
else
  GL="--use-gl=egl --ignore-gpu-blocklist --enable-gpu-rasterization --enable-zero-copy"
fi
# Default 150% zoom via a tiny content-script extension that sets CSS zoom on
# every page. This is display-independent, which is why it works where the
# alternatives did not: --force-device-scale-factor=1.5 made a partial window
# (weston has no fractional buffer scale), and the profile default_zoom_level
# pref was not honored on this Chromium build. Override with KIOSK_ZOOM.
ZOOM="${KIOSK_ZOOM:-1.5}"
ZP=$(awk "BEGIN{printf \"%g\", $ZOOM*100}")
EXT=/tmp/zoomext
mkdir -p "$EXT"
cat > "$EXT/manifest.json" <<EOF
{"manifest_version":3,"name":"kioskzoom","version":"1","content_scripts":[{"matches":["<all_urls>"],"js":["cs.js"],"run_at":"document_start","all_frames":true}]}
EOF
cat > "$EXT/cs.js" <<EOF
(function(){function z(){try{document.documentElement.style.zoom="${ZP}%";}catch(e){}}z();document.addEventListener("DOMContentLoaded",z);window.addEventListener("load",z);setInterval(z,1000);})();
EOF
COMMON="--ozone-platform=wayland --enable-features=UseOzonePlatform $GL \
  --no-sandbox --test-type \
  --no-first-run --no-default-browser-check \
  --disable-session-crashed-bubble --disable-breakpad \
  --disable-features=TranslateUI \
  --load-extension=$EXT --disable-extensions-except=$EXT \
  --user-data-dir=/tmp/chrome-profile"
case "${KIOSK_MODE:-browser}" in
  kiosk) exec chromium --kiosk $COMMON "$URL" ;;
  app)   exec chromium --app="$URL" --start-maximized $COMMON ;;
  *)     exec chromium --start-maximized $COMMON "$URL" ;;
esac
