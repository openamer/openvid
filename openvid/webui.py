"""OPENVID WebUI v2 — chat + mic (STT/TTS) + settings + streaming feel.

Served by server.py at /. Improvements over v1:
- mic button: MediaRecorder -> /stt -> text -> /ask; answer auto-spoken via /tts
- settings drawer: model + agent mode + auto-approve, POST /config
- optimistic message list with spinner, health indicator as before
"""
WEBUI_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>OPENVID</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { --bg:#fafafa; --fg:#111; --accent:#0a84ff; --user:#e8f0fe; --warn:#ff9f0a; }
  * { box-sizing:border-box }
  body { margin:0; font:16px/1.5 system-ui,sans-serif; background:var(--bg); color:var(--fg);
         display:flex; flex-direction:column; height:100vh; }
  header { padding:10px 16px; border-bottom:1px solid #ddd; display:flex; gap:10px; align-items:center; }
  header .dot { width:10px; height:10px; border-radius:50%; background:#aaa; }
  header .dot.ok { background:#34c759; }
  header .spacer { flex:1 }
  .gear { cursor:pointer; font-size:20px; opacity:.6 }
  #settings { display:none; padding:14px 20px; background:#f0f0f0; border-bottom:1px solid #ddd; }
  #settings.open { display:block }
  #settings label { display:block; margin:8px 0 2px; font-size:13px; opacity:.7 }
  #settings input { width:100%; padding:8px; border:1px solid #ccc; border-radius:8px; }
  #settings button { margin-top:10px; }
  main { flex:1; overflow-y:auto; padding:20px; display:flex; flex-direction:column; gap:12px; }
  .msg { max-width:70%; padding:10px 14px; border-radius:14px; white-space:pre-wrap; }
  .user { align-self:flex-end; background:var(--user); }
  .bot { align-self:flex-start; background:#fff; border:1px solid #e5e5e5; }
  form { display:flex; gap:8px; padding:12px; border-top:1px solid #ddd; align-items:center; }
  input[type=text] { flex:1; padding:12px; border:1px solid #ccc; border-radius:10px; font-size:16px; }
  button { padding:12px 18px; border:0; border-radius:10px; background:var(--accent); color:#fff; font-size:16px; cursor:pointer; }
  button:disabled { opacity:.5 }
  #mic { background:#fff; color:var(--fg); border:1px solid #ccc; font-size:18px; }
  #mic.rec { background:var(--warn); color:#fff; border-color:var(--warn); }
</style>
</head>
<body>
<header>
  <span class="dot" id="dot"></span><b>OPENVID</b><span id="status"></span>
  <span class="spacer"></span><span class="gear" id="gear" title="Settings">⚙</span>
</header>
<div id="settings">
  <label>Model (z-ai/glm-5.3-flash, anthropic/..., or local)</label>
  <input id="cfgModel" placeholder="z-ai/glm-5.3-flash">
  <label>Files root (extra readable dirs, comma separated)</label>
  <input id="cfgRoots" placeholder="C:/Users/you/projects">
  <button id="cfgSave">Save & restart backend</button>
  <span id="cfgMsg"></span>
</div>
<main id="log"></main>
<form id="f">
  <button type="button" id="mic" title="Voice input">🎤</button>
  <input type="text" id="t" autocomplete="off" placeholder="Message OPENVID…">
  <button id="b">Send</button>
</form>
<script>
const log=document.getElementById('log'), f=document.getElementById('f'),
      t=document.getElementById('t'), b=document.getElementById('b'),
      mic=document.getElementById('mic'), dot=document.getElementById('dot'),
      st=document.getElementById('status'), gear=document.getElementById('gear'),
      settings=document.getElementById('settings');

function add(cls,text){const d=document.createElement('div');d.className='msg '+cls;
  d.textContent=text;log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
async function health(){try{const r=await fetch('/health');const j=await r.json();
  dot.className='dot ok';st.textContent=j.status+' · '+j.workers.join(', ');
}catch{dot.className='dot';st.textContent='offline';}}
health();setInterval(health,5000);

gear.onclick=()=>settings.classList.toggle('open');
document.getElementById('cfgSave').onclick=async()=>{
  const body={};
  const m=document.getElementById('cfgModel').value.trim();
  const r=document.getElementById('cfgRoots').value.trim();
  if(m)body.OPENVID_LLM_MODEL=m; if(r)body.OPENVID_FILES_ROOT=r;
  const res=await fetch('/config',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body)});
  const j=await res.json();
  document.getElementById('cfgMsg').textContent = j.ok ? 'saved ✓ (restart backend for model change)' : 'failed';
};

f.onsubmit=async e=>{e.preventDefault();
  const text=t.value.trim(); if(!text)return;
  add('user',text); t.value=''; b.disabled=true; mic.disabled=true;
  const wait=add('bot','…');
  try{const r=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text})});
      const j=await r.json(); wait.textContent=j.answer||'(empty)';
      speak(j.answer||'');
  }catch(err){wait.textContent='error: '+err;}
  b.disabled=false; mic.disabled=false; t.focus(); };

// ---- voice ----
let media=null, chunks=[], recOn=false;
mic.onclick=async()=>{
  if(recOn){ media.stop(); return; }
  try{
    const stream=await navigator.mediaDevices.getUserMedia({audio:true});
    media=new MediaRecorder(stream); chunks=[];
    media.ondataavailable=e=>chunks.push(e.data);
    media.onstop=async()=>{
      recOn=false; mic.classList.remove('rec');
      stream.getTracks().forEach(x=>x.stop());
      const blob=new Blob(chunks,{type:'audio/webm'});
      const b64=btoa(String.fromCharCode(...new Uint8Array(await blob.arrayBuffer())));
      mic.disabled=true;
      const wait=add('bot','🎙 transcribing…');
      try{
        const r=await fetch('/stt',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({audio:b64})});
        const j=await r.json();
        if(j.text){ wait.remove(); t.value=j.text; f.dispatchEvent(new Event('submit')); }
        else { wait.textContent='STT: '+(j.error||'no text'); }
      }catch(err){ wait.textContent='STT error: '+err; }
      mic.disabled=false;
    };
    media.start(); recOn=true; mic.classList.add('rec');
  }catch(err){ add('bot','mic error: '+err.message); }
};
function speak(text){
  if(!text || text.length>600) return;
  const u=new URL('/tts?text='+encodeURIComponent(text),'location');
  const a=new Audio(u); a.play().catch(()=>{});  // silent fail if no TTS key
}
t.focus();
</script>
</body>
</html>"""
