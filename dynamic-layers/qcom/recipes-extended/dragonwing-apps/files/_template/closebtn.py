#!/usr/bin/env python3
"""In-frame red X close button for fullscreen Dragonwing camera apps.

waylandsink does not hand pointer input back to the app, so we read the USB
mouse directly via evdev and EVIOCGRAB it (exclusive: Weston stops drawing its
own cursor while the app runs). The app tracks its own cursor, draws a red X in
the top-right corner, and on a left-click inside it asks the marketplace to stop
this app's container. Stdlib only (raw evdev structs); import + start() + draw().
"""
import os, glob, struct, threading, fcntl, time, urllib.request

try:
    import cv2
except Exception:
    cv2 = None

_EV_SIZE = struct.calcsize('llHHi')      # struct input_event on 64-bit = 24
EV_KEY, EV_REL = 0x01, 0x02
REL_X, REL_Y = 0x00, 0x01
BTN_LEFT = 0x110
EVIOCGRAB = 0x40044590                   # _IOW('E', 0x90, int)

_BTN = 60                                 # red X box size (frame px)
_MARGIN = 16
_S = {'cx': 0, 'cy': 0, 'w': 0, 'h': 0, 'have': False, 'closing': False}


def _find_mouse():
    for p in sorted(glob.glob('/dev/input/by-id/*-event-mouse')):
        return os.path.realpath(p)
    return None


def _box():
    return _S['w'] - _BTN - _MARGIN, _MARGIN, _BTN


def _close():
    if _S['closing']:
        return
    _S['closing'] = True
    aid = os.environ.get('APP_ID', '')
    base = os.environ.get('MARKETPLACE_URL', 'http://172.17.0.1:8080')
    print(f'[closebtn] close clicked; stopping app {aid!r}', flush=True)
    try:
        req = urllib.request.Request(f'{base}/api/apps/{aid}/stop', method='POST',
                                     data=b'{}', headers={'content-type': 'application/json'})
        urllib.request.urlopen(req, timeout=5).read()
    except Exception as e:
        print(f'[closebtn] stop POST failed: {e!r}', flush=True)
    time.sleep(3)            # marketplace docker rm -f should kill us first
    os._exit(0)


def _reader(fd, sens):
    while True:
        try:
            data = os.read(fd, _EV_SIZE * 32)
        except OSError:
            return
        for i in range(0, len(data) - _EV_SIZE + 1, _EV_SIZE):
            _, _, etype, code, value = struct.unpack('llHHi', data[i:i + _EV_SIZE])
            if etype == EV_REL:
                if code == REL_X:
                    _S['cx'] = min(max(0, _S['cx'] + int(value * sens)), _S['w'] - 1)
                elif code == REL_Y:
                    _S['cy'] = min(max(0, _S['cy'] + int(value * sens)), _S['h'] - 1)
            elif etype == EV_KEY and code == BTN_LEFT and value == 1:
                bx, by, bs = _box()
                if bx <= _S['cx'] <= bx + bs and by <= _S['cy'] <= by + bs:
                    threading.Thread(target=_close, daemon=True).start()


def _reader_safe(fd, sens):
    # A bug or a yanked mouse must never take anything down; this is a daemon
    # thread, so swallowing here just stops the button working.
    try:
        _reader(fd, sens)
    except Exception as e:
        print(f'[closebtn] reader thread stopped: {e!r}', flush=True)


def start(w, h, sensitivity=2.0):
    """Best-effort. NEVER raises: if there is no mouse / no /dev/input / no
    permission, the close button is simply disabled and the app runs normally."""
    try:
        _S['w'], _S['h'] = int(w), int(h)
        _S['cx'], _S['cy'] = int(w) // 2, int(h) // 2
        dev = _find_mouse()
        if not dev:
            print('[closebtn] no mouse found; close button disabled (app runs normally)', flush=True)
            return
        fd = os.open(dev, os.O_RDONLY)
        try:
            fcntl.ioctl(fd, EVIOCGRAB, 1)
        except Exception as e:
            print(f'[closebtn] EVIOCGRAB failed (cursor may double): {e!r}', flush=True)
        _S['have'] = True
        threading.Thread(target=_reader_safe, args=(fd, float(sensitivity)), daemon=True).start()
        print(f'[closebtn] grabbed {dev}; click the red X to close', flush=True)
    except Exception as e:
        # No mouse node, EACCES (cgroup not granting char 13), etc.
        _S['have'] = False
        print(f'[closebtn] disabled ({e!r}); app continues without a close button', flush=True)


def draw(frame):
    """Draw the red X (and cursor if a mouse is grabbed). NEVER raises, so a
    drawing error cannot break the video loop."""
    if cv2 is None or frame is None:
        return
    try:
        h, w = frame.shape[:2]
        _S['w'], _S['h'] = w, h
        bs = min(_BTN, w // 4, h // 4)
        bx, by = w - bs - _MARGIN, _MARGIN
        if bx < 0 or by < 0:
            return
        roi = frame[by:by + bs, bx:bx + bs]
        if roi.shape[0] == bs and roi.shape[1] == bs:
            dark = roi.copy(); dark[:] = (30, 20, 20)
            cv2.addWeighted(dark, 0.5, roi, 0.5, 0, roi)
        cv2.rectangle(frame, (bx, by), (bx + bs, by + bs), (90, 70, 255), 2)
        p = max(10, bs // 4)
        cv2.line(frame, (bx + p, by + p), (bx + bs - p, by + bs - p), (90, 70, 255), 3, cv2.LINE_AA)
        cv2.line(frame, (bx + bs - p, by + p), (bx + p, by + bs - p), (90, 70, 255), 3, cv2.LINE_AA)
        if _S['have']:
            cx = min(max(0, _S['cx']), w - 1)
            cy = min(max(0, _S['cy']), h - 1)
            cv2.circle(frame, (cx, cy), 7, (0, 0, 0), -1, cv2.LINE_AA)
            cv2.circle(frame, (cx, cy), 5, (255, 255, 255), -1, cv2.LINE_AA)
    except Exception:
        pass
