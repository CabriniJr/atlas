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
  --sidebar-w:240px;--bottom-h:200px;--titlebar-h:35px;
}
/* ── Layout base ── */
html,body{height:100%;overflow:hidden}
body{background:var(--bg);color:var(--text);font-family:'SF Mono',Consolas,monospace;font-size:13px;display:flex;flex-direction:column}
/* ── Titlebar ── */
#titlebar{height:var(--titlebar-h);background:var(--bg2);border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 14px;gap:12px;flex-shrink:0;user-select:none}
#titlebar .logo{color:var(--blue);font-weight:700;font-size:13px;letter-spacing:1px}
#titlebar .sep{color:var(--border)}
#titlebar #filter{background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:4px 10px;border-radius:5px;font-family:inherit;font-size:12px;width:220px}
#titlebar #filter::placeholder{color:var(--muted)}
#titlebar #filter:focus{outline:none;border-color:var(--blue)}
#titlebar .spacer{flex:1}
/* ── Workspace (sidebar + editor) ── */
#workspace{flex:1;display:flex;overflow:hidden;min-height:0}
/* ── Sidebar ── */
#sidebar{width:var(--sidebar-w);min-width:120px;max-width:500px;background:var(--bg2);border-right:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0;overflow:hidden}
#sidebar-head{padding:8px 12px;font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.8px;border-bottom:1px solid var(--border);flex-shrink:0;display:flex;align-items:center;gap:6px}
#tree{flex:1;overflow-y:auto;padding:4px 0}
/* ── Sidebar resize handle ── */
#sb-resize{width:4px;cursor:ew-resize;flex-shrink:0;background:transparent;transition:background .12s;position:relative;z-index:5}
#sb-resize:hover,#sb-resize.drag{background:var(--blue)}
/* ── Editor area ── */
#editor{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}
/* ── Tab bar ── */
#tabbar{height:35px;background:var(--bg2);border-bottom:1px solid var(--border);display:flex;align-items:stretch;flex-shrink:0;overflow-x:auto;overflow-y:hidden}
#tabbar::-webkit-scrollbar{height:2px}
#tabbar::-webkit-scrollbar-thumb{background:var(--border)}
.tab{display:flex;align-items:center;gap:6px;padding:0 14px 0 12px;border-right:1px solid var(--border);cursor:pointer;font-size:12px;color:var(--muted);white-space:nowrap;flex-shrink:0;transition:background .1s;position:relative;min-width:100px;max-width:200px}
.tab:hover{background:var(--bg3);color:var(--text)}
.tab.active{background:var(--bg);color:var(--text);border-bottom:1px solid var(--blue)}
.tab .tab-icon{font-size:11px;flex-shrink:0}
.tab .tab-name{flex:1;overflow:hidden;text-overflow:ellipsis}
.tab .tab-close{opacity:0;font-size:12px;line-height:1;padding:2px 4px;border-radius:3px;margin-left:2px;flex-shrink:0}
.tab:hover .tab-close,.tab.active .tab-close{opacity:.5}
.tab .tab-close:hover{opacity:1;background:var(--bg3);color:var(--red)}
.tab-welcome{color:var(--muted);font-style:italic}
/* ── Editor content ── */
#editor-content{flex:1;overflow:auto;padding:20px 24px;min-height:0}
/* ── Bottom resize handle ── */
#bot-resize{height:4px;cursor:ns-resize;flex-shrink:0;background:transparent;transition:background .12s}
#bot-resize:hover,#bot-resize.drag{background:var(--blue)}
/* ── Bottom panel ── */
#bottom{height:var(--bottom-h);min-height:60px;max-height:70vh;background:#0a0e13;border-top:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0}
#bot-tabbar{height:30px;background:var(--bg2);border-bottom:1px solid var(--border);display:flex;align-items:stretch;flex-shrink:0}
.bot-tab{display:flex;align-items:center;padding:0 14px;cursor:pointer;font-size:11px;color:var(--muted);border-right:1px solid var(--border)}
.bot-tab:hover{color:var(--text)}
.bot-tab.active{color:var(--text);border-bottom:2px solid var(--blue)}
/* ── CLI ── */
#cli-wrap{flex:1;display:flex;flex-direction:column;overflow:hidden;min-height:0}
#cli-output{flex:1;overflow-y:auto;padding:6px 14px;font-size:12px;line-height:1.6}
.cli-cmd{color:var(--green)}
.cli-out{color:var(--text);white-space:pre-wrap;word-break:break-word}
.cli-err{color:var(--red);white-space:pre-wrap}
.cli-sep{color:var(--border);user-select:none;font-size:11px}
#cli-bar{display:flex;align-items:center;padding:5px 12px;border-top:1px solid var(--border);flex-shrink:0;position:relative}
#cli-prompt{color:var(--green);margin-right:8px;flex-shrink:0}
#cli-input{flex:1;background:none;border:none;color:var(--text);font-family:inherit;font-size:13px;outline:none;caret-color:var(--green)}
#cli-input::placeholder{color:var(--border)}
#cli-suggestions{position:absolute;bottom:100%;left:0;right:0;background:var(--bg2);border:1px solid var(--border);border-bottom:none;border-radius:6px 6px 0 0;max-height:160px;overflow-y:auto;z-index:30}
.sug{padding:4px 14px;cursor:pointer;color:var(--muted);font-size:12px}
.sug:hover,.sug.active{background:var(--bg3);color:var(--text)}
.sug-match{color:var(--blue);font-weight:600}
/* ── Tree items ── */
.kind-row{display:flex;align-items:center;gap:5px;padding:4px 8px 4px 10px;cursor:pointer;font-size:12px;color:var(--muted);user-select:none;transition:background .1s}
.kind-row:hover{background:var(--bg3);color:var(--text)}
.kind-row .arrow{width:14px;font-size:10px;flex-shrink:0;transition:transform .12s}
.kind-row.open .arrow{transform:rotate(90deg)}
.kind-row .k-name{flex:1}
.kind-row .k-count{font-size:10px;background:var(--bg3);border-radius:8px;padding:0 5px;color:var(--muted)}
.res-row{display:flex;align-items:center;gap:5px;padding:3px 8px 3px 26px;cursor:pointer;font-size:12px;color:var(--muted);transition:background .1s;border-left:2px solid transparent}
.res-row:hover{background:rgba(88,166,255,.06);color:var(--text)}
.res-row.active{background:rgba(88,166,255,.1);color:var(--blue);border-left-color:var(--blue)}
.res-row .r-icon{font-size:10px;flex-shrink:0}
.res-row .r-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* ── Editor content styles ── */
.welcome{text-align:center;padding:60px 20px;color:var(--muted)}
.welcome .w-logo{font-size:40px;margin-bottom:16px}
.welcome h2{color:var(--text);font-size:16px;margin-bottom:8px}
.welcome p{font-size:12px;line-height:1.8}
.welcome kbd{background:var(--bg3);border:1px solid var(--border);border-radius:3px;padding:1px 6px;font-size:11px}
.r-card{max-width:860px}
.r-card .r-header{display:flex;align-items:center;gap:10px;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid var(--border)}
.r-card .r-header .r-kind{font-size:11px;color:var(--muted);background:var(--bg3);border:1px solid var(--border);border-radius:4px;padding:2px 8px}
.r-card .r-header .r-name-big{font-size:18px;color:var(--text);font-weight:600}
.r-card .r-header .r-actions{margin-left:auto;display:flex;gap:6px}
.btn{padding:4px 10px;border-radius:5px;border:1px solid var(--border);background:var(--bg3);color:var(--text);cursor:pointer;font-family:inherit;font-size:11px;transition:all .15s}
.btn:hover{border-color:var(--blue);color:var(--blue)}
.btn.danger:hover{border-color:var(--red);color:var(--red)}
.r-meta{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px;margin-bottom:16px}
.meta-item{background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:8px 12px}
.meta-item .mi-key{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;margin-bottom:3px}
.meta-item .mi-val{font-size:12px;color:var(--text)}
.labels-row{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:16px}
.label-chip{background:var(--bg3);border:1px solid var(--border);border-radius:3px;padding:2px 7px;font-size:11px;color:var(--muted)}
.label-chip.lc-active-true{border-color:var(--green);color:var(--green)}
.label-chip.lc-state-done{border-color:var(--purple);color:var(--purple)}
.label-chip.lc-state-active{border-color:var(--blue);color:var(--blue)}
.label-chip.lc-state-running{border-color:var(--orange);color:var(--orange)}
.label-chip.lc-topic-adr{border-color:var(--yellow);color:var(--yellow)}
.label-chip.lc-topic-kindref{border-color:var(--purple);color:var(--purple)}
.r-section{margin-bottom:16px}
.r-section .sec-title{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px;padding-bottom:4px;border-bottom:1px solid var(--border)}
pre.json{background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:12px;font-size:11px;color:var(--text);overflow-x:auto;white-space:pre-wrap;word-break:break-all;line-height:1.6}
/* ── Markdown ── */
.md h1,.md h2,.md h3{color:var(--blue);margin:.6em 0 .3em;font-weight:600}
.md h1{font-size:16px;border-bottom:1px solid var(--border);padding-bottom:5px}
.md h2{font-size:14px}.md h3{font-size:13px;color:var(--text)}
.md p{margin:.4em 0;line-height:1.7}
.md code{background:var(--bg3);border:1px solid var(--border);border-radius:3px;padding:1px 5px;font-size:11px;color:var(--orange)}
.md pre{background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:10px 12px;overflow-x:auto;margin:.5em 0}
.md pre code{background:none;border:none;padding:0;color:var(--text);font-size:11px}
.md ul,.md ol{padding-left:20px;margin:.3em 0}.md li{margin:.15em 0;line-height:1.6}
.md blockquote{border-left:3px solid var(--blue);padding-left:10px;color:var(--muted);margin:.4em 0}
.md hr{border:none;border-top:1px solid var(--border);margin:.6em 0}
.md strong{color:var(--yellow);font-weight:600}.md em{color:var(--muted);font-style:italic}
.md a{color:var(--blue);text-decoration:none}.md a:hover{text-decoration:underline}
.md table{border-collapse:collapse;width:100%;margin:.5em 0;font-size:12px}
.md th{background:var(--bg3);color:var(--blue);padding:5px 10px;border:1px solid var(--border);text-align:left}
.md td{padding:4px 10px;border:1px solid var(--border)}
.md tr:nth-child(even) td{background:rgba(255,255,255,.02)}
/* ── Misc ── */
#toast{position:fixed;bottom:16px;right:16px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:8px 14px;font-size:12px;opacity:0;transition:opacity .3s;pointer-events:none;z-index:200}
#toast.show{opacity:1}
#toast.err{border-color:var(--red);color:var(--red)}
#toast.ok{border-color:var(--green);color:var(--green)}
::-webkit-scrollbar{width:5px;height:5px}::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}
#token-overlay{position:fixed;inset:0;background:rgba(0,0,0,.85);display:flex;align-items:center;justify-content:center;z-index:100}
#token-box{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:32px;width:340px;text-align:center}
#token-box h2{color:var(--blue);margin-bottom:8px;font-size:15px}
#token-box p{color:var(--muted);font-size:12px;margin-bottom:20px}
#token-input{width:100%;background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:8px 12px;border-radius:6px;font-family:inherit;font-size:13px;margin-bottom:12px}
#token-input:focus{outline:none;border-color:var(--blue)}
#token-submit{width:100%;padding:8px;border-radius:6px;border:1px solid var(--blue);background:#1c2d3e;color:var(--blue);cursor:pointer;font-family:inherit;font-size:13px}
#token-submit:hover{background:var(--blue);color:var(--bg)}
#toast{position:fixed;bottom:20px;right:20px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:10px 16px;font-size:12px;opacity:0;transition:opacity .3s;pointer-events:none}
#toast.show{opacity:1}
#toast.err{border-color:var(--red);color:var(--red)}
#toast.ok{border-color:var(--green);color:var(--green)}
::-webkit-scrollbar{width:4px}
::-webkit-scrollbar-track{background:transparent}
/* ── markdown render ── */
.md h1,.md h2,.md h3{color:var(--blue);margin:.6em 0 .3em;font-weight:600}
.md h1{font-size:15px;border-bottom:1px solid var(--border);padding-bottom:4px}
.md h2{font-size:13px}
.md h3{font-size:12px;color:var(--text)}
.md p{margin:.3em 0;line-height:1.6}
.md code{background:var(--bg3);border:1px solid var(--border);border-radius:3px;padding:1px 5px;font-size:11px;color:var(--orange)}
.md pre{background:var(--bg3);border:1px solid var(--border);border-radius:6px;padding:10px 12px;overflow-x:auto;margin:.4em 0}
.md pre code{background:none;border:none;padding:0;color:var(--text);font-size:11px}
.md ul,.md ol{padding-left:18px;margin:.3em 0}
.md li{margin:.15em 0;line-height:1.5}
.md blockquote{border-left:3px solid var(--blue);padding-left:10px;color:var(--muted);margin:.3em 0}
.md hr{border:none;border-top:1px solid var(--border);margin:.5em 0}
.md strong{color:var(--yellow);font-weight:600}
.md em{color:var(--muted);font-style:italic}
.md a{color:var(--blue);text-decoration:none}
.md a:hover{text-decoration:underline}
.md table{border-collapse:collapse;width:100%;margin:.4em 0;font-size:11px}
.md th{background:var(--bg3);color:var(--blue);padding:4px 8px;border:1px solid var(--border);text-align:left}
.md td{padding:3px 8px;border:1px solid var(--border)}
.md tr:nth-child(even) td{background:rgba(255,255,255,.02)}
#cli-section{border-top:1px solid var(--border);height:220px;min-height:80px;max-height:80vh;display:flex;flex-direction:column;flex-shrink:0;background:#0a0e13;position:relative}
#cli-resize{height:4px;cursor:ns-resize;background:transparent;flex-shrink:0;transition:background .15s}
#cli-resize:hover,#cli-resize.dragging{background:var(--blue)}
#cli-resize::before{content:'';display:block;width:32px;height:2px;background:var(--border);border-radius:1px;margin:1px auto 0}
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

<!-- Token overlay -->
<div id="token-overlay" style="display:none">
  <div id="token-box">
    <h2>⚡ Atlas</h2>
    <p>Configure <code>ATLAS_API_TOKEN</code> no .env e cole aqui:</p>
    <input id="token-input" type="password" placeholder="token…" autocomplete="off">
    <button id="token-submit">Entrar</button>
  </div>
</div>

<!-- Titlebar -->
<div id="titlebar">
  <span class="logo">⚡ ATLAS</span>
  <span class="sep">/</span>
  <input id="filter" type="text" placeholder="filtrar…" autocomplete="off">
  <span class="spacer"></span>
  <span style="font-size:11px;color:var(--muted)" id="status-bar">—</span>
</div>

<!-- Main workspace: sidebar + editor -->
<div id="workspace">

  <!-- Sidebar: árvore -->
  <div id="sidebar">
    <div id="sidebar-head">EXPLORER</div>
    <div id="tree"></div>
  </div>
  <div id="sb-resize"></div>

  <!-- Editor: tabbar + content -->
  <div id="editor">
    <div id="tabbar">
      <div class="tab tab-welcome active" data-id="welcome">
        <span class="tab-icon">⚡</span>
        <span class="tab-name">Bem-vindo</span>
      </div>
    </div>
    <div id="editor-content">
      <div class="welcome">
        <div class="w-logo">⚡</div>
        <h2>Atlas Resource Explorer</h2>
        <p>Clique em um recurso na árvore para abrir.<br>
        <kbd>Ctrl+K</kbd> foca o terminal · <kbd>Tab</kbd> completa comandos<br>
        <kbd>↑↓</kbd> histórico · <kbd>Ctrl+L</kbd> limpa terminal</p>
      </div>
    </div>
  </div>

</div><!-- /workspace -->

<!-- Bottom resize handle -->
<div id="bot-resize"></div>

<!-- Bottom panel: terminal -->
<div id="bottom">
  <div id="bot-tabbar">
    <div class="bot-tab active">TERMINAL</div>
  </div>
  <div id="cli-wrap">
    <div id="cli-output"></div>
    <div id="cli-bar">
      <span id="cli-prompt">$</span>
      <div id="cli-suggestions"></div>
      <input id="cli-input" type="text" placeholder="/ para comandos…" autocomplete="off" spellcheck="false">
    </div>
  </div>
</div>

<div id="toast"></div>

<script>
const API = '/apis/atlas/v1';
let TOKEN = localStorage.getItem('atlas_token') || '';
let allKinds = {};
// openTabs: [{id, kind, name, label, icon}]
let openTabs = [{id:'welcome', kind:null, name:null, label:'Bem-vindo', icon:'⚡'}];
let activeTab = 'welcome';
let treeOpen = {}; // kind → bool
let treeData = {}; // kind → [resource]

// ── Token ──
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
  init();
};
document.getElementById('token-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') document.getElementById('token-submit').click();
});

// ── API ──
async function apiFetch(path, opts={}) {
  const h = {'Content-Type':'application/json'};
  if (TOKEN) h['Authorization'] = 'Bearer ' + TOKEN;
  const r = await fetch(path, {...opts, headers:{...h,...(opts.headers||{})}});
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

// ── Init ──
async function init() {
  try {
    allKinds = await apiFetch(API + '/');
    updateStatus();
    renderTree();
  } catch(e) {
    if (e.message.includes('401') || e.message.toLowerCase().includes('unauth')) {
      showTokenOverlay();
    } else {
      toast('erro: ' + e.message, true);
    }
  }
}

function updateStatus() {
  const total = Object.values(allKinds).reduce((a,b)=>a+b,0);
  document.getElementById('status-bar').textContent =
    Object.keys(allKinds).length + ' kinds · ' + total + ' resources';
}

// ── Tree ──
function kindIcon(k) {
  const icons = {Doc:'📄',Tracker:'📊',Goal:'🎯',Alarm:'⏰',Timer:'⏱',Routine:'🔄',
    Idea:'💡',Task:'✅',RoutineRequest:'📋'};
  return icons[k] || '🗂';
}

function renderTree() {
  const el = document.getElementById('tree');
  const filter = document.getElementById('filter').value.toLowerCase();
  let html = '';
  Object.keys(allKinds).sort().forEach(kind => {
    const open = !!treeOpen[kind];
    const cnt = allKinds[kind];
    html += `<div class="kind-row${open?' open':''}" onclick="toggleKind('${kind}')">
      <span class="arrow">▶</span>
      <span>${kindIcon(kind)}</span>
      <span class="k-name">${kind}</span>
      <span class="k-count">${cnt}</span>
    </div>`;
    if (open && treeData[kind]) {
      treeData[kind]
        .filter(r => !filter || r.name.toLowerCase().includes(filter))
        .forEach(r => {
          const tabId = kind + '/' + r.name;
          const isActive = activeTab === tabId;
          html += `<div class="res-row${isActive?' active':''}" onclick="openResource('${kind}','${r.name}')">
            <span class="r-icon">${kindIcon(kind)}</span>
            <span class="r-name">${esc(r.name)}</span>
          </div>`;
        });
    }
  });
  el.innerHTML = html;
}

async function toggleKind(kind) {
  treeOpen[kind] = !treeOpen[kind];
  if (treeOpen[kind] && !treeData[kind]) {
    treeData[kind] = await apiFetch(API + '/' + kind).catch(()=>[]);
  }
  renderTree();
}

// ── Tabs ──
function renderTabs() {
  const bar = document.getElementById('tabbar');
  bar.innerHTML = openTabs.map(t => {
    const cls = 'tab' + (t.id === activeTab ? ' active' : '');
    const closeBtn = t.id === 'welcome' ? '' :
      `<span class="tab-close" onclick="closeTab(event,'${t.id}')">✕</span>`;
    return `<div class="${cls}" data-id="${t.id}" onclick="activateTab('${t.id}')">
      <span class="tab-icon">${t.icon}</span>
      <span class="tab-name" title="${t.label}">${esc(t.label)}</span>
      ${closeBtn}
    </div>`;
  }).join('');
}

function activateTab(id) {
  activeTab = id;
  renderTabs();
  const t = openTabs.find(x=>x.id===id);
  if (!t) return;
  if (id === 'welcome') {
    showWelcome();
  } else {
    loadAndRender(t.kind, t.name);
  }
  renderTree();
}

function closeTab(e, id) {
  e.stopPropagation();
  openTabs = openTabs.filter(t=>t.id!==id);
  if (!openTabs.length) openTabs = [{id:'welcome',kind:null,name:null,label:'Bem-vindo',icon:'⚡'}];
  if (activeTab === id) activeTab = openTabs[openTabs.length-1].id;
  renderTabs();
  const t = openTabs.find(x=>x.id===activeTab);
  if (!t) return;
  if (t.id === 'welcome') showWelcome();
  else loadAndRender(t.kind, t.name);
  renderTree();
}

function showWelcome() {
  document.getElementById('editor-content').innerHTML = `
    <div class="welcome">
      <div class="w-logo">⚡</div>
      <h2>Atlas Resource Explorer</h2>
      <p>Clique em um recurso na árvore para abrir.<br>
      <kbd>Ctrl+K</kbd> foca o terminal · <kbd>Tab</kbd> completa comandos<br>
      <kbd>↑↓</kbd> histórico · <kbd>Ctrl+L</kbd> limpa terminal</p>
    </div>`;
}

// ── Open resource ──
async function openResource(kind, name) {
  const id = kind + '/' + name;
  const existing = openTabs.find(t=>t.id===id);
  if (!existing) {
    openTabs.push({id, kind, name, label: name, icon: kindIcon(kind)});
  }
  activeTab = id;
  renderTabs();
  renderTree();
  await loadAndRender(kind, name);
}

async function loadAndRender(kind, name) {
  const ec = document.getElementById('editor-content');
  ec.innerHTML = '<div style="padding:20px;color:var(--muted)">carregando…</div>';
  try {
    const r = await apiFetch(API + '/' + kind + '/' + name);
    renderResource(r);
  } catch(e) {
    ec.innerHTML = `<div style="padding:20px;color:var(--red)">erro: ${esc(e.message)}</div>`;
  }
}

function renderResource(r) {
  const meta = [
    ['apiVersion', r.api_version], ['kind', r.kind], ['name', r.name],
    ['criado_em', r.criado_em?.slice(0,19)], ['atualizado_em', r.atualizado_em?.slice(0,19)],
  ].filter(([,v])=>v).map(([k,v])=>`
    <div class="meta-item"><div class="mi-key">${k}</div><div class="mi-val">${esc(String(v))}</div></div>
  `).join('');

  const labels = Object.entries(r.labels||{}).map(([k,v])=>
    `<span class="label-chip lc-${k}-${v}">${esc(k)}=${esc(v)}</span>`
  ).join('');

  let specHtml = '';
  if (Object.keys(r.spec||{}).length) {
    if (r.kind === 'Doc' && r.spec.body) {
      specHtml = `<div class="r-section">
        <div class="sec-title">spec · body</div>
        <div class="md">${markdownToHtml(r.spec.body.slice(0,8000))}</div>
        ${r.spec.source ? `<div style="margin-top:8px;font-size:10px;color:var(--muted)">src: ${esc(r.spec.source)}</div>` : ''}
      </div>`;
    } else {
      specHtml = `<div class="r-section">
        <div class="sec-title">spec</div>
        <pre class="json">${jsonStr(r.spec)}</pre>
      </div>`;
    }
  }

  let statusHtml = '';
  if (Object.keys(r.status||{}).length) {
    statusHtml = `<div class="r-section">
      <div class="sec-title">status</div>
      <pre class="json">${jsonStr(r.status)}</pre>
    </div>`;
  }

  document.getElementById('editor-content').innerHTML = `
    <div class="r-card">
      <div class="r-header">
        <span class="r-kind">${esc(r.kind)}</span>
        <span class="r-name-big">${esc(r.name)}</span>
        <div class="r-actions">
          <button class="btn" onclick="copyDescribe('${r.kind}','${r.name}')">📋 copiar cmd</button>
          <button class="btn danger" onclick="deleteResource('${r.kind}','${r.name}')">🗑 deletar</button>
        </div>
      </div>
      <div class="r-meta">${meta}</div>
      ${labels ? `<div class="labels-row">${labels}</div>` : ''}
      ${specHtml}
      ${statusHtml}
    </div>`;
}

function copyDescribe(kind, name) {
  navigator.clipboard.writeText('/describe ' + kind + ' ' + name);
  toast('copiado: /describe ' + kind + ' ' + name);
}

async function deleteResource(kind, name) {
  if (!confirm('Deletar ' + kind + '/' + name + '?')) return;
  try {
    const h = {};
    if (TOKEN) h['Authorization'] = 'Bearer ' + TOKEN;
    const r = await fetch(API + '/' + kind + '/' + name, {method:'DELETE', headers:h});
    if (!r.ok) throw new Error(await r.text());
    toast('deletado: ' + kind + '/' + name);
    closeTab({stopPropagation:()=>{}}, kind + '/' + name);
    delete treeData[kind];
    allKinds = await apiFetch(API + '/').catch(()=>allKinds);
    if (treeOpen[kind]) treeData[kind] = await apiFetch(API + '/' + kind).catch(()=>[]);
    updateStatus();
    renderTree();
  } catch(e) { toast('erro: ' + e.message, true); }
}

function jsonStr(obj) {
  return JSON.stringify(obj, null, 2)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

let toastTimer;
function toast(msg, err=false) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'show ' + (err ? 'err' : 'ok');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.className = '', 3000);
}

// ── Filter ──
document.getElementById('filter').addEventListener('input', () => renderTree());

// ── Markdown ──
function markdownToHtml(md) {
  if (!md) return '';
  let s = md;
  const blocks = [];
  s = s.replace(/```[\w]*\n?([\s\S]*?)```/g, (_, code) => {
    blocks.push(code.trimEnd());
    return '\x00BLOCK'+(blocks.length-1)+'\x00';
  });
  s = s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  s = s.replace(/`([^`]+)`/g,'<code>$1</code>');
  s = s.replace(/\*\*\*(.+?)\*\*\*/g,'<strong><em>$1</em></strong>');
  s = s.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
  s = s.replace(/\*(.+?)\*/g,'<em>$1</em>');
  s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2" target="_blank">$1</a>');
  s = s.replace(/^### (.+)$/gm,'<h3>$1</h3>');
  s = s.replace(/^## (.+)$/gm,'<h2>$1</h2>');
  s = s.replace(/^# (.+)$/gm,'<h1>$1</h1>');
  s = s.replace(/^[-*]{3,}$/gm,'<hr>');
  s = s.replace(/^&gt; (.+)$/gm,'<blockquote>$1</blockquote>');
  s = s.replace(/^\|(.+)\|\s*\n\|[-| :]+\|\s*\n((?:\|.+\|\s*\n?)+)/gm, (_, head, body) => {
    const ths = head.split('|').filter(c=>c.trim()).map(c=>`<th>${c.trim()}</th>`).join('');
    const rows = body.trim().split('\n').map(row => {
      const tds = row.split('|').filter(c=>c.trim()).map(c=>`<td>${c.trim()}</td>`).join('');
      return `<tr>${tds}</tr>`;
    }).join('');
    return `<table><thead><tr>${ths}</tr></thead><tbody>${rows}</tbody></table>`;
  });
  s = s.replace(/((?:^[-*+] .+\n?)+)/gm, m => {
    const items = m.trim().split('\n').map(l=>`<li>${l.replace(/^[-*+] /,'')}</li>`).join('');
    return `<ul>${items}</ul>`;
  });
  s = s.replace(/((?:^\d+\. .+\n?)+)/gm, m => {
    const items = m.trim().split('\n').map(l=>`<li>${l.replace(/^\d+\. /,'')}</li>`).join('');
    return `<ol>${items}</ol>`;
  });
  s = s.replace(/\x00BLOCK(\d+)\x00/g, (_,i) =>
    `<pre><code>${blocks[+i].replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}</code></pre>`
  );
  s = s.split('\n\n').map(para => {
    para = para.trim();
    if (!para) return '';
    if (/^<(h[1-3]|ul|ol|pre|table|blockquote|hr)/.test(para)) return para;
    return `<p>${para.replace(/\n/g,'<br>')}</p>`;
  }).join('\n');
  return s;
}
function isMarkdown(t) { return /^#+\s|```|\*\*|\|.+\|/.test(t); }

// ── Resize: sidebar (ew) ──
(function(){
  const handle = document.getElementById('sb-resize');
  const sb = document.getElementById('sidebar');
  let dragging = false, startX, startW;
  const saved = localStorage.getItem('atlas_sb_w');
  if (saved) sb.style.width = saved + 'px';

  handle.addEventListener('mousedown', e => {
    dragging = true; startX = e.clientX; startW = sb.offsetWidth;
    handle.classList.add('drag');
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'ew-resize';
  });
  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const w = Math.min(Math.max(startW + e.clientX - startX, 120), 500);
    sb.style.width = w + 'px';
    document.documentElement.style.setProperty('--sidebar-w', w + 'px');
  });
  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    handle.classList.remove('drag');
    document.body.style.userSelect = '';
    document.body.style.cursor = '';
    localStorage.setItem('atlas_sb_w', sb.offsetWidth);
  });
})();

// ── Resize: bottom panel (ns) ──
(function(){
  const handle = document.getElementById('bot-resize');
  const bot = document.getElementById('bottom');
  let dragging = false, startY, startH;
  const saved = localStorage.getItem('atlas_bot_h');
  if (saved) bot.style.height = saved + 'px';

  handle.addEventListener('mousedown', e => {
    dragging = true; startY = e.clientY; startH = bot.offsetHeight;
    handle.classList.add('drag');
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'ns-resize';
  });
  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const h = Math.min(Math.max(startH - (e.clientY - startY), 60), window.innerHeight * 0.7);
    bot.style.height = h + 'px';
  });
  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    handle.classList.remove('drag');
    document.body.style.userSelect = '';
    document.body.style.cursor = '';
    localStorage.setItem('atlas_bot_h', bot.offsetHeight);
  });
  // Duplo clique: toggle colapso
  handle.addEventListener('dblclick', () => {
    const h = bot.offsetHeight;
    if (h <= 62) {
      bot.style.height = (+(localStorage.getItem('atlas_bot_h_prev') || 200)) + 'px';
    } else {
      localStorage.setItem('atlas_bot_h_prev', h);
      bot.style.height = '30px';
    }
  });
})();

// ── CLI ──
const cliInput = document.getElementById('cli-input');
const cliOutput = document.getElementById('cli-output');
const cliSugs = document.getElementById('cli-suggestions');
let cliHistory = JSON.parse(localStorage.getItem('atlas_cli_history') || '[]');
let histIdx = -1, sugList = [], sugIdx = -1, sugDebounce;

function cliAppend(text, cls) {
  const el = document.createElement('div');
  el.className = cls;
  if (cls === 'cli-out' && isMarkdown(text)) {
    el.classList.add('md');
    el.innerHTML = markdownToHtml(text);
  } else { el.textContent = text; }
  cliOutput.appendChild(el);
  cliOutput.scrollTop = cliOutput.scrollHeight;
}

async function cliRun(text) {
  text = text.trim();
  if (!text) return;
  cliAppend('$ ' + text, 'cli-cmd');
  cliHistory = [text, ...cliHistory.filter(h=>h!==text)].slice(0,80);
  localStorage.setItem('atlas_cli_history', JSON.stringify(cliHistory));
  histIdx = -1;
  try {
    const h = {'Content-Type':'application/json'};
    if (TOKEN) h['Authorization'] = 'Bearer ' + TOKEN;
    const r = await fetch(API+'/_cmd', {method:'POST', headers:h, body:JSON.stringify({text})});
    const j = await r.json();
    if (j.error) { cliAppend(j.error, 'cli-err'); return; }
    cliAppend(j.output || '(sem saída)', 'cli-out');
    // Refresh tree após comandos que mudam o store
    if (/^\/(apply|delete|patch|rm|a)\b/.test(text)) {
      allKinds = await apiFetch(API+'/').catch(()=>allKinds);
      for (const k of Object.keys(treeOpen)) {
        if (treeOpen[k]) treeData[k] = await apiFetch(API+'/'+k).catch(()=>[]);
      }
      updateStatus(); renderTree();
    }
  } catch(e) { cliAppend('erro: '+e.message, 'cli-err'); }
  cliAppend('─'.repeat(40), 'cli-sep');
}

async function fetchSuggestions(q) {
  const h = {}; if (TOKEN) h['Authorization'] = 'Bearer '+TOKEN;
  const r = await fetch(API+'/_complete?q='+encodeURIComponent(q), {headers:h}).catch(()=>null);
  if (!r || !r.ok) return [];
  return r.json();
}

function renderSugs(list, q) {
  sugList = list; sugIdx = -1;
  cliSugs.innerHTML = '';
  list.slice(0,12).forEach((s,i) => {
    const el = document.createElement('div');
    el.className = 'sug';
    const ml = q.length;
    el.innerHTML = `<span class="sug-match">${esc(s.slice(0,ml))}</span>${esc(s.slice(ml))}`;
    el.onmousedown = e => { e.preventDefault(); cliInput.value = s; hideSugs(); cliInput.focus(); };
    cliSugs.appendChild(el);
  });
}
function hideSugs() { cliSugs.innerHTML = ''; sugList = []; sugIdx = -1; }
function highlightSug(i) { cliSugs.querySelectorAll('.sug').forEach((el,j)=>el.classList.toggle('active',j===i)); }

cliInput.addEventListener('input', () => {
  clearTimeout(sugDebounce);
  const q = cliInput.value;
  sugDebounce = setTimeout(async () => renderSugs(await fetchSuggestions(q), q), 80);
});

cliInput.addEventListener('keydown', async e => {
  if (e.key === 'Tab') {
    e.preventDefault();
    if (sugList.length === 1) { cliInput.value = sugList[0]+' '; hideSugs(); }
    else if (sugList.length > 1) { sugIdx=(sugIdx+1)%sugList.length; highlightSug(sugIdx); cliInput.value=sugList[sugIdx]; }
    else { const l=await fetchSuggestions(cliInput.value); renderSugs(l,cliInput.value); if(l.length===1){cliInput.value=l[0]+' ';hideSugs();} }
    return;
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    if (sugList.length) { sugIdx=Math.min(sugIdx+1,sugList.length-1); highlightSug(sugIdx); cliInput.value=sugList[sugIdx]; return; }
    if (histIdx>0){histIdx--;cliInput.value=cliHistory[histIdx]||'';}
    else if (histIdx===0){histIdx=-1;cliInput.value='';}
    return;
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault();
    if (sugList.length){sugIdx=Math.max(sugIdx-1,0);highlightSug(sugIdx);cliInput.value=sugList[sugIdx];return;}
    if (histIdx<cliHistory.length-1){histIdx++;cliInput.value=cliHistory[histIdx];}
    return;
  }
  if (e.key==='Escape'){hideSugs();return;}
  if (e.key==='Enter'){
    e.preventDefault(); hideSugs();
    const cmd=cliInput.value.trim(); cliInput.value='';
    if (cmd) await cliRun(cmd); return;
  }
  if (e.key==='l'&&e.ctrlKey){e.preventDefault();cliOutput.innerHTML='';return;}
});

document.addEventListener('keydown', e => {
  if ((e.key==='k'&&e.ctrlKey)||(e.key==='`'&&!e.ctrlKey&&document.activeElement!==cliInput)){
    e.preventDefault(); cliInput.focus();
  }
});
document.addEventListener('click', e => { if (!e.target.closest('#cli-bar')) hideSugs(); });

// ── Boot ──
cliAppend('Atlas CLI · Tab completa · ↑↓ histórico · Ctrl+K foca · Ctrl+L limpa', 'cli-sep');
cliAppend('─'.repeat(40), 'cli-sep');

if (TOKEN) { init(); } else { showTokenOverlay(); }

// Auto-refresh kinds a cada 20s
setInterval(async () => {
  try {
    allKinds = await apiFetch(API+'/');
    updateStatus(); renderTree();
  } catch(_){}
}, 20000);
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
