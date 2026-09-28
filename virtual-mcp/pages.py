"""Server-rendered shell for the Virtual MCP explorer UI. Everything is loaded
client-side from the JSON APIs (/api/login-status, /api/tools, /api/call,
/api/revoke); the page is a two-pane layout -- a left nav of services and a
detail pane showing each service's status, tools, and a tool-invocation form.

CSS/JS are plain strings (not f-strings) so their braces need no escaping.
"""

from __future__ import annotations

import config as cfg_mod

_STYLE = """
<style>
 :root{--blue600:#2272b4;--blue700:#0e538b;--blue800:#04355d;
   --ink:#161616;--muted:#6f6f6f;--line:#e3e6ea;--hair:#f2f2f2;--bg:#f7f8fa;--card:#fff;
   --shadow:0 4px 16px rgba(31,39,45,.10);--radius:8px;
   --green-bg:#e5f4ea;--green:#137a3e;--amber-bg:#fcf3e0;--amber:#8a5a00;
   --gray-bg:#f0f0f0;--gray:#6f6f6f;--red-bg:#fbeaea;--red:#b4232c}
 @media(prefers-color-scheme:dark){:root{--ink:#e6e9ee;--muted:#9aa4b0;--line:#2a323d;--hair:#232a33;
   --bg:#0f1319;--card:#171c23;--gray-bg:#232a33;--gray:#9aa4b0;--blue600:#4f8fd0;--blue700:#6aa3dd;
   --green-bg:#123f1e;--green:#7ee2a0;--amber-bg:#3a2e12;--amber:#e9c273;--red-bg:#4a1f1f;--red:#ffb4b4;
   --shadow:0 4px 16px rgba(0,0,0,.35)}}
 *{box-sizing:border-box}
 body{margin:0;font-family:'DM Sans',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
   color:var(--ink);background:var(--bg);line-height:1.5;font-size:13px}
 header{background:var(--card);border-bottom:1px solid var(--line);padding:16px 0}
 .hwrap{max-width:1160px;margin:0 auto;padding:0 28px;display:flex;align-items:center;
   justify-content:space-between;gap:20px;flex-wrap:wrap}
 header h1{margin:0;font-size:18px;font-weight:600;display:flex;align-items:center;gap:9px}
 .dot0{width:11px;height:11px;border-radius:3px;background:var(--blue600)}
 header p{margin:5px 0 0;font-size:13px;color:var(--muted)}
 .endpoint{display:flex;align-items:center;gap:8px;margin-top:8px}
 .endpoint code{background:var(--gray-bg);padding:6px 10px;border-radius:6px;font-size:12.5px;
   font-family:ui-monospace,Menlo,Consolas,monospace}
 .hactions{display:flex;gap:8px;flex-wrap:wrap}
 .wrap{display:flex;gap:24px;padding:24px 28px;max-width:1160px;margin:0 auto;align-items:flex-start}
 .list{flex:0 0 320px}.detail{flex:1;min-width:0}
 @media(max-width:880px){.wrap{flex-direction:column}.list{flex:1 1 auto;width:100%}}
 .card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}
 .card-h{padding:12px 16px;border-bottom:1px solid var(--line);font-size:12px;text-transform:uppercase;
   letter-spacing:.5px;color:var(--muted);font-weight:600}
 .row{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:11px 16px;
   border-bottom:1px solid var(--hair);color:var(--ink);cursor:pointer}
 .row:last-child{border-bottom:none}.row:hover{background:var(--hair)}
 .row.sel{background:rgba(34,114,180,.10);box-shadow:inset 3px 0 0 var(--blue600)}
 .row .nm{font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .row .al{color:var(--muted);font-size:11.5px}
 .dot{flex:none;width:9px;height:9px;border-radius:50%;background:var(--gray)}
 .dot.ok{background:var(--green);box-shadow:0 0 0 3px var(--green-bg)}
 .pill{flex:none;font-size:11px;font-weight:600;padding:2px 9px;border-radius:999px;white-space:nowrap}
 .pill.warn{background:var(--amber-bg);color:var(--amber)}
 .pill.err{background:var(--red-bg);color:var(--red)}
 .pill.none{background:var(--gray-bg);color:var(--gray)}
 .pill.ok{background:var(--green-bg);color:var(--green)}
 .dbody{padding:24px}
 .dhead{display:flex;align-items:center;flex-wrap:wrap;gap:10px;margin:0 0 4px}
 .dtitle{font-size:22px;font-weight:600;margin:0}
 .dsub{color:var(--muted);font-size:13px;margin:0 0 16px}
 dl{display:grid;grid-template-columns:150px 1fr;gap:8px 16px;margin:0 0 8px}
 dt{color:var(--muted)}dd{margin:0;word-break:break-word}
 code{font-family:ui-monospace,Menlo,Consolas,monospace}
 .btn{display:inline-block;padding:8px 15px;border-radius:6px;font-size:13px;font-weight:600;
   text-decoration:none;border:1px solid transparent;cursor:pointer;font-family:inherit}
 .btn-sm{padding:5px 12px;font-size:12px}
 .btn:disabled{opacity:.55;cursor:default}
 .btn-primary{background:var(--blue600);color:#fff}.btn-primary:hover{background:var(--blue700)}
 .btn-secondary{background:transparent;color:var(--ink);border-color:var(--line)}
 .btn-secondary:hover{border-color:var(--muted)}
 .sec{font-weight:600;font-size:13px;margin:20px 0 6px}
 table{width:100%;border-collapse:collapse}
 th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--hair);vertical-align:top}
 th{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;font-weight:600}
 .tname{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12.5px;white-space:nowrap}
 .tag{font-size:11px;padding:2px 7px;border-radius:5px;font-weight:600}
 .tag.read{background:var(--green-bg);color:var(--green)}
 .tag.write{background:var(--amber-bg);color:var(--amber)}
 .tag.neutral{background:var(--gray-bg);color:var(--gray)}
 td.desc{max-width:520px}
 details.descx>summary{cursor:pointer;list-style:none;display:block;white-space:nowrap;overflow:hidden;
   text-overflow:ellipsis;color:var(--muted);font-size:12.5px}
 details.descx>summary::-webkit-details-marker{display:none}
 details.descx>summary::before{content:"\\25B8  ";color:var(--muted)}
 details.descx[open]>summary{white-space:normal;overflow:visible}
 details.descx[open]>summary::before{content:"\\25BE  "}
 .field{display:flex;flex-direction:column;gap:4px;margin:8px 0}
 .field label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.03em}
 select,textarea{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12.5px;padding:8px 10px;
   border:1px solid var(--line);border-radius:6px;color:var(--ink);background:var(--card)}
 textarea{min-height:70px;resize:vertical}
 select:focus,textarea:focus{outline:none;border-color:var(--blue600)}
 .callout{background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:12px;margin-top:10px;
   font-size:12px;font-family:ui-monospace,Menlo,Consolas,monospace;white-space:pre-wrap;
   overflow-wrap:anywhere;max-height:340px;overflow:auto}
 .note{border-radius:8px;padding:12px 14px;font-size:13px;margin:12px 0}
 .note.warn{background:var(--amber-bg);color:var(--amber)}
 .muted{color:var(--muted)}
 .spin{color:var(--muted)}
</style>
"""

_APP_JS = """
async function api(path, opts){
  const c=new AbortController();const t=setTimeout(()=>c.abort(),30000);
  try{const r=await fetch(path,Object.assign({signal:c.signal},opts||{}));
    let d=null;try{d=await r.json()}catch(e){};return{ok:r.ok,status:r.status,data:d};}
  catch(e){return{ok:false,status:0,data:null}}finally{clearTimeout(t)}
}
const MCP_URL = location.origin + '/mcp';
let STATES=[], LOGIN_BASE='', TOOLS={}, SCHEMA={}, DIAG={}, SEL=null;

function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function tagFor(n){const b=n.split('__').pop();
  if(/^(get|list|search|read|poll|fetch)_?/.test(b))return'read';
  if(/^(create|update|delete|send|write|add|remove|run|revoke|cancel|set)_?/.test(b))return'write';
  return'neutral'}
function statusPill(state){
  if(state==='ACTIVE')return'<span class="pill ok">signed in</span>';
  if(state==='NO_AUTH')return'<span class="pill none">no sign-in</span>';
  if(state==='UNKNOWN')return'<span class="pill err">unavailable</span>';
  return'<span class="pill warn">needs sign-in</span>'}

async function boot(){
  document.getElementById('mcpurl').textContent=MCP_URL;
  document.getElementById('copybtn').onclick=()=>navigator.clipboard&&navigator.clipboard.writeText(MCP_URL);
  document.getElementById('signinall').onclick=signInAll;
  document.getElementById('revokeall').onclick=revokeAll;
  await load();
}

async function load(){
  const [st,tl]=await Promise.all([api('/api/login-status'),api('/api/tools')]);
  const nav=document.getElementById('nav');
  if(st.status===401||st.status===0||!st.ok){
    nav.innerHTML="<div class='note warn' style='margin:12px'>Needs user authorization + a writable <code>unity-catalog</code> scope. Reopen in a fresh window after it's granted.</div>";
    return;
  }
  STATES=(st.data&&st.data.services)||[]; LOGIN_BASE=(st.data&&st.data.login_base)||'';
  TOOLS={}; SCHEMA={}; DIAG={};
  ((tl.data&&tl.data.tools)||[]).forEach(t=>{(TOOLS[t.alias]=TOOLS[t.alias]||[]).push(t);SCHEMA[t.name]=t.inputSchema||{}});
  ((tl.data&&tl.data.diagnostics)||[]).forEach(d=>DIAG[d.name]=d);
  renderNav();
  if(!SEL&&STATES.length)SEL=STATES[0].name;
  renderDetail();
}

function renderNav(){
  const nav=document.getElementById('nav');
  if(!STATES.length){nav.innerHTML="<div class='muted' style='padding:14px 16px'>No services configured.</div>";return}
  nav.innerHTML=STATES.map(s=>{
    const on=s.name===SEL?' sel':'';
    const dot=s.state==='ACTIVE'?'<span class="dot ok"></span>':'';
    return `<div class="row${on}" data-name="${esc(s.name)}"><div style="min-width:0">`
      +`<div class="nm">${esc(s.alias||s.name)}</div><div class="al">${esc(s.name)}</div></div>`
      +`<div style="display:flex;align-items:center;gap:8px">${dot}${statusPill(s.state)}</div></div>`;
  }).join('');
  nav.querySelectorAll('.row').forEach(r=>r.onclick=()=>{SEL=r.dataset.name;renderNav();renderDetail()});
}

function renderDetail(){
  const el=document.getElementById('detail');
  const s=STATES.find(x=>x.name===SEL);
  if(!s){el.innerHTML="<div class='dbody muted'>Select a service on the left.</div>";return}
  const tools=TOOLS[s.alias]||[], diag=DIAG[s.name]||{};
  const action = s.state==='ACTIVE'
    ? `<button class="btn btn-secondary btn-sm" id="revbtn">Revoke</button>`
    : (s.state==='NO_AUTH' ? ''
       : `<a class="btn btn-primary btn-sm" target="_blank" href="${LOGIN_BASE}?name=${encodeURIComponent(s.name)}">Sign in</a>`);
  const toolErr = diag.error ? `<div class="note warn">Tools unavailable: ${esc(diag.error)}</div>` : '';
  const rows = tools.map(t=>{const b=t.name.split('__').pop();const tg=tagFor(t.name);
    const desc=(t.description||'').replace(/^\\[[^\\]]*\\]\\s*/,'');
    const dcell=desc?`<details class="descx"><summary>${esc(desc)}</summary></details>`:'<span class="muted">—</span>';
    return `<tr><td class="tname">${esc(b)} <span class="tag ${tg}">${tg}</span></td><td class="desc">${dcell}</td></tr>`}).join('');
  el.innerHTML = `<div class="dbody">
    <div class="dhead"><h2 class="dtitle">${esc(s.alias||s.name)}</h2>${statusPill(s.state)}${action}</div>
    <p class="dsub">${esc(s.name)}</p>
    <dl><dt>Full name</dt><dd><code>${esc(s.name)}</code></dd>
        <dt>Alias (tool prefix)</dt><dd><code>${esc(s.alias)}__</code></dd>
        <dt>Tools exposed</dt><dd>${tools.length}</dd></dl>
    ${toolErr}
    <div class="sec">Tools (${tools.length})</div>
    ${tools.length?`<table><thead><tr><th>Tool</th><th>Description</th></tr></thead><tbody>${rows}</tbody></table>`:'<div class="muted">No tools.</div>'}
    ${tools.length?invokeHtml(s,tools):''}
  </div>`;
  const rb=document.getElementById('revbtn'); if(rb)rb.onclick=()=>revoke(s.name);
  if(tools.length)wireInvoke(s);
}

function invokeHtml(s,tools){
  const opts=tools.map(t=>`<option value="${esc(t.name)}">${esc(t.name.split('__').pop())}</option>`).join('');
  return `<div class="sec">Invoke a tool</div>
    <div class="field"><label>Tool</label><select id="tsel">${opts}</select></div>
    <div class="field"><label>Arguments (JSON)</label><textarea id="targs">{}</textarea></div>
    <button class="btn btn-primary btn-sm" id="runbtn">Run</button>
    <div id="result"></div>`;
}
function wireInvoke(s){
  const sel=document.getElementById('tsel'), args=document.getElementById('targs');
  const showSchema=()=>{const sc=SCHEMA[sel.value]||{};const props=(sc&&sc.properties)||{};
    if(Object.keys(props).length&&args.value.trim()==='{}'){
      const tmpl={};Object.keys(props).forEach(k=>tmpl[k]=(props[k]&&props[k].type)||'');
      args.value=JSON.stringify(tmpl,null,2)}};
  sel.onchange=()=>{args.value='{}';showSchema()}; showSchema();
  document.getElementById('runbtn').onclick=async()=>{
    const out=document.getElementById('result');const btn=document.getElementById('runbtn');
    let parsed;try{parsed=JSON.parse(args.value||'{}')}catch(e){out.innerHTML=`<div class="callout">Invalid JSON: ${esc(e.message)}</div>`;return}
    btn.disabled=true;out.innerHTML='<div class="spin" style="margin-top:10px">Running…</div>';
    const r=await api('/api/call',{method:'POST',headers:{'content-type':'application/json'},
      body:JSON.stringify({name:sel.value,arguments:parsed})});
    btn.disabled=false;const d=r.data||{};
    if(d.needs_login){out.innerHTML=`<div class="note warn">Not signed in to <code>${esc(s.name)}</code>. <a target="_blank" href="${LOGIN_BASE}?name=${encodeURIComponent(s.name)}">Sign in</a> and retry.</div>`;return}
    if(d.error){out.innerHTML=`<div class="callout">${esc(d.error)}</div>`;return}
    out.innerHTML=`<div class="callout">${esc(d.text||'(no output)')}</div>`;
  };
}

async function revoke(name){
  const r=await api('/api/revoke',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({name})});
  const d=r.data||{};
  if(d&&d.ok===false){alert('Revoke failed (HTTP '+d.status+')'+(d.detail?' — '+d.detail:''));return}
  await load();
}
async function revokeAll(){
  const active=STATES.filter(x=>x.state==='ACTIVE');
  for(const s of active){const r=await api('/api/revoke',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({name:s.name})});
    const d=r.data||{};if(d&&d.ok===false){alert('Revoke failed for '+s.name+' (HTTP '+d.status+')');break}}
  await load();
}
async function pollActive(name){
  // Poll the app (same-origin) until this service is no longer NEEDS_LOGIN.
  for(let i=0;i<40;i++){
    await new Promise(r=>setTimeout(r,3000));
    const st=await api('/api/login-status');
    const svc=((st.data&&st.data.services)||[]).find(x=>x.name===name);
    if(!svc||svc.state!=='NEEDS_LOGIN')return true;
  }
  return false;
}
async function signInAll(){
  const btn=document.getElementById('signinall');
  // Open ONE popup synchronously inside the click gesture (avoids the popup
  // blocker), then reuse it -- navigating it to each service's platform login in
  // turn and polling our own API between. This works cross-origin (no return_to,
  // which the workspace login page won't honor back to the app origin).
  const win=window.open('about:blank','mcp_signin','width=560,height=720');
  if(!win){alert('Popup blocked — allow popups for this app, then click Sign in to all again.');return}
  await load();
  const pending=STATES.filter(s=>s.state==='NEEDS_LOGIN');
  if(!pending.length){try{win.close()}catch(e){}; return}
  btn.disabled=true;
  for(let i=0;i<pending.length;i++){
    const s=pending[i];
    if(win.closed)break;
    try{win.location.href=LOGIN_BASE+'?name='+encodeURIComponent(s.name)}catch(e){}
    btn.textContent='Signing in '+(i+1)+'/'+pending.length+'…';
    await pollActive(s.name);
    await load();               // live-update nav/detail as each completes
  }
  try{win.close()}catch(e){}
  btn.disabled=false;btn.textContent='Sign in to all';
}
window.addEventListener('DOMContentLoaded',boot);
"""


def home_page(cfg: cfg_mod.VirtualMcpConfig) -> str:
    body = """
<header><div class="hwrap">
  <div>
    <h1><span class="dot0"></span>Virtual MCP Server</h1>
    <p>Point your agent here. It merges the tools below and routes each call to the right service.</p>
    <div class="endpoint"><code id="mcpurl">…</code><button class="btn btn-secondary btn-sm" id="copybtn">Copy</button></div>
  </div>
  <div class="hactions">
    <button class="btn btn-primary" id="signinall">Sign in to all</button>
    <button class="btn btn-secondary" id="revokeall">Revoke all</button>
  </div>
</div></header>
<div class="wrap">
  <div class="list"><div class="card"><div class="card-h">Services</div><div id="nav"><div class="spin" style="padding:14px 16px">Loading…</div></div></div></div>
  <div class="detail"><div class="card"><div id="detail"><div class="dbody spin">Loading…</div></div></div></div>
</div>
"""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Virtual MCP Server</title>"
        "<link rel='preconnect' href='https://fonts.googleapis.com'>"
        "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700&display=swap'>"
        + _STYLE
        + "</head><body>"
        + body
        + "<script>"
        + _APP_JS
        + "</script></body></html>"
    )
