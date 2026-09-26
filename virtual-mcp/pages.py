"""Single-page UI for the app: the MCP endpoint plus, per underlying service, its
sign-in status, its tools, and sign-in / revoke actions -- all on `/`.

The guided-login *flow* (`/login`) is a server-side redirect controller in app.py.
"""

from __future__ import annotations

import config as cfg_mod

# Clean, neutral theme (light + dark). No alarm-red chrome.
_STYLE = """
<style>
  :root {
    color-scheme: light dark;
    --bg:#f7f8fa; --panel:#ffffff; --border:#e5e8ec; --text:#1c2530; --muted:#68727e;
    --accent:#4f46e5; --accent-fg:#ffffff; --code:#eef0f4;
    --ok-bg:#e7f6ec; --ok-fg:#1a7f37; --warn-bg:#fdf3e2; --warn-fg:#8a5a00;
    --idle-bg:#eef0f3; --idle-fg:#5a636e; --info-bg:#eef2ff; --info-fg:#3730a3;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg:#0f1319; --panel:#171c23; --border:#262d37; --text:#e6e9ee; --muted:#9aa4b0;
      --accent:#7c74f0; --code:#20262f;
      --ok-bg:#14351f; --ok-fg:#7ee2a0; --warn-bg:#3a2e12; --warn-fg:#e9c273;
      --idle-bg:#232a33; --idle-fg:#9aa4b0; --info-bg:#1e2340; --info-fg:#b9bcf7;
    }
  }
  * { box-sizing:border-box; }
  body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; margin:0; background:var(--bg); color:var(--text); }
  header { background:var(--panel); border-bottom:1px solid var(--border); padding:14px 20px; }
  .hwrap { max-width:880px; margin:0 auto; display:flex; align-items:center; gap:10px; }
  .dot { width:11px; height:11px; border-radius:3px; background:var(--accent); }
  .brand { font-weight:650; font-size:16px; }
  main { max-width:880px; margin:0 auto; padding:24px 20px 64px; }
  .card { background:var(--panel); border:1px solid var(--border); border-radius:12px; padding:18px 20px; margin-bottom:16px; }
  .card h2 { margin:0 0 4px; font-size:15px; }
  .sub { color:var(--muted); font-size:13px; line-height:1.5; }
  .row { display:flex; align-items:center; gap:10px; }
  .between { justify-content:space-between; }
  .wrap { flex-wrap:wrap; }
  a { color:var(--accent); }
  code { background:var(--code); padding:2px 7px; border-radius:6px; font-size:12.5px; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; word-break:break-all; }
  .endpoint { display:flex; align-items:center; gap:8px; margin-top:8px; }
  .endpoint code { font-size:13px; padding:8px 10px; flex:1; }
  button,.btn { border:1px solid var(--border); border-radius:8px; padding:8px 15px; background:var(--panel); color:var(--text); cursor:pointer; font-size:13.5px; text-decoration:none; display:inline-block; }
  button:hover,.btn:hover { border-color:var(--muted); }
  button.primary,.btn.primary { background:var(--accent); color:var(--accent-fg); border-color:var(--accent); }
  button:disabled { opacity:.5; cursor:default; }
  .svc { border:1px solid var(--border); border-radius:10px; padding:12px 14px; margin:10px 0; }
  .svc .name { font-size:14px; font-weight:600; }
  .svc .fqn { color:var(--muted); font-size:12.5px; margin-left:6px; }
  .toolrow { font-size:13px; margin:4px 0 0 2px; }
  .badge { font-size:12px; padding:3px 9px; border-radius:20px; white-space:nowrap; }
  .badge.ok { background:var(--ok-bg); color:var(--ok-fg); }
  .badge.need { background:var(--warn-bg); color:var(--warn-fg); }
  .badge.none { background:var(--idle-bg); color:var(--idle-fg); }
  .badge.err { background:var(--warn-bg); color:var(--warn-fg); }
  .note { border-radius:10px; padding:12px 14px; font-size:13px; line-height:1.5; margin-top:12px; }
  .note.info { background:var(--info-bg); color:var(--info-fg); }
  .note.warn { background:var(--warn-bg); color:var(--warn-fg); }
  .spin { color:var(--muted); font-size:13px; }
</style>
"""

_FETCH_JS = """
async function apiGet(path) {
  const ctrl = new AbortController(); const t = setTimeout(() => ctrl.abort(), 20000);
  try { const r = await fetch(path, { signal: ctrl.signal });
    let data=null; try { data = await r.json(); } catch(e) {}
    return { ok:r.ok, status:r.status, data };
  } catch(e) { return { ok:false, status:0, data:null }; } finally { clearTimeout(t); }
}
"""


def home_page(cfg: cfg_mod.VirtualMcpConfig) -> str:
    """Everything on one page: endpoint + per-service status, tools, sign in, revoke."""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Virtual MCP Server</title>{_STYLE}</head><body>
<header><div class="hwrap"><span class="dot"></span><span class="brand">Virtual MCP Server</span></div></header>
<main>
  <div class="card">
    <h2>MCP endpoint</h2>
    <div class="sub">Point your agent here. It merges the tools below and routes each call to the right service.</div>
    <div class="endpoint"><code id="mcpUrl">…</code><button id="copy">Copy</button></div>
  </div>
  <div class="card">
    <div class="row between wrap">
      <div><h2>Services &amp; tools</h2><div class="sub">Sign in to each service to expose its tools. Status shown per service.</div></div>
      <div class="row wrap">
        <a class="btn primary" href="/login">Sign in to all</a>
        <button id="revokeall">Revoke all</button>
        <button id="reload">Reload</button>
      </div>
    </div>
    <div id="msg" class="sub" style="margin-top:8px"></div>
    <div id="list" style="margin-top:12px"><span class="spin">Loading…</span></div>
  </div>
</main>
<script>
{_FETCH_JS}
const url = location.origin + '/mcp';
document.getElementById('mcpUrl').textContent = url;
document.getElementById('copy').addEventListener('click', () => navigator.clipboard && navigator.clipboard.writeText(url));

let LOGIN_BASE = '', STATES = [];

function badge(state) {{
  if (state === 'ACTIVE') return '<span class="badge ok">signed in</span>';
  if (state === 'NO_AUTH') return '<span class="badge none">no sign-in needed</span>';
  return '<span class="badge need">needs sign-in</span>';
}}

async function load() {{
  const list = document.getElementById('list');
  list.innerHTML = '<span class="spin">Loading…</span>';
  const [st, tl] = await Promise.all([apiGet('/api/login-status'), apiGet('/api/tools')]);
  if (st.status === 401 || st.status === 0 || !st.ok) {{
    list.innerHTML = "<div class='note warn'>This app needs user authorization plus a <code>unity-catalog</code> (or <code>unity-catalog:read</code>) scope on its OAuth integration. After granting it, reopen this page in a new/incognito window.</div>";
    return;
  }}
  STATES = (st.data && st.data.services) || [];
  LOGIN_BASE = (st.data && st.data.login_base) || '';
  // index tools + diagnostics by service alias / name
  const tools = (tl.data && tl.data.tools) || [], diags = (tl.data && tl.data.diagnostics) || [];
  const byAlias = {{}}; tools.forEach(t => (byAlias[t.alias] = byAlias[t.alias] || []).push(t));
  const diagByName = {{}}; diags.forEach(d => diagByName[d.service] = d);

  if (!STATES.length) {{ list.innerHTML = "<div class='note info'>No services are configured for this app.</div>"; return; }}
  list.innerHTML = '';
  STATES.forEach(s => {{
    const d = diagByName[s.name] || {{}};
    const tools = byAlias[d.alias] || [];
    const toolBadge = d.error ? `<span class="badge err">${{d.error}}</span>` : (d.ok ? `<span class="badge none">${{d.count}} tools</span>` : '');
    const action = s.state === 'ACTIVE'
      ? `<button data-name="${{s.name}}" class="rev">Revoke</button>`
      : (s.state === 'NEEDS_LOGIN' ? `<a class="btn" target="_blank" href="${{LOGIN_BASE}}?name=${{encodeURIComponent(s.name)}}">Sign in</a>` : '');
    const div = document.createElement('div'); div.className = 'svc';
    let html = `<div class="row between wrap"><div><span class="name">${{d.alias || s.name}}</span><span class="fqn">${{s.name}}</span></div>`
             + `<div class="row wrap">${{badge(s.state)}}${{toolBadge}}${{action}}</div></div>`;
    tools.forEach(t => html += `<div class="toolrow"><code>${{t.name}}</code> <span class="fqn">${{(t.description||'').slice(0,80)}}</span></div>`);
    div.innerHTML = html; list.appendChild(div);
  }});
}}

async function revokeOne(name) {{
  await fetch('/api/revoke', {{ method:'POST', headers:{{'content-type':'application/json'}}, body: JSON.stringify({{ name }}) }});
}}
document.getElementById('list').addEventListener('click', async (e) => {{
  const b = e.target.closest('.rev'); if (!b) return;
  b.disabled = true; await revokeOne(b.dataset.name); await load();
}});
document.getElementById('revokeall').addEventListener('click', async () => {{
  const msg = document.getElementById('msg');
  const active = STATES.filter(x => x.state === 'ACTIVE');
  if (!active.length) {{ msg.textContent = 'Nothing to revoke.'; return; }}
  for (const s of active) {{ msg.textContent = 'Revoking ' + s.name + '…'; await revokeOne(s.name); }}
  msg.textContent = '✓ Revoked all connections.'; await load();
}});
document.getElementById('reload').addEventListener('click', load);
load();
</script>
</body></html>"""
