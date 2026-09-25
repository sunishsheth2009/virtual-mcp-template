"""Server-rendered HTML shells. The heavy lifting is client-side JS hitting the
JSON APIs in app.py -- keeps all the list/tool/login logic in the app template
rather than requiring changes elsewhere.

The running app is a *ready MCP server*: `/` (home) shows the endpoint and the
live tool list post-login. Which services are mixed in is decided at app-creation
time (the VIRTUAL_MCP_CONFIG env var); `/configure` is the optional picker to
change that selection afterwards.
"""

from __future__ import annotations

import config as cfg_mod

_STYLE = """
<style>
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; background: #f6f7f9; color: #1b1f24; }
  @media (prefers-color-scheme: dark) { body { background: #14171a; color: #e6e6e6; } .card,.svc { background: #1e2227 !important; border-color: #2c3138 !important; } input,button { background:#2a2f36; color:#e6e6e6; border-color:#3a4048; } }
  header { background: #ff3621; color: #fff; padding: 18px 24px; }
  header h1 { margin: 0; font-size: 20px; }
  header a { color: #ffe3df; margin-left: 16px; font-size: 14px; text-decoration: none; }
  header a:hover { text-decoration: underline; }
  main { max-width: 900px; margin: 0 auto; padding: 24px 16px 64px; }
  .card { background: #fff; border: 1px solid #e2e5e9; border-radius: 10px; padding: 16px 18px; margin-bottom: 16px; }
  .svc { background: #fff; border: 1px solid #e2e5e9; border-radius: 8px; padding: 12px 14px; margin: 8px 0; }
  .svc h3 { margin: 0 0 4px; font-size: 15px; }
  .row { display: flex; align-items: center; gap: 10px; }
  .between { justify-content: space-between; }
  .muted { color: #6b7480; font-size: 13px; }
  code { background: rgba(127,127,127,.15); padding: 2px 6px; border-radius: 4px; font-size: 13px; word-break: break-all; }
  button { border: 1px solid #c8ccd1; border-radius: 6px; padding: 7px 14px; background: #fff; cursor: pointer; font-size: 14px; }
  button.primary { background: #ff3621; color: #fff; border-color: #ff3621; }
  input[type=text] { border: 1px solid #c8ccd1; border-radius: 6px; padding: 6px 8px; font-size: 13px; width: 220px; }
  .tools { margin: 8px 0 0 0; }
  .tools label, .tool-item { display: block; font-size: 13px; margin: 2px 0; }
  .badge { font-size: 12px; padding: 2px 8px; border-radius: 10px; }
  .badge.ok { background: #d8f5dd; color: #145523; }
  .badge.need { background: #ffe1b3; color: #7a4a00; }
  .badge.none { background: #e5e7eb; color: #4b5563; }
  .err { background: #ffe0e0; color: #7a1a1a; border-radius: 6px; padding: 8px 10px; font-size: 13px; }
  @media (prefers-color-scheme: dark) { .err { background:#4a1f1f; color:#ffd0d0; } .badge.ok{background:#123f1e;color:#9be3ac} .badge.need{background:#4a3410;color:#ffcf87} .badge.none{background:#2c3138;color:#aab2bd} }
</style>
"""

# Shared JS: a fetch that always resolves to {ok, status, data|error} and never
# hangs (10s timeout), so a page never gets stuck on a spinner.
_FETCH_JS = """
async function apiGet(path) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 10000);
  try {
    const r = await fetch(path, { signal: ctrl.signal });
    let data = null;
    try { data = await r.json(); } catch (e) { data = null; }
    return { ok: r.ok, status: r.status, data };
  } catch (e) {
    return { ok: false, status: 0, data: null, error: String(e) };
  } finally { clearTimeout(t); }
}
function scopeHintHtml() {
  return "<div class='err'>Couldn't reach Unity Catalog. This app needs user authorization enabled and an OBO scope that can read MCP services " +
    "(e.g. <code>unity-catalog</code> / <code>all-apis</code> / <code>catalog.*</code>) added to its OAuth app integration. " +
    "Once the scope is granted, reopen this page (clear the app cookie / use incognito).</div>";
}
"""


def _header(active: str) -> str:
    def link(href, label, key):
        star = " ●" if key == active else ""
        return f'<a href="{href}">{label}{star}</a>'

    return (
        "<header><div class='row between'>"
        "<h1>Virtual MCP Server</h1><div>"
        + link("/", "Home", "home")
        + link("/login", "Guided Login", "login")
        + "</div></div></header>"
    )


def home_page(cfg: cfg_mod.VirtualMcpConfig) -> str:
    """The ready-MCP-server landing page: endpoint + live tools post-login."""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Virtual MCP</title>{_STYLE}</head><body>
{_header("home")}
<main>
  <div class="card">
    <div class="muted">Agents connect to this virtual MCP endpoint:</div>
    <div style="margin-top:6px"><code id="mcpUrl">…</code></div>
    <div class="muted" style="margin-top:8px">It merges the tools below and routes each call to its underlying service.
      New here? Run <a href="/login">Guided Login</a> first to sign in to every underlying service.</div>
  </div>
  <div class="card">
    <div class="row between">
      <strong>Tools in this virtual MCP</strong>
      <button id="reload">Reload</button>
    </div>
    <div class="muted" style="margin-top:6px">This is exactly what an agent sees post-login. Services you haven't signed into yet are skipped — do <a href="/login">Guided Login</a>.</div>
    <div id="tools" style="margin-top:12px">Loading tools…</div>
  </div>
</main>
<script>
{_FETCH_JS}
document.getElementById('mcpUrl').textContent = location.origin + '/mcp';

async function loadTools() {{
  const box = document.getElementById('tools');
  box.innerHTML = 'Loading tools…';
  const res = await apiGet('/api/tools');
  if (res.status === 401 || (!res.ok && res.status === 0)) {{ box.innerHTML = scopeHintHtml(); return; }}
  if (!res.ok || !res.data) {{ box.innerHTML = "<div class='err'>Failed to load tools (HTTP " + res.status + ").</div>"; return; }}
  const tools = res.data.tools || [];
  const diags = res.data.diagnostics || [];
  box.innerHTML = '';
  // Per-service diagnostics first, so an empty/partial result explains itself.
  if (diags.length) {{
    const d = document.createElement('div'); d.className = 'card'; d.style.margin = '0 0 12px';
    d.innerHTML = '<strong>Underlying services</strong>' + diags.map(x => {{
      const status = x.error ? `<span class='badge need'>${{x.error}}</span>`
                             : `<span class='badge ok'>${{x.count}} tools</span>`;
      return `<div class='row between' style='margin-top:6px'><code>${{x.service}}</code> ${{status}}</div>`;
    }}).join('');
    box.appendChild(d);
  }}
  if (!tools.length) {{
    const m = document.createElement('div'); m.className = 'muted';
    m.innerHTML = diags.length
      ? "No tools exposed yet — sign in to the services above via <a href='/login'>Guided Login</a> (or check the errors)."
      : "No services are baked into this app. Set them at creation time (VIRTUAL_MCP_CONFIG / services.json).";
    box.appendChild(m);
    return;
  }}
  const byAlias = {{}};
  tools.forEach(t => {{ (byAlias[t.alias] = byAlias[t.alias] || []).push(t); }});
  Object.keys(byAlias).sort().forEach(alias => {{
    const div = document.createElement('div');
    div.className = 'svc';
    let html = `<h3>${{alias}} <span class='muted'>(${{byAlias[alias].length}} tools)</span></h3><div class='tools'>`;
    byAlias[alias].forEach(t => {{ html += `<div class='tool-item'><code>${{t.name}}</code> <span class='muted'>${{(t.description||'').slice(0,90)}}</span></div>`; }});
    box.appendChild(div); div.innerHTML = html + '</div>';
  }});
}}
document.getElementById('reload').addEventListener('click', loadTools);
loadTools();
</script>
</body></html>"""


def login_page(cfg: cfg_mod.VirtualMcpConfig) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Virtual MCP - Guided Login</title>{_STYLE}</head><body>
{_header("login")}
<main>
  <div class="card">
    <strong>Sign in to everything this virtual MCP needs</strong>
    <div class="muted" style="margin-top:6px">The virtual MCP combines several services. We'll walk you through signing in to each one that still needs it, one after another, using the platform's own <code>/mcp-service-login</code> page in a popup.</div>
    <div class="row" style="margin-top:12px">
      <button class="primary" id="guided">Start guided login</button>
      <button id="revokeall">Revoke all logins</button>
      <button id="refresh">Refresh status</button>
    </div>
    <div id="list" style="margin-top:14px">Loading…</div>
    <div id="done" class="muted" style="margin-top:10px"></div>
  </div>
</main>
<script>
{_FETCH_JS}
let STATUS = [];
let LOGIN_BASE = '';

async function refresh() {{
  const res = await apiGet('/api/login-status');
  const root = document.getElementById('list');
  if (res.status === 401 || res.status === 0 || !res.ok) {{ root.innerHTML = scopeHintHtml(); return []; }}
  STATUS = (res.data && res.data.services) || [];
  LOGIN_BASE = (res.data && res.data.login_base) || '';
  render();
  return STATUS;
}}

function badge(state) {{
  if (state === 'ACTIVE') return '<span class="badge ok">signed in</span>';
  if (state === 'NO_AUTH') return '<span class="badge none">no login needed</span>';
  return '<span class="badge need">needs login</span>';
}}

function render() {{
  const root = document.getElementById('list');
  if (!STATUS.length) {{ root.innerHTML = "<div class='muted'>No services configured yet. Add some on the Configure page.</div>"; return; }}
  root.innerHTML = '';
  STATUS.forEach(s => {{
    const div = document.createElement('div');
    div.className = 'svc';
    const action = s.state === 'NEEDS_LOGIN'
      ? `<button data-name="${{s.name}}" class="one">Login</button>`
      : (s.state === 'ACTIVE' ? `<button data-name="${{s.name}}" class="rev">Revoke</button>` : '');
    div.innerHTML = `<div class="row between">
      <div><h3>${{s.name}}</h3><span class="muted">${{s.alias}}</span></div>
      <div class="row">${{badge(s.state)}} ${{action}}</div>
    </div>`;
    root.appendChild(div);
  }});
  root.querySelectorAll('.one').forEach(b => b.addEventListener('click', () => loginOne(b.dataset.name)));
  root.querySelectorAll('.rev').forEach(b => b.addEventListener('click', () => revokeOne(b.dataset.name)));
  const allDone = STATUS.every(s => s.state !== 'NEEDS_LOGIN');
  document.getElementById('done').textContent = allDone ? '✓ All set — your virtual MCP is ready to use.' : '';
}}

async function revokeOne(name) {{
  await fetch('/api/revoke', {{ method:'POST', headers:{{'content-type':'application/json'}}, body: JSON.stringify({{ name }}) }});
  await refresh();
}}

function popup(name) {{
  return window.open(LOGIN_BASE + '?name=' + encodeURIComponent(name), 'mcp_login', 'width=520,height=680');
}}

// Open the login popup for one service, then poll until it flips to signed-in.
function loginOne(name) {{
  const win = popup(name);
  return new Promise(resolve => {{
    const timer = setInterval(async () => {{
      const st = await refresh();
      const svc = st.find(s => s.name === name);
      if (!svc || svc.state !== 'NEEDS_LOGIN') {{ clearInterval(timer); try {{ win && win.close(); }} catch(e){{}} resolve(); }}
    }}, 2500);
  }});
}}

// Guided: sign in to each still-needed service, one after another.
document.getElementById('guided').addEventListener('click', async () => {{
  await refresh();
  for (const s of STATUS.filter(x => x.state === 'NEEDS_LOGIN')) {{
    const fresh = STATUS.find(x => x.name === s.name);
    if (fresh && fresh.state === 'NEEDS_LOGIN') await loginOne(s.name);
  }}
  await refresh();
}});
// Guided revoke: sign OUT of every signed-in service, one after another.
document.getElementById('revokeall').addEventListener('click', async () => {{
  const done = document.getElementById('done');
  await refresh();
  const active = STATUS.filter(x => x.state === 'ACTIVE');
  if (!active.length) {{ done.textContent = 'Nothing to revoke — no services are signed in.'; return; }}
  for (const s of active) {{ done.textContent = 'Revoking ' + s.name + '…'; await revokeOne(s.name); }}
  await refresh();
  done.textContent = '✓ Revoked all logins for this virtual MCP.';
}});
document.getElementById('refresh').addEventListener('click', refresh);
refresh();
</script>
</body></html>"""
