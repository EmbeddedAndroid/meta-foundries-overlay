#!/usr/bin/env python3
"""Dragonwing AI Developer — chat-first agent + marketplace, single-file http server."""
import http.server, socketserver, json, subprocess, os, signal, threading, time, re, uuid, http.client, tarfile, shutil, io, glob
try:
    import grp as _grp
    INPUT_GID = _grp.getgrnam("input").gr_gid
except Exception:
    INPUT_GID = None

PORT = 8080
ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(ROOT, 'static')
ANTHROPIC_HOST = "api.anthropic.com"
ANTHROPIC_MODEL = "claude-opus-4-7"

# --- App catalog ----------------------------------------------------------
STATE_FILE = '/var/lib/dragonwing-marketplace.json'
state_lock = threading.Lock()
state = {
    'cam-detect': {
        'id': 'cam-detect',
        'name': 'Deal With It',
        'description': 'Live YOLOv8 detection on the Hexagon NPU. Drops Dragonwing sunglasses on every face in frame, with real-time thermal & FPS telemetry overlaid on top.',
        'cover_image': '/static/deal-with-it.png',
        'output': 'hdmi',
        'image': 'rubikpi3-cam-test:npu',
        'container': 'cam-npu',
        'capabilities': ['camera', 'npu', 'display'],
        # Source scaffold at /root/apps/cam-detect/ (Dockerfile FROM the baked
        # rubikpi3-cam-test:npu image + main.py copied out of it). Forkable.
        'type': 'source',
        'version': '1.0.0',
        'author': 'Qualcomm',
        'base_image': 'rubikpi3-cam-test:npu',
        'forked_from': None,
    },
}

# Fields with publishing/manifest semantics. Backfilled on load for legacy state.
_PUBLISHING_DEFAULTS = {
    'type': 'source', 'version': '0.1.0', 'author': '',
    'base_image': 'ubuntu:24.04', 'forked_from': None, 'ports': [],
}

def load_state():
    try:
        with open(STATE_FILE) as f: saved = json.load(f)
        with state_lock:
            for k, v in saved.items():
                if k in state:
                    # Hardcoded app: keep hardcoded defaults, overlay only user-mutable fields
                    for field in ('output',):
                        if field in v: state[k][field] = v[field]
                else:
                    # Runtime-installed app (via install_app): take the whole record.
                    state[k] = v
            # Backfill publishing metadata for runtime apps registered before
            # the schema gained type/version/author/base_image/forked_from.
            backfilled = False
            for k, rec in state.items():
                if k == 'cam-detect': continue  # hardcoded has its own defaults
                for f, default in _PUBLISHING_DEFAULTS.items():
                    if f not in rec:
                        rec[f] = default; backfilled = True
            if backfilled: save_state()
    except Exception: pass

def save_state():
    try:
        with open(STATE_FILE, 'w') as f: json.dump(state, f)
    except Exception: pass

# --- Shell utilities ------------------------------------------------------
def sh(cmd, timeout=30):
    class R:
        __slots__ = ('returncode','stdout','stderr')
    try:
        # text=False so we never raise on non-utf-8 (some commands print protobuf, binary blobs, etc).
        # Decode bytes ourselves with errors="replace".
        cp = subprocess.run(cmd, shell=True, capture_output=True, timeout=timeout)
        r = R(); r.returncode = cp.returncode
        r.stdout = (cp.stdout or b'').decode('utf-8', 'replace')
        r.stderr = (cp.stderr or b'').decode('utf-8', 'replace')
        return r
    except subprocess.TimeoutExpired as e:
        r = R(); r.returncode = -1
        r.stdout = (e.stdout or b'').decode('utf-8', 'replace') if isinstance(e.stdout, (bytes, bytearray)) else (e.stdout or '')
        r.stderr = ((e.stderr or b'').decode('utf-8', 'replace') if isinstance(e.stderr, (bytes, bytearray)) else (e.stderr or '')) + f'\n[timed out after {timeout}s]'
        return r

# --- Hardware discovery -----------------------------------------------------
# Everything the marketplace and the onboard agent say about the platform is
# read from the running system, not hardcoded, so the same image works on any
# Dragonwing-class board (QCS6490, QCS8275, SA8775P, ...).

def _read_first(path, max_bytes=4096):
    """Stripped contents of a small sysfs/procfs/DT file, or None."""
    try:
        with open(path, 'rb') as f:
            v = f.read(max_bytes).decode('utf-8', 'replace').strip().strip('\x00')
        return v or None
    except OSError:
        return None

def _dt_compatible():
    """Device-tree compatible entries (NUL-separated), e.g. ['arduino,ventuno', 'qcom,qcs8275']."""
    try:
        with open('/proc/device-tree/compatible', 'rb') as f:
            return [s.decode('utf-8', 'replace') for s in f.read(4096).split(b'\x00') if s]
    except OSError:
        return []

def _detect_hexagon_version():
    """Hexagon arch from the QNN HTP skel libraries shipped with the DSP
    runtime (libQnnHtpV79Skel.so → 'V79'). Highest wins if several ship."""
    best = None
    for root in ('/usr/lib/dsp', '/usr/lib/rfsa', '/opt/qnn-libs', '/opt/qnn'):
        for p in glob.glob(os.path.join(root, '**', 'libQnnHtp*Skel.so'), recursive=True):
            m = re.search(r'HtpV(\d+)', os.path.basename(p))
            if m and (best is None or int(m.group(1)) > best):
                best = int(m.group(1))
    return f'V{best}' if best else None

def _detect_gpu():
    """Adreno model, preferring the kgsl model node, falling back to the GPU's
    device-tree compatible (e.g. 'qcom,adreno-623.0' → 'Adreno 623')."""
    v = _read_first('/sys/class/kgsl/kgsl-3d0/gpu_model')
    if v:
        m = re.match(r'(?i)adreno[_\s-]*(\w+)', v)
        return f'Adreno {m.group(1)}' if m else v
    for node in glob.glob('/proc/device-tree/soc*/gpu*/compatible') + glob.glob('/proc/device-tree/gpu*/compatible'):
        for entry in (_read_first(node) or '').replace('\x00', ' ').split():
            m = re.match(r'qcom,adreno-(\d+)', entry)
            if m:
                return f'Adreno {m.group(1)}'
    return None

def _detect_mesa():
    """Mesa version from the installed gallium library name, if present."""
    for pat in ('/usr/lib/libgallium-*.so', '/usr/lib/*/libgallium-*.so'):
        for p in glob.glob(pat):
            m = re.search(r'libgallium-([\d.]+)\.so', os.path.basename(p))
            if m: return m.group(1).rstrip('.')
    return None

def _detect_distro():
    try:
        for line in open('/etc/os-release'):
            if line.startswith('PRETTY_NAME='):
                return line.split('=', 1)[1].strip().strip('"') or None
    except OSError:
        pass
    return None

def detect_hardware():
    """One-shot platform survey. Every value may be None when its source is
    missing — consumers must degrade gracefully, never assume a board."""
    un = os.uname()
    mem_kb = None
    try:
        for line in open('/proc/meminfo'):
            if line.startswith('MemTotal:'):
                mem_kb = int(line.split()[1]); break
    except (OSError, ValueError):
        pass
    soc = _read_first('/sys/devices/soc0/machine')
    compat = _dt_compatible()
    if not soc:
        for c in compat:
            if c.startswith('qcom,'):
                soc = c.split(',', 1)[1].upper(); break
    return {
        'soc': soc,                                            # e.g. 'QCS8275'
        'soc_family': _read_first('/sys/devices/soc0/family'),
        'soc_id': _read_first('/sys/devices/soc0/soc_id'),
        'board': _read_first('/proc/device-tree/model'),       # e.g. 'Arduino VENTUNO Q'
        'compatible': compat,
        'hexagon': _detect_hexagon_version(),                  # e.g. 'V75'
        'npu_node': next((n for n in ('/dev/fastrpc-cdsp', '/dev/fastrpc-adsp')
                          if os.path.exists(n)), next(iter(sorted(glob.glob('/dev/fastrpc-*'))), None)),
        'gpu': _detect_gpu(),                                  # e.g. 'Adreno 623'
        'mesa': _detect_mesa(),
        'distro': _detect_distro(),
        'kernel': un.release,
        'arch': un.machine,
        'cpu_cores': os.cpu_count(),
        'mem_gb': round(mem_kb / 1024 / 1024, 1) if mem_kb else None,
        'hostname': un.nodename,
    }

HW = detect_hardware()

def hw_summary():
    """Short human label, e.g. 'Arduino VENTUNO Q · QCS8275 · Hexagon V75 NPU'."""
    parts = []
    if HW.get('board'): parts.append(HW['board'])
    if HW.get('soc'): parts.append(HW['soc'])
    if HW.get('hexagon'): parts.append(f"Hexagon {HW['hexagon']} NPU")
    if HW.get('gpu'): parts.append(HW['gpu'])
    return ' · '.join(parts) or 'unknown platform'

def camera_present():
    """A USB video-class camera is attached (by-id avoids counting ISP nodes)."""
    return bool(glob.glob('/dev/v4l/by-id/usb-*-video-index0'))


def container_running(name):
    r = sh(f"docker ps --filter name=^{name}$ --format '{{{{.Status}}}}'", timeout=5)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None

def cam_status_line(name='cam-npu'):
    r = sh(f"docker logs --tail 40 {name} 2>&1", timeout=5)
    last = None
    for line in (r.stdout or '').splitlines():
        m = re.search(r"\[[\w-]+\]\s+(\d+)\s*fr\s+([\d.]+)\s*fps", line)
        if m: last = m
    return f"{last.group(2)} fps · {int(last.group(1))} frames" if last else "Starting…"

def feed_is_live(app_id, max_age_s=5):
    """Heuristic: the app is producing output if its feed jpg has been written
    in the last few seconds. Used as a universal 'is alive' signal for apps
    that don't emit fps telemetry to stdout."""
    try:
        return time.time() - os.path.getmtime(f'/var/lib/dragonwing-feeds/{app_id}.jpg') < max_age_s
    except OSError:
        return False

def container_uptime_s(name):
    """How many seconds since the container entered Running state. Returns 0
    if not running or on parse failure. Used to distinguish 'just started'
    from 'has been running for a while' for non-camera apps that don't write
    a feed jpg or fps log line."""
    r = sh(f"docker inspect --format '{{{{.State.StartedAt}}}}' {name} 2>/dev/null", timeout=3)
    iso = (r.stdout or '').strip()
    if not iso or iso.startswith('0001-'):  # empty / unset
        return 0
    try:
        import datetime
        # Docker returns RFC3339 with nanoseconds like 2026-05-15T13:40:28.190463213Z
        # Python's fromisoformat caps at microseconds (6 digits) so trim nanos
        # AND replace the trailing Z with +00:00.
        m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:?\d{2})?$", iso)
        if not m: return 0
        head, frac, tz = m.group(1), (m.group(2) or '')[:6], m.group(3) or 'Z'
        tz = '+00:00' if tz == 'Z' else tz
        norm = head + (('.' + frac) if frac else '') + tz
        started = datetime.datetime.fromisoformat(norm)
        return max(0, (datetime.datetime.now(datetime.timezone.utc) - started).total_seconds())
    except Exception:
        return 0


def cam_device_args():
    """Map the whole /dev tree plus a cgroup rule for video4linux (char major
    81) instead of pinning --device nodes: enumeration order shuffles across
    reboots and a node missing at boot is a failed start that docker restart
    policies never retry. Apps scan /dev/video* for the camera themselves."""
    return "-v /dev:/dev " + (f"--group-add {INPUT_GID} " if INPUT_GID else "") + "--device-cgroup-rule='c 81:* rmw' --device-cgroup-rule='c 13:* rmw' "

def htp_cache_dir(aid):
    """Per-board, per-app dir where the QNN HTP delegate caches the
    compiled context for the local NPU (Lever A: ship a portable quantized
    tflite, compile + cache for THIS Hexagon once, restore instantly after).
    Keyed by Hexagon arch so a different SoC/firmware gets a fresh cache.
    World-writable since apps run as uid 1000."""
    hx = HW.get('hexagon') or 'unknown'
    d = f'/var/lib/dragonwing-htp-cache/{hx}/{aid}'
    try:
        os.makedirs(d, exist_ok=True); os.chmod(d, 0o777)
    except Exception:
        pass
    return d

def app_containers(aid):
    """Every container name an app may run under."""
    if aid == 'cam-detect':
        return ['cam-npu', 'cam-npu-hdmi', 'cam-npu-rdp']
    return [state.get(aid, {}).get('container', aid)]

def build_launch_commands(aid):
    """The shell commands that (re)create an app's container(s). Single source
    of truth shared by interactive start and the deployed-at-boot systemd unit."""
    rm = "docker rm -f " + " ".join(app_containers(aid)) + " 2>/dev/null || true"
    if aid != 'cam-detect':
        cont = state[aid].get('container', aid)
        return [rm, _build_generic_run(aid, cont, state[aid].get('image'))]
    output = state[aid].get('output', 'hdmi')
    base = (
        "docker run -d --restart=always "
        "--user 1000:1000 --group-add 44 "
        + cam_device_args() +
        "--device-cgroup-rule='c 10:* rmw' "
        "-v /run/user/1000:/run/user/1000:rw "
        "-v /usr/lib/dsp:/usr/lib/dsp:ro "
        # cDSP loads the HTP skel from its default search path /usr/lib/rfsa/adsp;
        # the host ships it (qairt V68 skel + fastrpc_shell_unsigned_3) under
        # /usr/lib/dsp/cdsp, so mount that there. Without it the skel never loads
        # ("Failed to load skel", qnn_open 0x8000060e) and inference falls to CPU.
        "-v /usr/lib/dsp/cdsp:/usr/lib/rfsa/adsp:ro "
        "-v /usr/lib/firmware:/usr/lib/firmware:ro "
        "-v /sys/class/thermal:/sys/class/thermal:ro "
        "-v /var/lib/dragonwing-feeds:/feeds:rw "
        "-v /usr/lib/libcdsprpc.so.1.0.0:/usr/lib/libcdsprpc.so.1.0.0:ro "
        "-v /usr/lib/libcdsprpc.so.1:/usr/lib/libcdsprpc.so.1:ro "
        "-v /usr/lib/libcdsprpc.so:/usr/lib/libcdsprpc.so:ro "
        "-e XDG_RUNTIME_DIR=/run/user/1000 "
        "-e MODEL=/models/yolov8_det.tflite -e CAM_DEVICE=/dev/video2 "
        "-e WIDTH=1280 -e HEIGHT=720 -e HOME=/tmp -e QNN_BACKEND=htp "
        "-e FULLSCREEN=true -e APP_ID=cam-detect "
        + (f"-e YOCTO_DISTRO='{HW['distro']}' " if HW.get('distro') else "")
        + (f"-e MESA_VERSION={HW['mesa']} " if HW.get('mesa') else "")
        + "-e ADSP_LIBRARY_PATH='/usr/lib/dsp;/usr/lib/dsp/cdsp' "
        + f"-v {htp_cache_dir('cam-detect')}:/htp-cache:rw -e QNN_CACHE_DIR=/htp-cache "
    )
    cmds = [rm]
    if output in ('hdmi', 'both'):
        cmds.append(base + "--name cam-npu-hdmi -e WAYLAND_DISPLAY=wayland-1 rubikpi3-cam-test:npu")
    if output in ('rdp', 'both'):
        cmds.append(base + "--name cam-npu-rdp -e WAYLAND_DISPLAY=wayland-rdp rubikpi3-cam-test:npu")
    return cmds

def start_cam():
    for cmd in build_launch_commands('cam-detect'):
        sh(cmd)

def stop_cam():
    sh("docker rm -f cam-npu cam-npu-hdmi cam-npu-rdp 2>/dev/null")


# --- Resource contention model ------------------------------------------
# Capabilities that cannot be shared by multiple running apps simultaneously.
# (camera = single USB v4l2 device, NPU = HTP backend prefers single tenant
# for predictable inference time. GPU/audio/display/network are shareable.)
EXCLUSIVE_CAPS = {'camera', 'npu'}
# Ports the marketplace itself or other always-on system services hold.
# An app cannot publish on these — detect_conflicts returns a synthetic
# entry pointing at "marketplace" so the start handler refuses.
RESERVED_PORTS = {PORT, 3389}  # marketplace HTTP, weston-rdp

def detect_conflicts(target_id):
    """Return [{resource, held_by, held_by_name}] for resources currently held
    by OTHER running apps that this app needs. Covers two resource families:
      * Exclusive capabilities (camera, npu) — declared via `capabilities`.
      * Host ports — declared via `ports`. Two running apps cannot publish the
        same TCP port to the host; the second `docker run -p N:N` would fail.
    """
    target = state.get(target_id)
    if not target: return []
    target_excl  = set(target.get('capabilities', [])) & EXCLUSIVE_CAPS
    target_ports = set(int(p) for p in (target.get('ports') or []) if str(p).isdigit() or isinstance(p, int))
    if not (target_excl or target_ports): return []
    out = []
    # First: anything in the reserved set is permanently held by the system.
    for port in (target_ports & RESERVED_PORTS):
        out.append({'resource': f'port:{port}', 'held_by': '__marketplace__',
                    'held_by_name': 'marketplace (system service)'})
    for aid, a in state.items():
        if aid == target_id: continue
        v = app_view(aid)
        if not v.get('running'): continue
        their_excl  = set(a.get('capabilities', [])) & EXCLUSIVE_CAPS
        their_ports = set(int(p) for p in (a.get('ports') or []) if str(p).isdigit() or isinstance(p, int))
        for cap in (target_excl & their_excl):
            out.append({'resource': cap, 'held_by': aid,
                        'held_by_name': a.get('name', aid)})
        for port in (target_ports & their_ports):
            out.append({'resource': f'port:{port}', 'held_by': aid,
                        'held_by_name': a.get('name', aid)})
    return out

def stop_app_by_id(aid):
    if aid == 'cam-detect':
        stop_cam()
    else:
        cont = state.get(aid, {}).get('container', aid)
        sh(f"docker rm -f {cont} 2>/dev/null")


def _build_generic_run(aid, cont, img):
    """Build a docker run command for marketplace apps based on their declared capabilities.
    Mirrors the bind-mounts/devices the cam-detect launcher uses, gated on caps."""
    caps  = set(state.get(aid, {}).get('capabilities', []) or [])
    output = state.get(aid, {}).get('output', 'hdmi')
    ports = [int(p) for p in (state.get(aid, {}).get('ports') or []) if str(p).isdigit() or isinstance(p, int)]
    parts = [
        "docker run -d --name", cont,
        "--restart=always",
        "--user 1000:1000 --group-add 44",
        "-v /var/lib/dragonwing-feeds:/feeds:rw",
        "-v /sys/class/thermal:/sys/class/thermal:ro",
        "-e", f"APP_ID={aid}",
        "-e HOME=/tmp",
        "-e WIDTH=1280 -e HEIGHT=720",
        "-e FULLSCREEN=true",
    ]
    for p in ports:
        # Publish each declared port to the host. The conflict check above
        # already rejected starts where another running app holds this port.
        parts += [f"-p {p}:{p}"]
    if 'camera' in caps:
        parts += [cam_device_args(),
                  "-e CAM_DEVICE=/dev/video2"]
    if 'npu' in caps:
        parts += [
            "--device-cgroup-rule='c 10:* rmw'",
            "-v /usr/lib/dsp:/usr/lib/dsp:ro",
            # cDSP HTP skel at its default load path (host qairt runtime).
            "-v /usr/lib/dsp/cdsp:/usr/lib/rfsa/adsp:ro",
            "-v /usr/lib/firmware:/usr/lib/firmware:ro",
            "-v /usr/lib/libcdsprpc.so.1.0.0:/usr/lib/libcdsprpc.so.1.0.0:ro",
            "-v /usr/lib/libcdsprpc.so.1:/usr/lib/libcdsprpc.so.1:ro",
            "-v /usr/lib/libcdsprpc.so:/usr/lib/libcdsprpc.so:ro",
            "-e ADSP_LIBRARY_PATH='/usr/lib/dsp;/usr/lib/dsp/cdsp'",
            "-e QNN_BACKEND=htp",
            f"-v {htp_cache_dir(aid)}:/htp-cache:rw", "-e QNN_CACHE_DIR=/htp-cache",
            # QNN libs come from the image's /opt/qnn (baked in by rubikpi3-cam-test).
            # For apps without it baked in, we mount from the cam-test image volume:
            "-v /opt/qnn-libs:/opt/qnn:ro",
        ]
    if 'display' in caps or 'camera' in caps:
        parts += [
            "-v /run/user/1000:/run/user/1000:rw",
            "-e XDG_RUNTIME_DIR=/run/user/1000",
        ]
        if INPUT_GID:
            parts += ["-v /dev/input:/dev/input", "--device-cgroup-rule='c 13:* rmw'", f"--group-add {INPUT_GID}"]
        if output == 'rdp':
            parts += ["-e WAYLAND_DISPLAY=wayland-rdp"]
        else:
            parts += ["-e WAYLAND_DISPLAY=wayland-1"]
    if 'sensors' in caps:
        # Privileged I/O: LED sysfs, GPIO, i2c, spidev, etc.
        # Override the default --user 1000:1000 with root so sysfs writes succeed.
        parts = [p for p in parts if not p.startswith('--user')]
        parts += [
            "--privileged",
            "--user 0:0",
            "-v /sys/class/leds:/sys/class/leds:rw",
        ]
    parts += [img]
    return " ".join(parts)


def do_start_app(aid, force=False):
    """Centralised start with conflict mediation. Returns dict {ok, conflicts?, message?}."""
    if aid not in state:
        return {"ok": False, "error": f"unknown app {aid!r}"}
    if 'camera' in (state[aid].get('capabilities') or []) and not camera_present():
        return {"ok": False, "reason": "no_camera",
                "message": "Cannot start: this app needs a camera and none is connected. Connect a USB camera and try again."}
    conflicts = detect_conflicts(aid)
    # Reserved system ports cannot be force-preempted — they're held by the
    # marketplace itself or weston-rdp. Surface as an unrecoverable error.
    reserved_hits = [c for c in conflicts if c['held_by'] == '__marketplace__']
    if reserved_hits:
        names = ', '.join(c['resource'] for c in reserved_hits)
        return {"ok": False, "conflicts": conflicts,
                "message": f"Cannot start: {names} are held by system services and cannot be preempted. Change the app's declared ports."}
    if conflicts and not force:
        names = ', '.join(f"{c['held_by_name']} (uses {c['resource']})" for c in conflicts)
        return {"ok": False, "conflicts": conflicts,
                "message": f"Cannot start: {names} already running."}
    if conflicts and force:
        for c in conflicts:
            stop_app_by_id(c['held_by'])
        time.sleep(0.5)
    if aid == 'cam-detect':
        start_cam()
    else:
        cont = state[aid].get('container', aid); img = state[aid].get('image')
        sh(f"docker rm -f {cont} 2>/dev/null")
        sh(_build_generic_run(aid, cont, img))
    return {"ok": True, "id": aid, "preempted": [c['held_by'] for c in conflicts] if conflicts else []}


# --- Deploy: boot persistence via systemd ---------------------------------
# "Deploying" an app installs a systemd unit that (re)creates its container(s)
# at every boot, independent of marketplace state. The launch commands are
# written to a script under DEPLOY_DIR so unit files never need shell-quote
# gymnastics; the unit file's existence is the single source of truth for
# "deployed". Recall removes both files.
DEPLOY_DIR = '/var/lib/dragonwing-deploy'
UNIT_DIR = '/etc/systemd/system'

def _deploy_unit_name(aid):
    return f'dragonwing-app-{aid}.service'

def app_deployed(aid):
    return os.path.isfile(os.path.join(UNIT_DIR, _deploy_unit_name(aid)))

def deploy_app(aid):
    """Write launch script + systemd unit, enable at boot. Raises ValueError."""
    if aid not in state: raise ValueError(f'unknown app {aid}')
    # Two deployed apps that both need an exclusive resource (camera, NPU) or
    # the same port would fight at every boot — refuse upfront.
    mine_excl  = set(state[aid].get('capabilities') or []) & EXCLUSIVE_CAPS
    mine_ports = set(int(p) for p in (state[aid].get('ports') or []) if str(p).isdigit() or isinstance(p, int))
    for oid, o in state.items():
        if oid == aid or not app_deployed(oid): continue
        excl  = mine_excl & set(o.get('capabilities') or [])
        ports = mine_ports & set(int(p) for p in (o.get('ports') or []) if str(p).isdigit() or isinstance(p, int))
        if excl or ports:
            res = ', '.join(sorted(excl) + [f'port:{p}' for p in sorted(ports)])
            raise ValueError(f"already-deployed app {o.get('name', oid)!r} also needs {res}; "
                             f"recall it first or undeclare the resource")
    os.makedirs(DEPLOY_DIR, exist_ok=True)
    script = os.path.join(DEPLOY_DIR, f'{aid}.sh')
    unit = os.path.join(UNIT_DIR, _deploy_unit_name(aid))
    body = ('#!/bin/sh\n# Generated by dragonwing-marketplace deploy.\n'
            '# Do not edit; recall + redeploy instead.\n'
            + '\n'.join(build_launch_commands(aid)) + '\n')
    with open(script + '.tmp', 'w') as f: f.write(body)
    os.chmod(script + '.tmp', 0o755)
    os.replace(script + '.tmp', script)
    stop_cmd = 'docker rm -f ' + ' '.join(app_containers(aid))
    unit_body = f"""[Unit]
Description=Dragonwing deployed app: {state[aid].get('name', aid)} ({aid})
Wants=network-online.target
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh {script}
ExecStop=/bin/sh -c "{stop_cmd}"

[Install]
WantedBy=multi-user.target
"""
    with open(unit + '.tmp', 'w') as f: f.write(unit_body)
    os.replace(unit + '.tmp', unit)
    r = sh(f'systemctl daemon-reload && systemctl enable {_deploy_unit_name(aid)}', timeout=15)
    if r.returncode != 0:
        # Roll back so app_deployed() doesn't report a half-installed unit.
        for p in (unit, script):
            try: os.remove(p)
            except OSError: pass
        sh('systemctl daemon-reload', timeout=15)
        raise ValueError(f'systemctl enable failed: {(r.stderr or r.stdout)[-300:]}')
    return True

def recall_app(aid):
    """Disable + remove the boot unit. Running containers are left untouched."""
    if not app_deployed(aid): raise ValueError('app is not deployed')
    sh(f'systemctl disable {_deploy_unit_name(aid)} 2>/dev/null', timeout=15)
    for p in (os.path.join(UNIT_DIR, _deploy_unit_name(aid)),
              os.path.join(DEPLOY_DIR, f'{aid}.sh')):
        try: os.remove(p)
        except OSError: pass
    sh('systemctl daemon-reload', timeout=15)
    return True


APPS_DIR = '/root/apps'

def build_manifest(aid):
    """The manifest.json embedded inside a .dwapp bundle."""
    s = state[aid]
    return {
        'spec_version': 1,
        'id': aid,
        'name': s.get('name', aid),
        'description': s.get('description', ''),
        'type': s.get('type', 'source'),
        'version': s.get('version', '0.1.0'),
        'author': s.get('author', ''),
        'base_image': s.get('base_image', ''),
        'capabilities': s.get('capabilities', []),
        'ports': s.get('ports', []),
        'container': s.get('container', aid),
        'image': s.get('image', f'{aid}:latest'),
        'output': s.get('output', 'hdmi'),
        'cover_image': s.get('cover_image'),
        'forked_from': s.get('forked_from'),
        'exported_ts': time.time(),
    }

def export_app_bytes(aid):
    """Tar+gzip /root/apps/<aid>/ with manifest.json injected, return bytes."""
    src = os.path.join(APPS_DIR, aid)
    if not os.path.isdir(src): return None
    buf = io.BytesIO()
    def _no_pycache(ti):
        return None if '__pycache__' in ti.name or ti.name.endswith('.pyc') else ti
    with tarfile.open(fileobj=buf, mode='w:gz') as tf:
        tf.add(src, arcname=aid, recursive=True, filter=_no_pycache)
        manifest = build_manifest(aid)
        data = json.dumps(manifest, indent=2).encode()
        info = tarfile.TarInfo(name=f'{aid}/manifest.json')
        info.size = len(data); info.mtime = int(time.time()); info.mode = 0o644
        tf.addfile(info, io.BytesIO(data))
        # Carry the cover image too. It lives in /static/ (outside the app
        # dir), so a plain tar of /root/apps/<aid> drops it and the tile shows
        # broken after importing onto another board. Bundle it under
        # <aid>/_cover/ so import can restore it to /static/.
        cover = manifest.get('cover_image') or ''
        if cover.startswith('/static/'):
            cp = os.path.join(ROOT, 'static', os.path.basename(cover))
            if os.path.isfile(cp):
                tf.add(cp, arcname=f'{aid}/_cover/{os.path.basename(cover)}')
    return buf.getvalue()

def import_app_bytes(body):
    """Untar to /root/apps/<aid>/, docker build, register. Returns aid."""
    buf = io.BytesIO(body)
    with tarfile.open(fileobj=buf, mode='r:gz') as tf:
        members = tf.getmembers()
        roots = {m.name.split('/', 1)[0] for m in members if m.name}
        if len(roots) != 1: raise ValueError(f'expected one root dir, got {sorted(roots)!r}')
        aid = roots.pop()
        if not re.match(r'^[a-z][a-z0-9-]{1,40}$', aid): raise ValueError(f'invalid app id: {aid!r}')
        for m in members:
            if '..' in m.name.split('/') or os.path.isabs(m.name):
                raise ValueError(f'unsafe path in bundle: {m.name}')
        target = os.path.join(APPS_DIR, aid)
        if os.path.exists(target): shutil.rmtree(target)
        tf.extractall(APPS_DIR)
    # Restore a bundled cover image to /static/ (see export_app_bytes) so the
    # tile renders, then drop _cover/ so it isn't baked into the docker image.
    covdir = os.path.join(target, '_cover')
    if os.path.isdir(covdir):
        sdir = os.path.join(ROOT, 'static'); os.makedirs(sdir, exist_ok=True)
        for f in os.listdir(covdir):
            shutil.copy2(os.path.join(covdir, f), os.path.join(sdir, f))
        shutil.rmtree(covdir)
    mpath = os.path.join(target, 'manifest.json')
    manifest = {}
    if os.path.exists(mpath):
        with open(mpath) as f: manifest = json.load(f)
    img = manifest.get('image', f'{aid}:latest')
    r = sh(f'docker build -t {img} {target}', timeout=600)
    if r.returncode != 0:
        raise ValueError(f'docker build failed (exit {r.returncode}): {r.stderr[-800:]}')
    with state_lock:
        state[aid] = {
            'id': aid,
            'name': manifest.get('name', aid),
            'description': manifest.get('description', ''),
            'image': img,
            'container': manifest.get('container', aid),
            'cover_image': manifest.get('cover_image'),
            'output': manifest.get('output', 'hdmi'),
            'capabilities': manifest.get('capabilities', []),
            'ports': [int(p) for p in (manifest.get('ports') or []) if str(p).lstrip('-').isdigit()],
            'type': manifest.get('type', 'source'),
            'base_image': manifest.get('base_image', ''),
            'author': manifest.get('author', ''),
            'version': manifest.get('version', '0.1.0'),
            'forked_from': manifest.get('forked_from'),
        }
    save_state()
    return aid

def app_has_draft(aid):
    """True when a .clean snapshot exists at /root/apps/<aid>.clean/."""
    return os.path.isdir(os.path.join(APPS_DIR, aid + '.clean'))

def modify_app(aid):
    """Snapshot /root/apps/<aid>/ to /root/apps/<aid>.clean/ if not already
    present. Idempotent. Returns True if a snapshot was taken this call."""
    if aid not in state: raise ValueError(f'unknown app {aid}')
    if state[aid].get('type', 'source') != 'source':
        raise ValueError(f'cannot modify prebuilt app {aid}')
    src = os.path.join(APPS_DIR, aid)
    clean = src + '.clean'
    if not os.path.isdir(src): raise ValueError(f'no source dir at {src}')
    if os.path.isdir(clean): return False
    shutil.copytree(src, clean, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    return True

def reset_app(aid):
    """Restore /root/apps/<aid>/ from .clean, rebuild image, restart if running."""
    if aid not in state: raise ValueError(f'unknown app {aid}')
    src = os.path.join(APPS_DIR, aid)
    clean = src + '.clean'
    if not os.path.isdir(clean): raise ValueError(f'no draft to reset')
    # Was it running? Restart afterwards to pick up the restored image.
    cont = state[aid].get('container', aid)
    was_running = container_running(cont) or container_running('cam-npu-hdmi') or container_running('cam-npu-rdp') or container_running('cam-npu')
    if was_running: stop_app_by_id(aid)
    shutil.rmtree(src)
    shutil.copytree(clean, src)
    img = state[aid].get('image', f'{aid}:latest')
    r = sh(f'docker build -t {img} {src}', timeout=600)
    if r.returncode != 0:
        raise ValueError(f'docker build failed: {r.stderr[-500:]}')
    if was_running: do_start_app(aid, force=True)
    return True

def commit_app(aid):
    """Drop the .clean snapshot — current source becomes the committed state."""
    if aid not in state: raise ValueError(f'unknown app {aid}')
    clean = os.path.join(APPS_DIR, aid + '.clean')
    if not os.path.isdir(clean): raise ValueError(f'no draft to commit')
    shutil.rmtree(clean)
    return True


def fork_app(src_aid, new_aid, new_name):
    """Copy /root/apps/<src>/ → /root/apps/<new>/, register, kick off image build."""
    if src_aid not in state: raise ValueError(f'unknown app {src_aid}')
    if state[src_aid].get('type', 'source') != 'source':
        raise ValueError(f'cannot fork prebuilt app {src_aid}')
    if not re.match(r'^[a-z][a-z0-9-]{1,40}$', new_aid):
        raise ValueError(f'invalid app id: {new_aid!r}')
    if new_aid in state: raise ValueError(f'app {new_aid} already exists')
    src_dir = os.path.join(APPS_DIR, src_aid)
    dst_dir = os.path.join(APPS_DIR, new_aid)
    if not os.path.isdir(src_dir): raise ValueError(f'no source dir at {src_dir}')
    if os.path.exists(dst_dir): raise ValueError(f'target dir exists: {dst_dir}')
    shutil.copytree(src_dir, dst_dir)
    s = dict(state[src_aid])
    s.update({'id': new_aid, 'name': new_name, 'image': f'{new_aid}:latest',
              'container': new_aid, 'version': '0.1.0', 'forked_from': src_aid})
    with state_lock: state[new_aid] = s
    save_state()
    # Image build runs in the background — chat session can start while it bakes.
    threading.Thread(target=lambda: sh(f'docker build -t {new_aid}:latest {dst_dir}', timeout=600),
                     daemon=True).start()
    return new_aid


def _docker_image_exists(tag):
    r = sh(f"docker image inspect --format=present {tag} 2>/dev/null", timeout=3)
    return (r.stdout or '').strip() == 'present'

def app_view(app_id):
    a = dict(state[app_id])
    a['has_draft'] = app_has_draft(app_id)
    a['deployed'] = app_deployed(app_id)
    # Surface why an app can't launch right now so the UI can grey the tile
    # and explain, instead of letting the user hit a failing start.
    caps = a.get('capabilities') or []
    a['blocked'] = 'no_camera' if ('camera' in caps and not camera_present()) else None
    if app_id == 'cam-detect':
        # Legacy multi-container launcher: cam-detect runs as cam-npu-{hdmi,rdp}
        hdmi = container_running('cam-npu-hdmi')
        rdp  = container_running('cam-npu-rdp')
        legacy = container_running('cam-npu')
        names = []
        if hdmi: names.append('HDMI')
        if rdp:  names.append('RDP')
        if legacy and not (hdmi or rdp): names.append('legacy')
        a['running'] = bool(names)
        if a['running']:
            line = cam_status_line('cam-npu-hdmi' if hdmi else ('cam-npu-rdp' if rdp else 'cam-npu'))
            outputs = ' + '.join(names)
            if line != 'Starting…':
                a['status'] = f"Running on {outputs} · {line}"
            elif feed_is_live(app_id):
                a['status'] = f"Running on {outputs}"
            else:
                a['status'] = 'Starting…'
        else:
            # If first-boot hasn't built the cam-test image yet, "Stopped" is
            # misleading — Launch will silently no-op. Surface the real state.
            if not os.path.exists('/var/lib/dragonwing-firstboot.done'):
                a['status'] = 'Setting up… (first-boot building image)'
            elif not _docker_image_exists('rubikpi3-cam-test:npu'):
                a['status'] = 'Image missing (rubikpi3-cam-test:npu)'
            else:
                a['status'] = 'Stopped'
    else:
        cont = a.get('container', app_id)
        if container_running(cont):
            a['running'] = True
            line = cam_status_line(cont)
            if line != 'Starting…':
                a['status'] = f"Running · {line}"
            elif feed_is_live(app_id):
                a['status'] = 'Running'
            elif container_uptime_s(cont) > 5:
                # No fps telemetry, no feed jpg, but the container has been up
                # past the brief startup window — it's a non-camera app
                # (web service, audio app, headless reporter etc.). Just say
                # Running; "Starting…" would be a lie.
                a['status'] = 'Running'
            else:
                a['status'] = 'Starting…'
        else:
            a['running'] = False
            a['status'] = 'Stopped'
    return a

# --- Anthropic streaming proxy --------------------------------------------
TOOLS = [
    # tools follow
    {
        "name": "bash",
        "description": (
            "Execute a shell command on the Dragonwing host as root and return its "
            "stdout+stderr (combined) and exit code. No confirmation, no sandbox: "
            "the user wants full-trust developer control. Use this freely to "
            "inspect the system (`docker ps`, `journalctl -u X`, `ls /var/lib`), "
            "diagnose issues (`dmesg | grep ...`), manage containers, edit files "
            "(via `cat > /path << EOF`), build images, etc. Default timeout 30s; "
            "pass timeout for longer-running commands (e.g., docker build)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run."},
                "timeout": {"type": "integer", "description": "Timeout seconds. Default 30.", "default": 30}
            },
            "required": ["command"]
        }
    },
    {
        "name": "set_todos",
        "description": (
            "Maintain a visible task checklist for the current turn. Use this at "
            "the START of any multi-step task to lay out the plan, then call it "
            "again as items move between pending → in_progress → completed. The "
            "UI renders this as a live checklist above the chat thread so the "
            "user can see your progress. Replaces the entire list each call — "
            "send all todos every time, not just the changed ones. Mark at most "
            "one item as in_progress at a time. Drop or rename items freely as "
            "the plan evolves."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text":   {"type": "string", "description": "Short imperative, e.g. 'Build pose docker image'."},
                            "status": {"type": "string", "enum": ["pending","in_progress","completed","cancelled"]}
                        },
                        "required": ["text", "status"]
                    }
                }
            },
            "required": ["todos"]
        }
    },
    {
        "name": "update_app",
        "description": (
            "Mutate an existing app tile's cover_image and/or description in "
            "place. Updates the in-memory state and persists atomically — no "
            "service restart, no manual edit of /var/lib/dragonwing-*.json. "
            "Use this whenever you generate a new tile graphic for a fork "
            "(e.g. moved a PNG to /root/marketplace/static/<id>-tile.png and "
            "want the tile to pick it up) or want to rewrite an app's "
            "description text."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "id":          {"type": "string", "description": "App id, e.g. 'cowboy-hat'."},
                "cover_image": {"type": "string", "description": "Path served by marketplace, e.g. '/static/cowboy-hat.png'. Optional."},
                "description": {"type": "string", "description": "One-sentence pitch. Optional."},
                "ports":       {"type": "array",  "items": {"type": "integer"}, "description": "Replace the app's declared host TCP ports (e.g. [8501]). Use when an app's port list changes after install. Optional."}
            },
            "required": ["id"]
        }
    },
    {
        "name": "install_app",
        "description": (
            "Register a new app tile in the marketplace. The docker image "
            "must already be built locally. After install_app succeeds the "
            "tile appears in the sidebar and can be launched. Use this only "
            "when you have a built image ready and want to make it visible "
            "to the user."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "id":          {"type": "string", "description": "Unique snake-case-ish id, e.g. 'qr-scanner'."},
                "name":        {"type": "string", "description": "Display name, e.g. 'QR Scanner'."},
                "description": {"type": "string", "description": "One-sentence pitch."},
                "image":       {"type": "string", "description": "Docker image tag, e.g. 'qr-scanner:latest'."},
                "container":   {"type": "string", "description": "Default container name, e.g. 'qr-scanner'."},
                "cover_image": {"type": "string", "description": "Path served by marketplace, e.g. '/static/qr.png'. Optional."},
                "output":      {"type": "string", "enum": ["hdmi","rdp","both"], "default": "hdmi"},
                "capabilities": {"type": "array", "items": {"type": "string", "enum": ["camera","npu","gpu","audio","display","network","sensors"]}, "description": "Hardware features the app uses; renders as icon badges on the tile."},
                "ports": {"type": "array", "items": {"type": "integer"}, "description": "Host TCP ports the app needs to publish (e.g. [8501] for Streamlit, [3000, 5000] for a frontend+backend). Marketplace adds -p N:N to docker run AND rejects starts where another running app holds the same port."}
            },
            "required": ["id", "name", "description", "image"]
        }
    },
    {
        "name": "deploy_app",
        "description": (
            "Persist an app across reboots. Installs a systemd unit "
            "(dragonwing-app-<id>.service) that recreates the app's container "
            "at every boot with the same capability-derived docker flags the "
            "marketplace uses, so the app keeps running on a headless device "
            "with no marketplace interaction. Refuses if another deployed app "
            "holds the same exclusive resource (camera/NPU) or port. Use when "
            "the user says deploy / 'make it survive reboots' / 'run at boot'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "App id to deploy."}},
            "required": ["id"]
        }
    },
    {
        "name": "recall_app",
        "description": (
            "Undo deploy_app: disables and removes the app's boot-time systemd "
            "unit. The currently-running container (if any) is left untouched — "
            "use stop_app to stop it now."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "App id to recall."}},
            "required": ["id"]
        }
    }

]

def execute_tool(name, inp, sess=None):
    _t0 = time.time()
    if name == 'bash':
        _summary = (inp.get('command','') or '')[:140].replace('\n', ' ')
        print(f'[tool] bash> {_summary}', flush=True)
    else:
        print(f'[tool] {name}({json.dumps(inp)[:200]})', flush=True)
    if name == 'set_todos':
        todos = inp.get('todos', [])
        if not isinstance(todos, list): return {"error": "todos must be a list"}
        cleaned = []
        for t in todos:
            if not isinstance(t, dict): continue
            text = (t.get('text') or '').strip()
            status = t.get('status') or 'pending'
            if not text: continue
            if status not in ('pending','in_progress','completed','cancelled'): status = 'pending'
            cleaned.append({'text': text, 'status': status})
        if sess is not None:
            sess.todos = cleaned
            sess.emit('todos', {'todos': cleaned})
        return {"ok": True, "count": len(cleaned)}
    if name == 'update_app':
        aid = inp.get('id')
        if not aid or aid not in state:
            return {"error": f"unknown app {aid!r}"}
        MUTABLE = ('cover_image', 'description', 'ports')
        changes = {k: inp[k] for k in MUTABLE if k in inp and inp[k] is not None}
        if not changes:
            return {"error": f"no whitelisted fields; allowed: {list(MUTABLE)}"}
        with state_lock:
            state[aid].update(changes)
        save_state()
        return {"ok": True, "id": aid, "updated": list(changes)}
    if name == 'install_app':
        aid = inp.get('id')
        if not aid:
            return {"error": "id required"}
        with state_lock:
            state[aid] = {
                'id': aid,
                'name': inp.get('name', aid),
                'description': inp.get('description', ''),
                'image': inp.get('image', f"{aid}:latest"),
                'container': inp.get('container', aid),
                'cover_image': inp.get('cover_image'),
                'output': inp.get('output', 'hdmi'),
                'capabilities': inp.get('capabilities', []),
                'ports': [int(p) for p in (inp.get('ports') or []) if isinstance(p, (int, str)) and str(p).lstrip('-').isdigit()],
                # Publishing metadata. Source apps live at /root/apps/<id>/ as a
                # Dockerfile + main.py + assets + models tree; prebuilt apps
                # have only a docker image and cannot be forked.
                'type': inp.get('type', 'source'),
                'base_image': inp.get('base_image', 'ubuntu:24.04'),
                'author': inp.get('author', ''),
                'version': inp.get('version', '0.1.0'),
                'forked_from': inp.get('forked_from'),
            }
        save_state()
        return {"ok": True, "registered": aid}
    if name == 'uninstall_app':
        aid = inp.get('id')
        if aid not in state: return {"error": f"unknown app {aid!r}"}
        if app_deployed(aid):
            try: recall_app(aid)
            except ValueError: pass
        if aid == 'cam-detect': stop_cam()
        else: sh(f"docker rm -f {state[aid].get('container', aid)} 2>/dev/null")
        with state_lock: state.pop(aid, None)
        save_state()
        return {"ok": True, "uninstalled": aid}
    if name == 'deploy_app':
        aid = inp.get('id')
        if aid not in state: return {"error": f"unknown app {aid!r}"}
        try: deploy_app(aid)
        except ValueError as e: return {"error": str(e)}
        return {"ok": True, "deployed": aid, "unit": _deploy_unit_name(aid)}
    if name == 'recall_app':
        aid = inp.get('id')
        if aid not in state: return {"error": f"unknown app {aid!r}"}
        try: recall_app(aid)
        except ValueError as e: return {"error": str(e)}
        return {"ok": True, "recalled": aid}
    if name == 'start_app':
        return do_start_app(inp.get('id'), force=bool(inp.get('force')))
    if name == 'stop_app':
        aid = inp.get('id')
        if aid not in state: return {"error": f"unknown app {aid!r}"}
        if aid == 'cam-detect': stop_cam()
        else: sh(f"docker rm -f {state[aid].get('container', aid)} 2>/dev/null")
        return {"ok": True, "stopped": aid}
    if name == 'set_app_output':
        aid, out = inp.get('id'), inp.get('output')
        if aid not in state: return {"error": f"unknown app {aid!r}"}
        if out not in ('hdmi','rdp','both'): return {"error": "output must be hdmi|rdp|both"}
        with state_lock: state[aid]['output'] = out
        save_state()
        # If running, restart with new target (cam-detect only — generic apps don't have output toggle yet)
        if aid == 'cam-detect' and (container_running('cam-npu-hdmi') or container_running('cam-npu-rdp') or container_running('cam-npu')):
            stop_cam(); start_cam()
        return {"ok": True, "id": aid, "output": out}
    if name == 'list_apps':
        with state_lock: ids = list(state.keys())
        return {"apps": [app_view(i) for i in ids]}

    if name == 'bash':
        # Run via Popen in a new process group so cancel can SIGKILL the entire
        # subtree (shell + descendants). start_new_session=True puts the child
        # in its own session; os.killpg(pgid, SIGKILL) then kills it and anything
        # it spawned (e.g. docker build runs).
        cmd = inp.get('command', '')
        if not (cmd or '').strip():
            return {"exit_code": -1, "output":
                    "[error: empty command — pass a shell command string in 'command']"}
        to = min(int(inp.get('timeout', 180)), 900)
        try:
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, start_new_session=True)
        except Exception as e:
            return {"exit_code": -1, "output": f"[failed to spawn shell: {e!r}]"}
        if sess is not None: sess.proc = proc
        killed = False
        try:
            stdout, stderr = proc.communicate(timeout=to)
        except subprocess.TimeoutExpired:
            try: os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception: pass
            stdout, stderr = proc.communicate()
            stderr = (stderr or b'') + (
                f'\n[timed out after {to}s and was killed. For longer work pass '
                f'{{"timeout": <seconds>}} (max 900), or start it detached with '
                f'nohup ... > /tmp/log 2>&1 & and poll the log.]').encode()
        finally:
            if sess is not None and sess.proc is proc: sess.proc = None
            if sess is not None and sess.cancel_flag.is_set():
                killed = True
        rc = proc.returncode
        body = (stdout or b'').decode('utf-8', 'replace') + (stderr or b'').decode('utf-8', 'replace')
        if killed: body += '\n[killed by user cancel]'
        print(f'[tool] bash exit={rc} {len(body)}B in {time.time()-_t0:.2f}s', flush=True)
        if len(body) > 60000:
            body = body[:30000] + f"\n\n... [output truncated, {len(body)} bytes total] ...\n\n" + body[-30000:]
        return {"exit_code": rc, "output": body}
    return {"error": f"unknown tool {name!r}"}

def _parse_base_url(base_url):
    """Return (scheme, host, path_prefix) for an optional base URL like
    'http://192.168.86.40:9099' or 'https://gateway.example.com/anthropic'.
    Default to https://api.anthropic.com."""
    if not base_url: return 'https', ANTHROPIC_HOST, ''
    from urllib.parse import urlparse
    u = urlparse(base_url if '://' in base_url else 'https://' + base_url)
    scheme = u.scheme or 'https'
    host = u.netloc or ANTHROPIC_HOST
    prefix = (u.path or '').rstrip('/')
    return scheme, host, prefix

def _open_conn(scheme, host, timeout):
    if scheme == 'http':
        return http.client.HTTPConnection(host, timeout=timeout)
    return http.client.HTTPSConnection(host, timeout=timeout)

def anthropic_call(api_key, messages, system=None, base_url=None, model=None):
    """Non-streaming Anthropic call. Returns parsed response dict."""
    payload = {
        "model": model or ANTHROPIC_MODEL,
        "max_tokens": 16000,
        "messages": messages,
        "tools": TOOLS,
    }
    if system: payload["system"] = system
    scheme, host, prefix = _parse_base_url(base_url)
    conn = _open_conn(scheme, host, 300)
    conn.request("POST", prefix + "/v1/messages", json.dumps(payload), {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    })
    resp = conn.getresponse()
    data = resp.read().decode()
    conn.close()
    try:
        return json.loads(data), resp.status
    except json.JSONDecodeError:
        return {"error": data}, resp.status


SESSIONS_DIR = '/var/lib/dragonwing-sessions'
os.makedirs(SESSIONS_DIR, exist_ok=True)

def save_session(sid):
    sess = sessions.get(sid)
    if sess is None or not isinstance(sess, SessionState): return
    try:
        path = os.path.join(SESSIONS_DIR, sid + '.json')
        # Mark 'running' as 'interrupted' on disk so resumers know
        status_on_disk = sess.status if sess.status != 'running' else 'interrupted'
        data = {
            'session_id': sid,
            'messages': sess.messages,
            'events': sess.events,
            'status': status_on_disk,
            'last_user': sess.last_user,
            'name': sess.name,
            'created_ts': sess.created_ts,
            'updated_ts': sess.updated_ts,
        }
        tmp = path + '.tmp'
        with open(tmp, 'w') as f: json.dump(data, f)
        os.replace(tmp, path)
    except Exception as e:
        print(f'[session] save error sid={sid[:8]}: {e!r}', flush=True)

def save_session_for(sess):
    if sess and sess.sid: save_session(sess.sid)


def _heal_orphan_tool_uses(messages):
    """When a process restart kills the agent between tool_use and tool_result,
    Anthropic rejects subsequent calls with 400. Inject a synthetic tool_result
    for any dangling tool_use so the API contract is satisfied."""
    healed = 0
    fixed = []
    i = 0
    while i < len(messages):
        m = messages[i]
        fixed.append(m)
        if m.get('role') == 'assistant' and isinstance(m.get('content'), list):
            tu_ids = [b.get('id') for b in m['content'] if b.get('type') == 'tool_use' and b.get('id')]
            if tu_ids:
                nxt = messages[i+1] if i+1 < len(messages) else None
                ok = False
                if nxt and nxt.get('role') == 'user' and isinstance(nxt.get('content'), list):
                    got = {b.get('tool_use_id') for b in nxt['content'] if b.get('type') == 'tool_result'}
                    ok = set(tu_ids).issubset(got)
                if not ok:
                    fixed.append({"role": "user", "content": [
                        {"type": "tool_result", "tool_use_id": tu_id,
                         "content": json.dumps({"exit_code": -1, "output": "[tool interrupted by service restart]"})}
                        for tu_id in tu_ids
                    ]})
                    healed += len(tu_ids)
        i += 1
    return fixed, healed

def load_sessions():
    if not os.path.isdir(SESSIONS_DIR): return
    n = 0
    for fn in os.listdir(SESSIONS_DIR):
        if not fn.endswith('.json'): continue
        try:
            with open(os.path.join(SESSIONS_DIR, fn)) as f: data = json.load(f)
            sid = data['session_id']
            sess = SessionState()
            sess.messages = data.get('messages', [])
            healed_msgs, n_heal = _heal_orphan_tool_uses(sess.messages)
            if n_heal:
                print(f'[session] healed {n_heal} orphan tool_use(s) on load for sid={data["session_id"][:8]}', flush=True)
                sess.messages = healed_msgs
            sess.events   = data.get('events', [])
            # 'interrupted' means it was running when the process died — surface as 'cancelled'
            s = data.get('status', 'done')
            sess.status = 'cancelled' if s == 'interrupted' else s
            # ----- UI-side healing of the events buffer (separate from message
            # healing above, which only fixes the Anthropic API contract). The
            # browser replays this buffer to reconstruct the chat thread, so any
            # orphan tool_use here renders as a "running…" pill forever.
            sealed = 0
            tu_seen = {}   # id -> idx of tool_use
            tr_done = set()
            for e in sess.events:
                if e.get('evt') == 'tool_use':
                    tu_seen[e['data'].get('id')] = e['idx']
                elif e.get('evt') == 'tool_result':
                    tr_done.add(e['data'].get('id'))
            now = time.time()
            for tu_id, _ in tu_seen.items():
                if tu_id and tu_id not in tr_done:
                    sess.events.append({
                        'idx': len(sess.events), 'evt': 'tool_result',
                        'data': {'id': tu_id, 'name': 'bash',
                                 'output': {'exit_code': -1, 'output': '[tool interrupted; session resumed]'}},
                        'ts': now,
                    })
                    sealed += 1
            # If the very last buffered event is a thinking_start with no matching
            # end, append synthetic thinking_end + cancelled + done so the UI
            # doesn't show a stale "thinking…" indicator on reopen.
            if sess.events and sess.events[-1].get('evt') == 'thinking_start':
                for evt, data2 in (('thinking_end', {'elapsed_ms': 0}),
                                   ('cancelled', {'reason': 'service restarted mid-hop'}),
                                   ('done', {'status': 'cancelled'})):
                    sess.events.append({'idx': len(sess.events), 'evt': evt, 'data': data2, 'ts': now})
                sealed += 3
            if sealed:
                print(f'[session] sealed {sealed} orphan event(s) for sid={data["session_id"][:8]}', flush=True)
            sess.last_user = data.get('last_user', '')
            sess.name = data.get('name', '')
            sess.created_ts = data.get('created_ts', time.time())
            sess.updated_ts = data.get('updated_ts', time.time())
            sessions[sid] = sess
            # If we sealed any orphans, persist the healed state so next load is a no-op.
            if sealed or n_heal: save_session(sid)
            n += 1
        except Exception as e:
            print(f'[session] load error {fn}: {e!r}', flush=True)
    print(f'[session] loaded {n} sessions from disk', flush=True)

# In-memory chat sessions: session_id -> SessionState
class SessionState:
    __slots__ = ('sid','messages','events','lock','cond','status','cancel_flag','thread','last_user','created_ts','updated_ts','proc','name','todos','usage_totals')
    def __init__(self, sid=None):
        self.sid = sid
        self.messages = []           # Anthropic messages history
        self.events = []             # [{idx, evt, data, ts}]
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.status = 'idle'         # idle | running | done | error | cancelled
        self.cancel_flag = threading.Event()
        self.proc = None  # currently-running bash subprocess (Popen), so cancel can kill it
        self.thread = None
        self.last_user = ''
        self.name = ''               # human-readable label for the sidebar list
        self.todos = []              # set_todos tool's current checklist for this turn
        self.created_ts = time.time()
        self.updated_ts = self.created_ts
    def emit(self, evt, data):
        with self.cond:
            e = {'idx': len(self.events), 'evt': evt, 'data': data, 'ts': time.time()}
            self.events.append(e)
            self.updated_ts = e['ts']
            self.cond.notify_all()
        # Persist to disk so a process restart doesn't lose the session.
        # Cheap (few KB), only one writer per session at a time, atomic rename.
        try: save_session_for(self)
        except Exception: pass

sessions = {}            # sid -> SessionState
sessions_lock = threading.Lock()


# The prompt is a template, not a constant: every hardware fact in it is
# detected from the running device (see detect_hardware) so the agent starts
# each session knowing the real board, SoC, NPU and camera state. Tokens are
# substituted with str.replace because the body is full of literal {braces}.
SYSTEM_PROMPT_TEMPLATE = """You are the Dragonwing AI Developer Agent, an embedded-dev assistant that lives on @@HW_INTRO@@. You run as root on the host and have full unrestricted shell access via the `bash` tool — there is no sandbox, no confirmation step, no guardrails. The user wants a Claude-Code-style power-user experience.

The platform facts in this prompt were read from the device itself at service start (device-tree, /sys/devices/soc0, the QNN HTP skel libraries, the kgsl GPU node). Trust them over assumptions about any specific board, and when you need a hardware detail that isn't listed, read it from the device rather than guessing.

# How to work — persistence rules (read this every turn)

When the user gives you a task, the implicit contract is: **drive it to verified completion**, not to a polite stopping point. Stopping early to "summarize what I've done so far" or "tell the user the next step" is failure, not progress.

- **Never end your turn while there is concrete pending work you can do yourself.** "Now I need to X" / "Next I'll Y" inside your text is a signal to KEEP GOING, not to stop. Just do X, then verify, then do Y.
- **Empty/zero-output tool calls are bugs to fix, not signals to stop.** If a `bash` call returned 0 bytes or exit≠0, you misformed it. Re-read the failure, fix the command, retry. Do not emit a summary text and stop after a broken tool call — that's the single most common way you waste the user's time.
- **Verify before declaring done.** Before saying a task is complete, prove it:
    - File written? `cat` it back, or grep for the key lines you intended.
    - Image built? `docker images | grep <id>` shows it.
    - Container running? `docker ps | grep <name>` AND check the feed/jpg mtime or first 10 log lines.
    - App installed? `curl /api/apps | python3 -m json.tool | grep <id>` shows it.
- **Self-check at the end of every text reply** (silently, before emitting): "Did I actually finish what the user asked, or am I about to stop in the middle?" If the latter, suppress the summary and emit another tool call instead.
- **Only ask the user a question when it's genuinely blocking** — a choice between equally valid paths, missing credentials, or destructive action confirmation. Don't ask for permission to do the obvious next step.
- **Hop budget is generous (40)**. Use it. A real app build will take 15-25 hops. Don't pace yourself for brevity.

# When the user says "build me X"

That means: design → write source → build image → register tile → start it → verify it runs and produces output → report with the verified evidence (`docker ps` line, feed jpg path, fps if available). All in one turn. Not "I'll write the Dockerfile next time."

# When the user says "fix Y"

Reproduce the failure first (run the failing command, read the actual error), then fix, then rerun to confirm the fix worked. Don't trust your first guess; let the error tell you.



You are aware of:
- The host: @@HOST_FACTS@@
- @@CAMERA_LINE@@
- A running marketplace at http://localhost:8080 (this app); systemd service `dragonwing-marketplace.service`.
- A "Deal With It" object detection container `cam-npu-hdmi`/`cam-npu-rdp` (image `rubikpi3-cam-test:npu`) — YOLOv8 on NPU, draws sunglasses on faces, renders to Weston via `wayland-1` (HDMI) or `wayland-rdp` (RDP on port 3389).

Workflow conventions:
- Use the `bash` tool proactively to inspect, diagnose, fix, build, and deploy. Do not ask for permission.
- For long-running tasks (docker build, yocto build, etc.), pass an explicit `timeout`.
- When the user asks to build a new app on this platform, the canonical workflow is:

1. **Always start from the template at `/root/apps/_template/`.** It already solves the hard things we hit the first time around:
   - Base image must be `ubuntu:24.04` (GLIBC 2.39+) because the host's libcdsprpc.so requires it.
   - Use `ai-edge-litert` for TFLite (no `tflite-runtime` wheel for py3.12+).
   - Install `opencv-data` to get Haar cascades; `python3-opencv` alone lacks `cv2.data`.
   - Install `libyaml-0-2` or QNN HtpProvider silently fails.
   - GStreamer in/out pipelines must use BGR appsrc/appsink, not dmabuf.
   - The runtime expects `/usr/lib/dsp`, `/usr/lib/firmware`, `/sys/class/thermal`, libcdsprpc.so bind-mounts.
   Read `/root/apps/_template/README.md` for the full list, then `cp -r /root/apps/_template /root/apps/<id>` and modify `main.py`'s `process_frame()`.

2. For models: prefer compiling on Qualcomm AI Hub targeting "Dragonwing RB3 Gen 2 Vision Kit", runtime tflite, precision w8a8. To run the export, use the `qai-export:latest` Docker image AND mount the host's `~/.qai_hub` directory containing the API token, plus an output dir:

    docker run --rm \
      -v /root/.qai_hub:/root/.qai_hub:ro \
      -v /root/qai-cache/<model>:/work \
      -w /work \
      qai-export:latest \
      'yes | python3 -m qai_hub_models.models.<name>.export \
         --target-runtime tflite \
         --device "Dragonwing RB3 Gen 2 Vision Kit" --device-os 1.6 \
         --precision w8a8'

   Without `-v /root/.qai_hub:/root/.qai_hub:ro` the qai-hub CLI silently falls back to "Unable to find API token" and produces no compiled artifact (you will see ~6 sec runs with ~1 KB output instead of the 5-10 min AI Hub job). The resulting tflite ends up at `/work/export_assets/<name>-tflite-w8a8/<name>.tflite`.

3. After `docker build -t <id>:latest .` succeeds, call the `install_app` tool to register the tile.

4. The marketplace handles `docker run` invocation automatically when the user clicks Launch — do not write your own start scripts.

**Fullscreen apps must be closable from the screen.** When an app renders fullscreen (FULLSCREEN / waylandsink fullscreen=true), the template automatically shows a red X in the top-right corner that the user clicks to stop the app: `closebtn.py` reads the USB mouse directly (the marketplace grants /dev/input access to apps with the `camera` or `display` capability) and calls the marketplace stop API. It is wired into `/root/apps/_template/` (closebtn.py plus a few lines in main.py) and no-ops safely when no mouse is present, so it never crashes the app. KEEP IT: never ship a fullscreen app the user cannot close from the HDMI screen. It comes for free when you start from the template; do not strip closebtn out. Only remove it if the user explicitly asks for a locked kiosk with no on-screen exit.

**Keep apps portable across Dragonwing boards.** Ship the quantized w8a8 `.tflite` in the app, NEVER a SoC-locked QNN context binary (`.bin`). The marketplace mounts a per-board HTP cache and sets `QNN_CACHE_DIR`, and the template loader passes it to the QNN delegate as `cache_dir`, so the model compiles for THIS Hexagon once and restores instantly on later launches. That makes a `.dwapp` shareable to any Dragonwing board and optimized on arrival. When exporting from AI Hub, produce the runtime tflite (w8a8) and let the delegate compile locally; do not bake a device-locked context into the bundle.

Tools you have:
  - bash(command, timeout)            — full root shell. Use freely.
  - set_todos({todos: [{text, status}]}) — maintain a visible plan checklist. Call at the start of any multi-step task with a plan, then update as items move pending → in_progress → completed. Shows the user what you're doing.
  - list_apps()                       — see what's currently installed/running.
  - install_app({id,name,description,image,cover_image,capabilities,output,type,version,author,base_image}) — register a new tile after `docker build`. Default type='source' assumes /root/apps/<id>/ holds the Dockerfile and main.py (forkable + exportable).
  - uninstall_app({id})               — delete a tile and stop its container.
  - start_app({id}) / stop_app({id}) — equivalent to the user clicking Launch/Stop.
  - set_app_output({id, output})      — switch hdmi|rdp|both for camera apps.
  - deploy_app({id}) / recall_app({id}) — install/remove a systemd unit (dragonwing-app-<id>.service) that relaunches the app at every boot. Deploy = survives reboots without the marketplace; recall = back to manual launches. Deploy refuses while another deployed app holds the same exclusive capability or port.

Use `set_todos` aggressively. Any task that takes more than 3 hops should start with a plan. Update it as you go — the user is watching the checklist tick.

When a user message starts a NEW multi-step task in an already-running session, the UI auto-clears the previous plan on send, so issue `set_todos` again with the new plan as your first action — don't assume the prior plan is still visible. For quick single-shot Q&A turns, no plan is needed and leaving it empty is correct.

**Never edit `/root/marketplace/marketplace.py`, `/root/marketplace/html.py`, or anything under `/root/marketplace/static/` on the running device.** Those files belong to the host runtime, not to any app you're working on. The legitimate channels for marketplace changes are the upstream `EmbeddedAndroid/age` GitHub repo and the vendored Yocto recipe at `meta-qcom-3rdparty/recipes-extended/dragonwing-marketplace/`. If you find a real bug or want to propose an enhancement, **write a unified diff to `/tmp/marketplace-suggestion-<short-description>.patch` and tell the user about it in your text reply** — do NOT apply it. Live edits will fail anyway because the files are chattr-immutable; do not `chattr -i` to work around this. If something obviously broken in the marketplace is blocking your task, surface that to the user as a question, not as a patch.

**Never edit `/var/lib/dragonwing-marketplace.json` or any `/var/lib/dragonwing-*` state file directly, and never `systemctl restart dragonwing-marketplace.service` to "force a state reload".** All app state mutations go through the API and update the in-memory dict + the JSON file atomically in the same call. The relevant endpoints/tools are:
  - `update_app({id, cover_image?, description?})` — change a tile's icon or description (no restart needed)
  - rename via `POST /api/apps/<id>/rename` body `{name}` — change the name
  - `set_app_output` — change hdmi|rdp|both
  - `install_app` / `uninstall_app` — add or remove a tile

If you ever feel the urge to `systemctl restart dragonwing-marketplace.service`, stop — that's a sign the path you're taking is wrong and there's an API call that does the same thing live. The only legitimate reason to restart the service is if YOU just edited `marketplace.py` itself or one of its `static/*` files in a way that needs Python to re-import.

When asked to "remove" or "delete" an app, prefer `uninstall_app` over a `bash`+`curl`. When asked "what's installed" or "is X running", call `list_apps` rather than parsing `docker ps` output.

Capabilities (declare in `install_app({capabilities: [...]})`, applied by the marketplace at `docker run` time):
  - `camera`     → /dev mapped + video4linux cgroup rule (apps scan /dev/video* themselves), `CAM_DEVICE` env hint. Exclusive. Apps with this capability cannot start while no USB camera is attached — the marketplace refuses with reason "no_camera" and the UI greys the tile.
  - `npu`        → FastRPC + QNN bind-mounts, `ADSP_LIBRARY_PATH`, `QNN_BACKEND=htp`, `/opt/qnn`. Exclusive.
  - `display`    → `/run/user/1000` + `WAYLAND_DISPLAY` (wayland-1 for HDMI, wayland-rdp for RDP).
  - `sensors`    → **`--privileged`** + `/sys/class/leds:rw` + `--user 0:0`. Declare this for any app that needs raw I/O: writing LED brightness, reading sysfs sensors, GPIO toggling, /dev/i2c-*, /dev/spidev*, etc. This is the right way to request privileged I/O — do not write your own `--privileged` flag into a Dockerfile or compose; declaring `sensors` in capabilities is the supported path.

Resource contention:
  - The platform has exclusive resources: the USB camera and the NPU (HTP backend).
  - Two apps with capability "camera" or "npu" cannot run simultaneously.
  - Host TCP ports: declare them in `install_app({ports: [8501, ...]})` for any app that exposes a web UI / API. The marketplace publishes each port via `docker run -p N:N` automatically, and refuses to launch a second app that overlaps with a port already held by a running one. The conflicts entries look like `{resource: "port:8501", held_by: "<aid>"}`.
  - **Picking a port for a NEW or FORKED app**: never just reuse a tutorial default — call `list_apps` first, collect every `ports[]` value across installed apps, and pick something that doesn't overlap. Also avoid `:8080` (marketplace itself) and `:3389` (weston-rdp); the marketplace flags those as held by `__marketplace__` and the conflict can't be force-preempted. Reasonable ranges to draw from: `8501-8599` for Streamlit/Gradio web UIs, `5000-5099` for Flask/FastAPI backends, `7000-7099` for general HTTP services. Pick the lowest free port in the range so users get predictable URLs.
  - `start_app` will return {ok: false, conflicts: [...]} if any resource (cap OR port) is held.
  - To proceed anyway, call `start_app({id, force: true})` — the holder is auto-stopped first.
  - When the user asks to launch app B while app A holds the resource, prefer asking the user before passing force=true. When it's obvious (e.g., the user said "switch from A to B"), force is fine.
- Prefer concise, direct responses. Show the user what you did via tool calls; they're visible in the UI.
"""

def build_system_prompt():
    """Substitute detected hardware facts into the prompt template. Called
    once per user turn so the camera line reflects live state without
    invalidating the API prompt cache between hops of the same turn."""
    hw_intro = []
    if HW.get('board'): hw_intro.append(f"a {HW['board']} board")
    soc_bits = [b for b in (
        f"Qualcomm {HW['soc']} SoC" if HW.get('soc') else None,
        f"Hexagon {HW['hexagon']} NPU" if HW.get('hexagon') else None,
        f"{HW['gpu']} GPU" if HW.get('gpu') else None) if b]
    if soc_bits: hw_intro.append('(' + ', '.join(soc_bits) + ')')
    intro = ' '.join(hw_intro) or 'a Qualcomm Dragonwing board'

    host = []
    if HW.get('distro'): host.append(HW['distro'])
    if HW.get('kernel'): host.append(f"kernel {HW['kernel']}")
    if HW.get('mesa'): host.append(f"Mesa {HW['mesa']}")
    if HW.get('gpu'): host.append(f"{HW['gpu']} GPU")
    host.append(f"Hexagon {HW['hexagon']} NPU reachable via FastRPC + QNN HTP"
                if HW.get('hexagon') else
                "no Hexagon NPU detected (QNN HTP skel libraries not found)")
    if HW.get('cpu_cores'): host.append(f"{HW['cpu_cores']} CPU cores")
    if HW.get('mem_gb'): host.append(f"{HW['mem_gb']} GB RAM")

    cam = ("A USB camera is currently connected."
           if camera_present() else
           "NO USB camera is currently connected — camera apps cannot start until one is plugged in; tiles for them are greyed out in the UI.")

    return (SYSTEM_PROMPT_TEMPLATE
            .replace('@@HW_INTRO@@', intro)
            .replace('@@HOST_FACTS@@', ', '.join(host) + '.')
            .replace('@@CAMERA_LINE@@', cam))


def npu_inference_ms():
    """Per-frame NPU inference latency (ms) parsed from the running NPU
    app's telemetry line (e.g. '... 30.0 fps  yolo=5.8ms face=3.1ms  loop='
    -> 8.9, the sum of model inferences between 'fps' and 'loop='). None
    when no NPU app is running. The Hexagon NPU exposes no freq/util counter,
    so model inference latency is the meaningful NPU perf signal."""
    try:
        for aid, a in list(state.items()):
            if 'npu' not in (a.get('capabilities') or []):
                continue
            run = next((c for c in app_containers(aid) if container_running(c)), None)
            if not run:
                continue
            r = sh(f"docker logs --tail 15 {run} 2>&1", timeout=4)
            val = None
            for line in (r.stdout or '').splitlines():
                m = re.search(r'fps(.*?)loop=', line)
                if not m:
                    continue
                ms = re.findall(r'=\s*([\d.]+)\s*ms', m.group(1))
                if ms:
                    val = round(sum(float(x) for x in ms), 1)
            if val is not None:
                return val
        return None
    except Exception:
        return None


# --- Performance metrics collector ---------------------------------------
class Metrics:
    """Samples /sys + /proc. Persistent across requests so we can compute deltas."""
    def __init__(self):
        self.last_cpu = None       # (total, busy)
        self.last_disk = None      # (read_sectors, write_sectors, ts)
        self.last_net = None       # (rx, tx, ts)
        self.primary_net = self._pick_net()
    def _pick_net(self):
        # Prefer a routed iface with bytes flowing; skip lo, virbr, veth, docker
        try:
            best = None; best_bytes = -1
            for d in os.listdir('/sys/class/net'):
                if d in ('lo',) or d.startswith(('veth','virbr','docker','br-')): continue
                try:
                    rx = int(open(f'/sys/class/net/{d}/statistics/rx_bytes').read())
                except Exception: continue
                if rx > best_bytes: best = d; best_bytes = rx
            return best
        except Exception: return None
    def _cpu_pct(self):
        try:
            parts = open('/proc/stat').readline().split()[1:9]
            user, nice, sys_, idle, iowait, irq, softirq, steal = [int(p) for p in parts]
            total = user+nice+sys_+idle+iowait+irq+softirq+steal
            busy  = total - idle - iowait
            now = (total, busy)
            if self.last_cpu is None:
                self.last_cpu = now; return 0.0
            dt = now[0] - self.last_cpu[0]; db = now[1] - self.last_cpu[1]
            self.last_cpu = now
            return round(100.0 * db / dt, 1) if dt > 0 else 0.0
        except Exception:
            return None
    def _meminfo(self):
        out = {}
        try:
            for line in open('/proc/meminfo'):
                k, _, rest = line.partition(':')
                out[k] = int(rest.strip().split()[0])
        except Exception: pass
        return out
    def _thermals(self):
        # Generic across SoCs: classify zones by name family and report the
        # hottest per class. Known NPU spellings: nspss (QCS6490), nsp-N-N
        # (QCS8275), npu*, hexagon*, cdsp*. CPU: cpu*/apc*/silver/gold/cluster.
        cpu, npu, gpu = None, None, None
        for z in os.listdir('/sys/class/thermal'):
            if not z.startswith('thermal_zone'): continue
            try:
                t = open(f'/sys/class/thermal/{z}/type').read().strip().lower()
                v = int(open(f'/sys/class/thermal/{z}/temp').read().strip())/1000.0
            except Exception: continue
            if v <= 0: continue
            if t.startswith(('nsp', 'npu', 'hexagon', 'cdsp')):
                npu = v if npu is None else max(npu, v)
            elif t.startswith('gpu'):
                gpu = v if gpu is None else max(gpu, v)
            elif t.startswith(('cpu', 'apc', 'silver', 'gold', 'cluster')):
                cpu = v if cpu is None else max(cpu, v)
        return cpu, npu, gpu
    def _devfreq(self, dev):
        try:
            cur = int(open(f'/sys/class/devfreq/{dev}/cur_freq').read().strip())
            mx  = int(open(f'/sys/class/devfreq/{dev}/max_freq').read().strip())
            return cur, mx
        except Exception:
            return None, None
    def _rproc_state(self, n):
        try: return open(f'/sys/class/remoteproc/{n}/state').read().strip()
        except Exception: return None
    def _disk_delta(self):
        # Sum reads/writes across all 'real' block devices (skip loop, ram)
        try:
            tot_r = tot_w = 0
            for line in open('/proc/diskstats'):
                f = line.split()
                if len(f) < 14: continue
                name = f[2]
                if name.startswith(('loop','ram','dm-')): continue
                # Only top-level devices (sda, mmcblk0, nvme0n1), not partitions
                if any(c.isdigit() for c in name[-1:]) and not name.startswith(('nvme','mmcblk')):
                    continue
                tot_r += int(f[5])  # sectors read
                tot_w += int(f[9])  # sectors written
            now = (tot_r, tot_w, time.time())
            if self.last_disk is None:
                self.last_disk = now; return 0.0, 0.0
            dt = now[2] - self.last_disk[2]
            if dt <= 0: return 0.0, 0.0
            r_kbps = (now[0] - self.last_disk[0]) * 512 / 1024.0 / dt
            w_kbps = (now[1] - self.last_disk[1]) * 512 / 1024.0 / dt
            self.last_disk = now
            return round(r_kbps, 1), round(w_kbps, 1)
        except Exception:
            return None, None
    def _net_delta(self):
        if not self.primary_net: return None, None
        try:
            rx = int(open(f'/sys/class/net/{self.primary_net}/statistics/rx_bytes').read())
            tx = int(open(f'/sys/class/net/{self.primary_net}/statistics/tx_bytes').read())
            now = (rx, tx, time.time())
            if self.last_net is None:
                self.last_net = now; return 0.0, 0.0
            dt = now[2] - self.last_net[2]
            if dt <= 0: return 0.0, 0.0
            rx_mbps = (now[0] - self.last_net[0]) * 8 / 1e6 / dt
            tx_mbps = (now[1] - self.last_net[1]) * 8 / 1e6 / dt
            self.last_net = now
            return round(rx_mbps, 2), round(tx_mbps, 2)
        except Exception:
            return None, None
    def sample(self):
        m = self._meminfo()
        cpu_c, npu_c, gpu_c = self._thermals()
        gpu_cur, gpu_max = self._devfreq('3d00000.gpu')
        try:
            la = open('/proc/loadavg').read().split()
            load_1m, load_5m, load_15m, tasks = float(la[0]), float(la[1]), float(la[2]), la[3]
        except Exception:
            load_1m = load_5m = load_15m = None; tasks = None
        dr, dw = self._disk_delta()
        nr, nt = self._net_delta()
        return {
            'cpu_pct': self._cpu_pct(),
            'mem_total_kb':   m.get('MemTotal'),
            'mem_avail_kb':   m.get('MemAvailable'),
            'mem_used_pct':   round(100 * (m['MemTotal'] - m['MemAvailable']) / m['MemTotal'], 1) if m.get('MemTotal') and m.get('MemAvailable') else None,
            'gpu_mhz':        round(gpu_cur/1e6, 0) if gpu_cur else None,
            'gpu_max_mhz':    round(gpu_max/1e6, 0) if gpu_max else None,
            'gpu_pct':        round(100*gpu_cur/gpu_max, 1) if gpu_cur and gpu_max else None,
            'cpu_c': cpu_c, 'npu_c': npu_c, 'gpu_c': gpu_c,
            'npu_ms': npu_inference_ms(),
            'cdsp_state': self._rproc_state('remoteproc1'),
            'adsp_state': self._rproc_state('remoteproc0'),
            'load_1m':  load_1m, 'load_5m':  load_5m, 'load_15m': load_15m, 'tasks': tasks,
            'disk_r_kbps': dr, 'disk_w_kbps': dw,
            'net_iface':  self.primary_net,
            'net_rx_mbps': nr, 'net_tx_mbps': nt,
        }

_metrics = Metrics()
_metrics.sample()  # prime delta state


def run_agent_turn(sid, api_key, user_msg, base_url=None, model=None):
    """Run a single user turn in the background. Emits events into sess.events as we go."""
    sess = sessions.get(sid)
    if sess is None: return
    sess.status = 'running'
    sess.messages.append({"role": "user", "content": user_msg})
    sess.emit('user', {'text': user_msg})
    # Stable within a turn (keeps the API prompt cache warm across hops),
    # rebuilt between turns so camera state stays truthful.
    system_prompt = build_system_prompt()
    try:
        for hop in range(80):  # raised from 40 — complex app builds (docker build + apt + qai-export) routinely chain 50+ tool calls
            if sess.cancel_flag.is_set():
                sess.emit('cancelled', {}); sess.status = 'cancelled'; return
            # Defensive: heal any orphan tool_use blocks that slipped through
            # (e.g. an earlier turn was cancelled between tool_use and tool_result).
            sess.messages, healed = _heal_orphan_tool_uses(sess.messages)
            if healed:
                print(f'[chat] sid={sid[:8]} healed {healed} orphan(s) before hop {hop}', flush=True)
            print(f'[chat] sid={sid[:8]} hop={hop} → anthropic ({len(sess.messages)} messages)', flush=True)
            sess.emit('thinking_start', {'hop': hop, 'message_count': len(sess.messages)})
            _t = time.time()
            resp, status = anthropic_call(api_key, sess.messages, system=system_prompt, base_url=base_url, model=model)
            sess.emit('thinking_end', {'elapsed_ms': int((time.time()-_t)*1000)})
            if status != 200:
                print(f'[chat] sid={sid[:8]} anthropic error {status}', flush=True)
                sess.emit('error', {'status': status, 'detail': resp.get('error', resp)})
                sess.status = 'error'; return
            u = resp.get('usage') or {}
            tot = getattr(sess, 'usage_totals', None) or {
                'input_tokens': 0, 'output_tokens': 0,
                'cache_read_input_tokens': 0, 'cache_creation_input_tokens': 0}
            for k in tot:
                tot[k] += int(u.get(k) or 0)
            sess.usage_totals = tot
            sess.emit('usage', {
                'last': u, 'totals': tot,
                'context_tokens': sum(int(u.get(k) or 0) for k in
                    ('input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')),
            })
            assistant_blocks = resp.get('content', [])
            sess.messages.append({"role": "assistant", "content": assistant_blocks})
            tool_results = []
            has_tool_use = any(b.get('type') == 'tool_use' for b in assistant_blocks)
            try:
                for block in assistant_blocks:
                    if sess.cancel_flag.is_set():
                        sess.emit('cancelled', {}); sess.status = 'cancelled'; return
                    btype = block.get('type')
                    if btype == 'text':
                        sess.emit('text', {'text': block.get('text', '')})
                    elif btype == 'tool_use':
                        name = block.get('name'); inp = block.get('input', {}); tu_id = block.get('id')
                        sess.emit('tool_use', {'id': tu_id, 'name': name, 'input': inp})
                        out = execute_tool(name, inp, sess=sess)
                        sess.emit('tool_result', {'id': tu_id, 'name': name, 'output': out})
                        tool_results.append({"type":"tool_result","tool_use_id":tu_id,"content":json.dumps(out)})
            finally:
                # Structural guarantee: every tool_use in the assistant message
                # gets a matching tool_result, even if the loop returned early
                # on cancel or an exception was raised. Pad any missing entries
                # with synthetic results so the Anthropic API contract holds.
                if has_tool_use:
                    done_ids = {tr["tool_use_id"] for tr in tool_results}
                    for b in assistant_blocks:
                        if b.get('type') == 'tool_use' and b.get('id') not in done_ids:
                            tool_results.append({
                                "type": "tool_result", "tool_use_id": b["id"],
                                "content": json.dumps({"exit_code": -1, "output": "[interrupted before completion]"}),
                            })
                    sess.messages.append({"role": "user", "content": tool_results})
            stop = resp.get('stop_reason')
            if stop == 'tool_use':
                continue
            if stop == 'max_tokens':
                # Output truncated mid-response (usually a huge tool call,
                # e.g. writing a whole file in one heredoc). Any tool call in
                # it was incomplete; tell the model and keep the turn going
                # so it can redo the work in smaller pieces.
                note = ("[system note: your previous response hit the max_tokens "
                        "output limit and was truncated. Any tool call above was "
                        "incomplete and its result is invalid. Redo that action in "
                        "smaller steps - write large files in chunks using an "
                        "initial cat > file <<'EOF' followed by cat >> file <<'EOF' "
                        "appends of ~100 lines each, then verify with wc -c and "
                        "py_compile before continuing.]")
                if has_tool_use and sess.messages and isinstance(sess.messages[-1].get('content'), list):
                    sess.messages[-1]['content'].append({"type": "text", "text": note})
                else:
                    sess.messages.append({"role": "user", "content": note})
                sess.emit('text', {'text': '\n\n[response hit max_tokens - asking agent to retry in smaller chunks]'})
                continue
            break
        else:
            # Loop completed without breaking → exhausted the hop budget.
            sess.emit('text', {'text': '\n\n[ran out of tool hops in this turn — send any message to continue]'})
    except Exception as e:
        sess.emit('error', {'detail': repr(e)}); sess.status = 'error'; return
    finally:
        if sess.status == 'running': sess.status = 'done'
        sess.emit('done', {'status': sess.status})
        print(f'[chat] sid={sid[:8]} {sess.status} · {len(sess.messages)} messages', flush=True)


# --- HTTP server ----------------------------------------------------------
class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('content-type', 'application/json')
        self.send_header('content-length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, fname, ct):
        fp = os.path.join(STATIC, fname)
        if not os.path.isfile(fp): return self.send_error(404)
        with open(fp, 'rb') as f: data = f.read()
        self.send_response(200)
        self.send_header('content-type', ct)
        self.send_header('content-length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---- GET ----
    def do_GET(self):
        if self.path in ('/', '/index.html'):
            return self._serve_static('index.html', 'text/html; charset=utf-8')
        if self.path == '/favicon.ico':
            return self._serve_static('favicon.png', 'image/png')
        if self.path.startswith('/static/'):
            p = self.path.removeprefix('/static/')
            ct = ('text/css' if p.endswith('.css') else
                  'application/javascript' if p.endswith('.js') else
                  'image/png' if p.endswith('.png') else
                  'image/svg+xml' if p.endswith('.svg') else
                  'application/octet-stream')
            return self._serve_static(p, ct)
        if self.path == '/api/system/camera':
            return self._json(200, {'present': camera_present()})
        if self.path == '/api/system/info':
            info = dict(HW)
            info['camera'] = camera_present()
            info['summary'] = hw_summary()
            return self._json(200, info)

        if self.path.startswith('/api/feed/'):
            name = self.path.rsplit('/', 1)[-1].split('?', 1)[0]
            if not re.match(r'^[\w-]+\.jpg$', name): return self.send_error(400)
            fp = '/var/lib/dragonwing-feeds/' + name
            if not os.path.isfile(fp): return self.send_error(404)
            with open(fp, 'rb') as f: data = f.read()
            self.send_response(200)
            self.send_header('content-type', 'image/jpeg')
            self.send_header('content-length', str(len(data)))
            self.send_header('cache-control', 'no-cache, no-store, must-revalidate')
            self.end_headers(); self.wfile.write(data); return
        if self.path == '/api/apps':
            with state_lock: ids = list(state.keys())
            return self._json(200, [app_view(i) for i in ids])

        m = re.match(r'^/api/apps/([\w-]+)/export$', self.path)
        if m:
            aid = m.group(1)
            if aid not in state: return self.send_error(404)
            if state[aid].get('type', 'source') != 'source':
                return self._json(400, {'error': 'cannot export prebuilt app'})
            data = export_app_bytes(aid)
            if data is None:
                return self._json(404, {'error': 'app dir not found on host'})
            self.send_response(200)
            self.send_header('content-type', 'application/gzip')
            self.send_header('content-disposition', f'attachment; filename="{aid}.dwapp"')
            self.send_header('content-length', str(len(data)))
            self.end_headers(); self.wfile.write(data); return
        if self.path == '/api/metrics':
            return self._json(200, _metrics.sample())
        if self.path.startswith('/api/chat/stream'):
            return self.handle_chat_stream()
        if self.path == '/api/chat/sessions':
            with sessions_lock: ss = list(sessions.items())
            out = []
            for sid, s in ss:
                out.append({'session_id': sid, 'status': s.status, 'events': len(s.events),
                            'preview': s.last_user[:80], 'name': s.name or s.last_user[:40] or 'New chat',
                            'created_ts': s.created_ts, 'updated_ts': s.updated_ts})
            return self._json(200, sorted(out, key=lambda x: -x['updated_ts']))
        if self.path == '/api/health':
            return self._json(200, {'ok': True})
        if self.path == '/api/system/status':
            # Lightweight readiness check. The two states that gate launching
            # the built-in cam-detect app are: did first-boot finish, and is
            # the rubikpi3-cam-test:npu docker image present.
            firstboot = 'unknown'
            firstboot_detail = ''
            if os.path.isfile('/var/lib/dragonwing-firstboot.done'):
                firstboot = 'done'
            else:
                r = sh('systemctl is-active dragonwing-firstboot.service', timeout=2)
                firstboot = (r.stdout or 'unknown').strip()  # active|activating|failed|inactive
                if firstboot in ('failed', 'inactive'):
                    rl = sh('journalctl -u dragonwing-firstboot.service --no-pager -n 1 -o cat', timeout=2)
                    firstboot_detail = (rl.stdout or '').strip()[:200]
            r = sh("docker image inspect --format=present rubikpi3-cam-test:npu 2>/dev/null", timeout=3)
            cam_test_image = (r.stdout or '').strip() == 'present'
            clock_synced = os.path.isfile('/run/systemd/timesync/synchronized')
            return self._json(200, {
                'firstboot': firstboot,
                'firstboot_detail': firstboot_detail,
                'cam_test_image': cam_test_image,
                'clock_synced': clock_synced,
                'ready': firstboot == 'done' and cam_test_image and clock_synced,
            })

        if self.path == '/api/config/qai-hub-status':
            qai_ini = '/root/.qai_hub/client.ini'
            if not os.path.isfile(qai_ini):
                return self._json(200, {'configured': False})
            api_url = ''
            try:
                for line in open(qai_ini):
                    if line.strip().startswith('api_url'):
                        api_url = line.split('=', 1)[1].strip()
            except Exception: pass
            return self._json(200, {'configured': True, 'api_url': api_url})
        return self.send_error(404)

    # ---- POST ----
    def do_POST(self):
        length = int(self.headers.get('content-length', '0') or 0)
        body_bytes = self.rfile.read(length) if length else b''
        try: body = json.loads(body_bytes) if body_bytes else {}
        except Exception: body = {}

        # App control
        m = re.match(r'^/api/apps/([\w-]+)/(start|stop|output|uninstall|rename|fork|modify|reset|commit|update|deploy|recall)$', self.path)
        if m:
            app_id, action = m.group(1), m.group(2)
            if app_id not in state: return self._json(404, {'error': 'unknown app'})
            if action == 'start':
                force = bool(body.get('force'))
                r = do_start_app(app_id, force=force)
                if not r.get('ok') and (r.get('conflicts') or r.get('reason')):
                    return self._json(409, r)
            elif action == 'stop':
                stop_app_by_id(app_id)
            elif action == 'uninstall':
                if app_deployed(app_id):
                    try: recall_app(app_id)
                    except ValueError: pass
                stop_app_by_id(app_id)
                with state_lock: state.pop(app_id, None)
                save_state()
                return self._json(200, {'ok': True, 'removed': app_id})
            elif action == 'output':
                with state_lock: state[app_id]['output'] = body.get('output', 'hdmi')
                save_state()
                if container_running('cam-npu-hdmi') or container_running('cam-npu-rdp') or container_running('cam-npu'):
                    stop_cam(); start_cam()
            elif action == 'rename':
                new_name = (body.get('name') or '').strip()
                if not new_name: return self._json(400, {'error': 'name required'})
                with state_lock: state[app_id]['name'] = new_name
                save_state()
            elif action == 'fork':
                new_id = (body.get('new_id') or '').strip().lower()
                new_name = (body.get('new_name') or '').strip() or new_id
                try:
                    fork_app(app_id, new_id, new_name)
                except ValueError as e:
                    return self._json(400, {'error': str(e)})
                return self._json(200, {'ok': True, 'forked_from': app_id, 'id': new_id,
                                        'app': app_view(new_id)})
            elif action == 'modify':
                try: created = modify_app(app_id)
                except ValueError as e: return self._json(400, {'error': str(e)})
                return self._json(200, {'ok': True, 'id': app_id, 'snapshot_created': created,
                                        'app': app_view(app_id)})
            elif action == 'reset':
                try: reset_app(app_id)
                except ValueError as e: return self._json(400, {'error': str(e)})
                return self._json(200, {'ok': True, 'id': app_id, 'app': app_view(app_id)})
            elif action == 'commit':
                try: commit_app(app_id)
                except ValueError as e: return self._json(400, {'error': str(e)})
                return self._json(200, {'ok': True, 'id': app_id, 'app': app_view(app_id)})
            elif action == 'deploy':
                try: deploy_app(app_id)
                except ValueError as e: return self._json(400, {'error': str(e)})
                return self._json(200, {'ok': True, 'id': app_id, 'app': app_view(app_id)})
            elif action == 'recall':
                try: recall_app(app_id)
                except ValueError as e: return self._json(400, {'error': str(e)})
                return self._json(200, {'ok': True, 'id': app_id, 'app': app_view(app_id)})
            elif action == 'update':
                # Whitelisted in-place mutation. Replaces the manual workflow of
                # editing /var/lib/dragonwing-marketplace.json + restarting the
                # service: this updates the in-memory state and persists in one
                # call, no restart needed.
                MUTABLE = ('cover_image', 'description', 'ports')
                changes = {k: v for k, v in (body or {}).items() if k in MUTABLE}
                if not changes:
                    return self._json(400, {'error': f'no whitelisted fields; allowed: {list(MUTABLE)}'})
                with state_lock:
                    state[app_id].update(changes)
                save_state()
                return self._json(200, {'ok': True, 'id': app_id, 'updated': list(changes), 'app': app_view(app_id)})
            return self._json(200, app_view(app_id))

        if self.path == '/api/apps/import':
            # Accepts a .dwapp (tar.gz) as the raw request body.
            if not body_bytes:
                return self._json(400, {'error': 'empty body; POST the .dwapp tar.gz bytes'})
            try:
                aid = import_app_bytes(body_bytes)
            except (ValueError, tarfile.TarError) as e:
                return self._json(400, {'error': str(e)})
            return self._json(200, {'ok': True, 'id': aid, 'app': app_view(aid)})

        # Verify API key
        if self.path in ('/api/config/verify-key', '/api/config/list-models'):
            key = body.get('api_key', '')
            scheme, host, prefix = _parse_base_url(body.get('base_url') or '')
            host_str = f"{scheme}://{host}"
            try:
                conn = _open_conn(scheme, host, 10)
                conn.request("GET", prefix + "/v1/models",
                             headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
                r = conn.getresponse(); data = r.read(); conn.close()
                ok = r.status == 200
                models = []
                if ok:
                    try:
                        body_json = json.loads(data)
                        # Two known shapes:
                        # 1) Anthropic standard: {"data": [{"id": "..."}, ...]}
                        # 2) LiteLLM / QGenie / similar gateways:
                        #    {"models": [{"model_name": "...", "capabilities": [...]}, ...]}
                        for m in body_json.get('data', []):
                            if isinstance(m, dict) and m.get('id'):
                                models.append(m['id'])
                        for m in body_json.get('models', []):
                            if not isinstance(m, dict): continue
                            mid = m.get('model_name') or m.get('id')
                            caps = m.get('capabilities') or []
                            # Only surface chat-capable models for the dropdown.
                            if mid and ('chat' in caps or not caps):
                                models.append(mid)
                        # Deduplicate while preserving order.
                        seen = set(); models = [x for x in models if not (x in seen or seen.add(x))]
                    except Exception: pass
                resp = {'valid': ok, 'status': r.status, 'host': host_str, 'models': models,
                        'detail': '' if ok else data.decode()[:300]}
                return self._json(200, resp)
            except Exception as e:
                return self._json(200, {'valid': False, 'host': host_str, 'models': [], 'error': repr(e)})

        # Write or clear the AI Hub token (lives on the device at
        # /root/.qai_hub/client.ini, bind-mounted into qai-export at run time).
        if self.path == '/api/config/qai-hub-token':
            qai_dir = '/root/.qai_hub'
            qai_ini = os.path.join(qai_dir, 'client.ini')
            if body.get('clear'):
                try: os.remove(qai_ini)
                except FileNotFoundError: pass
                except Exception as e: return self._json(500, {'error': repr(e)})
                return self._json(200, {'ok': True, 'cleared': True})
            token = (body.get('token') or '').strip()
            if not token: return self._json(400, {'error': 'token required'})
            api_url = body.get('api_url') or 'https://app.aihub.qualcomm.com'
            web_url = body.get('web_url') or 'https://app.aihub.qualcomm.com'
            try:
                os.makedirs(qai_dir, mode=0o700, exist_ok=True)
                tmp = qai_ini + '.tmp'
                with open(tmp, 'w') as f:
                    f.write(f"[api]\napi_token = {token}\napi_url = {api_url}\nweb_url = {web_url}\n")
                os.chmod(tmp, 0o600)
                os.replace(tmp, qai_ini)
            except Exception as e:
                return self._json(500, {'error': repr(e)})
            return self._json(200, {'ok': True, 'path': qai_ini, 'api_url': api_url})

        # Chat (SSE)
        if self.path == '/api/chat':
            return self.handle_chat(body)

        # Reset session
        if self.path == '/api/chat/reset':
            sid = body.get('session_id', '')
            with sessions_lock:
                sess = sessions.pop(sid, None)
            if sess: sess.cancel_flag.set();
            try: os.remove(os.path.join(SESSIONS_DIR, sid + '.json'))
            except FileNotFoundError: pass
            except Exception: pass
            return self._json(200, {'ok': True})

        if self.path == '/api/chat/cancel':
            sid = body.get('session_id', '')
            sess = sessions.get(sid)
            if not sess: return self._json(404, {'error': 'no such session'})
            sess.cancel_flag.set()
            # If a bash tool is mid-flight, killing the process group ensures
            # the subprocess.communicate() in execute_tool returns promptly
            # so the agent loop can observe the cancel flag at the next block.
            proc = sess.proc
            if proc is not None and proc.poll() is None:
                try: os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception as e: print(f'[chat] kill failed: {e!r}', flush=True)
            # No live thread? Emit synthetic terminal events so the UI clears its
            # "thinking…" indicator instead of waiting forever for a thinking_end.
            if sess.thread is None or not sess.thread.is_alive():
                if sess.events and sess.events[-1].get('evt') == 'thinking_start':
                    sess.emit('thinking_end', {'elapsed_ms': 0})
                sess.emit('cancelled', {'reason': 'no live thread'})
                sess.emit('done', {'status': 'cancelled'})
                sess.status = 'cancelled'
            with sess.cond: sess.cond.notify_all()
            print(f'[chat] sid={sid[:8]} cancel requested', flush=True)
            return self._json(200, {'ok': True, 'session_id': sid})

        if self.path == '/api/chat/delete':
            sid = body.get('session_id', '')
            with sessions_lock:
                sess = sessions.pop(sid, None)
            if sess:
                sess.cancel_flag.set()
                proc = sess.proc
                if proc is not None and proc.poll() is None:
                    try: os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except Exception: pass
            try: os.remove(os.path.join(SESSIONS_DIR, sid + '.json'))
            except FileNotFoundError: pass
            except Exception as e: print(f'[session] delete error: {e!r}', flush=True)
            return self._json(200, {'ok': True, 'deleted': sid})

        if self.path == '/api/chat/rename-session':
            sid = body.get('session_id', '')
            name = (body.get('name') or '').strip()
            if not name: return self._json(400, {'error': 'name required'})
            sess = sessions.get(sid)
            if not sess: return self._json(404, {'error': 'no such session'})
            sess.name = name[:80]
            save_session(sid)
            return self._json(200, {'ok': True, 'session_id': sid, 'name': sess.name})

        return self.send_error(404)


    def handle_chat_stream(self):
        import urllib.parse as _u
        qs = _u.parse_qs(self.path.split('?', 1)[1] if '?' in self.path else '')
        sid = (qs.get('session_id') or [''])[0]
        frm = int((qs.get('from') or ['0'])[0])
        # The browser, on auto-reconnect, sends `Last-Event-ID: <idx>` with the
        # idx of the last successfully received event. Prefer this over ?from=.
        last_id = self.headers.get('Last-Event-ID')
        if last_id is not None:
            try: frm = int(last_id) + 1
            except ValueError: pass
        if not sid or sid not in sessions:
            return self.send_error(404)
        sess = sessions[sid]
        self.send_response(200)
        self.send_header('content-type', 'text/event-stream')
        self.send_header('cache-control', 'no-cache')
        self.send_header('connection', 'keep-alive')
        self.send_header('x-accel-buffering', 'no')
        self.end_headers()
        # Tell EventSource to retry after 2s on disconnect
        try:
            self.wfile.write(b"retry: 2000\n\n"); self.wfile.flush()
        except Exception: pass
        print(f'[chat] sse OPEN sid={sid[:8]} from={frm} client={self.client_address[0]}', flush=True)
        cursor = frm
        # Drain + tail
        try:
            while True:
                with sess.cond:
                    while cursor < len(sess.events):
                        e = sess.events[cursor]
                        try:
                            line = f"id: {e['idx']}\nevent: {e['evt']}\ndata: {json.dumps(e['data'])}\n\n"
                            self.wfile.write(line.encode()); self.wfile.flush()
                        except (BrokenPipeError, ConnectionResetError):
                            return
                        cursor += 1
                    if sess.status in ('done','error','cancelled') and cursor >= len(sess.events):
                        return
                    # keepalive ping
                    try:
                        self.wfile.write(b": ping\n\n"); self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    sess.cond.wait(timeout=15)
        except Exception as e:
            print(f'[chat] sse error sid={sid[:8]}: {e!r}', flush=True)
        finally:
            print(f'[chat] sse CLOSE sid={sid[:8]} cursor={cursor}', flush=True)

    def handle_chat(self, body):
        print(f'[chat] inbound /api/chat from {self.client_address[0]}', flush=True)
        api_key = (self.headers.get('Authorization', '') or '').replace('Bearer ', '').strip()
        if not api_key:
            return self._json(400, {'error': 'no api key'})
        base_url = (self.headers.get('X-Anthropic-Base-Url', '') or '').strip() or None
        model    = (self.headers.get('X-Anthropic-Model',    '') or '').strip() or None
        sid = body.get('session_id') or str(uuid.uuid4())
        user_msg = body.get('message', '').strip()
        if not user_msg:
            return self._json(400, {'error': 'empty message'})
        with sessions_lock:
            sess = sessions.get(sid)
            if sess is None or not isinstance(sess, SessionState):
                sess = SessionState(sid=sid); sessions[sid] = sess
            sess.sid = sid
        if sess.status == 'running':
            return self._json(409, {'error': 'busy', 'session_id': sid})
        sess.cancel_flag.clear()
        sess.last_user = user_msg
        # First message in a fresh session becomes its sidebar label (truncate).
        if not sess.name:
            label = ' '.join(user_msg.split())[:60]
            sess.name = label or 'New chat'
        sess.thread = threading.Thread(target=run_agent_turn, args=(sid, api_key, user_msg, base_url, model), daemon=True)
        sess.thread.start()
        print(f'[chat] sid={sid[:8]} kicked off, user> {user_msg[:120]!r}', flush=True)
        return self._json(200, {'session_id': sid, 'turn_started': True, 'event_idx': len(sess.events)})

# --- main -----------------------------------------------------------------
if __name__ == '__main__':
    load_state()
    load_sessions()
    print(f"marketplace listening on :{PORT}")
    class _Srv(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        allow_reuse_port = True
        daemon_threads = True
    with _Srv(("0.0.0.0", PORT), Handler) as httpd:
        httpd.serve_forever()
