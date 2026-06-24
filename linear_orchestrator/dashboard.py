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

<div class="grid">
  <div class="card">
    <div class="row"><h2>Sessions</h2><button onclick="loadAll()">refresh</button></div>
    <table id="t-sess"><thead><tr><th>session</th><th>issue / agent</th><th>events</th><th>last</th></tr></thead><tbody></tbody></table>
  </div>
  <div class="card">
    <h2>Recent deliveries</h2>
    <table id="t-deliv"><thead><tr><th>ts</th><th>session</th><th>status</th><th>detail</th></tr></thead><tbody></tbody></table>
  </div>
</div>

<div class="card" style="margin-top:16px;">
  <div class="row">
    <h2>Live stream (all sessions)</h2>
    <span class="muted" id="stream-state">connecting…</span>
  </div>
  <pre id="stream"></pre>
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
  const [s, d] = await Promise.all([
    fetch(HUB + '/sessions').then(r=>r.json()),
    fetch(HUB + '/deliveries').then(r=>r.json()),
  ]);
  const tbS = document.querySelector('#t-sess tbody');
  tbS.innerHTML = s.map(r => `
    <tr>
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
      <td class="muted">${esc(r.detail).slice(0, 160)}</td>
    </tr>`).join('');
  document.getElementById('meta').textContent =
    `${s.length} sessions · ${d.length} recent deliveries · ${new Date().toLocaleString('zh-TW')}`;
}

let streamCtrl;
async function subscribeStream() {
  if (streamCtrl) streamCtrl.abort();
  streamCtrl = new AbortController();
  const ss = document.getElementById('stream');
  const state = document.getElementById('stream-state');
  state.textContent = 'connecting…';
  try {
    const r = await fetch(HUB + '/sessions/*/stream', { signal: streamCtrl.signal });
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
    setTimeout(subscribeStream, 3000);
  }
}

loadAll();
setInterval(loadAll, 30000);
subscribeStream();
</script>
</body></html>"""


async def index(request: web.Request) -> web.Response:
    return web.Response(text=HTML, content_type="text/html", charset="utf-8")
