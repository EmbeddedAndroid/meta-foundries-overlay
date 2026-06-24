// ---- Settings (BYOK) ----
const KEY_NAME = 'dw_anthropic_key';
const BASE_URL_NAME = 'dw_anthropic_base_url';
const MODEL_NAME = 'dw_anthropic_model';
const MODELS_CACHE = 'dw_anthropic_models_cache';
const SID_NAME = 'dw_session_id';

function getKey()  { return localStorage.getItem(KEY_NAME) || ''; }
function setKey(k) { localStorage.setItem(KEY_NAME, k); updateKeyDot(); }
function clearKey(){ localStorage.removeItem(KEY_NAME); document.getElementById('api-key-input').value=''; document.getElementById('verify-state').textContent=''; updateKeyDot(); }
function getBaseUrl()  { return localStorage.getItem(BASE_URL_NAME) || ''; }
function setBaseUrl(u) { if (u) localStorage.setItem(BASE_URL_NAME, u); else localStorage.removeItem(BASE_URL_NAME); }
function getModel()  { return localStorage.getItem(MODEL_NAME) || ''; }
function setModel(m) { if (m) localStorage.setItem(MODEL_NAME, m); else localStorage.removeItem(MODEL_NAME); syncModelPicker(); }

function getCachedModels() {
  try { return JSON.parse(localStorage.getItem(MODELS_CACHE) || '[]'); } catch { return []; }
}
function setCachedModels(list) {
  localStorage.setItem(MODELS_CACHE, JSON.stringify(Array.isArray(list) ? list : []));
  syncModelPicker();
}

// Render the chat-head model dropdown from the cached list. Selected value
// reflects getModel() (or empty = "Default" placeholder option).
function syncModelPicker() {
  const sel = document.getElementById('model-picker');
  if (!sel) return;
  const models = getCachedModels();
  const current = getModel();
  // Hide entirely if no key is configured yet — the picker would be empty.
  sel.style.display = (getKey() && models.length) ? '' : 'none';
  if (!models.length) { sel.innerHTML = ''; return; }
  const opts = ['<option value="">Default model</option>']
    .concat(models.map(m => `<option value="${escapeHtml(m)}"${m===current?' selected':''}>${escapeHtml(m)}</option>`));
  sel.innerHTML = opts.join('');
  sel.value = current; // ensure default selected if no current
}
function getSid()  { return localStorage.getItem(SID_NAME) || ''; }
function setSid(s) { if (s) localStorage.setItem(SID_NAME, s); }
function clearSid(){ localStorage.removeItem(SID_NAME); }

function updateKeyDot() {
  const set = !!getKey();
  document.getElementById('key-dot').classList.toggle('set', set);
  document.getElementById('welcome-keyhint').style.display = set ? 'none' : 'block';
}
function openSettings() {
  document.getElementById('api-key-input').value = getKey();
  document.getElementById('api-base-url-input').value = getBaseUrl();
  document.getElementById('api-model-input').value = getModel();
  // If a key is already saved, prefetch the model list so the datalist is
  // populated by the time the user clicks the field.
  if (getKey()) refreshModelOptions();
  document.getElementById('verify-state').textContent = '';
  document.getElementById('verify-state').className = 'verify-state';
  // Mirror the sidebar dot inside the modal so users see configured-state
  document.getElementById('key-dot-modal').classList.toggle('set', !!getKey());
  // Don't pre-fill the qai token (it's write-only on the server) — just show status
  document.getElementById('qai-token-input').value = '';
  document.getElementById('qai-state').textContent = '';
  document.getElementById('qai-state').className = 'verify-state';
  refreshQaiStatus();
  document.getElementById('settings-modal').showModal();
}

async function refreshModelOptions() {
  const key = document.getElementById('api-key-input').value.trim() || getKey();
  const baseUrl = document.getElementById('api-base-url-input').value.trim() || getBaseUrl();
  if (!key) return;
  try {
    const r = await fetch('/api/config/list-models', {
      method: 'POST', headers: {'content-type': 'application/json'},
      body: JSON.stringify({api_key: key, base_url: baseUrl})
    });
    const d = await r.json();
    const models = d.models || [];
    const list = document.getElementById('model-options');
    list.innerHTML = models.map(m => `<option value="${escapeHtml(m)}">`).join('');
    setCachedModels(models);
  } catch (e) {}
}

async function refreshQaiStatus() {
  try {
    const r = await fetch('/api/config/qai-hub-status');
    const d = await r.json();
    document.getElementById('qai-dot').classList.toggle('set', !!d.configured);
    if (d.configured) {
      const s = document.getElementById('qai-state');
      s.textContent = '✓ Token configured on device (' + (d.api_url || 'app.aihub.qualcomm.com') + ')';
      s.className = 'verify-state ok';
    }
  } catch (e) {}
}

async function saveQaiToken() {
  const token = document.getElementById('qai-token-input').value.trim();
  const s = document.getElementById('qai-state');
  if (!token) { s.textContent = 'Empty token'; s.className = 'verify-state err'; return; }
  document.getElementById('save-qai-btn').disabled = true;
  try {
    const r = await fetch('/api/config/qai-hub-token', {
      method: 'POST', headers: {'content-type': 'application/json'},
      body: JSON.stringify({token})
    });
    const d = await r.json();
    if (d.ok) {
      s.textContent = '✓ Saved to /root/.qai_hub/client.ini';
      s.className = 'verify-state ok';
      document.getElementById('qai-token-input').value = '';
      document.getElementById('qai-dot').classList.add('set');
    } else {
      s.textContent = 'Save failed: ' + (d.error || r.status);
      s.className = 'verify-state err';
    }
  } catch (e) {
    s.textContent = 'Network error: ' + e; s.className = 'verify-state err';
  } finally {
    document.getElementById('save-qai-btn').disabled = false;
  }
}

async function clearQaiToken() {
  if (!confirm('Delete /root/.qai_hub/client.ini on the device?')) return;
  await fetch('/api/config/qai-hub-token', {
    method: 'POST', headers: {'content-type': 'application/json'},
    body: JSON.stringify({clear: true})
  });
  document.getElementById('qai-token-input').value = '';
  document.getElementById('qai-dot').classList.remove('set');
  const s = document.getElementById('qai-state');
  s.textContent = 'Cleared'; s.className = 'verify-state';
}
async function saveKey() {
  const key = document.getElementById('api-key-input').value.trim();
  const baseUrl = document.getElementById('api-base-url-input').value.trim();
  const model = document.getElementById('api-model-input').value.trim();
  const vs = document.getElementById('verify-state');
  if (!key) { vs.textContent = 'Empty key'; vs.className = 'verify-state err'; return; }
  vs.textContent = 'Verifying…'; vs.className = 'verify-state';
  document.getElementById('save-key-btn').disabled = true;
  try {
    const r = await fetch('/api/config/verify-key', {
      method: 'POST', headers: {'content-type': 'application/json'},
      body: JSON.stringify({api_key: key, base_url: baseUrl})
    });
    const d = await r.json();
    if (d.valid) {
      setKey(key);
      setBaseUrl(baseUrl);
      setModel(model);
      // verify-key returns the available models list from /v1/models in the
      // same call; populate the datalist + chat-head picker so the user gets
      // a dropdown immediately.
      if (Array.isArray(d.models)) {
        const list = document.getElementById('model-options');
        list.innerHTML = d.models.map(m => `<option value="${escapeHtml(m)}">`).join('');
        setCachedModels(d.models);
      }
      const extras = [baseUrl && 'custom base URL', model && `model=${model}`,
                      (d.models||[]).length && `${d.models.length} models available`]
                      .filter(Boolean).join(', ');
      vs.textContent = '✓ Verified · saved to this browser' + (extras ? ' (' + extras + ')' : '');
      vs.className = 'verify-state ok';
      setTimeout(() => document.getElementById('settings-modal').close(), 700);
    } else {
      vs.textContent = `Key rejected (${d.status || ''}). ${d.detail || d.error || ''}`.trim();
      vs.className = 'verify-state err';
    }
  } catch (e) {
    vs.textContent = 'Network error: ' + e; vs.className = 'verify-state err';
  } finally {
    document.getElementById('save-key-btn').disabled = false;
  }
}

// ---- Apps sidebar ----
let _appsCache = [];
async function importAppFile(fileInput) {
  const file = fileInput.files[0]; if (!file) return;
  fileInput.value = '';
  const startAllBtn = document.getElementById('start-all-btn');
  const importing = `Importing ${file.name}… docker build can take a few minutes.`;
  console.log(importing);
  try {
    const r = await fetch('/api/apps/import', {
      method: 'POST', headers: {'content-type': 'application/gzip'}, body: file,
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { alert('Import failed: ' + (d.error || r.status)); return; }
    alert(`Installed "${d.id}". Opening tile…`);
    loadApps();
    setTimeout(() => openAppModal(d.id), 800);
  } catch (e) { alert('Import error: ' + e); }
}

async function loadApps() {
  try {
    const r = await fetch('/api/apps');
    const apps = await r.json();
    _appsCache = apps;
    const list = document.getElementById('apps-list');
    list.innerHTML = '';
    apps.forEach(app => list.appendChild(renderTile(app)));
    updateBulkButtons();
  } catch (e) {}
}
function updateBulkButtons() {
  const startBtn = document.getElementById('start-all-btn');
  const stopBtn  = document.getElementById('stop-all-btn');
  if (!startBtn || !stopBtn) return;
  const stopped = _appsCache.filter(a => a.id !== 'app-builder' && !a.running).length;
  const running = _appsCache.filter(a => a.id !== 'app-builder' &&  a.running).length;
  startBtn.disabled = (stopped === 0);
  stopBtn.disabled  = (running === 0);
}
async function startAllApps() {
  const btn = document.getElementById('start-all-btn'); btn.classList.add('busy');
  try {
    await Promise.all(_appsCache.filter(a => a.id !== 'app-builder' && !a.running && !a.blocked)
      .map(a => fetch(`/api/apps/${a.id}/start`, { method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({force: true}) })));
  } finally {
    btn.classList.remove('busy'); setTimeout(loadApps, 800);
  }
}
async function stopAllApps() {
  const btn = document.getElementById('stop-all-btn'); btn.classList.add('busy');
  try {
    await Promise.all(_appsCache.filter(a => a.id !== 'app-builder' && a.running)
      .map(a => fetch(`/api/apps/${a.id}/stop`, { method: 'POST' })));
  } finally {
    btn.classList.remove('busy'); setTimeout(loadApps, 800);
  }
}
const CAP_ICONS = {
  camera: {label: 'Camera', svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3" y="7" width="18" height="13" rx="2.5"/><circle cx="12" cy="13.5" r="3.7"/><rect x="9" y="4" width="6" height="3" rx="1"/></svg>'},
  npu:    {label: 'NPU',    svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="6" y="6" width="12" height="12" rx="1.5"/><rect x="9" y="9" width="6" height="6" rx="1"/><line x1="3" y1="9"  x2="6"  y2="9"/><line x1="3" y1="15" x2="6"  y2="15"/><line x1="18" y1="9"  x2="21" y2="9"/><line x1="18" y1="15" x2="21" y2="15"/><line x1="9"  y1="3" x2="9"  y2="6"/><line x1="15" y1="3" x2="15" y2="6"/><line x1="9"  y1="18" x2="9"  y2="21"/><line x1="15" y1="18" x2="15" y2="21"/></svg>'},
  gpu:    {label: 'GPU',    svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="8" cy="12" r="2"/><circle cx="16" cy="12" r="2"/></svg>'},
  audio:  {label: 'Audio',  svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M11 5 L6 9 H3 v6 h3 l5 4 z"/><path d="M16 9 a4 4 0 0 1 0 6"/><path d="M19 6 a8 8 0 0 1 0 12"/></svg>'},
  display:{label: 'Display',svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3" y="4" width="18" height="13" rx="2"/><line x1="8" y1="20" x2="16" y2="20"/><line x1="12" y1="17" x2="12" y2="20"/></svg>'},
  network:{label: 'Network',svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="9"/><path d="M3 12 h18"/><path d="M12 3 a13 13 0 0 1 0 18 M12 3 a13 13 0 0 0 0 18"/></svg>'},
  sensors:{label: 'Sensors',svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="2.5"/><path d="M12 6 v-3"/><path d="M12 21 v-3"/><path d="M6 12 H3"/><path d="M21 12 h-3"/><path d="M7.8 7.8 L5.7 5.7"/><path d="M18.3 18.3 l-2.1-2.1"/><path d="M7.8 16.2 L5.7 18.3"/><path d="M18.3 5.7 l-2.1 2.1"/></svg>'}
};
function capChipsHtml(caps) {
  if (!caps || !caps.length) return '';
  return '<div class="tile-caps">' + caps.map(c => {
    const i = CAP_ICONS[c]; if (!i) return '';
    return `<span class="cap-chip" title="${i.label}">${i.svg}</span>`;
  }).join('') + '</div>';
}
function portChipsHtml(ports) {
  if (!ports || !ports.length) return '';
  // Click → open http://<this-host>:<port>/ in a new tab. Use location.hostname
  // so it works whether you're on 192.168.1.71 directly, an SSH tunnel, or RDP.
  return '<div class="tile-ports">' + ports.map(p =>
    `<a class="port-chip" href="http://${location.hostname}:${p}/" target="_blank" rel="noopener" title="Open http://${location.hostname}:${p}/" onclick="event.stopPropagation()">:${p}</a>`
  ).join('') + '</div>';
}

function renderTile(app) {
  const el = document.createElement('div');
  el.className = 'tile' + (app.running ? ' running' : '') + (app.blocked ? ' blocked' : '');
  el.dataset.appId = app.id;
  const cover = app.cover_image ? `<img src="${app.cover_image}">` : '⚡';
  // `blocked` comes from the server (app_view): the app declares a capability
  // the device can't satisfy right now (e.g. camera app, no camera attached).
  const statusText = app.blocked === 'no_camera'
    ? 'Camera required'
    : (app.status || 'Idle');
  const blockedTip = app.blocked === 'no_camera'
    ? '<div class="tile-blocked-tip">Connect a USB camera to run this app</div>'
    : '';
  el.innerHTML = `
    <div class="tile-summary">
      <div class="tile-cover">${cover}</div>
      <div class="tile-body">
        <div class="tile-name-row"><span class="tile-name">${app.name}</span>${app.has_draft ? '<span class="draft-tag tile-draft">DRAFT</span>' : ''}${app.deployed ? '<span class="deploy-tag tile-deploy" title="Launches at every boot via systemd">DEPLOYED</span>' : ''}${capChipsHtml(app.capabilities)}${portChipsHtml(app.ports)}</div>
        <div class="tile-status">${statusText}</div>
      </div>
    </div>${blockedTip}`;
  el.addEventListener('click', () => openAppModal(app.id));
  return el;
}
loadApps();
setInterval(loadApps, 3000);

// ---- Chat ----
const thread = document.getElementById('thread');
const input  = document.getElementById('input');
const sendBtn= document.getElementById('send-btn');

function el(tag, cls, html) { const e = document.createElement(tag); if (cls) e.className = cls; if (html !== undefined) e.innerHTML = html; return e; }

function addUser(text) {
  document.querySelector('.welcome')?.remove();
  const m = el('div', 'msg msg-user');
  m.appendChild(el('span', 'who', 'You'));
  m.appendChild(el('p', '', escapeHtml(text)));
  thread.appendChild(m); scrollDown();
}
function addBotStart() {
  document.querySelector('.welcome')?.remove();
  const m = el('div', 'msg msg-bot');
  m.appendChild(el('span', 'who', 'Agent'));
  const body = el('div', 'msg-body');
  m.appendChild(body);
  thread.appendChild(m); scrollDown();
  return body;
}

function setThinking(on) {
  const body = currentBotBody();
  let pill = body.querySelector('.thinking');
  if (on) {
    if (!pill) {
      pill = el('div', 'thinking', '<span class="td"></span><span class="td"></span><span class="td"></span><span class="tlabel">thinking</span>');
      body.appendChild(pill);
    }
    scrollDown();
  } else if (pill) {
    pill.remove();
  }
}
function markToolRunning(toolEl, on) {
  toolEl.classList.toggle('busy', on);
  // tick an elapsed-time counter while busy; the .running pill is CSS-hidden
  // for the first 600ms via animation-delay so short calls don't flicker
  const elapsedEl = toolEl.querySelector('.tool-running .elapsed');
  if (on) {
    const startedAt = Date.now();
    toolEl._elapsedTimer = setInterval(() => {
      if (!elapsedEl) return;
      const sec = Math.floor((Date.now() - startedAt) / 1000);
      const m = Math.floor(sec / 60), s = sec % 60;
      elapsedEl.textContent = m + ':' + String(s).padStart(2, '0');
    }, 250);
  } else if (toolEl._elapsedTimer) {
    clearInterval(toolEl._elapsedTimer);
    toolEl._elapsedTimer = null;
  }
}
let _streamStartTs = 0;
let _streamTimerId = null;
function setStreamState(s) {
  const dot = document.querySelector('.chat-head .live-dot');
  const tag = document.getElementById('uptime-tag');
  if (dot) {
    dot.classList.toggle('warn', s === 'reconnecting');
    dot.classList.toggle('off',  s === 'idle');
  }
  if (s === 'connecting' || s === 'live') {
    if (!_streamTimerId) {
      _streamStartTs = Date.now();
      _streamTimerId = setInterval(() => {
        const sec = ((Date.now() - _streamStartTs) / 1000);
        const cb = document.getElementById('cancel-btn');
        if (cb) cb.textContent = `Cancel · ${sec.toFixed(0)}s`;
      }, 250);
    }
  } else if (s === 'idle') {
    if (_streamTimerId) { clearInterval(_streamTimerId); _streamTimerId = null; }
    const cb = document.getElementById('cancel-btn'); if (cb) cb.textContent = 'Cancel';
  }
}

function appendText(target, text) {
  let p = target.querySelector('p.tail');
  if (!p) { p = el('p', 'tail'); target.appendChild(p); }
  p.textContent += text; scrollDown();
}
function appendToolUse(target, name, input) {
  const wrap = el('div', 'tool');
  const head = el('div', 'tool-head');
  const fullArg = name === 'bash' ? (input.command || '') : JSON.stringify(input, null, 2);
  // Head shows only the first line (truncated with ellipsis via CSS); the full
  // command + output live in the body and reveal when the head is clicked.
  const headArg = (name === 'bash' ? (input.command || '').split('\n')[0] : fullArg).slice(0, 200);
  head.innerHTML = `
    <span class="thead-left"><span class="tname">${name}</span><span class="tcmd"> ${escapeHtml(headArg)}</span></span>
    <span class="tool-toggle" aria-label="Expand">▸</span>
    <span class="status-pill" data-pill>running…</span>`;
  head.addEventListener('click', () => {
    wrap.classList.toggle('open');
    const tog = head.querySelector('.tool-toggle');
    if (tog) tog.textContent = wrap.classList.contains('open') ? '▾' : '▸';
  });
  const running = el('div', 'tool-running',
    '<span class="td"></span><span class="td"></span><span class="td"></span>' +
    '<span class="tlabel">running</span>' +
    '<span class="elapsed">0:00</span>');
  const body = el('div', 'tool-body');
  body.innerHTML = `<pre class="tool-cmd"><span class="tool-section">command</span>${escapeHtml(fullArg)}</pre>` +
                   `<pre class="tool-out" data-out><span class="tool-section">output</span>…</pre>`;
  wrap.append(head, running, body);
  target.appendChild(wrap); scrollDown();
  // Clear text tail so next tokens start a new paragraph after tool
  target.querySelectorAll('p.tail').forEach(p => p.classList.remove('tail'));
  return wrap;
}
function fillToolResult(tool, out) {
  const pill = tool.querySelector('[data-pill]');
  const exit = out.exit_code;
  pill.textContent = exit === 0 ? `exit 0` : `exit ${exit}`;
  pill.classList.toggle('ok', exit === 0);
  pill.classList.toggle('err', exit !== 0 && exit !== undefined);
  const outEl = tool.querySelector('[data-out]');
  const text  = out.output || JSON.stringify(out, null, 2);
  // Preserve the leading label, replace just the content.
  outEl.innerHTML = `<span class="tool-section">output</span>${escapeHtml(text)}`;
}
function scrollDown() { thread.scrollTop = thread.scrollHeight; }
function escapeHtml(s) { return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#x27;'}[c])); }

async function sendChat(ev) {
  ev?.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  const key = getKey();
  if (!key) { openSettings(); return; }
  input.value = ''; sendBtn.disabled = true;
  addUser(text);
  // Reset the plan card on every send. The agent issues set_todos when it
  // starts a multi-step task; if it doesn't (quick Q&A turn), the card stays
  // empty rather than showing stale items from the previous turn.
  renderTodos([]);
  const sid = getSid();
  try {
    const _headers = { 'content-type': 'application/json', 'Authorization': 'Bearer ' + key };
    const _baseUrl = getBaseUrl();
    if (_baseUrl) _headers['X-Anthropic-Base-Url'] = _baseUrl;
    const _model = getModel();
    if (_model) _headers['X-Anthropic-Model'] = _model;
    const r = await fetch('/api/chat', {
      method: 'POST',
      headers: _headers,
      body: JSON.stringify({ session_id: sid, message: text }),
    });
    const data = await r.json();
    if (!r.ok) {
      addBotStartIfMissing(); appendText(currentBotBody(), '[error: ' + (data.error || r.status) + ']');
      sendBtn.disabled = false; return;
    }
    setSid(data.session_id);
    streamFrom(data.session_id, data.event_idx || 0);
    loadSessions(); // refresh sidebar so the newly-named session appears
  } catch (e) {
    sendBtn.disabled = false;
  }
}

let _es = null;
let _toolEls = {};
let _lastEventIdx = -1;
let _activeSid = '';
let _currentBotBody = null;
function currentBotBody() {
  if (!_currentBotBody || !_currentBotBody.isConnected) _currentBotBody = addBotStart();
  return _currentBotBody;
}
function addBotStartIfMissing() {
  if (!_currentBotBody || !_currentBotBody.isConnected) _currentBotBody = addBotStart();
}
function streamFrom(sid, fromIdx) {
  if (_es) _es.close();
  _activeSid = sid;
  _lastEventIdx = fromIdx - 1;
  showCancel(true);
  setStreamState('connecting');
  console.log('[stream] opening sid=', sid.slice(0,8), 'from=', fromIdx);
  _es = new EventSource(`/api/chat/stream?session_id=${encodeURIComponent(sid)}&from=${fromIdx}`);

  const wrap = (handler) => (e) => {
    if (e.lastEventId) {
      const n = parseInt(e.lastEventId, 10);
      if (!isNaN(n) && n > _lastEventIdx) _lastEventIdx = n;
    }
    handler(e);
  };
  _es.onopen = () => { setStreamState('live'); console.log('[stream] open'); };
  _es.onerror = (e) => {
    setStreamState('reconnecting');
    console.warn('[stream] error / will auto-reconnect; lastEventIdx=', _lastEventIdx,
                 'readyState=', _es ? _es.readyState : 'n/a');
  };
  _es.addEventListener('user', wrap((e) => {
    // Replay-safe: render historical user messages in chronological order.
    // For the live just-sent message, sendChat opens the stream from the
    // event AFTER the user event, so this handler only fires on replay.
    try { const p = JSON.parse(e.data); if (p && p.text) addUser(p.text); } catch {}
  }));
  _es.addEventListener('todos', wrap((e) => {
    try { const p = JSON.parse(e.data); renderTodos(p.todos || []); } catch {}
  }));
  _es.addEventListener('thinking_start', wrap(() => setThinking(true)));
  _es.addEventListener('thinking_end',   wrap(() => {}));
  _es.addEventListener('text', wrap((e) => {
    setThinking(false);
    const p = JSON.parse(e.data); appendText(currentBotBody(), p.text);
  }));
  _es.addEventListener('tool_use', wrap((e) => {
    setThinking(false);
    const p = JSON.parse(e.data); _toolEls[p.id] = appendToolUse(currentBotBody(), p.name, p.input);
    markToolRunning(_toolEls[p.id], true);
  }));
  _es.addEventListener('tool_result', wrap((e) => {
    const p = JSON.parse(e.data); if (_toolEls[p.id]) { fillToolResult(_toolEls[p.id], p.output); markToolRunning(_toolEls[p.id], false); }
  }));
  _es.addEventListener('usage', wrap((e) => {
    try {
      const p = JSON.parse(e.data);
      const el = document.getElementById('token-meter');
      if (!el) return;
      const t = p.totals || {};
      const fmt = (n) => { n = n || 0; return n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n); };
      const tin = (t.input_tokens || 0) + (t.cache_read_input_tokens || 0) + (t.cache_creation_input_tokens || 0);
      el.textContent = '\u2191 ' + fmt(tin) + ' \u2193 ' + fmt(t.output_tokens) + ' \u00b7 ctx ' + fmt(p.context_tokens);
      el.title = 'Session tokens \u2014 input: ' + tin.toLocaleString() +
        ' (cache read ' + (t.cache_read_input_tokens || 0).toLocaleString() +
        ', cache write ' + (t.cache_creation_input_tokens || 0).toLocaleString() +
        ') \u00b7 output: ' + (t.output_tokens || 0).toLocaleString() +
        ' \u00b7 current context: ' + (p.context_tokens || 0).toLocaleString();
    } catch {}
  }));
  _es.addEventListener('error', wrap((e) => {
    setThinking(false);
    let p; try { p = JSON.parse(e.data); } catch { return; }
    // Suppress legacy orphan-tool_use 400s that have since been healed —
    // they remain in the on-disk buffer but replaying them confuses the user.
    const detailMsg = p && p.detail && p.detail.message;
    if (typeof detailMsg === 'string' && detailMsg.includes('tool_use') && detailMsg.includes('tool_result')) {
      console.log('[stream] suppressed legacy orphan error event');
      return;
    }
    appendText(currentBotBody(), '\n[error: ' + JSON.stringify(p) + ']');
  }));
  _es.addEventListener('cancelled', wrap(() => { setThinking(false); appendText(currentBotBody(), '\n[cancelled]'); }));
  _es.addEventListener('done', wrap(() => {
    setThinking(false);
    if (_es) { _es.close(); _es = null; }
    _currentBotBody = null; _toolEls = {};
    showCancel(false); setStreamState('idle');
    sendBtn.disabled = false; input.focus();
  }));
}

document.addEventListener('visibilitychange', () => {
  if (document.hidden) return;
  if (!_activeSid) return;
  // If the EventSource died (closed/no longer streaming), force-reopen using our tracked idx
  if (!_es || _es.readyState === EventSource.CLOSED) {
    console.log('[stream] tab visible again, reopening from idx', _lastEventIdx + 1);
    streamFrom(_activeSid, _lastEventIdx + 1);
  }
});

async function cancelTurn() {
  const sid = getSid(); if (!sid) return;
  await fetch('/api/chat/cancel', {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({session_id: sid})});
}
function showCancel(on) {
  const c = document.getElementById('cancel-btn');
  if (c) c.style.display = on ? '' : 'none';
}
// ---- Sessions sidebar ---------------------------------------------------
async function loadSessions() {
  try {
    const r = await fetch('/api/chat/sessions');
    const list = await r.json();
    renderSessions(list);
  } catch (e) {}
}

function renderSessions(list) {
  const el = document.getElementById('sessions-list');
  if (!el) return;
  if (!list || !list.length) { el.innerHTML = '<div class="session-empty">No sessions yet</div>'; return; }
  const fmtAge = (ts) => {
    const d = Date.now()/1000 - ts;
    if (d < 60)    return Math.floor(d) + 's';
    if (d < 3600)  return Math.floor(d/60) + 'm';
    if (d < 86400) return Math.floor(d/3600) + 'h';
    return Math.floor(d/86400) + 'd';
  };
  el.innerHTML = list.map(s => `
    <div class="session-item ${s.session_id === _activeSid ? 'active' : ''} status-${s.status}"
         data-sid="${s.session_id}" title="${escapeHtml(s.preview || '')}">
      <div class="session-name">${escapeHtml(s.name || s.preview || 'New chat')}</div>
      <div class="session-meta"><span class="session-status">${s.status}</span> · <span class="session-age">${fmtAge(s.updated_ts)}</span></div>
      <button class="session-del" data-sid="${s.session_id}" title="Delete session">×</button>
    </div>`).join('');
  el.querySelectorAll('.session-item').forEach(it => {
    it.addEventListener('click', (e) => {
      if (e.target.classList.contains('session-del')) return;
      switchSession(it.dataset.sid);
    });
  });
  el.querySelectorAll('.session-del').forEach(btn => {
    btn.addEventListener('click', (e) => { e.stopPropagation(); deleteSession(btn.dataset.sid); });
  });
}

function clearChatThread() {
  thread.innerHTML = '';
  _toolEls = {};
  _lastEventIdx = -1;
  _currentBotBody = null;
  setThinking(false);
  renderTodos([]);
}

function renderTodos(todos) {
  let card = document.getElementById('todos-card');
  if (!todos || !todos.length) { if (card) card.remove(); return; }
  if (!card) {
    card = document.createElement('div');
    card.id = 'todos-card';
    card.className = 'todos-card';
    const composer = document.querySelector('.composer');
    (composer ? composer.parentNode.insertBefore(card, composer) : thread.parentNode.appendChild(card));
  }
  const icon = (s) => s === 'completed' ? '✓' : s === 'in_progress' ? '◐' : s === 'cancelled' ? '✕' : '○';
  card.innerHTML = `
    <div class="todos-head">Plan</div>
    <ul class="todos-list">
      ${todos.map(t => `<li class="todo-${t.status}"><span class="todo-icon">${icon(t.status)}</span><span class="todo-text">${escapeHtml(t.text)}</span></li>`).join('')}
    </ul>`;
}

function startNewSession() {
  if (_es) { try { _es.close(); } catch {} _es = null; }
  _activeSid = '';
  clearSid();
  clearChatThread();
  thread.innerHTML = `
    <div class="welcome">
      <h2>Hello.</h2>
      <p>Fresh session. I have unrestricted shell access via a <code>bash</code> tool — point me at anything.</p>
    </div>`;
  setStreamState('idle');
  showCancel(false);
  sendBtn.disabled = false;
  input.focus();
  loadSessions();
}

function switchSession(sid) {
  if (!sid || sid === _activeSid) return;
  if (_es) { try { _es.close(); } catch {} _es = null; }
  clearChatThread();
  setSid(sid);
  streamFrom(sid, 0);
  loadSessions();
}

async function deleteSession(sid) {
  if (!confirm('Delete this session? The conversation history will be lost.')) return;
  try {
    await fetch('/api/chat/delete', {
      method: 'POST', headers: {'content-type': 'application/json'},
      body: JSON.stringify({session_id: sid})
    });
  } catch (e) {}
  if (sid === _activeSid) startNewSession();
  else loadSessions();
}


async function resetChat() {
  const sid = getSid();
  if (sid) {
    try { await fetch('/api/chat/reset', { method: 'POST', headers: {'content-type':'application/json'}, body: JSON.stringify({session_id: sid}) }); } catch {}
  }
  clearSid();
  thread.innerHTML = `
    <div class="welcome">
      <h2>Hello.</h2>
      <p>Fresh session. I have unrestricted shell access via a <code>bash</code> tool — point me at anything.</p>
    </div>`;
  updateKeyDot();
}

input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
});

// Uptime ticker
(() => {
  const start = Date.now();
  setInterval(() => {
    const s = Math.floor((Date.now() - start) / 1000);
    const m = Math.floor(s/60), ss = s%60;
    const el = document.getElementById('uptime-tag');
    if (el) el.textContent = `session ${m}:${ss.toString().padStart(2,'0')}`;
  }, 1000);
})();

updateKeyDot();

// ---- System readiness banner ----
async function refreshSystemStatus() {
  const banner = document.getElementById('status-banner');
  if (!banner) return;
  try {
    const r = await fetch('/api/system/status');
    if (!r.ok) return;
    const s = await r.json();
    if (s.ready) { banner.style.display = 'none'; return; }
    // Pick the most actionable message
    let cls = 'warn', text = '';
    if (s.firstboot === 'activating' || s.firstboot === 'active') {
      cls = 'progress';
      text = 'First-boot setup in progress — building rubikpi3-cam-test:npu (~5 min on first run). cam-detect Launch is blocked until this finishes.';
    } else if (s.firstboot === 'failed') {
      cls = 'error';
      text = 'First-boot setup failed' + (s.firstboot_detail ? ': ' + s.firstboot_detail : '') + '. Common causes: no network, expired clock, or docker.io unreachable. Retry: systemctl restart dragonwing-firstboot.';
    } else if (!s.cam_test_image) {
      cls = 'warn';
      text = 'rubikpi3-cam-test:npu docker image is missing. cam-detect Launch will not work until it is built.';
    } else if (!s.clock_synced) {
      cls = 'warn';
      text = 'System clock not synced via NTP — agent calls and TLS may fail.';
    }
    if (!text) { banner.style.display = 'none'; return; }
    banner.className = 'status-banner ' + cls;
    banner.innerHTML = '<span class="status-dot"></span><span class="status-msg">' + escapeHtml(text) + '</span>';
    banner.style.display = '';
  } catch (e) {}
}
refreshSystemStatus();
setInterval(refreshSystemStatus, 10000);

// Hook up the chat-head model picker once the DOM is in place.
(function initModelPicker() {
  const sel = document.getElementById('model-picker');
  if (!sel) return;
  sel.addEventListener('change', () => setModel(sel.value));
  syncModelPicker();
  if (getKey() && !getCachedModels().length) refreshModelOptions();
})();


// ---- App detail modal ----
let _appModalApp = null;
let _appFeedTimer = null;
async function openAppModal(appId) {
  const r = await fetch('/api/apps');
  const apps = await r.json();
  const app = apps.find(a => a.id === appId);
  if (!app) return;
  _appModalApp = app;
  const m = document.getElementById('app-modal');
  m.querySelector('.app-modal-inner').innerHTML = renderAppModal(app);
  bindAppModal(app);
  m.showModal();
  m.addEventListener('close', stopFeedPolling, { once: true });
  if (app.running) startFeedPolling(app.id);
}
function renderAppModal(app) {
  const coverHtml = app.cover_image
    ? `<img class="cover" src="${app.cover_image}" alt="${app.name}">`
    : `<div class="big-icon">⚡</div>`;
  const seg = app.id === 'cam-detect' ? `
    <div class="app-control-row">
      <span class="label">Output</span>
      <div class="app-seg" data-app="${app.id}">
        ${['hdmi','rdp','both'].map(o => `<button data-out="${o}" class="${app.output === o ? 'active':''}">${o}</button>`).join('')}
      </div>
    </div>` : '';
  // Hero: cover by default. If running, layer a feed image on top that fades in only once it actually loads.
  const hero = app.running
    ? `<div class="app-hero" id="app-hero">
         ${coverHtml}
         <img class="feed" id="app-feed" alt=""
              src="/api/feed/${app.id}.jpg?_=${Date.now()}"
              onload="onFeedLoaded(this)"
              onerror="onFeedError(this)">
         <div class="live-badge" id="live-badge" style="display:none"><span class="ldot"></span>LIVE</div>
         <button class="fs-btn" id="fs-btn" style="display:none" onclick="enterFullscreen()" title="Fullscreen live stream">⛶ Fullscreen</button>
         <button class="close-x" onclick="closeAppModal()">×</button>
       </div>`
    : `<div class="app-hero">${coverHtml}<button class="close-x" onclick="closeAppModal()">×</button></div>`;
  return hero + `
    <div class="app-meta">
      <h2>${app.name}<button class="rename-btn" data-modal-act="rename" title="Rename">✎</button></h2>
      <div class="app-status">${app.status || 'Idle'}</div>
    </div>
    <div class="app-controls">
      ${app.description ? `<p class="app-desc">${escapeHtml(app.description)}</p>` : ''}
      ${seg}
      ${app.blocked === 'no_camera' ? '<p class="app-desc" style="color:var(--dw-warn)">⚠ This app needs a camera and none is connected. Connect a USB camera to launch it.</p>' : ''}
      <div class="app-actions">
        <button class="btn primary" data-modal-act="start" ${app.running || app.blocked ? 'disabled' : ''} ${app.blocked === 'no_camera' ? 'title="Connect a USB camera to run this app"' : ''}>Launch</button>
        <button class="btn"         data-modal-act="stop"  ${!app.running ? 'disabled' : ''}>Stop</button>
        ${app.deployed
          ? `<button class="btn" data-modal-act="recall" title="Remove the systemd service that launches this app at boot — back to manual launches">Recall</button>`
          : `<button class="btn" data-modal-act="deploy" title="Install a systemd service that launches this app at every boot and keeps it running">Deploy</button>`}
        ${app.type === 'source' && !app.has_draft ? `<button class="btn" data-modal-act="modify" title="Improve this app — opens a new chat session with an editable working copy">Modify</button>` : ''}
        ${app.has_draft ? `<button class="btn primary" data-modal-act="commit" title="Make the current source the committed state — drops the snapshot">Commit</button>` : ''}
        ${app.has_draft ? `<button class="btn danger" data-modal-act="reset" title="Discard modifications, restore original source, rebuild + restart">Reset</button>` : ''}
        ${app.type === 'source' ? `<button class="btn" data-modal-act="fork" title="Create a new app starting from this one's source">Fork</button>` : ''}
        ${app.type === 'source' ? `<button class="btn" data-modal-act="export" title="Download .dwapp bundle">Export</button>` : ''}
        <button class="btn danger"  data-modal-act="uninstall" style="flex:0 0 auto; padding-left:18px; padding-right:18px;">Remove</button>
      </div>
      ${app.type ? `<div class="app-pubmeta">type: <code>${app.type}</code>${app.version ? ' · v' + escapeHtml(app.version) : ''}${app.author ? ' · ' + escapeHtml(app.author) : ''}${app.forked_from ? ' · forked from <code>' + escapeHtml(app.forked_from) + '</code>' : ''}${app.has_draft ? ' · <span class="draft-tag">DRAFT</span>' : ''}${app.deployed ? ' · <span class="deploy-tag" title="dragonwing-app-' + app.id + '.service launches this app at boot">DEPLOYED</span>' : ''}</div>` : ''}
    </div>`;
}
function bindAppModal(app) {
  const m = document.getElementById('app-modal');
  m.querySelectorAll('[data-modal-act]').forEach(b => b.addEventListener('click', async () => {
    const act = b.dataset.modalAct;
    if (act === 'uninstall' && !confirm(`Remove "${app.name}"?`)) return;
    if (act === 'rename') {
      const next = prompt('Rename app to:', app.name);
      if (!next || next.trim() === '' || next.trim() === app.name) return;
      await fetch(`/api/apps/${app.id}/rename`, {
        method: 'POST', headers: {'content-type': 'application/json'},
        body: JSON.stringify({name: next.trim()})
      });
      setTimeout(() => { loadApps(); openAppModal(app.id); }, 300);
      return;
    }
    if (act === 'export') {
      window.location.href = `/api/apps/${app.id}/export`;
      return;
    }
    if (act === 'deploy' || act === 'recall') {
      b.disabled = true; b.textContent = act === 'deploy' ? 'Deploying…' : 'Recalling…';
      const r = await fetch(`/api/apps/${app.id}/${act}`, {method: 'POST'});
      const d = await r.json().catch(() => ({}));
      if (!r.ok) {
        alert((act === 'deploy' ? 'Deploy' : 'Recall') + ' failed: ' + (d.error || r.status));
        b.disabled = false; b.textContent = act === 'deploy' ? 'Deploy' : 'Recall';
        return;
      }
      setTimeout(() => { loadApps(); openAppModal(app.id); }, 300);
      return;
    }
    if (act === 'modify') {
      const r = await fetch(`/api/apps/${app.id}/modify`, {method: 'POST'});
      if (!r.ok) { const d = await r.json().catch(() => ({})); alert('Modify failed: ' + (d.error || r.status)); return; }
      closeAppModal();
      startNewSession();
      input.value = `I want to improve the "${app.name}" app. The full source is at /root/apps/${app.id}/ (Dockerfile, main.py, README, assets/, models/). A snapshot of the current state is preserved at /root/apps/${app.id}.clean/ so I can Reset if needed; you can edit the live tree freely. Image: ${app.image}. Currently ${app.running ? 'running' : 'stopped'}. After making changes, remember to: docker build -t ${app.image} /root/apps/${app.id}/${app.running ? ' and restart the container so the new image takes effect' : ''}. What I want to change — `;
      input.focus();
      setTimeout(loadApps, 600);
      return;
    }
    if (act === 'reset') {
      if (!confirm(`Reset "${app.name}" to its committed state? Modifications since Modify began will be lost (the snapshot will be restored, image rebuilt, container restarted if it was running).`)) return;
      b.disabled = true; b.textContent = 'Resetting…';
      const r = await fetch(`/api/apps/${app.id}/reset`, {method: 'POST'});
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { alert('Reset failed: ' + (d.error || r.status)); b.disabled = false; b.textContent = 'Reset'; return; }
      setTimeout(() => { loadApps(); openAppModal(app.id); }, 600);
      return;
    }
    if (act === 'commit') {
      if (!confirm(`Commit current state of "${app.name}" as the new committed source? (Drops the snapshot — you won't be able to Reset back.)`)) return;
      const r = await fetch(`/api/apps/${app.id}/commit`, {method: 'POST'});
      if (!r.ok) { const d = await r.json().catch(() => ({})); alert('Commit failed: ' + (d.error || r.status)); return; }
      setTimeout(() => { loadApps(); openAppModal(app.id); }, 300);
      return;
    }
    if (act === 'fork') {
      const newId = prompt(`Fork "${app.name}" — new app id (lowercase, no spaces):`, app.id + '-fork');
      if (!newId) return;
      const cleaned = newId.trim().toLowerCase();
      const newName = prompt('Display name for the new app:', app.name + ' (fork)');
      if (!newName) return;
      const r = await fetch(`/api/apps/${app.id}/fork`, {
        method: 'POST', headers: {'content-type': 'application/json'},
        body: JSON.stringify({new_id: cleaned, new_name: newName.trim()})
      });
      if (!r.ok) { const d = await r.json().catch(() => ({})); alert('Fork failed: ' + (d.error || r.status)); return; }
      closeAppModal();
      startNewSession();
      input.value = `I just forked "${app.name}" as a new app called "${newName.trim()}" (id=${cleaned}). The full source has been copied to /root/apps/${cleaned}/ and a docker image build is running in the background. The marketplace already registered the new app. Help me modify it — `;
      input.focus();
      setTimeout(loadApps, 800);
      return;
    }
    b.disabled = true;
    const r = await fetch(`/api/apps/${app.id}/${act}`, { method: 'POST' });
    if (r.status === 409 && act === 'start') {
      const data = await r.json();
      if (data.reason === 'no_camera') {
        alert(data.message || 'This app needs a camera and none is connected.');
        b.disabled = false; return;
      }
      const names = (data.conflicts || []).map(c => `${c.held_by_name} (${c.resource})`).join(', ');
      if (confirm(`Cannot launch — currently held by: ${names}.\n\nStop them and launch "${app.name}"?`)) {
        await fetch(`/api/apps/${app.id}/start`, {
          method:'POST', headers:{'content-type':'application/json'},
          body: JSON.stringify({force: true})
        });
      } else { b.disabled = false; return; }
    }
    setTimeout(async () => {
      loadApps();
      if (act === 'uninstall') closeAppModal();
      else openAppModal(app.id);
    }, 600);
  }));
  m.querySelectorAll('button[data-out]').forEach(b => b.addEventListener('click', async () => {
    await fetch(`/api/apps/${app.id}/output`, {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({output: b.dataset.out})});
    setTimeout(() => openAppModal(app.id), 500);
  }));
}


function enterFullscreen() {
  const img = document.getElementById('app-feed');
  if (!img) return;
  const req = img.requestFullscreen || img.webkitRequestFullscreen || img.mozRequestFullScreen || img.msRequestFullscreen;
  if (req) req.call(img);
}

function onFeedLoaded(img) {
  img.classList.add('show');
  const b = document.getElementById('live-badge'); if (b) b.style.display = '';
  const fs = document.getElementById('fs-btn'); if (fs) fs.style.display = '';
}
function onFeedError(img) {
  stopFeedPolling();
  img.remove();
  document.getElementById('live-badge')?.remove();
  document.getElementById('fs-btn')?.remove();
}

function startFeedPolling(appId) {
  stopFeedPolling();
  _appFeedTimer = setInterval(() => {
    const img = document.getElementById('app-feed');
    if (img) img.src = `/api/feed/${appId}.jpg?_=${Date.now()}`;
  }, 250);
}
function stopFeedPolling() {
  if (_appFeedTimer) { clearInterval(_appFeedTimer); _appFeedTimer = null; }
}
function closeAppModal() {
  stopFeedPolling();
  document.getElementById('app-modal').close();
}

// ---- Performance metrics (top strip) ----
const PERF_TICK_MS = 2000;

function fmt(v, suffix='', digits=1) {
  if (v === null || v === undefined) return '—';
  return (typeof v === 'number' ? v.toFixed(digits) : v) + suffix;
}
function sevPct(p, warn=70, bad=88) {
  if (p == null) return ''; if (p >= bad) return 'bad'; if (p >= warn) return 'warn'; return '';
}
function sevTemp(t, warn=75, bad=88) {
  if (t == null) return ''; if (t >= bad) return 'bad'; if (t >= warn) return 'warn'; return '';
}
function sevLoad(l) {
  if (l == null) return ''; if (l >= 8) return 'bad'; if (l >= 4) return 'warn'; return '';
}
function pill(name, value, sev='', barPct=null) {
  const bar = barPct == null ? '' : `<span class="mini-bar ${sev}"><i style="width:${Math.max(0,Math.min(100,barPct))}%"></i></span>`;
  return `<span class="perf-pill"><span class="name">${name}</span>${bar}<span class="v ${sev}">${value}</span></span>`;
}
function cluster(title, pillsHtml) {
  return `<div class="perf-cluster"><span class="ctitle">${title}</span>${pillsHtml}</div>`;
}

async function loadPerf() {
  try {
    const r = await fetch('/api/metrics');
    const m = await r.json();
    const root = document.getElementById('perf');
    if (!root) return;

    const compute = cluster('Compute',
      pill('CPU',  fmt(m.cpu_pct, '%', 0), sevPct(m.cpu_pct, 75, 92), m.cpu_pct) +
      pill('GPU',  fmt(m.gpu_mhz, ' MHz', 0), sevPct(m.gpu_pct, 75, 92), m.gpu_pct) +
      pill('CDSP', `<span class="dot-state ${m.cdsp_state === 'running' ? 'run' : 'off'}"></span>${m.cdsp_state || '—'}`) +
      pill('ADSP', `<span class="dot-state ${m.adsp_state === 'running' ? 'run' : 'off'}"></span>${m.adsp_state || '—'}`)
    );
    const therm = cluster('Thermal',
      pill('CPU', fmt(m.cpu_c, '°C', 1), sevTemp(m.cpu_c)) +
      pill('GPU', fmt(m.gpu_c, '°C', 1), sevTemp(m.gpu_c)) +
      pill('NPU', fmt(m.npu_c, '°C', 1), sevTemp(m.npu_c))
    );
    const memVal = m.mem_total_kb ? `${((m.mem_total_kb - m.mem_avail_kb)/1024/1024).toFixed(1)}/${(m.mem_total_kb/1024/1024).toFixed(1)} GB` : '—';
    const mem = cluster('Memory',
      pill('Used', fmt(m.mem_used_pct, '%', 0), sevPct(m.mem_used_pct, 80, 92), m.mem_used_pct) +
      pill('', memVal)
    );
    const io = cluster('I/O',
      pill('Disk R', fmt(m.disk_r_kbps, ' kB/s', 0)) +
      pill('Disk W', fmt(m.disk_w_kbps, ' kB/s', 0)) +
      pill('Net Rx', fmt(m.net_rx_mbps, ' Mb/s', 2)) +
      pill('Net Tx', fmt(m.net_tx_mbps, ' Mb/s', 2))
    );
    const load = cluster('Load',
      pill('1m',  fmt(m.load_1m,  '', 2), sevLoad(m.load_1m)) +
      pill('5m',  fmt(m.load_5m,  '', 2)) +
      pill('15m', fmt(m.load_15m, '', 2))
    );
    root.innerHTML = compute + therm + mem + io + load;
  } catch (e) {}
}
loadPerf();
setInterval(loadPerf, PERF_TICK_MS);

// Page reload always starts a fresh session — past sessions live in the sidebar.
clearSid();
loadSessions();
setInterval(loadSessions, 4000);

// Poll-based watchdog: if the server-side session has more events than we've received,
// force-reopen the stream. Catches the case where the EventSource silently rotted
// without emitting an error (e.g. OS network sleep, ISP middlebox).
setInterval(async () => {
  if (!_activeSid) return;
  try {
    const r = await fetch('/api/chat/sessions');
    const list = await r.json();
    const me = list.find(s => s.session_id === _activeSid);
    if (!me) return;
    const lag = me.events - (_lastEventIdx + 1);
    if (lag > 0) {
      console.warn('[stream] watchdog: ' + lag + ' events behind (' + me.events + ' vs ' + (_lastEventIdx+1) + '); reopening');
      if (_es) { try { _es.close(); } catch {} _es = null; }
      streamFrom(_activeSid, _lastEventIdx + 1);
    }
  } catch (e) {}
}, 5000);


// ---- Platform identity + camera presence ----
// The sidebar chip, welcome line, and camera dot are all populated from the
// device (/api/system/info, /api/system/camera) — nothing board-specific is
// hardcoded in the UI. When camera presence flips, the app grid re-renders so
// camera-gated tiles grey/ungrey live.
let _camPresent = null;
async function loadPlatformInfo() {
  try {
    const r = await fetch('/api/system/info');
    const j = await r.json();
    const el = document.getElementById('platform-info');
    if (el) {
      const bits = [];
      if (j.soc) bits.push(`<span class="chip-id">${escapeHtml(j.soc)}</span>`);
      if (j.hexagon) bits.push(`Hexagon ${escapeHtml(j.hexagon)} NPU`);
      if (!bits.length && j.board) bits.push(escapeHtml(j.board));
      el.innerHTML = bits.join(' · ') || 'unknown platform';
      el.title = j.summary || 'Detected from the device at startup';
    }
    const w = document.getElementById('welcome-hw');
    if (w && (j.board || j.soc)) {
      w.textContent = ` (${[j.board, j.soc].filter(Boolean).join(', ')})`;
    }
  } catch (e) {}
}
async function camPoll() {
  try {
    const r = await fetch('/api/system/camera');
    const j = await r.json();
    const dot = document.getElementById('cam-dot');
    const txt = document.getElementById('cam-text');
    if (dot) {
      dot.style.background = j.present ? '#00d4a0' : '#ff5555';
      dot.style.boxShadow  = j.present ? '0 0 6px #00d4a0' : '0 0 6px #ff5555';
    }
    if (txt) {
      txt.textContent = j.present ? 'camera: online' : 'camera: MISSING - replug';
      txt.style.color = j.present ? '' : '#ff5555';
    }
    if (_camPresent !== null && _camPresent !== j.present) loadApps();
    _camPresent = j.present;
  } catch (e) {}
}
loadPlatformInfo();
camPoll(); setInterval(camPoll, 5000);
