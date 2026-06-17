"""API HTTP do Atlas (E0-02 / ADR-0015).

Expõe o ResourceStore como REST API estilo Kubernetes:

  GET    /apis/atlas/v1/                   → lista kinds + counts
  GET    /apis/atlas/v1/<kind>             → lista recursos do kind
  GET    /apis/atlas/v1/<kind>/<name>      → detalhe de um recurso
  PUT    /apis/atlas/v1/<kind>/<name>      → apply (upsert)
  DELETE /apis/atlas/v1/<kind>/<name>      → delete
  GET    /health                           → {"status": "ok"}
  GET    /                                 → dashboard HTML (E0-06 lite)

Auth (E0-05): Bearer token via ATLAS_API_TOKEN env. Se não definido a API
aceita só conexões de loopback (127.0.0.1 / ::1).

Roda em thread daemon paralela ao bot Telegram.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore

_log = logging.getLogger("atlas.api")

_API_PREFIX = "/apis/atlas/v1"
_TOKEN = os.environ.get("ATLAS_API_TOKEN", "")
_PORT = int(os.environ.get("ATLAS_API_PORT", "8080"))

# Store injetado no boot — partilhado com o bot Telegram
_store: ResourceStore | None = None


def _html_dashboard() -> str:
    return r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Atlas</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d1117;--bg2:#161b22;--bg3:#21262d;
  --border:#30363d;--text:#c9d1d9;--muted:#8b949e;
  --blue:#58a6ff;--green:#3fb950;--red:#f85149;--orange:#d29922;
  --purple:#bc8cff;--yellow:#e3b341;
}
body{background:var(--bg);color:var(--text);font-family:'SF Mono',Consolas,monospace;font-size:13px;display:flex;height:100vh;overflow:hidden}
#sidebar{width:200px;min-width:200px;background:var(--bg2);border-right:1px solid var(--border);display:flex;flex-direction:column}
#sidebar h1{padding:16px;font-size:14px;color:var(--blue);border-bottom:1px solid var(--border);letter-spacing:1px}
#kinds{flex:1;overflow-y:auto;padding:8px 0}
.kind-btn{display:flex;justify-content:space-between;align-items:center;width:100%;padding:6px 16px;background:none;border:none;color:var(--muted);cursor:pointer;text-align:left;font-family:inherit;font-size:12px;transition:all .15s}
.kind-btn:hover,.kind-btn.active{background:var(--bg3);color:var(--text)}
.kind-btn .badge{background:var(--bg3);color:var(--blue);border-radius:8px;padding:1px 7px;font-size:11px;min-width:20px;text-align:center}
.kind-btn.active .badge{background:var(--blue);color:var(--bg)}
#main{flex:1;display:flex;flex-direction:column;overflow:hidden}
#toolbar{padding:10px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;background:var(--bg2)}
#toolbar h2{font-size:13px;color:var(--text);flex:1}
#filter{background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:5px 10px;border-radius:6px;font-family:inherit;font-size:12px;width:240px}
#filter::placeholder{color:var(--muted)}
#filter:focus{outline:none;border-color:var(--blue)}
#resource-list{flex:1;overflow-y:auto;padding:12px}
.resource-row{background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:10px 14px;margin-bottom:6px;cursor:pointer;transition:all .15s;display:flex;align-items:flex-start;gap:10px}
.resource-row:hover{border-color:var(--blue);background:var(--bg3)}
.resource-row.selected{border-color:var(--blue);background:#1c2433}
.res-name{color:var(--blue);font-weight:600;font-size:13px;flex-shrink:0}
.res-labels{flex:1;display:flex;flex-wrap:wrap;gap:4px;margin-top:2px}
.label-chip{background:var(--bg3);border:1px solid var(--border);border-radius:4px;padding:1px 6px;font-size:11px;color:var(--muted)}
.label-chip.label-active-true{border-color:var(--green);color:var(--green)}
.label-chip.label-state-done{border-color:var(--purple);color:var(--purple)}
.label-chip.label-state-running{border-color:var(--orange);color:var(--orange)}
.res-status{font-size:11px;color:var(--muted);flex-shrink:0;text-align:right}
#detail{width:360px;min-width:280px;border-left:1px solid var(--border);background:var(--bg2);display:flex;flex-direction:column;overflow:hidden}
#detail-header{padding:12px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px}
#detail-title{flex:1;font-size:13px;color:var(--blue);font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.btn{padding:5px 12px;border-radius:6px;border:1px solid var(--border);background:var(--bg3);color:var(--text);cursor:pointer;font-family:inherit;font-size:12px;transition:all .15s}
.btn:hover{border-color:var(--blue);color:var(--blue)}
.btn.danger:hover{border-color:var(--red);color:var(--red)}
.btn.primary{border-color:var(--blue);background:#1c2d3e;color:var(--blue)}
#detail-body{flex:1;overflow-y:auto;padding:12px}
.section{margin-bottom:16px}
.section-title{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;padding-bottom:4px;border-bottom:1px solid var(--border)}
pre.json{background:var(--bg3);border:1px solid var(--border);border-radius:6px;padding:10px;font-size:11px;color:var(--text);overflow-x:auto;white-space:pre-wrap;word-break:break-all}
.meta-row{display:flex;justify-content:space-between;padding:3px 0;font-size:12px}
.meta-key{color:var(--muted)}
.meta-val{color:var(--text)}
#empty{text-align:center;padding:60px;color:var(--muted)}
#empty .icon{font-size:36px;margin-bottom:12px}
.loading{text-align:center;padding:40px;color:var(--muted)}
#toast{position:fixed;bottom:20px;right:20px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:10px 16px;font-size:12px;opacity:0;transition:opacity .3s;pointer-events:none}
#toast.show{opacity:1}
#toast.err{border-color:var(--red);color:var(--red)}
#toast.ok{border-color:var(--green);color:var(--green)}
::-webkit-scrollbar{width:4px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}
#cli-section{border-top:1px solid var(--border);height:220px;display:flex;flex-direction:column;flex-shrink:0;background:#0a0e13}
#cli-output{flex:1;overflow-y:auto;padding:8px 14px;font-size:12px;line-height:1.6}
.cli-cmd{color:var(--green)}
.cli-out{color:var(--text);white-space:pre-wrap;word-break:break-word}
.cli-err{color:var(--red);white-space:pre-wrap}
.cli-sep{color:var(--border);user-select:none}
#cli-bar{display:flex;align-items:center;padding:6px 12px;border-top:1px solid var(--border);position:relative;flex-shrink:0}
#cli-prompt{color:var(--green);margin-right:8px;flex-shrink:0;font-size:13px}
#cli-input{flex:1;background:none;border:none;color:var(--text);font-family:inherit;font-size:13px;outline:none;caret-color:var(--green)}
#cli-input::placeholder{color:var(--border)}
#cli-suggestions{position:absolute;bottom:100%;left:0;right:0;background:var(--bg2);border:1px solid var(--border);border-bottom:none;border-radius:6px 6px 0 0;max-height:180px;overflow-y:auto;z-index:20}
.sug{padding:5px 14px;cursor:pointer;color:var(--muted);font-size:12px;display:flex;align-items:center;gap:8px}
.sug:hover,.sug.active{background:var(--bg3);color:var(--text)}
.sug-match{color:var(--blue);font-weight:600}
.sug-rest{color:var(--muted)}
#cli-hint{font-size:10px;color:var(--muted);padding:0 14px 4px;flex-shrink:0;text-align:right}
#token-overlay{position:fixed;inset:0;background:rgba(0,0,0,.85);display:flex;align-items:center;justify-content:center;z-index:100}
#token-box{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:32px;width:340px;text-align:center}
#token-box h2{color:var(--blue);margin-bottom:8px;font-size:15px}
#token-box p{color:var(--muted);font-size:12px;margin-bottom:20px}
#token-input{width:100%;background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:8px 12px;border-radius:6px;font-family:inherit;font-size:13px;margin-bottom:12px}
#token-input:focus{outline:none;border-color:var(--blue)}
#token-submit{width:100%;padding:8px;border-radius:6px;border:1px solid var(--blue);background:#1c2d3e;color:var(--blue);cursor:pointer;font-family:inherit;font-size:13px}
#token-submit:hover{background:var(--blue);color:var(--bg)}
</style>
</head>
<body>
<div id="token-overlay" style="display:none">
  <div id="token-box">
    <h2>⚡ Atlas — API Token</h2>
    <p>Configure <code>ATLAS_API_TOKEN</code> no .env e cole aqui:</p>
    <input id="token-input" type="password" placeholder="seu token…" autocomplete="off">
    <button id="token-submit">Entrar</button>
  </div>
</div>
<div id="sidebar">
  <h1>⚡ ATLAS</h1>
  <div id="kinds"></div>
</div>
<div id="main">
  <div id="toolbar">
    <h2 id="kind-title">—</h2>
    <input id="filter" type="text" placeholder="filtrar nome ou label…">
  </div>
  <div id="resource-list"><div class="loading">carregando…</div></div>
  <div id="cli-section">
    <div id="cli-output"></div>
    <div id="cli-hint">Tab → completa · ↑↓ → histórico · Ctrl+L → limpa</div>
    <div id="cli-bar">
      <span id="cli-prompt">$</span>
      <div id="cli-suggestions"></div>
      <input id="cli-input" type="text" placeholder="/ para comandos…" autocomplete="off" spellcheck="false">
    </div>
  </div>
</div>
<div id="detail">
  <div id="detail-header">
    <span id="detail-title">selecione um recurso</span>
    <button class="btn" id="btn-copy" title="copiar /describe">📋</button>
    <button class="btn danger" id="btn-delete" title="deletar">🗑</button>
  </div>
  <div id="detail-body"><div id="empty"><div class="icon">🔍</div>Selecione um recurso<br>para ver o detalhe.</div></div>
</div>
<div id="toast"></div>

<script>
const API = '/apis/atlas/v1';
let TOKEN = localStorage.getItem('atlas_token') || '';
let allKinds = {}, currentKind = null, allResources = [], selectedName = null;

// Token overlay
function showTokenOverlay() {
  document.getElementById('token-overlay').style.display = 'flex';
  document.getElementById('token-input').focus();
}
document.getElementById('token-submit').onclick = () => {
  const val = document.getElementById('token-input').value.trim();
  if (!val) return;
  TOKEN = val;
  localStorage.setItem('atlas_token', val);
  document.getElementById('token-overlay').style.display = 'none';
  loadKinds();
};
document.getElementById('token-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') document.getElementById('token-submit').click();
});

async function apiFetch(path, opts={}) {
  const h = {'Content-Type':'application/json'};
  if (TOKEN) h['Authorization'] = 'Bearer ' + TOKEN;
  const r = await fetch(path, {...opts, headers:{...h,...(opts.headers||{})}});
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function loadKinds() {
  try {
    allKinds = await apiFetch(API + '/');
    renderSidebar();
    const first = Object.keys(allKinds)[0];
    if (first) selectKind(first);
  } catch(e) {
    if (e.message.includes('401') || e.message.toLowerCase().includes('unauth')) {
      showTokenOverlay();
    } else {
      toast('erro ao carregar: ' + e.message, true);
    }
  }
}

function renderSidebar() {
  const el = document.getElementById('kinds');
  el.innerHTML = Object.entries(allKinds)
    .sort(([a],[b]) => a.localeCompare(b))
    .map(([k,v]) =>
      `<button class="kind-btn" data-kind="${k}" onclick="selectKind('${k}')">
        <span>${k}</span><span class="badge">${v}</span>
      </button>`
    ).join('');
}

async function selectKind(kind) {
  currentKind = kind;
  selectedName = null;
  document.getElementById('kind-title').textContent = kind;
  document.querySelectorAll('.kind-btn').forEach(b=>{
    b.classList.toggle('active', b.dataset.kind === kind);
  });
  document.getElementById('resource-list').innerHTML = '<div class="loading">carregando…</div>';
  clearDetail();
  try {
    allResources = await apiFetch(API + '/' + kind);
    renderList(allResources);
  } catch(e) { toast('erro: ' + e.message, true); }
}

function renderList(resources) {
  const filter = document.getElementById('filter').value.toLowerCase();
  const filtered = resources.filter(r => {
    if (!filter) return true;
    if (r.name.toLowerCase().includes(filter)) return true;
    return Object.entries(r.labels||{}).some(([k,v])=>(k+'='+v).toLowerCase().includes(filter));
  });
  const el = document.getElementById('resource-list');
  if (!filtered.length) {
    el.innerHTML = `<div class="loading">${resources.length ? 'sem resultados para "'+filter+'"' : 'vazio'}</div>`;
    return;
  }
  el.innerHTML = filtered.map(r => {
    const labels = Object.entries(r.labels||{}).map(([k,v]) =>
      `<span class="label-chip label-${k}-${v}">${k}=${v}</span>`
    ).join('');
    const st = statusSummary(r.status);
    return `<div class="resource-row${r.name===selectedName?' selected':''}" onclick="selectResource('${r.name}')">
      <div style="flex:1">
        <div class="res-name">${r.name}</div>
        <div class="res-labels">${labels}</div>
      </div>
      ${st ? `<div class="res-status">${st}</div>` : ''}
    </div>`;
  }).join('');
}

function statusSummary(status) {
  if (!status) return '';
  const keys = ['state','active','progress','duration_min','chars','count','last_value','next_fire'];
  for (const k of keys) {
    if (status[k] !== undefined) return `${k}=${status[k]}`;
  }
  const entries = Object.entries(status);
  return entries.length ? entries[0].join('=') : '';
}

async function selectResource(name) {
  selectedName = name;
  renderList(allResources);
  try {
    const r = await apiFetch(API + '/' + currentKind + '/' + name);
    renderDetail(r);
  } catch(e) { toast('erro: ' + e.message, true); }
}

function renderDetail(r) {
  document.getElementById('detail-title').textContent = r.kind + '/' + r.name;
  document.getElementById('btn-copy').onclick = () => {
    navigator.clipboard.writeText('/describe ' + r.kind + ' ' + r.name);
    toast('copiado: /describe ' + r.kind + ' ' + r.name);
  };
  document.getElementById('btn-delete').onclick = () => deleteResource(r.kind, r.name);
  const body = document.getElementById('detail-body');
  const meta = [
    ['apiVersion', r.api_version],
    ['kind', r.kind],
    ['name', r.name],
    ['criado_em', r.criado_em?.slice(0,19)],
    ['atualizado_em', r.atualizado_em?.slice(0,19)],
  ].map(([k,v])=>v?`<div class="meta-row"><span class="meta-key">${k}</span><span class="meta-val">${v}</span></div>`:'').join('');
  const labels = Object.entries(r.labels||{}).map(([k,v])=>
    `<span class="label-chip label-${k}-${v}">${k}=${v}</span>`
  ).join(' ');
  body.innerHTML = `
    <div class="section">
      <div class="section-title">metadata</div>
      ${meta}
      ${labels ? `<div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:4px">${labels}</div>` : ''}
    </div>
    ${Object.keys(r.spec||{}).length ? `
    <div class="section">
      <div class="section-title">spec</div>
      <pre class="json">${jsonStr(r.spec)}</pre>
    </div>` : ''}
    ${Object.keys(r.status||{}).length ? `
    <div class="section">
      <div class="section-title">status</div>
      <pre class="json">${jsonStr(r.status)}</pre>
    </div>` : ''}
  `;
}

function jsonStr(obj) {
  return JSON.stringify(obj, null, 2)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

async function deleteResource(kind, name) {
  if (!confirm(`Deletar ${kind}/${name}?`)) return;
  try {
    const h = {};
    if (TOKEN) h['Authorization'] = 'Bearer ' + TOKEN;
    const r = await fetch(API + '/' + kind + '/' + name, {method:'DELETE', headers:h});
    if (!r.ok) throw new Error(await r.text());
    toast('deletado: ' + kind + '/' + name, false);
    clearDetail();
    await selectKind(currentKind);
    await loadKinds();
  } catch(e) { toast('erro: ' + e.message, true); }
}

function clearDetail() {
  document.getElementById('detail-title').textContent = 'selecione um recurso';
  document.getElementById('detail-body').innerHTML =
    '<div id="empty"><div class="icon">🔍</div>Selecione um recurso<br>para ver o detalhe.</div>';
  document.getElementById('btn-copy').onclick = null;
  document.getElementById('btn-delete').onclick = null;
}

let toastTimer;
function toast(msg, err=false) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'show ' + (err ? 'err' : 'ok');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.className = '', 3000);
}

document.getElementById('filter').addEventListener('input', () => renderList(allResources));

// ── CLI ──────────────────────────────────────────────────────────────────────
const cliInput = document.getElementById('cli-input');
const cliOutput = document.getElementById('cli-output');
const cliSugs = document.getElementById('cli-suggestions');
let cliHistory = JSON.parse(localStorage.getItem('atlas_cli_history') || '[]');
let histIdx = -1;
let sugList = [], sugIdx = -1;
let sugDebounce;

function cliAppend(text, cls) {
  const el = document.createElement('div');
  el.className = cls;
  el.textContent = text;
  cliOutput.appendChild(el);
  cliOutput.scrollTop = cliOutput.scrollHeight;
}

async function cliRun(text) {
  text = text.trim();
  if (!text) return;
  cliAppend('$ ' + text, 'cli-cmd');
  cliHistory = [text, ...cliHistory.filter(h => h !== text)].slice(0, 80);
  localStorage.setItem('atlas_cli_history', JSON.stringify(cliHistory));
  histIdx = -1;
  try {
    const h = {'Content-Type':'application/json'};
    if (TOKEN) h['Authorization'] = 'Bearer ' + TOKEN;
    const r = await fetch(API + '/_cmd', {method:'POST', headers:h, body:JSON.stringify({text})});
    const j = await r.json();
    if (j.error) { cliAppend(j.error, 'cli-err'); return; }
    cliAppend(j.output || '(sem saída)', 'cli-out');
  } catch(e) { cliAppend('erro: ' + e.message, 'cli-err'); }
  cliAppend('─'.repeat(36), 'cli-sep');
}

async function fetchSuggestions(q) {
  if (!TOKEN && !q) return [];
  const h = {};
  if (TOKEN) h['Authorization'] = 'Bearer ' + TOKEN;
  const r = await fetch(API + '/_complete?q=' + encodeURIComponent(q), {headers:h}).catch(()=>null);
  if (!r || !r.ok) return [];
  return r.json();
}

function renderSugs(list, q) {
  sugList = list; sugIdx = -1;
  cliSugs.innerHTML = '';
  if (!list.length) return;
  list.slice(0, 12).forEach((s, i) => {
    const el = document.createElement('div');
    el.className = 'sug';
    el.dataset.idx = i;
    const matchLen = q.length;
    el.innerHTML = `<span class="sug-match">${esc(s.slice(0, matchLen))}</span><span class="sug-rest">${esc(s.slice(matchLen))}</span>`;
    el.onmousedown = e => { e.preventDefault(); cliInput.value = s; hideSugs(); cliInput.focus(); };
    cliSugs.appendChild(el);
  });
}

function hideSugs() { cliSugs.innerHTML = ''; sugList = []; sugIdx = -1; }

function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function highlightSug(idx) {
  cliSugs.querySelectorAll('.sug').forEach((el, i) => el.classList.toggle('active', i === idx));
}

cliInput.addEventListener('input', () => {
  clearTimeout(sugDebounce);
  const q = cliInput.value;
  sugDebounce = setTimeout(async () => {
    const list = await fetchSuggestions(q);
    renderSugs(list, q);
  }, 80);
});

cliInput.addEventListener('keydown', async e => {
  if (e.key === 'Tab') {
    e.preventDefault();
    if (sugList.length === 1) { cliInput.value = sugList[0] + ' '; hideSugs(); }
    else if (sugList.length > 1) {
      sugIdx = (sugIdx + 1) % sugList.length;
      highlightSug(sugIdx);
      cliInput.value = sugList[sugIdx];
    } else {
      const list = await fetchSuggestions(cliInput.value);
      renderSugs(list, cliInput.value);
      if (list.length === 1) { cliInput.value = list[0] + ' '; hideSugs(); }
    }
    return;
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    if (sugList.length) { sugIdx = Math.min(sugIdx + 1, sugList.length - 1); highlightSug(sugIdx); cliInput.value = sugList[sugIdx]; return; }
    if (histIdx > 0) { histIdx--; cliInput.value = cliHistory[histIdx] || ''; }
    else if (histIdx === 0) { histIdx = -1; cliInput.value = ''; }
    return;
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault();
    if (sugList.length) { sugIdx = Math.max(sugIdx - 1, 0); highlightSug(sugIdx); cliInput.value = sugList[sugIdx]; return; }
    if (histIdx < cliHistory.length - 1) { histIdx++; cliInput.value = cliHistory[histIdx]; }
    return;
  }
  if (e.key === 'Escape') { hideSugs(); return; }
  if (e.key === 'Enter') {
    e.preventDefault();
    hideSugs();
    const cmd = cliInput.value.trim();
    cliInput.value = '';
    if (cmd) await cliRun(cmd);
    return;
  }
  if (e.key === 'l' && e.ctrlKey) {
    e.preventDefault();
    cliOutput.innerHTML = '';
    return;
  }
});

// Ctrl+K / backtick foca o CLI
document.addEventListener('keydown', e => {
  if ((e.key === 'k' && e.ctrlKey) || (e.key === '`' && !e.ctrlKey && document.activeElement !== cliInput)) {
    e.preventDefault();
    cliInput.focus();
  }
});

// Clique fora esconde sugestões
document.addEventListener('click', e => {
  if (!e.target.closest('#cli-bar')) hideSugs();
});

// Mensagem de boas-vindas no CLI
cliAppend('Atlas CLI — Tab para completar, ↑↓ para histórico, Ctrl+K para focar', 'cli-sep');
cliAppend('Comandos: /list /get /describe /apply /delete /docs /snip /help', 'cli-sep');
cliAppend('─'.repeat(36), 'cli-sep');

if (TOKEN) { loadKinds(); } else { showTokenOverlay(); }
setInterval(async () => {
  if (currentKind) {
    const fresh = await apiFetch(API + '/').catch(()=>null);
    if (fresh) { allKinds = fresh; renderSidebar(); }
  }
}, 15000);
</script>
</body>
</html>"""


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: ANN401
        _log.debug(fmt, *args)

    def _auth(self) -> bool:
        if not _TOKEN:
            ip = self.client_address[0]
            return ip in ("127.0.0.1", "::1", "::ffff:127.0.0.1")
        auth = self.headers.get("Authorization", "")
        return auth == f"Bearer {_TOKEN}"

    def _json(self, code: int, body: Any) -> None:
        data = json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _html(self, body: str) -> None:
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization,Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path.split("?")[0].rstrip("/")

        if path == "" or path == "/":
            self._html(_html_dashboard())
            return
        if path == "/health":
            self._json(200, {"status": "ok"})
            return
        if not self._auth():
            self._json(401, {"error": "unauthorized"})
            return
        if _store is None:
            self._json(503, {"error": "store not ready"})
            return

        if path == _API_PREFIX:
            counts = {k: len(_store.list(k)) for k in _store.kinds()}
            self._json(200, counts)
            return

        # /_complete?q=<text> → sugestões de autocomplete
        if path == _API_PREFIX + "/_complete":
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query).get("q", [""])[0]
            self._json(200, _autocomplete(q, _store))
            return

        rest = path[len(_API_PREFIX):].strip("/")
        parts = rest.split("/") if rest else []

        if len(parts) == 1:
            kind = parts[0]
            resources = _store.list(kind)
            self._json(200, [_resource_to_dict(r) for r in resources])
            return

        if len(parts) == 2:
            kind, name = parts
            r = _store.get(kind, name)
            if r is None:
                self._json(404, {"error": f"{kind}/{name} not found"})
                return
            self._json(200, _resource_to_dict(r))
            return

        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not self._auth():
            self._json(401, {"error": "unauthorized"})
            return
        if _store is None:
            self._json(503, {"error": "store not ready"})
            return

        path = self.path.split("?")[0].rstrip("/")
        if path != _API_PREFIX + "/_cmd":
            self._json(404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        text = body.get("text", "").strip()
        if not text:
            self._json(400, {"error": "text required"})
            return

        output = _cmd_router(text, _store)
        self._json(200, {"output": output})

    def do_PUT(self) -> None:
        if not self._auth():
            self._json(401, {"error": "unauthorized"})
            return
        if _store is None:
            self._json(503, {"error": "store not ready"})
            return

        path = self.path.split("?")[0].rstrip("/")
        rest = path[len(_API_PREFIX):].strip("/")
        parts = rest.split("/") if rest else []
        if len(parts) != 2:
            self._json(400, {"error": "PUT requires /apis/atlas/v1/<kind>/<name>"})
            return

        kind, name = parts
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        existing = _store.get(kind, name)
        labels = {**((existing.labels or {}) if existing else {}), **body.get("labels", {})}
        spec = {**((existing.spec or {}) if existing else {}), **body.get("spec", {})}
        status = {**((existing.status or {}) if existing else {}), **body.get("status", {})}

        res = Resource(kind=kind, name=name, labels=labels, spec=spec, status=status)
        _store.apply(res, datetime.now())
        self._json(200, _resource_to_dict(_store.get(kind, name)))

    def do_DELETE(self) -> None:
        if not self._auth():
            self._json(401, {"error": "unauthorized"})
            return
        if _store is None:
            self._json(503, {"error": "store not ready"})
            return

        path = self.path.split("?")[0].rstrip("/")
        rest = path[len(_API_PREFIX):].strip("/")
        parts = rest.split("/") if rest else []
        if len(parts) != 2:
            self._json(400, {"error": "DELETE requires /apis/atlas/v1/<kind>/<name>"})
            return

        kind, name = parts
        ok = _store.delete(kind, name)
        if ok:
            self._json(200, {"deleted": f"{kind}/{name}"})
        else:
            self._json(404, {"error": f"{kind}/{name} not found"})


_CMD_VERBS = [
    "/list", "/get", "/describe", "/apply", "/delete", "/resources",
    "/docs", "/snip", "/help",
    "/ls", "/r", "/cat", "/d", "/a", "/rm",
]
_VERBS_KIND = {"/list", "/get", "/describe", "/apply", "/delete", "/ls", "/r", "/cat", "/d", "/a", "/rm"}
_VERBS_NAME = {"/get", "/describe", "/delete", "/r", "/cat", "/d", "/rm"}


def _cmd_router(text: str, store: ResourceStore) -> str:
    from atlas.aliases import expandir, responder_snip
    from atlas.comandos import texto_ajuda
    from atlas.docs_cmd import responder_docs
    from atlas.verbos import responder_verbos

    text = expandir(text)
    agora = datetime.now()

    if text in ("/help", "/ajuda"):
        return texto_ajuda()
    snip = responder_snip(text)
    if snip is not None:
        return snip
    docs = responder_docs(text, agora, store=store)
    if docs is not None:
        return docs
    verbos = responder_verbos(text, store, agora)
    if verbos is not None:
        return verbos
    return f"❓ comando não reconhecido: '{text}'\nUse /help para ver os comandos."


def _autocomplete(q: str, store: ResourceStore) -> list[str]:
    parts = q.split()
    verb = parts[0] if parts else ""
    kind = parts[1] if len(parts) > 1 else ""
    name_frag = parts[2] if len(parts) > 2 else ""

    # completando verbo
    if not verb or (len(parts) == 1 and not q.endswith(" ")):
        frag = verb.lower()
        return [v for v in _CMD_VERBS if v.startswith(frag or "/")]

    # completando kind
    if verb in _VERBS_KIND and (len(parts) == 1 or (len(parts) == 2 and not q.endswith(" "))):
        frag = kind.lower()
        kinds = store.kinds()
        matches = [k for k in kinds if k.lower().startswith(frag)]
        return [f"{verb} {k}" for k in matches]

    # completando name
    if verb in _VERBS_NAME and kind and (len(parts) == 2 or (len(parts) == 3 and not q.endswith(" "))):
        frag = name_frag.lower()
        try:
            resources = store.list(kind)
        except Exception:  # noqa: BLE001
            return []
        matches = [r.name for r in resources if r.name.lower().startswith(frag)]
        return [f"{verb} {kind} {n}" for n in matches]

    return []


def _resource_to_dict(r: Resource) -> dict:
    return {
        "api_version": r.api_version,
        "kind": r.kind,
        "name": r.name,
        "labels": r.labels,
        "spec": r.spec,
        "status": r.status,
        "criado_em": r.criado_em,
        "atualizado_em": r.atualizado_em,
    }


def iniciar(store: ResourceStore, port: int = _PORT) -> None:
    """Inicia o servidor HTTP em thread daemon. Chamado pelo app no boot."""
    global _store
    _store = store

    server = HTTPServer(("0.0.0.0", port), _Handler)

    def _run() -> None:
        _log.info("API HTTP no ar: http://0.0.0.0:%d  (token=%s)", port, "sim" if _TOKEN else "loopback-only")
        server.serve_forever()

    t = threading.Thread(target=_run, daemon=True, name="atlas-api")
    t.start()
