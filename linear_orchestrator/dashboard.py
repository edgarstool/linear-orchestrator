"""Tiny self-contained live dashboard served at GET / .

Pulls /sessions and /deliveries on load, opens NDJSON SSE-ish stream to /sessions/*/stream.
Zero deps — single HTML file rendered inline.
"""
from __future__ import annotations
from aiohttp import web


HTML = """<!doctype html>
<html lang="zh-Hant"><head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>linear-orchestrator</title>
<style>
  :root { color-scheme: dark; }
  body { font-family: ui-sans-serif, system-ui, -apple-system; background:#0b0d10; color:#e6e6e6;
         margin:0; padding:20px; }
  h1 { font-size:18px; margin:0 0 4px; }
  .sub { color:#888; font-size:12px; margin-bottom:14px; }
  .grid { display:grid; grid-template-columns: 1fr 1fr; gap:16px; }
  @media (max-width:900px) { .grid { grid-template-columns:1fr; } }
  .card { background:#12161b; border-radius:10px; padding:14px 16px; }
  .card h2 { font-size:13px; margin:0 0 10px; color:#9ab; font-weight:500; letter-spacing:.5px; text-transform:uppercase; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th, td { padding:6px 8px; border-bottom:1px solid #222; text-align:left; vertical-align:top; }
  th { color:#888; font-weight:500; font-size:11px; text-transform:uppercase; letter-spacing:.4px; }
  .pill { padding:2px 7px; border-radius:99px; font-size:11px; display:inline-block; }
  .ok { background:#0f3; color:#000; }
  .skip { background:#345; color:#bcd; }
  .fail { background:#f33; color:#fff; }
  .warn { background:#fa0; color:#000; }
  .muted { color:#888; font-size:11px; }
  pre { background:#0a0c0f; padding:8px; border-radius:6px; font-size:11px;
        max-height:380px; overflow:auto; margin:0; white-space:pre-wrap; word-break:break-word; }
  .row { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
  button { background:#234; color:#cef; border:0; padding:5px 10px; border-radius:5px; cursor:pointer; }
  button:hover { background:#345; }
  code.k { color:#8cf; }
  .stream-line { padding:3px 0; border-bottom:1px solid #181c20; font-size:11px; font-family:ui-monospace,monospace; }
  .ts { color:#688; }
</style></head>
<body>
<h1>linear-orchestrator</h1>
<div class="sub" id="meta">connecting…</div>

<div class="grid" style="margin-bottom:16px;">
  <div class="card"><div class="muted">Last 24h agent runs</div><div style="font-size:24px; font-weight:600;" id="kpi-runs">–</div><div class="muted" id="kpi-runs-sub"></div></div>
  <div class="card"><div class="muted">Success rate</div><div style="font-size:24px; font-weight:600;" id="kpi-sr">–</div><div class="muted">written / (all agent runs)</div></div>
  <div class="card"><div class="muted">Avg latency</div><div style="font-size:24px; font-weight:600;" id="kpi-lat">–</div><div class="muted">end-to-end webhook → write-back</div></div>
  <div class="card"><div class="muted">Active sessions (24h)</div><div style="font-size:24px; font-weight:600;" id="kpi-sess">–</div><div class="muted">unique session keys</div></div>
</div>

<div class="grid">
  <div class="card">
    <div class="row"><h2>Sessions</h2><button onclick="loadAll()">refresh</button></div>
    <table id="t-sess"><thead><tr><th>session</th><th>issue / agent</th><th>events</th><th>last</th></tr></thead><tbody></tbody></table>
  </div>
  <div class="card">
    <h2>Recent deliveries</h2>
    <table id="t-deliv"><thead><tr><th>ts</th><th>session</th><th>status</th><th>latency</th><th>detail</th></tr></thead><tbody></tbody></table>
  </div>
</div>

<div class="card" style="margin-top:16px;">
  <div class="row">
    <h2>Live stream <span class="muted" id="stream-scope">(all sessions)</span></h2>
    <span class="muted" id="stream-state">connecting…</span>
  </div>
  <pre id="stream"></pre>
</div>

<div id="session-modal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,.7); z-index:10; padding:30px; overflow:auto;">
  <div style="max-width:1000px; margin:0 auto; background:#0b0d10; border-radius:12px; padding:18px;">
    <div class="row">
      <h2 id="modal-title" style="margin:0;">session</h2>
      <div>
        <button id="modal-stream-btn" onclick="streamFor(currentSession)">stream this</button>
        <button onclick="closeSession()">close</button>
      </div>
    </div>
    <p class="muted" id="modal-stats">loading…</p>
    <table style="margin-top:8px;"><thead><tr><th>ts</th><th>status</th><th>latency</th><th>detail</th></tr></thead><tbody id="modal-deliv"></tbody></table>
  </div>
</div>

<script>
const HUB = location.origin;
function pill(status) {
  if (!status) return '';
  const cls = {
    'written': 'ok', 'queued': 'ok', 'duplicate': 'skip', 'skip': 'skip',
    'hermes_fail': 'fail', 'write_fail': 'fail', 'exception': 'fail',
    'hermes_skip': 'warn',
  }[status] || 'skip';
  return `<span class="pill ${cls}">${status}</span>`;
}
function esc(s) { return String(s||'').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }
async function loadAll() {
  const [s, d, stats] = await Promise.all([
    fetch(HUB + '/sessions').then(r=>r.json()),
    fetch(HUB + '/deliveries').then(r=>r.json()),
    fetch(HUB + '/stats').then(r=>r.json()),
  ]);
  document.getElementById('kpi-runs').textContent = stats.agent_runs;
  document.getElementById('kpi-runs-sub').textContent =
    Object.entries(stats.by_status).map(([k,v])=>`${k}:${v.count}`).join(' · ');
  document.getElementById('kpi-sr').textContent =
    stats.success_rate === null ? '—' : (stats.success_rate*100).toFixed(0) + '%';
  document.getElementById('kpi-lat').textContent =
    stats.avg_processing_ms ? (stats.avg_processing_ms/1000).toFixed(1) + 's' : '—';
  document.getElementById('kpi-sess').textContent = stats.active_sessions;
  const tbS = document.querySelector('#t-sess tbody');
  tbS.innerHTML = s.map(r => `
    <tr style="cursor:pointer" onclick="openSession('${esc(r.session_key)}')">
      <td><code class="k">${esc(r.session_key)}</code></td>
      <td class="muted">${esc(r.issue || r.agent_session || '')}</td>
      <td>${r.events}</td>
      <td class="muted">${esc(r.last_seen?.slice(11,19) || '')}</td>
    </tr>`).join('');
  const tbD = document.querySelector('#t-deliv tbody');
  tbD.innerHTML = d.map(r => `
    <tr>
      <td class="muted">${esc(r.ts?.slice(11,19) || '')}</td>
      <td><code class="k">${esc(r.session_key)}</code></td>
      <td>${pill(r.status)}</td>
      <td class="muted">${r.latency_ms ? (r.latency_ms/1000).toFixed(1)+'s' : ''}</td>
      <td class="muted">${esc(r.detail).slice(0, 160)}</td>
    </tr>`).join('');
  document.getElementById('meta').textContent =
    `${s.length} sessions · ${d.length} recent deliveries · ${new Date().toLocaleString('zh-TW')}`;
}

let streamCtrl;
async function subscribeStream(key) {
  if (streamCtrl) streamCtrl.abort();
  streamCtrl = new AbortController();
  const ss = document.getElementById('stream');
  const state = document.getElementById('stream-state');
  state.textContent = 'connecting…';
  const sub = encodeURIComponent(key || '*');
  try {
    const r = await fetch(HUB + '/sessions/' + sub + '/stream', { signal: streamCtrl.signal });
    state.textContent = 'connected';
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf('\\n')) >= 0) {
        const line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        if (!line) continue;
        try {
          const o = JSON.parse(line);
          const div = document.createElement('div');
          div.className = 'stream-line';
          const t = (o.ts ? new Date(o.ts * 1000).toLocaleTimeString('zh-TW') : '');
          div.innerHTML = `<span class="ts">${t}</span> <code class="k">${esc(o.session_key||'')}</code> ${esc(o.type||'')}` +
            (o.delivery_id ? ` <span class="muted">${esc(o.delivery_id.slice(0,8))}</span>` : '') +
            (o.chars ? ` · ${o.chars} chars` : '') +
            (o.detail ? ` · ${esc(o.detail).slice(0,160)}` : '') +
            (o.reply_preview ? ` · ${esc(o.reply_preview).slice(0,160)}` : '');
          ss.appendChild(div);
          while (ss.children.length > 200) ss.removeChild(ss.firstChild);
          ss.scrollTop = ss.scrollHeight;
          if (o.type === 'written' || o.type === 'write_fail') setTimeout(loadAll, 800);
        } catch (e) {}
      }
    }
  } catch (e) {
    state.textContent = 'reconnecting in 3s…';
    setTimeout(() => subscribeStream(currentSession), 3000);
  }
}

let currentSession = '*';
async function openSession(key) {
  currentSession = key;
  document.getElementById('modal-title').textContent = key;
  document.getElementById('session-modal').style.display = 'block';
  const ds = await fetch(HUB + '/deliveries?session_key=' + encodeURIComponent(key)).then(r=>r.json());
  const tb = document.getElementById('modal-deliv');
  tb.innerHTML = ds.map(r => `
    <tr>
      <td class="muted">${esc(r.ts?.slice(11,19) || '')}</td>
      <td>${pill(r.status)}</td>
      <td class="muted">${r.latency_ms ? (r.latency_ms/1000).toFixed(1)+'s' : ''}</td>
      <td class="muted">${esc(r.detail).slice(0, 220)}</td>
    </tr>`).join('');
  const total = ds.length;
  const ok = ds.filter(r => r.status === 'written').length;
  const ag = ds.filter(r => r.status !== 'skip' && r.status !== 'duplicate').length;
  document.getElementById('modal-stats').textContent =
    `${total} events · ${ok} written · ${ag} agent runs`;
}
function closeSession() {
  document.getElementById('session-modal').style.display = 'none';
  if (currentSession !== '*') { currentSession = '*'; streamFor('*'); }
}
function streamFor(key) {
  currentSession = key;
  document.getElementById('stream-scope').textContent = key === '*' ? '(all sessions)' : `(${key})`;
  document.getElementById('stream').textContent = '';
  subscribeStream(key);
}

loadAll();
setInterval(loadAll, 30000);
subscribeStream('*');
</script>
</body></html>"""


async def index(request: web.Request) -> web.Response:
    return web.Response(text=HTML, content_type="text/html", charset="utf-8")
