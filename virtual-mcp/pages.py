"""Server-rendered HTML for the app's two human-facing pages:

  /              home -- the MCP endpoint + the live merged tool list
  /login-status  manage per-service sign-in (status, sign in, revoke)

The guided-login *flow* itself is a server-side redirect controller in app.py
(`/login`), not a page here.
"""

from __future__ import annotations

import config as cfg_mod

# Clean, neutral theme (light + dark). No alarm-red chrome: a slim bordered
# header, a muted indigo accent, and soft amber/red only for real warnings.
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
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin:0; background:var(--bg); color:var(--text); }
  header { background:var(--panel); border-bottom:1px solid var(--border); padding:14px 20px; }
  .hwrap { max-width:860px; margin:0 auto; display:flex; align-items:center; justify-content:space-between; gap:16px; }
  .brand { display:flex; align-items:center; gap:10px; font-weight:650; font-size:16px; }
  .dot { width:11px; height:11px; border-radius:3px; background:var(--accent); display:inline-block; }
  nav a { color:var(--muted); text-decoration:none; font-size:14px; margin-left:18px; }
  nav a.active { color:var(--text); font-weight:600; }
  nav a:hover { color:var(--text); }
  main { max-width:860px; margin:0 auto; padding:24px 20px 64px; }
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
  button, .btn { border:1px solid var(--border); border-radius:8px; padding:8px 15px; background:var(--panel); color:var(--text); cursor:pointer; font-size:13.5px; text-decoration:none; display:inline-block; }
  button:hover, .btn:hover { border-color:var(--muted); }
  button.primary, .btn.primary { background:var(--accent); color:var(--accent-fg); border-color:var(--accent); }
  button.primary:hover { filter:brightness(1.06); }
  button:disabled { opacity:.5; cursor:default; }
  .svc { border:1px solid var(--border); border-radius:10px; padding:12px 14px; margin:10px 0; }
  .svc .name { font-size:14px; font-weight:600; }
  .svc .alias { color:var(--muted); font-size:12.5px; }
  .toolrow { font-size:13px; margin:3px 0; }
  .badge { font-size:12px; padding:3px 9px; border-radius:20px; white-space:nowrap; }
  .badge.ok { background:var(--ok-bg); color:var(--ok-fg); }
  .badge.need { background:var(--warn-bg); color:var(--warn-fg); }
  .badge.none { background:var(--idle-bg); color:var(--idle-fg); }
  .note { border-radius:10px; padding:12px 14px; font-size:13px; line-height:1.5; }
  .note.info { background:var(--info-bg); color:var(--info-fg); }
  .note.warn { background:var(--warn-bg); color:var(--warn-fg); }
  .spin { color:var(--muted); font-size:13px; }
</style>
"""

_FETCH_JS = """
async function apiGet(path) {
  const ctrl = new AbortController(); const t = setTimeout(() => ctrl.abort(), 12000);
  try { const r = await fetch(path, { signal: ctrl.signal });
    let data=null; try { data = await r.json(); } catch(e) {}
    return { ok:r.ok, status:r.status, data };
  } catch(e) { return { ok:false, status:0, data:null }; } finally { clearTimeout(t); }
}
function scopeNote() {
  return "<div class='note warn'>Couldn't reach Unity Catalog. This app needs user authorization plus an OBO scope that can read MCP services "
    + "(<code>unity-catalog</code> / <code>unity-catalog:read</code>) on its OAuth integration. After granting it, reopen this page in a new/incognito window.</div>";
}
"""


def _header(active: str) -> str:
    def link(href: str, label: str, key: str) -> str:
        cls = ' class="active"' if key == active else ""
        return f'<a href="{href}"{cls}>{label}</a>'

    return (
        '<header><div class="hwrap">'
        '<div class="brand"><span class="dot"></span>Virtual MCP Server</div>'
        '<nav>'
        + link("/", "Home", "home")
        + link("/login", "Sign in", "login")
        + link("/login-status", "Connections", "status")
        + "</nav></div></header>"
    )


def home_page(cfg: cfg_mod.VirtualMcpConfig) -> str:
    """Landing page: the MCP endpoint + the live merged tool list."""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Virtual MCP Server</title>{_STYLE}</head><body>
{_header("home")}
<main>
  <div class="card">
    <h2>MCP endpoint</h2>
    <div class="sub">Point your agent here. It merges the tools below and routes each call to the right underlying service.</div>
    <div class="endpoint"><code id="mcpUrl">…</code><button id="copy">Copy</button></div>
    <div class="sub" style="margin-top:10px">First time? <a href="/login">Sign in</a> to the underlying services, or view <a href="/login-status">Connections</a>.</div>
  </div>
  <div class="card">
    <div class="row between"><h2>Available tools</h2><button id="reload">Reload</button></div>
    <div class="sub">Exactly what an agent sees. Services you haven't signed into are skipped.</div>
    <div id="tools" style="margin-top:14px"><span class="spin">Loading…</span></div>
  </div>
</main>
<script>
{_FETCH_JS}
const url = location.origin + '/mcp';
document.getElementById('mcpUrl').textContent = url;
document.getElementById('copy').addEventListener('click', () => navigator.clipboard && navigator.clipboard.writeText(url));

async function loadTools() {{
  const box = document.getElementById('tools');
  box.innerHTML = '<span class="spin">Loading…</span>';
  const res = await apiGet('/api/tools');
  if (res.status === 401 || res.status === 0) {{ box.innerHTML = scopeNote(); return; }}
  if (!res.ok || !res.data) {{ box.innerHTML = "<div class='note warn'>Couldn't load tools (HTTP " + res.status + ").</div>"; return; }}
  const tools = res.data.tools || [], diags = res.data.diagnostics || [];
  box.innerHTML = '';
  const byAlias = {{}};
  tools.forEach(t => (byAlias[t.alias] = byAlias[t.alias] || []).push(t));
  diags.forEach(d => {{
    const div = document.createElement('div'); div.className = 'svc';
    const badge = d.error ? `<span class="badge need">${{d.error}}</span>` : `<span class="badge ok">${{d.count}} tools</span>`;
    let html = `<div class="row between"><div><span class="name">${{d.alias}}</span> <span class="alias">${{d.service}}</span></div>${{badge}}</div>`;
    (byAlias[d.alias] || []).forEach(t => html += `<div class="toolrow"><code>${{t.name}}</code> <span class="alias">${{(t.description||'').slice(0,88)}}</span></div>`);
    div.innerHTML = html; box.appendChild(div);
  }});
  if (!tools.length) {{
    const m = document.createElement('div'); m.className = 'note info';
    m.innerHTML = diags.length ? "No tools yet — <a href='/login'>sign in</a> to the services above." : "No services are configured for this app.";
    box.appendChild(m);
  }}
}}
document.getElementById('reload').addEventListener('click', loadTools);
loadTools();
</script>
</body></html>"""


def status_page(cfg: cfg_mod.VirtualMcpConfig) -> str:
    """Connections/management page: per-service state, sign in, revoke."""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Connections · Virtual MCP</title>{_STYLE}</head><body>
{_header("status")}
<main>
  <div class="card">
    <div class="row between wrap">
      <div><h2>Connections</h2><div class="sub">Sign in to each underlying service, or revoke access.</div></div>
      <div class="row wrap">
        <a class="btn primary" href="/login">Guided sign-in</a>
        <button id="revokeall">Revoke all</button>
        <button id="refresh">Refresh</button>
      </div>
    </div>
    <div id="msg" class="sub" style="margin-top:10px"></div>
    <div id="list" style="margin-top:8px"><span class="spin">Loading…</span></div>
  </div>
</main>
<script>
{_FETCH_JS}
let STATUS = [], LOGIN_BASE = '';

async function refresh() {{
  const res = await apiGet('/api/login-status');
  const root = document.getElementById('list');
  if (res.status === 401 || res.status === 0 || !res.ok) {{ root.innerHTML = scopeNote(); return []; }}
  STATUS = (res.data && res.data.services) || [];
  LOGIN_BASE = (res.data && res.data.login_base) || '';
  render(); return STATUS;
}}
function badge(s) {{
  if (s === 'ACTIVE') return '<span class="badge ok">signed in</span>';
  if (s === 'NO_AUTH') return '<span class="badge none">no sign-in needed</span>';
  return '<span class="badge need">needs sign-in</span>';
}}
function render() {{
  const root = document.getElementById('list');
  if (!STATUS.length) {{ root.innerHTML = "<div class='note info'>No services are configured for this app.</div>"; return; }}
  root.innerHTML = '';
  STATUS.forEach(s => {{
    const div = document.createElement('div'); div.className = 'svc';
    const action = s.state === 'ACTIVE'
      ? `<button data-name="${{s.name}}" class="rev">Revoke</button>`
      : (s.state === 'NEEDS_LOGIN' ? `<a class="btn" target="_blank" href="${{LOGIN_BASE}}?name=${{encodeURIComponent(s.name)}}">Sign in</a>` : '');
    div.innerHTML = `<div class="row between"><div><span class="name">${{s.name}}</span></div><div class="row">${{badge(s.state)}}${{action}}</div></div>`;
    root.appendChild(div);
  }});
  root.querySelectorAll('.rev').forEach(b => b.addEventListener('click', () => revokeOne(b.dataset.name)));
}}
async function revokeOne(name) {{
  await fetch('/api/revoke', {{ method:'POST', headers:{{'content-type':'application/json'}}, body: JSON.stringify({{ name }}) }});
  await refresh();
}}
document.getElementById('revokeall').addEventListener('click', async () => {{
  const msg = document.getElementById('msg');
  await refresh();
  const active = STATUS.filter(x => x.state === 'ACTIVE');
  if (!active.length) {{ msg.textContent = 'Nothing to revoke.'; return; }}
  for (const s of active) {{ msg.textContent = 'Revoking ' + s.name + '…'; await revokeOne(s.name); }}
  msg.textContent = '✓ Revoked all connections.';
}});
document.getElementById('refresh').addEventListener('click', refresh);
refresh();
</script>
</body></html>"""
