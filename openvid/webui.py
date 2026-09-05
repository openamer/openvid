"""OPENVID WebUI — single-file chat UI served by the HTTP API (phase 8).

Served automatically by openvid.server at / — no build step, no framework.
The page talks to the same /ask + /health endpoints.
"""
WEBUI_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>OPENVID</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { --bg:#fafafa; --fg:#111; --accent:#0a84ff; --user:#e8f0fe; }
  * { box-sizing:border-box }
  body { margin:0; font:16px/1.5 system-ui,sans-serif; background:var(--bg); color:var(--fg);
         display:flex; flex-direction:column; height:100vh; }
  header { padding:12px 20px; border-bottom:1px solid #ddd; display:flex; gap:10px; align-items:center; }
  header .dot { width:10px; height:10px; border-radius:50%; background:#aaa; }
  header .dot.ok { background:#34c759; }
  main { flex:1; overflow-y:auto; padding:20px; display:flex; flex-direction:column; gap:12px; }
  .msg { max-width:70%; padding:10px 14px; border-radius:14px; white-space:pre-wrap; }
  .user { align-self:flex-end; background:var(--user); }
  .bot { align-self:flex-start; background:#fff; border:1px solid #e5e5e5; }
  form { display:flex; gap:8px; padding:12px; border-top:1px solid #ddd; }
  input { flex:1; padding:12px; border:1px solid #ccc; border-radius:10px; font-size:16px; }
  button { padding:12px 20px; border:0; border-radius:10px; background:var(--accent); color:#fff; font-size:16px; }
  button:disabled { opacity:.5 }
</style>
</head>
<body>
<header><span class="dot" id="dot"></span><b>OPENVID</b><span id="status"></span></header>
<main id="log"></main>
<form id="f"><input id="t" autocomplete="off" placeholder="Message OPENVID…"><button id="b">Send</button></form>
<script>
const log = document.getElementById('log'), f = document.getElementById('f'),
      t = document.getElementById('t'), b = document.getElementById('b'),
      dot = document.getElementById('dot'), st = document.getElementById('status');
function add(cls, text) { const d=document.createElement('div'); d.className='msg '+cls;
  d.textContent=text; log.appendChild(d); log.scrollTop=log.scrollHeight; return d; }
async function health() { try { const r = await fetch('/health'); const j = await r.json();
  dot.className='dot ok'; st.textContent = j.status + ' · ' + j.workers.join(', ');
} catch { dot.className='dot'; st.textContent='offline'; } }
health(); setInterval(health, 5000);
f.onsubmit = async e => { e.preventDefault();
  const text = t.value.trim(); if (!text) return;
  add('user', text); t.value=''; b.disabled=true;
  const wait = add('bot', '…');
  try { const r = await fetch('/ask', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({text})});
        const j = await r.json(); wait.textContent = j.answer || '(empty)';
  } catch (err) { wait.textContent = 'error: ' + err; }
  b.disabled=false; t.focus(); };
t.focus();
</script>
</body>
</html>"""
