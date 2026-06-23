const API = '/apis/atlas/v1';
let TOKEN = localStorage.getItem('atlas_token') || '';
let allKinds = {};
let allSchema = {}; // kind → {meta, spec, labels, hidden?, actions?} — from /_schema
// openTabs: [{id, kind, name, label, icon}]
let openTabs = [{id:'welcome', kind:null, name:null, label:'Bem-vindo', icon:'⚡'}];
let activeTab = 'welcome';
let treeOpen = {}; // kind → bool
let treeData = {}; // kind → [resource]

// ── Render registry (ADR-0020): kind → async fn(resource, container) ──────────
const RENDER_REGISTRY = {};
function registerRender(kind, fn) { RENDER_REGISTRY[kind] = fn; }

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
    [allKinds, allSchema] = await Promise.all([
      apiFetch(API + '/'),
      apiFetch(API + '/_schema').then(p => p.kinds || {}).catch(() => ({})),
    ]);
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

// ── State ──
let _curRes = null;   // currently rendered resource object
let subTab  = {};     // tabId → 'card' | 'manifest'

// ── Kind helpers ──
function kindIcon(k) {
  const icons = {Doc:'📄',Tracker:'📊',Goal:'🎯',Alarm:'⏰',Timer:'⏱',
    Job:'🧩',Routine:'🧩',  // Routine = alias legado de Job (ADR-0021)
    Idea:'💡',Task:'✅',RoutineRequest:'📋',Repo:'📦',Diff:'🔀',CheckIn:'📍',Agente:'🤖'};
  return icons[k] || '🗂';
}

// ── Tree ──
function renderTree() {
  const el = document.getElementById('tree');
  const filter = document.getElementById('filter').value.toLowerCase();
  let html = '';
  Object.keys(allKinds).sort().filter(kind => !allSchema[kind]?.hidden).forEach(kind => {
    const open = !!treeOpen[kind];
    const cnt = allKinds[kind];
    html += `<div class="kind-row${open?' open':''}" onclick="toggleKind('${kind}')">
      <span class="arrow">▶</span>
      <span>${kindIcon(kind)}</span>
      <span class="k-name">${kind}</span>
      <span class="k-count">${cnt}</span>
      <button class="k-new" onclick="event.stopPropagation();newResource('${kind}')" title="Novo ${kind}">＋</button>
    </div>`;
    if (open && treeData[kind]) {
      if (kind === 'Doc') {
        html += _renderDocTree(treeData[kind], filter);
      } else {
        treeData[kind]
          .filter(r => !filter || r.name.toLowerCase().includes(filter))
          .forEach(r => {
            const tabId = kind + '/' + r.name;
            const isActive = activeTab === tabId;
            html += `<div class="res-row${isActive?' active':''}" onclick="openResource('${kind}','${escJs(r.name)}')">
              <span class="r-icon">${kindIcon(kind)}</span>
              <span class="r-name">${esc(r.name)}</span>
            </div>`;
          });
      }
    }
  });
  el.innerHTML = html;
}

// ── Doc hierarchy: agrupa por labels (topic → repo/tipo → doc) ──
let docGroupOpen = {};
function _renderDocTree(docs, filter){
  const tree = {};
  docs.filter(r => !filter
      || r.name.toLowerCase().includes(filter)
      || ((r.spec&&r.spec.title||'').toLowerCase().includes(filter)))
    .forEach(r => {
      const lb = r.labels||{};
      const topic = lb.topic || '(geral)';
      const sub = lb.repo || lb.tipo || lb.grupo || '';
      tree[topic] = tree[topic] || {docs:[], subs:{}};
      if (sub) { (tree[topic].subs[sub] = tree[topic].subs[sub]||[]).push(r); }
      else tree[topic].docs.push(r);
    });
  let html='';
  Object.keys(tree).sort().forEach(topic => {
    const tkey='Doc::'+topic, topen=!!docGroupOpen[tkey], node=tree[topic];
    const cnt=node.docs.length+Object.values(node.subs).reduce((a,b)=>a+b.length,0);
    html += `<div class="doc-group lvl1${topen?' open':''}" onclick="toggleDocGroup('${escJs(tkey)}')">
      <span class="arrow">▶</span><span>📂</span><span class="k-name">${esc(topic)}</span><span class="k-count">${cnt}</span></div>`;
    if(!topen) return;
    Object.keys(node.subs).sort().forEach(sub => {
      const skey=tkey+'::'+sub, sopen=!!docGroupOpen[skey], list=node.subs[sub];
      html += `<div class="doc-group lvl2${sopen?' open':''}" onclick="toggleDocGroup('${escJs(skey)}')">
        <span class="arrow">▶</span><span>📁</span><span class="k-name">${esc(sub)}</span><span class="k-count">${list.length}</span></div>`;
      if(sopen) list.forEach(r => html += _docRow(r, 3));
    });
    node.docs.forEach(r => html += _docRow(r, 2));
  });
  return html;
}
function _docRow(r, lvl){
  const isActive = activeTab === 'Doc/'+r.name;
  const pad = 12 + lvl*13;
  const titulo = (r.spec&&r.spec.title) || r.name;
  return `<div class="res-row${isActive?' active':''}" style="padding-left:${pad}px" onclick="openResource('Doc','${escJs(r.name)}')">
    <span class="r-icon">📄</span><span class="r-name" title="${esc(r.name)}">${esc(titulo)}</span></div>`;
}
function toggleDocGroup(key){ docGroupOpen[key]=!docGroupOpen[key]; renderTree(); }

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
  const tabs = openTabs.map(t => {
    const cls = 'tab' + (t.id === activeTab ? ' active' : '');
    const closeBtn = t.id === 'welcome' ? '' :
      `<span class="tab-close" onclick="closeTab(event,'${t.id}')">✕</span>`;
    return `<div class="${cls}" data-id="${t.id}" onclick="activateTab('${t.id}')">
      <span class="tab-icon">${t.icon}</span>
      <span class="tab-name" title="${t.label}">${esc(t.label)}</span>
      ${closeBtn}
    </div>`;
  }).join('');
  bar.innerHTML = tabs + '<div class="tab-add" onclick="newResource()" title="Novo recurso">＋</div>';
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
  toggleSidebar(false);  // fecha o drawer no celular ao escolher um recurso
  await loadAndRender(kind, name);
}

async function loadAndRender(kind, name) {
  const ec = document.getElementById('editor-content');
  ec.innerHTML = '<div style="padding:20px;color:var(--muted)">carregando…</div>';
  try {
    const r = await apiFetch(API + '/' + kind + '/' + name);
    if (RENDER_REGISTRY[kind]) {
      ec.innerHTML = '';
      ec.classList.add('no-pad');
      await RENDER_REGISTRY[kind](r, ec);
    } else {
      ec.classList.remove('no-pad');
      renderResource(r);
    }
  } catch(e) {
    ec.classList.remove('no-pad');
    ec.innerHTML = `<div style="padding:20px;color:var(--red)">erro: ${esc(e.message)}</div>`;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// MANIFEST BUILDER — advanced resource editor
// ═══════════════════════════════════════════════════════════════════════════════

// ── Kind schemas: field definitions for form mode ──────────────────────────────
const _KIND_SCHEMA = {
  Tracker: {
    meta: {icon:'📊', desc:'Coleta valores numéricos via micro-sintaxe no chat'},
    spec: [
      {k:'unit',     type:'text',  label:'Unidade',       hint:'Ex: kg, min, ml, km'},
      {k:'syntax',   type:'text',  label:'Sintaxe',       hint:'Ex: "peso:" — como registrar no Telegram'},
      {k:'type',     type:'select',label:'Tipo',          opts:['number','text','duration'], hint:'Tipo do valor'},
      {k:'active',   type:'bool',  label:'Ativo',         hint:'Desativar para parar de coletar'},
    ],
    labels: [{k:'domain',label:'Domínio',hint:'fisico · estudo · sono · saude · trabalho'}],
  },
  Goal: {
    meta: {icon:'🎯', desc:'Meta com progresso calculado automaticamente'},
    spec: [
      {k:'tracker',  type:'text',  label:'Tracker',       hint:'Nome do Tracker a monitorar'},
      {k:'target',   type:'number',label:'Meta (target)',  hint:'Valor alvo'},
      {k:'start',    type:'number',label:'Valor inicial',  hint:'Baseline para cálculo de %'},
      {k:'unit',     type:'text',  label:'Unidade',       hint:'Ex: kg, dias, pontos'},
      {k:'direction',type:'select',label:'Direção',       opts:['down','up'], hint:'down = menor é melhor'},
    ],
    labels: [{k:'domain',label:'Domínio',hint:'fisico · estudo · sono · saude'}],
  },
  Alarm: {
    meta: {icon:'⏰', desc:'Lembrete agendado enviado via Telegram'},
    spec: [
      {k:'hora',    type:'time', label:'Horário',          hint:'Quando o lembrete dispara'},
      {k:'mensagem',type:'text', label:'Mensagem',        hint:'Texto enviado pelo bot'},
      {k:'once',    type:'bool', label:'Uma vez só',      hint:'false = repete diariamente'},
    ],
    labels:[],
  },
  Job: {
    meta: {icon:'🧩', desc:'Job agendado ou por trigger (ex-Routine, ADR-0021)'},
    spec: [
      {k:'agenda',  type:'cron',  label:'Agenda',         hint:'Escolha um preset ou edite o cron'},
      {k:'modelo',  type:'select',label:'Modelo IA',      opts:['none','claude-haiku-4-5-20251001','claude-sonnet-4-6'], hint:'none = sem IA'},
      {k:'saida',   type:'select',label:'Saída',          opts:['telegram','none'], hint:'Destino do resultado'},
      {k:'label',   type:'text',  label:'Label grupo',    hint:'Grupo de recursos (coletar-por-label)'},
      {k:'coletar', type:'text',  label:'Collect fn',     hint:'Nome da função collect; default = nome do job'},
    ],
    labels: [{k:'domain',label:'Domínio',hint:'fisico · estudo · sono · saude · trabalho'}],
  },
  Routine: {  // alias legado — não aparece no explorer (hidden via /_schema)
    meta: {icon:'🧩', desc:'Depreciado — use Job'},
    spec: [],
    labels: [],
  },
  Repo: {
    meta: {icon:'📦', desc:'Repositório git monitorado pelo collect repo-sync'},
    spec: [
      {k:'url', type:'text', label:'URL do repositório', hint:'https://github.com/user/repo'},
    ],
    labels: [],
  },
  Idea: {
    meta: {icon:'💡', desc:'Ideia capturada para o pool'},
    spec: [{k:'body', type:'area', label:'Corpo', hint:'Descrição completa da ideia'}],
    labels: [{k:'estado',label:'Estado',hint:'capturada · ativo · arquivada · descartada'}],
  },
  Task: {
    meta: {icon:'✅', desc:'Tarefa do pool'},
    spec: [
      {k:'body', type:'area', label:'Corpo',  hint:'Descrição da tarefa'},
      {k:'done', type:'bool', label:'Feita',  hint:'Marcar como concluída'},
    ],
    labels: [],
  },
  Doc: {
    meta: {icon:'📚', desc:'Documento markdown no store'},
    spec: [
      {k:'title', type:'text', label:'Título', hint:'Título exibido na listagem'},
      {k:'body',  type:'area', label:'Corpo (markdown)', hint:'Conteúdo em markdown'},
      {k:'source',type:'text', label:'Fonte (URL)',      hint:'Opcional — origem do conteúdo'},
    ],
    labels: [{k:'topic',label:'Tópico',hint:'arch · kindref · user · spec · adr'}],
  },
  RoutineRequest: {
    meta: {icon:'📬', desc:'Solicitação de nova rotina para o backlog'},
    spec: [{k:'body', type:'area', label:'Descrição', hint:'O que a rotina deve fazer'}],
    labels: [],
  },
  Timer: {
    meta: {icon:'⏱', desc:'Cronômetro — iniciado/parado via /timer'},
    spec: [],
    labels: [{k:'domain',label:'Domínio',hint:'trabalho · estudo · treino'}],
  },
  Prompt: {
    meta: {icon:'🧠', desc:'Chamada de IA plugável — qualquer rotina usa via coletar=prompt'},
    spec: [
      {k:'template', type:'area',  label:'Template',  hint:'Prompt. Use {dados} e {agora} como placeholders'},
      {k:'model',    type:'select',label:'Modelo',    opts:['claude-haiku-4-5-20251001','claude-sonnet-4-6'], hint:'Haiku = barato/rápido'},
      {k:'fonte',    type:'text',  label:'Fonte de {dados}', hint:'grupo:<g> · kind:<K> · repo:<r> · texto:<t>'},
      {k:'timeout',  type:'number',label:'Timeout (s)', hint:'Máximo de espera da IA'},
    ],
    labels: [{k:'grupo',label:'Grupo',hint:'Agrupa com outros recursos'}],
  },
  Agente: {
    meta: {icon:'🤖', desc:'Analisador configurável: motor + contexto + prompt (ADR-0024)'},
    spec: [
      {k:'motor',          type:'select',label:'Motor',             opts:['claude','ollama'],hint:'Provider de IA'},
      {k:'modelo',         type:'text',  label:'Modelo',            hint:'claude-haiku-4-5-20251001 / gemma4'},
      {k:'nivel_contexto', type:'select',label:'Nível de contexto', opts:['none','resumo','completo'],hint:'Custo×qualidade'},
      {k:'prompt',         type:'area',  label:'Prompt/template',   hint:'Use {mensagem} e {agora}'},
      {k:'endpoint',       type:'text',  label:'Endpoint Ollama',   hint:'http://host:11434'},
      {k:'timeout',        type:'number',label:'Timeout (s)',        hint:'Default: 60'},
    ],
    labels: [{k:'dominio',label:'Domínio',hint:'repo · estudo · geral'}],
  },
};

// ── Templates JSON por Kind ────────────────────────────────────────────────────
const _MANIFEST_TPL = {
  Tracker:        {kind:'Tracker',       name:'',labels:{},spec:{unit:'',syntax:'nome:',active:true,type:'number'},status:{}},
  Goal:           {kind:'Goal',          name:'',labels:{},spec:{target:0,start:0,unit:'',tracker:'',direction:'down'},status:{}},
  Alarm:          {kind:'Alarm',         name:'',labels:{},spec:{hora:'07:30',mensagem:'',once:false},status:{}},
  Timer:          {kind:'Timer',         name:'',labels:{},spec:{},status:{}},
  Job:            {kind:'Job',           name:'',labels:{},spec:{agenda:'0 9 * * *',modelo:'none',saida:'telegram',ativa:false},status:{}},
  Routine:        {kind:'Job',           name:'',labels:{},spec:{agenda:'0 9 * * *',modelo:'none',saida:'telegram',ativa:false},status:{}},
  Repo:           {kind:'Repo',          name:'',labels:{},spec:{url:'https://github.com/user/repo'},status:{}},
  Diff:           {kind:'Diff',          name:'',labels:{repo:''},spec:{commit:'',diff_raw:'',explicacao:''},status:{}},
  Idea:           {kind:'Idea',          name:'',labels:{},spec:{body:''},status:{}},
  Task:           {kind:'Task',          name:'',labels:{},spec:{body:'',done:false},status:{}},
  Doc:            {kind:'Doc',           name:'',labels:{topic:'user'},spec:{title:'',body:'# Título\n\nConteúdo…'},status:{}},
  RoutineRequest: {kind:'RoutineRequest',name:'',labels:{},spec:{body:''},status:{}},
  Agente:         {kind:'Agente',        name:'',labels:{},spec:{motor:'claude',modelo:'claude-haiku-4-5-20251001',nivel_contexto:'resumo',prompt:'Responda em PT-BR:\n{mensagem}',timeout:60},status:{}},
  Prompt:         {kind:'Prompt',        name:'',labels:{},spec:{template:'Analise e dê insights em PT-BR:\n{dados}',model:'claude-haiku-4-5-20251001',fonte:'grupo:saude',timeout:90},status:{}},
};

// ── Editor state ───────────────────────────────────────────────────────────────
const _NEW_ID = '__new__';
let _edMode = 'json'; // 'form' | 'json'

// ── History (localStorage) ─────────────────────────────────────────────────────
function _histPush(kind, name, manifest) {
  try {
    const key = 'atlas_manifest_hist';
    const hist = JSON.parse(localStorage.getItem(key)||'[]');
    hist.unshift({kind, name, manifest: JSON.stringify(manifest), ts: Date.now()});
    localStorage.setItem(key, JSON.stringify(hist.slice(0,30)));
  } catch(_){}
}
function _histGet() {
  try { return JSON.parse(localStorage.getItem('atlas_manifest_hist')||'[]'); } catch(_){ return []; }
}

// ── Sub-tab switching ──────────────────────────────────────────────────────────
function switchSubTab(mode) {
  if (!_curRes) return;
  const tabId = _curRes.kind + '/' + _curRes.name;
  subTab[tabId] = mode;
  _renderSubContent(_curRes, mode);
}

function _renderSubContent(r, mode) {
  const ec = document.getElementById('editor-content');
  ec.style.overflow = mode === 'manifest' ? 'hidden' : 'auto';
  ec.style.display  = mode === 'manifest' ? 'flex' : 'block';
  ec.style.flexDirection = 'column';
  ec.style.padding  = '0';

  const subtabs = `<div class="sub-tabbar">
    <div class="sub-tab${mode==='card'?' active':''}" onclick="switchSubTab('card')">Overview</div>
    <div class="sub-tab${mode==='manifest'?' active':''}" onclick="switchSubTab('manifest')">✏️ Manifest</div>
    <span class="sub-path">${esc(r.kind)}/${esc(r.name)}</span>
  </div>`;

  if (mode === 'manifest') {
    ec.innerHTML = subtabs + _manifestEditorHtml(r);
    _bindEditorEvents(false);
  } else {
    ec.innerHTML = subtabs + `<div style="padding:20px 24px">${_cardHtml(r)}</div>`;
    if (r.kind === 'Repo') _hydrateRepoCard(r.name);
  }
}

function renderResource(r) {
  _curRes = r;
  const tabId = r.kind + '/' + r.name;
  _renderSubContent(r, subTab[tabId] || 'card');
}

// ── Card HTML (overview) ───────────────────────────────────────────────────────
function _cardHtml(r) {
  const meta = [
    ['kind', r.kind], ['name', r.name],
    ['criado_em', fmtDt(r.criado_em)], ['atualizado_em', fmtDt(r.atualizado_em)],
  ].filter(([,v])=>v).map(([k,v])=>`<div class="meta-item"><div class="mi-key">${k}</div><div class="mi-val">${esc(String(v))}</div></div>`).join('');
  const labels = Object.entries(r.labels||{}).map(([k,v])=>`<span class="label-chip lc-${k}-${v}">${esc(k)}=${esc(v)}</span>`).join('');
  const schema = _KIND_SCHEMA[r.kind];
  const kindDesc = schema?.meta?.desc ? `<div style="font-size:11px;color:var(--muted);margin-bottom:12px">${esc(schema.meta.desc)}</div>` : '';
  return `<div class="r-card">
    <div class="r-header">
      <span class="r-kind">${esc(r.kind)}</span>
      <span class="r-name-big">${esc(r.name)}</span>
      <div class="r-actions">
        ${kindActionsHtml(r)}
        <button class="btn" onclick="switchSubTab('manifest')">✏️ Editar</button>
        <button class="btn" onclick="copyApply()">📋 CLI</button>
        <button class="btn danger" onclick="deleteResource('${esc(r.kind)}','${escJs(r.name)}')">🗑</button>
      </div>
    </div>
    ${kindDesc}
    <div class="r-meta">${meta}</div>
    ${labels ? `<div class="labels-row">${labels}</div>` : ''}
    ${_kindCard(r)}
    ${_rawDetails(r)}
  </div>`;
}

// ── Manifest editor HTML ───────────────────────────────────────────────────────
function _manifestEditorHtml(r) {
  const manifest = {kind:r.kind, name:r.name, labels:r.labels||{}, spec:r.spec||{}, status:r.status||{}};
  const jsonVal = JSON.stringify(manifest, null, 2);
  const schema = _KIND_SCHEMA[r.kind];
  const hasForm = schema && (schema.spec.length > 0 || schema.labels.length > 0);
  const modeBar = hasForm ? `<div class="ed-mode-toggle">
    <button class="ed-mode-btn${_edMode==='form'?' active':''}" onclick="setEdMode('form')">📋 Form</button>
    <button class="ed-mode-btn${_edMode==='json'?' active':''}" onclick="setEdMode('json')">{ } JSON</button>
  </div>` : '';

  return `<div class="manifest-wrap">
    <div class="ed-toolbar">
      ${modeBar}
      <button class="btn" onclick="pasteFromClipboard()">📥 Colar</button>
      <button class="btn" onclick="copyManifest()">📋 Copiar</button>
      <button class="btn" onclick="toggleHistory()">🕐 Histórico</button>
      <div style="position:relative;display:inline-block">
        <div id="hist-panel" class="hist-panel"></div>
      </div>
      <span style="flex:1"></span>
      <span id="ed-statusbar" class="ed-statusbar ed-valid">✓ JSON válido</span>
    </div>
    <div class="ed-wrap">
      ${hasForm ? `<div id="form-editor" class="form-editor${_edMode==='form'?' active':''}">
        ${_buildFormHtml(r, schema)}
      </div>` : ''}
      <div id="json-editor-wrap" class="json-editor-wrap${(_edMode==='json'||!hasForm)?' active':''}">
        <textarea id="manifest-ta" class="manifest-area" spellcheck="false">${esc(jsonVal)}</textarea>
      </div>
    </div>
    <div class="manifest-bar">
      <button class="btn" id="apply-btn" onclick="applyManifest()" style="min-width:100px">💾 Aplicar</button>
      <button class="btn" onclick="previewDiff()">🔍 Ver diff</button>
      <span style="flex:1"></span>
      <span id="manifest-err" style="font-size:10px;color:var(--red)"></span>
      <button class="btn danger" onclick="deleteResource('${esc(r.kind)}','${escJs(r.name)}')">🗑 Deletar</button>
    </div>
    <div style="font-size:10px;color:var(--border);padding-top:4px">Ctrl+S salvar · Tab indenta · Ctrl+Z desfaz</div>
  </div>`;
}

// ── Form builder ───────────────────────────────────────────────────────────────
function _buildFormHtml(r, schema) {
  const spec   = r.spec||{};
  const labels = r.labels||{};
  let html = `<div style="padding:14px 4px 0">`;
  html += `<div class="form-section">Metadados</div>`;
  html += `<div class="form-field"><label>name</label>
    <input type="text" id="f-name" value="${esc(r.name)}" oninput="_formToJson()">
    <div class="f-hint">Identificador único do recurso (imutável após criação)</div></div>`;

  if (schema.labels.length) {
    html += `<div class="form-section">Labels</div>`;
    for(const lf of schema.labels) {
      const val = labels[lf.k]||'';
      html += `<div class="form-field"><label>${esc(lf.label)} <span style="color:var(--border)">(labels.${esc(lf.k)})</span></label>
        <input type="text" id="f-l-${esc(lf.k)}" value="${esc(val)}" oninput="_formToJson()">
        <div class="f-hint">${esc(lf.hint)}</div></div>`;
    }
    // Extra labels KV editor
    const extraLabels = Object.entries(labels).filter(([k])=>!schema.labels.find(l=>l.k===k));
    html += `<div class="form-field"><label>Labels extras</label>
      <div id="kv-labels">`;
    for(const [k,v] of extraLabels)
      html += `<div class="form-kv-row"><input placeholder="chave" value="${esc(k)}" oninput="_formToJson()" class="kv-lk">
        <input placeholder="valor" value="${esc(v)}" oninput="_formToJson()" class="kv-lv">
        <button class="btn danger" onclick="_removeKvRow(this)">✕</button></div>`;
    html += `</div>
      <button class="btn" onclick="_addKvRow('kv-labels','kv-lk','kv-lv')" style="margin-top:4px">+ label</button></div>`;
  }

  if (schema.spec.length) {
    html += `<div class="form-section">Spec</div>`;
    for(const sf of schema.spec) {
      const val = spec[sf.k];
      const vStr = val===undefined||val===null ? '' : String(val);
      html += `<div class="form-field"><label>${esc(sf.label)} <span style="color:var(--border)">(spec.${esc(sf.k)})</span></label>`;
      if (sf.type==='area') {
        html += `<textarea id="f-s-${esc(sf.k)}" rows="5" oninput="_formToJson()" style="font-family:monospace">${esc(vStr)}</textarea>`;
      } else if (sf.type==='bool') {
        html += `<label style="display:flex;align-items:center;gap:6px;cursor:pointer">
          <input type="checkbox" id="f-s-${esc(sf.k)}" ${val?'checked':''} onchange="_formToJson()"> Ativado</label>`;
      } else if (sf.type==='select') {
        html += `<select id="f-s-${esc(sf.k)}" onchange="_formToJson()">
          ${(sf.opts||[]).map(o=>`<option${o===vStr?' selected':''}>${esc(o)}</option>`).join('')}
          ${!(sf.opts||[]).includes(vStr)&&vStr?`<option selected>${esc(vStr)}</option>`:''}
        </select>`;
      } else {
        html += `<input type="${sf.type||'text'}" id="f-s-${esc(sf.k)}" value="${esc(vStr)}" oninput="_formToJson()">`;
      }
      html += `<div class="f-hint">${esc(sf.hint)}</div></div>`;
    }
    // Extra spec KV
    const extraSpec = Object.entries(spec).filter(([k])=>!schema.spec.find(s=>s.k===k));
    html += `<div class="form-field"><label>Spec extras</label>
      <div id="kv-spec">`;
    for(const [k,v] of extraSpec)
      html += `<div class="form-kv-row"><input placeholder="chave" value="${esc(k)}" oninput="_formToJson()" class="kv-sk">
        <input placeholder="valor" value="${esc(typeof v==='object'?JSON.stringify(v):v)}" oninput="_formToJson()" class="kv-sv">
        <button class="btn danger" onclick="_removeKvRow(this)">✕</button></div>`;
    html += `</div>
      <button class="btn" onclick="_addKvRow('kv-spec','kv-sk','kv-sv')" style="margin-top:4px">+ campo</button></div>`;
  }
  html += '</div>';
  return html;
}

function _addKvRow(containerId, kClass, vClass) {
  const c = document.getElementById(containerId);
  if (!c) return;
  const row = document.createElement('div'); row.className='form-kv-row';
  row.innerHTML = `<input placeholder="chave" oninput="_formToJson()" class="${kClass}">
    <input placeholder="valor" oninput="_formToJson()" class="${vClass}">
    <button class="btn danger" onclick="_removeKvRow(this)">✕</button>`;
  c.appendChild(row);
}

function _removeKvRow(btn) {
  btn.closest('.form-kv-row')?.remove();
  _formToJson();
}

// ── Sync form → JSON ───────────────────────────────────────────────────────────
function _formToJson() {
  const ta = document.getElementById('manifest-ta');
  if (!ta) return;
  const r = _curRes;
  if (!r) return;
  const schema = _KIND_SCHEMA[r.kind];
  if (!schema) return;

  let cur = {};
  try { cur = JSON.parse(ta.value); } catch(_){}
  const name = document.getElementById('f-name')?.value || cur.name || r.name;

  // labels
  const labels = {...(cur.labels||{})};
  for(const lf of schema.labels) {
    const el = document.getElementById('f-l-'+lf.k);
    if (el) { if(el.value) labels[lf.k]=el.value; else delete labels[lf.k]; }
  }
  // extra labels kv
  document.querySelectorAll('#kv-labels .form-kv-row').forEach(row=>{
    const k=row.querySelector('.kv-lk')?.value?.trim();
    const v=row.querySelector('.kv-lv')?.value?.trim();
    if(k&&v) labels[k]=v;
  });

  // spec
  const spec = {...(cur.spec||{})};
  for(const sf of schema.spec) {
    const el = document.getElementById('f-s-'+sf.k);
    if (!el) continue;
    if (sf.type==='bool') spec[sf.k]=el.checked;
    else if (sf.type==='number') spec[sf.k]=isNaN(parseFloat(el.value))?el.value:parseFloat(el.value);
    else spec[sf.k]=el.value;
  }
  // extra spec kv
  document.querySelectorAll('#kv-spec .form-kv-row').forEach(row=>{
    const k=row.querySelector('.kv-sk')?.value?.trim();
    const v=row.querySelector('.kv-sv')?.value?.trim();
    if(k) { try{spec[k]=JSON.parse(v);}catch(_){spec[k]=v||'';} }
  });

  ta.value = JSON.stringify({kind:r.kind, name, labels, spec, status:cur.status||{}}, null, 2);
  _updateStatusBar();
}

// ── Sync JSON → form ───────────────────────────────────────────────────────────
function _jsonToForm() {
  const ta = document.getElementById('manifest-ta');
  if (!ta) return;
  let obj; try { obj=JSON.parse(ta.value); } catch(_){ return; }
  const schema = _KIND_SCHEMA[obj.kind];
  if (!schema) return;
  const fName = document.getElementById('f-name');
  if (fName) fName.value = obj.name||'';
  for(const lf of schema.labels) {
    const el = document.getElementById('f-l-'+lf.k);
    if (el) el.value = obj.labels?.[lf.k]||'';
  }
  for(const sf of schema.spec) {
    const el = document.getElementById('f-s-'+sf.k);
    if (!el) continue;
    const v = obj.spec?.[sf.k];
    if (sf.type==='bool') el.checked=!!v;
    else el.value=v===undefined||v===null?'':String(v);
  }
}

// ── Editor mode switch ─────────────────────────────────────────────────────────
function setEdMode(mode) {
  _edMode = mode;
  document.querySelectorAll('.ed-mode-btn').forEach(b=>b.classList.toggle('active', b.textContent.includes(mode==='form'?'Form':'JSON')));
  const fe = document.getElementById('form-editor');
  const je = document.getElementById('json-editor-wrap');
  if (mode==='form') {
    fe?.classList.add('active'); je?.classList.remove('active');
    _jsonToForm();
  } else {
    je?.classList.add('active'); fe?.classList.remove('active');
  }
  document.getElementById('manifest-ta')?.focus();
}

// ── Status bar ─────────────────────────────────────────────────────────────────
function _updateStatusBar() {
  const ta = document.getElementById('manifest-ta');
  const sb = document.getElementById('ed-statusbar');
  const err = document.getElementById('manifest-err');
  if (!ta||!sb) return;
  try {
    JSON.parse(ta.value);
    ta.classList.remove('err');
    if(err) err.textContent='';
    // line:col
    const pos = ta.selectionStart;
    const lines = ta.value.slice(0,pos).split('\n');
    const line = lines.length, col = lines[lines.length-1].length+1;
    const bytes = new Blob([ta.value]).size;
    sb.className='ed-statusbar ed-valid';
    sb.textContent=`✓ válido · ${line}:${col} · ${bytes}B`;
  } catch(e) {
    ta.classList.add('err');
    sb.className='ed-statusbar ed-invalid';
    sb.textContent='✗ '+e.message.slice(0,40);
    if(err) err.textContent=e.message.slice(0,60);
  }
}

// ── Smart textarea key bindings ────────────────────────────────────────────────
function _bindEditorEvents(isNew) {
  const ta = document.getElementById('manifest-ta');
  if (!ta) return;
  const applyFn = isNew ? applyNewResource : applyManifest;

  ta.addEventListener('keydown', e => {
    if (e.key==='s' && e.ctrlKey) { e.preventDefault(); applyFn(); return; }
    if (e.key==='Tab') {
      e.preventDefault();
      const s=ta.selectionStart, end=ta.selectionEnd;
      ta.value=ta.value.slice(0,s)+'  '+ta.value.slice(end);
      ta.selectionStart=ta.selectionEnd=s+2;
      _updateStatusBar();
      return;
    }
    // Auto-close brackets/quotes
    const pairs = {'{':'}','[':']','"':'"'};
    const s=ta.selectionStart, end=ta.selectionEnd;
    if (pairs[e.key] && s===end) {
      e.preventDefault();
      ta.value=ta.value.slice(0,s)+e.key+pairs[e.key]+ta.value.slice(end);
      ta.selectionStart=ta.selectionEnd=s+1;
      _updateStatusBar();
      return;
    }
    // Skip over an auto-inserted closing char instead of doubling it
    if ((e.key==='}'||e.key===']'||e.key==='"') && s===end && ta.value[s]===e.key) {
      e.preventDefault();
      ta.selectionStart=ta.selectionEnd=s+1;
      return;
    }
  });
  ta.addEventListener('input', _updateStatusBar);
  ta.addEventListener('click', _updateStatusBar);
  ta.addEventListener('keyup', _updateStatusBar);
  ta.focus();
  _updateStatusBar();
}

// ── Apply manifest ─────────────────────────────────────────────────────────────
async function applyManifest() {
  const ta = document.getElementById('manifest-ta');
  if (!ta) return;
  let obj;
  try { obj = JSON.parse(ta.value); }
  catch(e) { toast('JSON inválido: '+e.message, true); return; }
  const {kind, name, labels={}, spec={}, status={}} = obj;
  if (!kind||!name) { toast('kind e name são obrigatórios', true); return; }
  try {
    document.getElementById('apply-btn')?.setAttribute('disabled','');
    await apiFetch(API+'/'+kind+'/'+name, {method:'PUT', body:JSON.stringify({labels,spec,status})});
    _histPush(kind, name, obj);
    toast('✓ '+kind+'/'+name+' aplicado');
    document.getElementById('apply-btn')?.classList.add('flash');
    await _refreshStore();
    const r2 = await apiFetch(API+'/'+kind+'/'+name);
    _curRes = r2;
    const tabId = kind+'/'+name;
    _renderSubContent(r2, subTab[tabId]||'manifest');
  } catch(e) { toast('erro: '+e.message, true); }
  finally { document.getElementById('apply-btn')?.removeAttribute('disabled'); }
}

// ── Diff preview modal ────────────────────────────────────────────────────────
function previewDiff() {
  const ta = document.getElementById('manifest-ta');
  if (!ta) return;
  let next;
  try { next = JSON.parse(ta.value); }
  catch(e) { toast('JSON inválido: '+e.message, true); return; }
  const prev = _curRes ? {kind:_curRes.kind,name:_curRes.name,labels:_curRes.labels||{},spec:_curRes.spec||{},status:_curRes.status||{}} : {};
  const prevLines = JSON.stringify(prev,null,2).split('\n');
  const nextLines = JSON.stringify(next,null,2).split('\n');
  let diffHtml = '';
  // Simple positional line diff (added/removed/equal)
  for(let i=0;i<Math.max(prevLines.length,nextLines.length);i++) {
    const pl=prevLines[i], nl=nextLines[i];
    if(pl===nl) diffHtml+=`<div class="diff-line diff-eq">${esc(nl||'')}</div>`;
    else {
      if(pl!==undefined) diffHtml+=`<div class="diff-line diff-rem">- ${esc(pl)}</div>`;
      if(nl!==undefined) diffHtml+=`<div class="diff-line diff-add">+ ${esc(nl)}</div>`;
    }
  }
  const modal = document.createElement('div');
  modal.className='diff-modal';
  modal.innerHTML=`<div class="diff-box">
    <h3>🔍 Diff — ${esc(next.kind||'?')}/${esc(next.name||'?')}</h3>
    <div class="diff-body">${diffHtml||'<span style="color:var(--muted)">Sem alterações</span>'}</div>
    <div class="diff-foot">
      <button class="btn" onclick="this.closest('.diff-modal').remove()">Fechar</button>
      <button class="btn" onclick="this.closest('.diff-modal').remove();applyManifest()">💾 Aplicar mesmo assim</button>
    </div>
  </div>`;
  document.body.appendChild(modal);
  modal.addEventListener('click',e=>{if(e.target===modal)modal.remove();});
}

// ── History panel ──────────────────────────────────────────────────────────────
function toggleHistory() {
  const panel = document.getElementById('hist-panel');
  if (!panel) return;
  if (panel.classList.toggle('open')) {
    const hist = _histGet();
    if (!hist.length) { panel.innerHTML='<div style="padding:12px;font-size:11px;color:var(--muted)">Sem histórico</div>'; return; }
    panel.innerHTML = hist.slice(0,15).map((h,i)=>{
      const ts = new Date(h.ts).toLocaleString('pt-BR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
      return `<div class="hist-item" onclick="_histRestore(${i})">
        <span class="hi-ts">${ts}</span>
        <div class="hi-kind">${esc(h.kind)}</div>
        <div class="hi-name">${esc(h.name)}</div>
      </div>`;
    }).join('');
  }
}

function _histRestore(idx) {
  const hist = _histGet();
  const h = hist[idx];
  if (!h) return;
  const ta = document.getElementById('manifest-ta');
  if (ta) { ta.value = h.manifest; _updateStatusBar(); if(_edMode==='form')_jsonToForm(); }
  document.getElementById('hist-panel')?.classList.remove('open');
  toast('manifest restaurado de '+new Date(h.ts).toLocaleTimeString('pt-BR'));
}

// ── Clipboard import ───────────────────────────────────────────────────────────
async function pasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText();
    const ta = document.getElementById('manifest-ta');
    if (!ta) return;
    // Try to parse as JSON; if it is, pretty-print it
    try {
      const obj = JSON.parse(text);
      ta.value = JSON.stringify(obj, null, 2);
    } catch(_) {
      ta.value = text;
    }
    _updateStatusBar();
    if (_edMode==='form') _jsonToForm();
    toast('conteúdo colado do clipboard');
  } catch(e) {
    toast('erro ao ler clipboard: '+e.message, true);
  }
}

function copyManifest() {
  const ta = document.getElementById('manifest-ta');
  if (!ta) return;
  navigator.clipboard.writeText(ta.value);
  toast('manifest copiado');
}

function copyApply() {
  if (!_curRes) return;
  const r = _curRes;
  const labels = Object.entries(r.labels||{}).map(([k,v])=>`labels.${k}=${v}`).join(' ');
  const spec   = Object.entries(r.spec||{}).slice(0,4).map(([k,v])=>`spec.${k}=${v}`).join(' ');
  const cmd = `/apply ${r.kind} ${r.name} ${labels} ${spec}`.trim();
  navigator.clipboard.writeText(cmd);
  toast('copiado: '+cmd.slice(0,60)+(cmd.length>60?'…':''));
}

// ── New Resource ───────────────────────────────────────────────────────────────
function cancelNewResource() {
  closeTab({stopPropagation:()=>{}}, _NEW_ID);
}

function newResource(kind='') {
  if (openTabs.find(t=>t.id===_NEW_ID)) {
    activeTab = _NEW_ID;
    renderTabs();
    _showNewTab(kind);
    return;
  }
  openTabs.push({id:_NEW_ID, kind:null, name:null, label:'＋ Novo', icon:'＋'});
  activeTab = _NEW_ID;
  renderTabs();
  _showNewTab(kind);
}

function _showNewTab(preKind='') {
  const ec = document.getElementById('editor-content');
  ec.style.overflow='hidden'; ec.style.display='flex'; ec.style.flexDirection='column'; ec.style.padding='0';
  const kinds = [...new Set([...Object.keys(_MANIFEST_TPL), ...Object.keys(allKinds)])].sort();
  const chips = kinds.map(k=>`<button class="kind-chip${k===preKind?' sel':''}" onclick="_newSelectKind('${escJs(k)}')">${kindIcon(k)} ${esc(k)}</button>`).join('');
  const tpl = _MANIFEST_TPL[preKind] || {kind:preKind||'',name:'',labels:{},spec:{},status:{}};
  const schema = _KIND_SCHEMA[preKind];
  const kindDesc = schema?.meta?.desc ? `<div style="font-size:11px;color:var(--muted);margin-bottom:8px">${esc(schema.meta.desc)}</div>` : '';

  ec.innerHTML = `<div class="sub-tabbar">
    <div class="sub-tab active">＋ Novo Recurso</div>
  </div>
  <div class="new-res-wrap">
    <div class="new-res-kind-bar">${chips}</div>
    ${kindDesc}
    <div class="ed-toolbar" style="margin-bottom:6px">
      <button class="btn" onclick="pasteFromClipboard()">📥 Colar</button>
      <button class="btn" onclick="copyManifest()">📋 Copiar</button>
      <span style="flex:1"></span>
      <span id="ed-statusbar" class="ed-statusbar ed-valid">✓ JSON válido</span>
    </div>
    <textarea id="manifest-ta" class="manifest-area" spellcheck="false"
      style="flex:1">${esc(JSON.stringify(tpl,null,2))}</textarea>
    <div class="manifest-bar">
      <button class="btn" id="apply-btn" onclick="applyNewResource()" style="min-width:100px">💾 Criar recurso</button>
      <button class="btn" onclick="previewDiff()">🔍 Ver diff</button>
      <span style="flex:1"></span>
      <span id="manifest-err" style="font-size:10px;color:var(--red)"></span>
      <button class="btn" onclick="cancelNewResource()">Cancelar</button>
    </div>
    <div style="font-size:10px;color:var(--border);padding-top:4px">Ctrl+S criar · Tab indenta · Ctrl+Z desfaz</div>
  </div>`;
  _bindEditorEvents(true);
}

function _newSelectKind(kind) {
  document.querySelectorAll('.kind-chip').forEach(c=>{
    const label=c.textContent.trim().replace(/^.\s*/,'');
    c.classList.toggle('sel', label===kind);
  });
  const ta = document.getElementById('manifest-ta');
  if (!ta) return;
  let cur={};
  try { cur=JSON.parse(ta.value); } catch(_){}
  const tpl = _MANIFEST_TPL[kind] || {kind,name:'',labels:{},spec:{},status:{}};
  ta.value = JSON.stringify({...tpl, kind, name:cur.name||'', labels:{...tpl.labels,...(cur.labels||{})}, spec:{...tpl.spec,...(cur.spec||{})}}, null, 2);
  // Update kind description
  const schema = _KIND_SCHEMA[kind];
  const existing = document.querySelector('.new-res-wrap > div:not(.new-res-kind-bar):not(.ed-toolbar):not(.manifest-bar)');
  if (schema?.meta?.desc) {
    if (existing && !existing.classList.contains('manifest-area')) {
      existing.textContent = schema.meta.desc;
    }
  }
  _updateStatusBar();
}

async function applyNewResource() {
  const ta = document.getElementById('manifest-ta');
  if (!ta) return;
  let obj;
  try { obj = JSON.parse(ta.value); }
  catch(e) { toast('JSON inválido: '+e.message, true); return; }
  const {kind, name, labels={}, spec={}, status={}} = obj;
  if (!kind) { toast('kind é obrigatório', true); return; }
  if (!name) { toast('name é obrigatório', true); return; }
  try {
    document.getElementById('apply-btn')?.setAttribute('disabled','');
    await apiFetch(API+'/'+kind+'/'+name, {method:'PUT', body:JSON.stringify({labels,spec,status})});
    _histPush(kind, name, obj);
    toast('✓ '+kind+'/'+name+' criado');
    closeTab({stopPropagation:()=>{}}, _NEW_ID);
    await _refreshStore();
    openResource(kind, name);
  } catch(e) { toast('erro: '+e.message, true); }
  finally { document.getElementById('apply-btn')?.removeAttribute('disabled'); }
}

async function _refreshStore() {
  allKinds = await apiFetch(API+'/').catch(()=>allKinds);
  for(const k of Object.keys(treeOpen)) {
    if(treeOpen[k]) treeData[k] = await apiFetch(API+'/'+k).catch(()=>[]);
  }
  updateStatus(); renderTree();
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
    await _refreshStore();
  } catch(e) { toast('erro: ' + e.message, true); }
}

function jsonStr(obj) {
  return JSON.stringify(obj, null, 2)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function fmtDt(s){ return s ? String(s).slice(0,16).replace('T',' ') : ''; }

function _rawDetails(r){
  const spec = Object.keys(r.spec||{}).length ? `<div class="sec-title">spec</div><pre class="json">${jsonStr(r.spec)}</pre>` : '';
  const status = Object.keys(r.status||{}).length ? `<div class="sec-title" style="margin-top:8px">status</div><pre class="json">${jsonStr(r.status)}</pre>` : '';
  if(!spec && !status) return '';
  return `<details class="r-section" style="margin-top:12px"><summary style="cursor:pointer;color:var(--muted);font-size:11px">spec / status (JSON)</summary><div style="margin-top:8px">${spec}${status}</div></details>`;
}

function _kindCard(r){
  switch(r.kind){
    case 'Repo':    return _repoCard(r);
    case 'Goal':    return _goalCard(r);
    case 'Timer':   return _timerCard(r);
    case 'Tracker': return _trackerCard(r);
    case 'Routine': return _routineCard(r);
    case 'Alarm':   return _alarmCard(r);
    case 'Diff':    return _diffCard(r);
    case 'Doc':     return _docCard(r);
    case 'Prompt':  return _promptCard(r);
    case 'Idea': case 'Task': case 'RoutineRequest': return _poolCard(r);
    default:        return _genericCard(r);
  }
}

function _genericCard(r){
  let html='';
  if(Object.keys(r.spec||{}).length) html += `<div class="r-section"><div class="sec-title">spec</div><pre class="json">${jsonStr(r.spec)}</pre></div>`;
  if(Object.keys(r.status||{}).length) html += `<div class="r-section"><div class="sec-title">status</div><pre class="json">${jsonStr(r.status)}</pre></div>`;
  return html;
}

function _mi(k,v){ return `<div class="meta-item"><div class="mi-key">${esc(k)}</div><div class="mi-val">${esc(String(v))}</div></div>`; }

// ── Kind-card stubs (replaced in Tasks 2–4) ───────────────────────────────────
function _repoCard(r){
  const s=r.spec||{}, st=r.status||{};
  const commit = st.last_commit ? `<div style="font-size:14px">${esc(st.last_commit_msg||'(sem mensagem)')} <span style="color:var(--muted)">${esc(st.last_commit)}</span></div>
    <div style="font-size:11px;color:var(--muted)">${st.last_author?esc(st.last_author)+' · ':''}${esc(fmtDt(st.last_commit_date))}</div>` : '<div style="color:var(--muted)">sem sync ainda</div>';
  const stat = (st.files_changed!=null) ? `<div style="margin-top:6px">🗂 ${esc(String(st.files_changed))} arq · +${esc(String(st.insertions??0))}/-${esc(String(st.deletions??0))}</div>` : '';
  const sync = `<div style="font-size:11px;color:var(--muted);margin-top:4px">${st.last_sync?'sync '+fmtDt(st.last_sync):''}${st.last_check?' · check '+fmtDt(st.last_check):''}</div>`;
  const url = s.url ? `<div style="margin-top:6px"><a href="${esc(s.url)}" target="_blank" rel="noopener" style="color:var(--blue)">${esc(s.url)}</a></div>` : '';
  const nm = r.name;  // slug; usado em ids — deve casar com getElementById em _hydrateRepoCard
  return `<div class="r-section">
    <div class="sec-title">📦 repositório</div>
    ${commit}${stat}${sync}${url}
  </div>
  <div class="r-section">
    <div class="sec-title">🧠 contexto do projeto</div>
    <div id="repo-ctx-${nm}" style="color:var(--muted)">carregando contexto…</div>
  </div>
  <div class="r-section">
    <div class="sec-title">🔄 atualizações recentes</div>
    <div id="repo-diffs-${nm}" style="color:var(--muted)">carregando diffs…</div>
  </div>`;
}

async function _hydrateRepoCard(name){
  const ctxEl = document.getElementById('repo-ctx-'+name);
  const diffEl = document.getElementById('repo-diffs-'+name);
  // contexto
  try {
    const doc = await apiFetch(API+'/Doc/repo-'+encodeURIComponent(name)+'-contexto');
    const md = doc.spec&&doc.spec.body ? markdownToHtml(String(doc.spec.body)) : '<span style="color:var(--muted)">vazio</span>';
    const gen = doc.status&&doc.status.generated_at ? `<div style="font-size:10px;color:var(--muted);margin-bottom:6px">modelo: ${esc((doc.status.model)||'-')} · ${esc(fmtDt(doc.status.generated_at))}</div>` : '';
    if(ctxEl) ctxEl.innerHTML = `${gen}<details open><summary style="cursor:pointer;color:var(--blue);font-size:11px">ver/ocultar</summary><div class="md">${md}</div></details>`;
  } catch(e){
    if(ctxEl) ctxEl.innerHTML = '<span style="color:var(--muted)">contexto ainda não gerado</span>';
  }
  // diffs recentes do repo
  try {
    const all = await apiFetch(API+'/Diff');
    const meus = (all||[]).filter(d=>d.labels&&d.labels.repo===name)
      .sort((a,b)=>String(b.criado_em||'').localeCompare(String(a.criado_em||''))).slice(0,8);
    if(diffEl){
      diffEl.innerHTML = meus.length ? meus.map(d=>{
        const sp=d.spec||{};
        return `<div style="padding:4px 0;border-bottom:1px solid var(--border);cursor:pointer" onclick="openResource('Diff','${escJs(d.name)}')">
          <div style="font-size:12px">${esc(sp.subject||sp.commit||d.name)}</div>
          <div style="font-size:10px;color:var(--muted)">${esc(sp.commit||'')} · +${esc(String(sp.insertions??0))}/-${esc(String(sp.deletions??0))}</div>
        </div>`;
      }).join('') : '<span style="color:var(--muted)">sem atualizações ainda</span>';
    }
  } catch(e){
    if(diffEl) diffEl.innerHTML = '<span style="color:var(--muted)">diffs indisponíveis</span>';
  }
}

function _goalCard(r){
  const s=r.spec||{}, st=r.status||{};
  const target=s.target, atual=(st.atual!=null?st.atual:st.current);
  const unit=s.unit||'';
  let pct=null;
  const m=String(st.progresso||st.progress||'').match(/(\d+)/); if(m) pct=Math.min(100,+m[1]);
  const bar = pct!=null ? `<div style="background:var(--bg3);border-radius:6px;height:14px;overflow:hidden;margin:8px 0"><div style="width:${pct}%;height:100%;background:var(--green)"></div></div><div style="font-size:11px;color:var(--muted)">${pct}%</div>` : '';
  return `<div class="r-section">
    <div class="sec-title">🎯 progresso</div>
    <div style="font-size:18px">${esc(String(atual??'?'))}${esc(unit)} <span style="color:var(--muted)">→ ${esc(String(target??'?'))}${esc(unit)}</span></div>
    ${bar}
    ${s.direction?`<div style="font-size:11px;color:var(--muted)">direção: ${esc(s.direction)}</div>`:''}
  </div>`;
}

function _timerCard(r){
  const st=r.status||{};
  const rodando = st.running===true || st.state==='running' || !!st.started_at;
  const cor = rodando?'var(--green)':'var(--muted)';
  const desde = st.started_at?` desde ${fmtDt(st.started_at)}`:'';
  const ult = st.last_duration||st.ultima_duracao;
  return `<div class="r-section">
    <div class="sec-title">⏱ estado</div>
    <div style="font-size:18px;color:${cor}">${rodando?'▶ rodando'+esc(desde):'⏹ parado'}</div>
    ${ult?`<div style="font-size:11px;color:var(--muted)">última duração: ${esc(String(ult))}</div>`:''}
  </div>`;
}

function _trackerCard(r){
  const s=r.spec||{}, st=r.status||{};
  const syn=s.syntax||r.name+':';
  const unit=s.unit?' ('+esc(s.unit)+')':'';
  const last=(st.ultimo_valor!=null?st.ultimo_valor:(st.last_value!=null?st.last_value:null));
  const hoje=(st.count_today!=null?st.count_today:null);
  return `<div class="r-section">
    <div class="sec-title">📊 ${esc(s.unit||s.type||'tracker')}</div>
    <div style="font-size:18px">${last!=null?esc(String(last))+(s.unit?' '+esc(s.unit):''):'<span style="color:var(--muted)">sem registro</span>'}</div>
    ${hoje!=null?`<div style="font-size:11px;color:var(--muted)">hoje: ${esc(String(hoje))}</div>`:''}
    <div class="tk-input" style="margin-top:8px">
      <input id="tk-val" type="text" inputmode="decimal" autocomplete="off" placeholder="${esc(syn)} valor${unit}" onkeydown="if(event.key==='Enter')_tkLog('${escJs(syn)}')">
      <button class="btn" style="border-color:var(--green);color:var(--green)" onclick="_tkLog('${escJs(syn)}')">registrar</button>
    </div>
  </div>`;
}

function _routineCard(r){
  const s=r.spec||{}, st=r.status||{};
  const ativo = s.active===true || s.ativa===true;
  return `<div class="r-section">
    <div class="sec-title">🧩 rotina</div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px">
      ${_mi('agenda', s.schedule||s.agenda||'-')}
      ${_mi('modelo', s.model||s.modelo||'none')}
      ${_mi('ativo', ativo?'on':'off')}
      ${_mi('último run', fmtDt(st.last_run)||'-')}
      ${_mi('status', st.last_status||'-')}
      ${_mi('execuções', st.run_count!=null?st.run_count:'-')}
    </div>
  </div>`;
}

function _alarmCard(r){
  const s=r.spec||{}, st=r.status||{};
  return `<div class="r-section">
    <div class="sec-title">⏰ alarme</div>
    <div style="font-size:18px">${esc(String(s.time||s.hora||'--:--'))}</div>
    <div style="margin:4px 0">${esc(String(s.message||s.mensagem||''))}</div>
    <div style="font-size:11px;color:var(--muted)">${s.once?'uma vez':'diário'} · ${(s.active!==false)?'ativo':'inativo'}${st.last_fired?' · disparou '+fmtDt(st.last_fired):''}</div>
  </div>`;
}

function _docCard(r){
  const s=r.spec||{};
  const body = s.body ? `<div class="md">${markdownToHtml(String(s.body))}</div>` : '<div style="color:var(--muted)">(sem corpo)</div>';
  return `<div class="r-section">
    ${s.title?`<div class="sec-title">${esc(s.title)}</div>`:''}
    ${body}
    ${s.source?`<div style="margin-top:8px;font-size:10px;color:var(--muted)">src: ${esc(s.source)}</div>`:''}
  </div>`;
}

function _diffCard(r){
  const s=r.spec||{};
  const head = `${esc(s.subject||s.commit||'')} <span style="color:var(--muted)">${esc(s.commit||'')}</span>`;
  const stat = `🗂 ${esc(String(s.files_changed??'?'))} arq · +${esc(String(s.insertions??0))}/-${esc(String(s.deletions??0))}`;
  const arquivos = Array.isArray(s.files_list)&&s.files_list.length ? `<div style="font-size:11px;color:var(--muted);margin:4px 0">${s.files_list.map(esc).join(', ')}</div>` : '';
  const expl = s.explicacao ? `<div class="sec-title" style="margin-top:10px">🧠 análise</div><div class="md">${markdownToHtml(String(s.explicacao))}</div>` : '';
  const diff = s.diff_raw ? `<div class="sec-title" style="margin-top:10px">diff</div><pre class="json">${esc(String(s.diff_raw))}</pre>` : '';
  return `<div class="r-section">
    <div style="font-size:14px">${head}</div>
    <div style="font-size:11px;color:var(--muted)">${s.author?esc(s.author)+' · ':''}${esc(fmtDt(s.date))}</div>
    <div style="margin-top:6px">${stat}</div>
    ${arquivos}${expl}${diff}
  </div>`;
}

function _promptCard(r){
  const s=r.spec||{}, st=r.status||{};
  return `<div class="r-section">
    <div class="sec-title">🧠 template</div>
    <pre class="json">${esc(String(s.template||''))}</pre>
    <div style="font-size:11px;color:var(--muted);margin-top:6px">modelo: ${esc(s.model||'-')} · fonte: ${esc(s.fonte||'-')}</div>
    ${st.last_output?`<div class="sec-title" style="margin-top:10px">última saída</div><div class="md">${markdownToHtml(String(st.last_output))}</div>`:''}
  </div>`;
}

function _poolCard(r){
  const s=r.spec||{}, st=r.status||{};
  const body = s.body ? `<div class="md">${markdownToHtml(String(s.body))}</div>` : '';
  const done = (r.kind==='Task') ? `<div style="font-size:12px;margin-top:6px">${s.done?'✅ feita':'⬜ pendente'}</div>` : '';
  const meta = [];
  if(s.priority!=null) meta.push('prioridade: '+esc(String(s.priority)));
  if(st.state||st.estado) meta.push('estado: '+esc(String(st.state||st.estado)));
  return `<div class="r-section">
    ${body||'<div style="color:var(--muted)">(vazio)</div>'}
    ${done}
    ${meta.length?`<div style="font-size:11px;color:var(--muted);margin-top:6px">${meta.join(' · ')}</div>`:''}
  </div>`;
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

// ── View switcher ──
function setView(v) {
  document.body.dataset.view = v;
  document.getElementById('btn-status').classList.toggle('active', v==='status');
  document.getElementById('btn-explorer').classList.toggle('active', v==='explorer');
  document.getElementById('btn-graph').classList.toggle('active', v==='graph');
  localStorage.setItem('atlas_view', v);
  if (v==='graph') { if (Object.keys(GV.data).length===0) loadGraph(); else renderGraph(); }
  clearInterval(_svTimer); _svTimer=null;
  if (v==='status') { loadStatus(); _svTimer=setInterval(loadStatus, 30000); }
}

// ── Status / overview view ──
let _svTimer = null;
function _ago(iso){
  if(!iso) return '';
  const d=new Date(iso), s=(Date.now()-d.getTime())/1000;
  if(s<0) return _in(-s);
  if(s<60) return 'agora';
  if(s<3600) return Math.floor(s/60)+'min atrás';
  if(s<86400) return Math.floor(s/3600)+'h atrás';
  return Math.floor(s/86400)+'d atrás';
}
function _in(s){
  if(s<60) return 'em <1min';
  if(s<3600) return 'em '+Math.floor(s/60)+'min';
  if(s<86400) return 'em '+Math.floor(s/3600)+'h';
  return 'em '+Math.floor(s/86400)+'d';
}
function _hhmm(iso){ if(!iso) return ''; const d=new Date(iso); return d.toLocaleString('pt-BR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}); }

const _SV_CARDS=['overview','routines','running','repos','runs'];
let svOrder=(()=>{ try{return JSON.parse(localStorage.getItem('atlas_sv_order'))||_SV_CARDS.slice();}catch(_){return _SV_CARDS.slice();} })();

async function loadStatus(){
  const body=document.getElementById('sv-body');
  try{
    const s=await apiFetch(API+'/_status');
    document.getElementById('sv-clock').textContent=new Date(s.now).toLocaleString('pt-BR');
    const parts={overview:_svOverview(s),routines:_svRoutines(s),running:_svRunning(s),repos:_svRepos(s),runs:_svRuns(s)};
    const order=svOrder.filter(id=>parts[id]!==undefined);
    _SV_CARDS.forEach(id=>{ if(!order.includes(id)) order.push(id); });
    body.innerHTML = order.map(id => parts[id] ? _svWrap(id, parts[id]) : '').join('');
  }catch(e){ body.innerHTML='<div class="sv-empty">erro: '+esc(e.message)+'</div>'; }
}

// envolve cada card num slot arrastável (janelas mexíveis)
function _svWrap(id, html){
  const span2 = html.indexOf('sv-card span2')>=0;
  return `<div class="sv-slot${span2?' span2':''}" draggable="true" data-card="${id}"
    ondragstart="_svDragStart(event,'${id}')" ondragover="_svDragOver(event)"
    ondragleave="event.currentTarget.classList.remove('sv-dragover')"
    ondrop="_svDrop(event,'${id}')" ondragend="_svDragEnd(event)">${html}</div>`;
}
let _svDragId=null;
function _svDragStart(e,id){ _svDragId=id; e.dataTransfer.effectAllowed='move'; e.currentTarget.classList.add('sv-dragging'); }
function _svDragOver(e){ e.preventDefault(); e.dataTransfer.dropEffect='move'; e.currentTarget.classList.add('sv-dragover'); }
function _svDrop(e,targetId){
  e.preventDefault();
  document.querySelectorAll('.sv-dragover').forEach(x=>x.classList.remove('sv-dragover'));
  if(_svDragId && _svDragId!==targetId){
    const o=svOrder.filter(x=>x!==_svDragId);
    const i=o.indexOf(targetId);
    o.splice(i<0?o.length:i, 0, _svDragId);
    svOrder=o; localStorage.setItem('atlas_sv_order', JSON.stringify(svOrder));
    loadStatus();
  }
}
function _svDragEnd(){ document.querySelectorAll('.sv-dragging,.sv-dragover').forEach(x=>x.classList.remove('sv-dragging','sv-dragover')); _svDragId=null; }

function _svOverview(s){
  const active=s.routines.filter(r=>r.active).length;
  const tiles=[
    ['total', s.total, 'recursos'],
    ['rotinas', active+'/'+s.routines.length, 'ativas'],
    ['rodando', s.running.length, 'agora'],
    ['repos', s.repos.length, 'monitorados'],
  ];
  return `<div class="sv-card span2"><h3>⚙ Visão geral</h3>
    <div class="sv-metrics">${tiles.map(([_,n,l])=>
      `<div class="sv-metric"><div class="m-num">${esc(String(n))}</div><div class="m-lbl">${esc(l)}</div></div>`
    ).join('')}</div></div>`;
}

function _svRoutines(s){
  const rs=[...s.routines].sort((a,b)=>(b.active-a.active)||((a.next_run||'z')<(b.next_run||'z')?-1:1));
  const rows = rs.map(r=>{
    const dot=r.active?'on':'off';
    const when=r.active&&r.next_run ? `próx: ${_in((new Date(r.next_run)-Date.now())/1000)}` :
               (r.active?'<span style="color:var(--orange)">agenda não-cron</span>':'inativa');
    const last=r.last_run?`<span class="sv-when2">últ: ${_ago(r.last_run)}</span>`:'';
    const ckBtn = r.checkin ? `<button class="sv-runbtn" style="color:var(--blue);width:34px" title="Check-in (registrar valores do grupo ${esc(r.grupo)})" onclick="event.stopPropagation();openCheckin('${escJs(r.grupo)}')">📝</button>` : '';
    return `<div class="sv-row" onclick="openResource('Job','${escJs(r.name)}');setView('explorer')">
      <div class="sv-dot ${dot}"></div>
      <div class="sv-main"><div class="sv-name">${esc(r.name)}</div>
        <div class="sv-sub">${esc(r.schedule||'sem agenda')}${r.model!=='none'?' · '+esc(r.model):''}</div></div>
      ${ckBtn}
      <button class="sv-runbtn" title="Executar agora" onclick="event.stopPropagation();runRoutine('${escJs(r.name)}')">▶</button>
      <div class="sv-when">${when}${last}</div></div>`;
  }).join('') || '<div class="sv-empty">nenhuma rotina</div>';
  return `<div class="sv-card span2"><h3>🧩 Rotinas<span class="sv-badge">${s.routines.filter(r=>r.active).length} ativas</span></h3>
    <div class="sv-cardbody">${rows}</div></div>`;
}

function _svRunning(s){
  const timers=s.running.map(t=>`<div class="sv-row">
      <div class="sv-dot run"></div>
      <div class="sv-main"><div class="sv-name">${esc(t.name)}</div>
        <div class="sv-sub">timer${t.domain?' · '+esc(t.domain):''}</div></div>
      <button class="sv-runbtn" style="color:var(--red)" title="Parar timer" onclick="timerStop('${escJs(t.name)}')">⏹</button>
      ${t.since?`<div class="sv-when">${_ago(t.since)}</div>`:''}</div>`).join('');
  const alarms=s.alarms.map(a=>`<div class="sv-row">
      <div class="sv-dot on"></div>
      <div class="sv-main"><div class="sv-name">${esc(a.name)}</div>
        <div class="sv-sub">alarme ${esc(a.hora||'')}${a.once?' (uma vez)':''}</div></div></div>`).join('');
  const total=s.running.length+s.alarms.length;
  const body=(timers+alarms) || '<div class="sv-empty">nada em execução</div>';
  return `<div class="sv-card"><h3>▶ Em execução<span class="sv-badge">${total}</span></h3>
    <div class="sv-cardbody">${body}</div></div>`;
}

function _svRepos(s){
  if(!s.repos.length) return '';
  const cards=s.repos.map(r=>{
    const stat=(r.files_changed!=null)?
      `<span>🗂 ${r.files_changed} arq</span><span class="rp-add">+${r.insertions||0}</span><span class="rp-del">-${r.deletions||0}</span>`:'';
    return `<div class="sv-repo sv-clickable" onclick="openResource('Repo','${escJs(r.name)}');setView('explorer')">
      <div class="rp-top"><span class="rp-name">${esc(r.name)}</span>
        ${r.last_commit?`<span class="rp-commit">${esc(r.last_commit)}</span>`:''}
        <span style="flex:1"></span>
        <button class="sv-runbtn" style="color:var(--purple);width:auto;padding:0 8px" title="Insight por IA" onclick="event.stopPropagation();aiInsight('repo','${escJs(r.name)}')">🧠</button>
        <span class="sv-sub">${r.last_sync?_ago(r.last_sync):(r.last_check?'verif. '+_ago(r.last_check):'nunca')}</span></div>
      ${r.last_commit_msg?`<div class="rp-msg">📝 ${esc(r.last_commit_msg)}</div>`:''}
      <div class="rp-meta">${r.last_author?`<span>👤 ${esc(r.last_author)}</span>`:''}${stat}</div>
    </div>`;
  }).join('');
  return `<div class="sv-card span2"><h3>📦 Repositórios<span class="sv-badge">${s.repos.length}</span></h3>
    <div style="display:flex;flex-direction:column">${cards}</div></div>`;
}

function _svRuns(s){
  const rows=(s.recent_runs||[]).map(r=>{
    const ok=r.status==='ok'||r.status==='success';
    const pill=`<span class="sv-pill ${ok?'ok':(r.status==='skip'?'':'err')}">${esc(r.status)}</span>`;
    return `<div class="sv-row"><div class="sv-main">
      <div class="sv-name">${esc(r.rotina)}</div>
      <div class="sv-sub">${esc(r.camada||'')} · ${_hhmm(r.iniciado_em)}</div></div>${pill}</div>`;
  }).join('') || '<div class="sv-empty">sem execuções registradas</div>';
  return `<div class="sv-card"><h3>🕐 Execuções recentes</h3><div class="sv-cardbody">${rows}</div></div>`;
}

// ── Executar rotina sob demanda ──
async function runRoutine(name){
  toast('▶ executando '+name+'…');
  try{
    const r=await apiFetch(API+'/_run',{method:'POST',body:JSON.stringify({routine:name})});
    _showRunResult(name, r);
    if(document.body.dataset.view==='status') loadStatus();
  }catch(e){ toast('erro: '+e.message, true); }
}

function _showRunResult(name, r){
  const out=String(r.output||'(sem saída)').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const m=document.createElement('div'); m.className='diff-modal';
  m.innerHTML=`<div class="diff-box">
    <h3>${r.ok?'✅':'⚠️'} ${esc(name)}${r.model&&r.model!=='none'?' · '+esc(r.model):''}</h3>
    <div class="diff-body"><pre style="white-space:pre-wrap;word-break:break-word;font-size:12px;line-height:1.55;color:var(--text);margin:0">${out}</pre></div>
    <div class="diff-foot">
      <button class="btn" onclick="runRoutine('${escJs(name)}');this.closest('.diff-modal').remove()">▶ De novo</button>
      <button class="btn" onclick="this.closest('.diff-modal').remove()">Fechar</button>
    </div>
  </div>`;
  document.body.appendChild(m);
  m.addEventListener('click',e=>{if(e.target===m)m.remove();});
}

// ── Insight por IA ──
async function aiInsight(scope, name=''){
  const titulo = scope==='repo' ? 'repo '+name : 'sistema';
  const m=document.createElement('div'); m.className='diff-modal';
  m.innerHTML=`<div class="diff-box">
    <h3>🧠 Insight IA · ${esc(titulo)}</h3>
    <div class="diff-body" id="ai-insight-body">
      <div style="display:flex;align-items:center;gap:10px;color:var(--purple);font-size:13px">
        <span class="ai-spin"></span> analisando com Haiku…</div></div>
    <div class="diff-foot"><button class="btn" onclick="this.closest('.diff-modal').remove()">Fechar</button></div>
  </div>`;
  document.body.appendChild(m);
  m.addEventListener('click',e=>{if(e.target===m)m.remove();});
  try{
    const r=await apiFetch(API+'/_insight',{method:'POST',body:JSON.stringify({scope,name})});
    const body=document.getElementById('ai-insight-body');
    if(!body) return;
    if(r.ok){
      const docLink = r.doc ? `<a onclick="openResource('Doc','${escJs(r.doc)}');document.querySelectorAll('.diff-modal').forEach(x=>x.remove())" style="color:var(--blue);cursor:pointer">📄 salvo em Doc/${esc(r.doc)}</a>` : '';
      body.innerHTML=`<div class="md">${markdownToHtml(r.insight||'')}</div>
      <div style="margin-top:10px;font-size:10px;color:var(--border)">via ${esc(r.model||'haiku')} · ${docLink}</div>`;
    }
    else { body.innerHTML=`<div style="color:var(--red);font-size:12px">⚠️ ${esc(r.error||'falha')}</div>`; }
  }catch(e){
    const body=document.getElementById('ai-insight-body');
    if(body) body.innerHTML=`<div style="color:var(--red);font-size:12px">erro: ${esc(e.message)}</div>`;
  }
}

// ── Registro visual de valor de tracker ──
async function logTrackerValue(syntax, value){
  const v=String(value).trim(); if(!v) return null;
  const sintaxe = syntax.trim().endsWith(':') ? syntax.trim() : syntax.trim()+':';
  const cmd = sintaxe+' '+v;
  const r = await apiFetch(API+'/_cmd',{method:'POST',body:JSON.stringify({text:cmd})});
  return r.output;
}

// input na própria card do Tracker
async function _tkLog(syntax){
  const inp=document.getElementById('tk-val'); if(!inp) return;
  const v=inp.value.trim(); if(!v){ toast('digite um valor',true); return; }
  try{
    const out=await logTrackerValue(syntax, v);
    toast('✓ '+(out||'registrado').slice(0,60));
    inp.value='';
    if(_curRes) loadAndRender(_curRes.kind, _curRes.name);
  }catch(e){ toast('erro: '+e.message, true); }
}

// ── Check-in visual (form da rotina configurada) ──
async function openCheckin(grupo){
  let tks=[], gls=[];
  try{
    [tks, gls] = await Promise.all([
      apiFetch(API+'/Tracker').catch(()=>[]),
      apiFetch(API+'/Goal').catch(()=>[]),
    ]);
  }catch(_){}
  tks=tks.filter(t=>((t.labels||{}).grupo===grupo) && (t.spec?t.spec.active!==false:true));
  gls=gls.filter(g=>(g.labels||{}).grupo===grupo);
  const rows = tks.map(t=>{
    const unit=t.spec&&t.spec.unit?' ('+esc(t.spec.unit)+')':'';
    const last=(t.status&&t.status.ultimo_valor!=null)?'último: '+esc(String(t.status.ultimo_valor)):'valor';
    const syn=(t.spec&&t.spec.syntax)||t.name+':';
    return `<div class="ck-row">
      <label>${esc(t.name)}${unit}</label>
      <input class="ck-in" data-syntax="${esc(syn)}" type="text" inputmode="decimal" placeholder="${last}">
    </div>`;
  }).join('') || '<div class="sv-empty">nenhum tracker no grupo "'+esc(grupo)+'"</div>';
  const metas = gls.length ? `<div class="ck-goals">🎯 ${gls.map(g=>esc(g.name)).join(', ')}</div>` : '';
  const m=document.createElement('div'); m.className='diff-modal';
  m.innerHTML=`<div class="diff-box" style="max-width:460px">
    <h3>📝 Check-in · ${esc(grupo)}</h3>
    <div class="diff-body">${rows}${metas}</div>
    <div class="diff-foot">
      <button class="btn" onclick="this.closest('.diff-modal').remove()">Cancelar</button>
      <button class="btn" style="border-color:var(--green);color:var(--green)" onclick="_submitCheckin(this)">✓ Registrar</button>
    </div>
  </div>`;
  document.body.appendChild(m);
  m.addEventListener('click',e=>{if(e.target===m)m.remove();});
  m.querySelector('.ck-in')?.focus();
}

async function _submitCheckin(btn){
  const modal=btn.closest('.diff-modal');
  const inputs=[...modal.querySelectorAll('.ck-in')];
  let n=0, erros=0;
  for(const inp of inputs){
    const v=inp.value.trim(); if(!v) continue;
    try{ await logTrackerValue(inp.dataset.syntax, v); n++; }
    catch(_){ erros++; }
  }
  modal.remove();
  toast(n+' valor(es) registrado(s)'+(erros?` · ${erros} erro(s)`:''));
  if(document.body.dataset.view==='status') loadStatus();
}

// ── Ações por Kind (abstração da API) — diretriz: todo kind tem GUI ──
async function kindCmd(cmd, refresh){
  try{
    const r=await apiFetch(API+'/_cmd',{method:'POST',body:JSON.stringify({text:cmd})});
    toast(String(r.output||'ok').slice(0,80));
    if(refresh) refresh();
    return r.output;
  }catch(e){ toast('erro: '+e.message, true); }
}
function _afterKindAction(kind, name){
  if(_curRes && _curRes.kind===kind && _curRes.name===name) loadAndRender(kind, name);
  if(document.body.dataset.view==='status') loadStatus();
  if(document.body.dataset.view==='graph') loadGraph();
}
function timerStart(name){ kindCmd('/timer start '+name, ()=>_afterKindAction('Timer',name)); }
function timerStop(name){ kindCmd('/timer finish '+name, ()=>_afterKindAction('Timer',name)); }
function goalCheck(name){ kindCmd('/goal check '+name, ()=>_afterKindAction('Goal',name)); }

// botões de ação conforme o kind (usado na card e no status)
function kindActionsHtml(r){
  const n=escJs(r.name);
  if(r.kind==='Timer'){
    const running=(r.status&&r.status.state)==='running';
    return running
      ? `<button class="btn" style="border-color:var(--red);color:var(--red)" onclick="timerStop('${n}')">⏹ Parar</button>`
      : `<button class="btn" style="border-color:var(--green);color:var(--green)" onclick="timerStart('${n}')">▶ Iniciar</button>`;
  }
  if(r.kind==='Routine') return `<button class="btn" style="border-color:var(--green);color:var(--green)" onclick="runRoutine('${n}')">▶ Executar</button>`;
  if(r.kind==='Goal') return `<button class="btn" style="border-color:var(--blue);color:var(--blue)" onclick="goalCheck('${n}')">🎯 Recalcular</button>`;
  if(r.kind==='Repo') return `<button class="btn" style="border-color:var(--purple);color:var(--purple)" onclick="aiInsight('repo','${n}')">🧠 Insight</button>`;
  return '';
}

// ── Sidebar drawer (mobile) ──
function toggleSidebar(force) {
  const open = force===undefined ? !document.body.classList.contains('sb-open') : force;
  document.body.classList.toggle('sb-open', open);
}

// ── Graph state ──
const GV = {
  NW: 178, NH: 80, COL: 216, PAD: 36, GAP: 10,
  data: {}, // kind → [resource]
  pos: {},  // 'kind/name' → {x,y,w,h}  (effective render positions)
  userPos: {}, // 'kind/name' → {x,y}  (manual drag overrides, persisted)
  sel: null,
  drag: null,  // {key, dx, dy, moved} while moving a node
  conn: null,  // {srcKey, srcKind, srcName, x1, y1} while drawing a connection
};
try { GV.userPos = JSON.parse(localStorage.getItem('atlas_gv_pos')||'{}'); } catch(_) { GV.userPos = {}; }
function gvSavePos() { try { localStorage.setItem('atlas_gv_pos', JSON.stringify(GV.userPos)); } catch(_){} }
const KIND_COLOR = {
  Tracker:'#58a6ff', Goal:'#3fb950', Routine:'#d29922', Alarm:'#e3b341',
  Timer:'#bc8cff', Doc:'#8b949e', Idea:'#f78166', Task:'#39d353',
  RoutineRequest:'#ff9f43', CheckIn:'#00cec9',
};
function gvColor(k) { return KIND_COLOR[k]||'#8b949e'; }
function escJs(s){ return String(s).replace(/\\/g,'\\\\').replace(/'/g,"\\'").replace(/"/g,'&quot;'); }

// ── Load ──
async function loadGraph() {
  const svg = document.getElementById('gv-canvas');
  svg.innerHTML = '<text x="20" y="40" fill="#8b949e" font-family="monospace" font-size="12">carregando…</text>';
  try {
    const kinds = await apiFetch(API+'/');
    const loaded = {};
    await Promise.all(Object.keys(kinds).map(async k => {
      loaded[k] = await apiFetch(API+'/'+k).catch(()=>[]);
    }));
    GV.data = loaded;
    // populate filter
    const sel = document.getElementById('gv-kind-filter');
    const prev = sel.value;
    sel.innerHTML = '<option value="">Todos os Kinds</option>' +
      Object.keys(loaded).sort().map(k=>
        `<option value="${k}"${k===prev?' selected':''}>${k} (${loaded[k].length})</option>`
      ).join('');
    gvRenderPalette();
    renderGraph();
  } catch(e) {
    svg.innerHTML = `<text x="20" y="40" fill="#f85149" font-family="monospace" font-size="12">erro: ${esc(e.message)}</text>`;
  }
}

// ── Layout (swim-lane default, manual drag overrides) ──
function gvLayout() {
  const fk = document.getElementById('gv-kind-filter').value;
  let kinds = Object.keys(GV.data).sort();
  if (fk) kinds = kinds.filter(k=>k===fk);
  GV.pos = {};
  kinds.forEach((kind, ci) => {
    (GV.data[kind]||[]).forEach((r, ri) => {
      const key = kind+'/'+r.name;
      const u = GV.userPos[key];
      const x = u ? u.x : GV.PAD + ci * GV.COL;
      const y = u ? u.y : GV.PAD + 30 + ri * (GV.NH + GV.GAP);
      GV.pos[key] = {x, y, w:GV.NW, h:GV.NH};
    });
  });
  return kinds;
}

// reorganiza tudo em colunas por Kind, descartando posições manuais
function gvAutoLayout() {
  GV.userPos = {}; gvSavePos(); renderGraph();
  toast('blocos reorganizados por Kind');
}

// ── Edge inference (rel = como desfazer a relação) ──
function gvEdges(kinds) {
  const edges = [];
  function pos(k,n){ return GV.pos[k+'/'+n]; }
  kinds.forEach(kind => {
    (GV.data[kind]||[]).forEach(r => {
      const s = pos(kind, r.name); if (!s) return;
      if (kind==='Goal' && r.spec?.tracker) {
        const t = pos('Tracker', r.spec.tracker);
        if (t) edges.push({s, t, cls:'edge-tracker',
          rel:{kind, name:r.name, scope:'spec', key:'tracker', target:r.spec.tracker}});
      }
      if (r.labels?.routine) {
        const t = pos('Routine', r.labels.routine);
        if (t) edges.push({s, t, cls:'edge-routine',
          rel:{kind, name:r.name, scope:'labels', key:'routine', target:r.labels.routine}});
      }
    });
  });
  // grupo clusters — connect first member to all others
  const grupos = {};
  kinds.forEach(k => (GV.data[k]||[]).forEach(r => {
    if (r.labels?.grupo) {
      const g=r.labels.grupo;
      if (!grupos[g]) grupos[g]=[];
      grupos[g].push({p:GV.pos[k+'/'+r.name], kind:k, name:r.name});
    }
  }));
  Object.entries(grupos).forEach(([g, members]) => {
    for (let i=1; i<members.length; i++) {
      const a=members[0], b=members[i];
      if (a.p && b.p) edges.push({s:a.p, t:b.p, cls:'edge-grupo',
        rel:{kind:b.kind, name:b.name, scope:'labels', key:'grupo', target:g}});
    }
  });
  return edges;
}

// ── Render SVG ──
function renderGraph() {
  const kinds = gvLayout();
  const edges = gvEdges(kinds);
  const NW=GV.NW, NH=GV.NH;
  const freeMode = Object.keys(GV.userPos).length > 0;

  // canvas dims from real node positions
  let maxX=760, maxY=480;
  Object.values(GV.pos).forEach(p => { maxX=Math.max(maxX, p.x+NW); maxY=Math.max(maxY, p.y+NH); });
  const W = maxX + GV.PAD, H = maxY + GV.PAD;
  const svg = document.getElementById('gv-canvas');
  svg.setAttribute('width', W); svg.setAttribute('height', H);

  // edges (with invisible hit-area for deletion)
  let esvg = '';
  edges.forEach((e,i) => {
    const {s,t,cls} = e;
    const x1=s.x+NW, y1=s.y+NH/2, x2=t.x, y2=t.y+NH/2;
    const mx=(x1+x2)/2;
    const d=`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`;
    const meta = e.rel ? ` data-rel='${esc(JSON.stringify(e.rel))}'` : '';
    esvg += `<path class="gv-edge-hit" d="${d}"${e.rel?` onclick="gvEdgeClick(${i})"`:''}></path>`;
    esvg += `<path class="gv-edge ${cls}" d="${d}" marker-end="url(#arr)"${meta}></path>`;
  });
  GV._edges = edges;

  // column headers — only in pristine swim-lane mode
  let hsvg = '';
  if (!freeMode) {
    kinds.forEach((k,ci) => {
      const cx = GV.PAD + ci*GV.COL + NW/2;
      const c = gvColor(k);
      hsvg += `<text x="${cx}" y="${GV.PAD+14}" text-anchor="middle" font-family="monospace" font-size="10" font-weight="700" fill="${c}" letter-spacing=".6">${esc(k).toUpperCase()}</text>`;
      hsvg += `<line x1="${GV.PAD+ci*GV.COL+8}" y1="${GV.PAD+20}" x2="${GV.PAD+ci*GV.COL+NW-8}" y2="${GV.PAD+20}" stroke="${c}" stroke-width="1" opacity=".25"/>`;
    });
  }

  // nodes (with in/out ports)
  let nsvg = '';
  kinds.forEach(kind => {
    const c = gvColor(kind);
    (GV.data[kind]||[]).forEach(r => {
      const key=kind+'/'+r.name, p=GV.pos[key]; if(!p) return;
      const {x,y}=p, isSel=GV.sel===key;
      const stroke=isSel?'#58a6ff':(c+'44');
      const sw=isSel?2:1;
      const hasStat=r.status&&Object.keys(r.status).length>0;
      const chipHtml = Object.entries(r.labels||{}).slice(0,2).map(([k,v])=>
        `<span style="background:#0d1117;border:1px solid #30363d;border-radius:2px;padding:0 4px;font-size:8px;color:#8b949e;margin-right:3px">${esc(k)}=${esc(v)}</span>`
      ).join('');
      const specPrev = Object.entries(r.spec||{}).slice(0,2).map(([k,v])=>
        `${k}=${String(v).slice(0,8)}`
      ).join(' · ');
      const kj=escJs(kind), nj=escJs(r.name);
      nsvg += `
<g class="gv-node" data-key="${esc(key)}" data-kind="${esc(kind)}" data-name="${esc(r.name)}">
  <rect x="${x}" y="${y}" width="${NW}" height="${NH}" rx="7"
    fill="#161b22" stroke="${stroke}" stroke-width="${sw}" class="gv-node-body"/>
  ${hasStat?`<circle cx="${x+NW-12}" cy="${y+12}" r="4" fill="#3fb950" opacity=".9"/>`:''}
  <text x="${x+10}" y="${y+15}" font-size="9" fill="${c}" font-family="monospace" font-weight="700" letter-spacing=".4" style="pointer-events:none">${esc(kind).toUpperCase()}</text>
  <text x="${x+10}" y="${y+33}" font-size="12" fill="${isSel?'#58a6ff':'#c9d1d9'}" font-family="monospace" font-weight="600" style="pointer-events:none">${esc(r.name.length>19?r.name.slice(0,18)+'…':r.name)}</text>
  <foreignObject x="${x+8}" y="${y+39}" width="${NW-16}" height="18" style="pointer-events:none">
    <div xmlns="http://www.w3.org/1999/xhtml" style="overflow:hidden;white-space:nowrap">${chipHtml}</div>
  </foreignObject>
  ${specPrev?`<text x="${x+10}" y="${y+70}" font-size="9" fill="#484f58" font-family="monospace" style="pointer-events:none">${esc(specPrev.slice(0,26))}</text>`:''}
  <circle class="gv-port gv-port-in"  cx="${x}"    cy="${y+NH/2}" r="5" data-port="in"  data-key="${esc(key)}"></circle>
  <circle class="gv-port gv-port-out" cx="${x+NW}" cy="${y+NH/2}" r="5" data-port="out" data-key="${esc(key)}" data-kind="${esc(kind)}" data-name="${esc(r.name)}"></circle>
</g>`;
    });
  });

  // temp connection line while dragging
  let tsvg = '';
  if (GV.conn && GV.conn.cx!=null) {
    tsvg = `<path class="gv-edge-temp" d="M${GV.conn.x1},${GV.conn.y1} C${(GV.conn.x1+GV.conn.cx)/2},${GV.conn.y1} ${(GV.conn.x1+GV.conn.cx)/2},${GV.conn.cy} ${GV.conn.cx},${GV.conn.cy}"/>`;
  }

  svg.innerHTML = `<defs>
  <marker id="arr" markerWidth="7" markerHeight="7" refX="5" refY="3.5" orient="auto">
    <path d="M0,0 L0,7 L7,3.5 z" fill="#484f58"/>
  </marker>
</defs>
${hsvg}${esvg}${nsvg}${tsvg}`;
}

// ── Select node ──
function gvSelect(kind, name) {
  GV.sel = kind+'/'+name;
  renderGraph();
  const r = (GV.data[kind]||[]).find(x=>x.name===name);
  epOpen(r||{}, kind, name, false);
}

// ── Interaction: drag blocks + draw connections ──
function gvCoords(evt) {
  const svg = document.getElementById('gv-canvas');
  const rect = svg.getBoundingClientRect();
  return { x: evt.clientX - rect.left, y: evt.clientY - rect.top };
}

let _gvRaf = 0;
function gvRender() { if (_gvRaf) return; _gvRaf = requestAnimationFrame(()=>{ _gvRaf=0; renderGraph(); }); }

function gvMouseDown(evt) {
  const port = evt.target.closest('.gv-port');
  if (port && port.dataset.port==='out') {
    const key=port.dataset.key, p=GV.pos[key]; if(!p) return;
    GV.conn = {srcKey:key, srcKind:port.dataset.kind, srcName:port.dataset.name,
               x1:p.x+GV.NW, y1:p.y+GV.NH/2, cx:p.x+GV.NW, cy:p.y+GV.NH/2};
    _gvShowHint('arraste até outro bloco para conectar');
    evt.preventDefault();
    return;
  }
  const g = evt.target.closest('.gv-node');
  if (g) {
    const key=g.dataset.key, p=GV.pos[key]; if(!p) return;
    const c=gvCoords(evt);
    GV.drag={key, ox:c.x-p.x, oy:c.y-p.y, kind:g.dataset.kind, name:g.dataset.name, moved:false, sx:c.x, sy:c.y};
    g.classList.add('dragging');
    evt.preventDefault();
  }
}

function gvMouseMove(evt) {
  if (GV.conn) {
    const c=gvCoords(evt);
    GV.conn.cx=c.x; GV.conn.cy=c.y;
    document.querySelectorAll('.gv-node.conn-target').forEach(n=>n.classList.remove('conn-target'));
    const over=evt.target.closest('.gv-node');
    if (over && over.dataset.key!==GV.conn.srcKey) over.classList.add('conn-target');
    gvRender();
    return;
  }
  if (GV.drag) {
    const c=gvCoords(evt);
    if (Math.abs(c.x-GV.drag.sx)>3||Math.abs(c.y-GV.drag.sy)>3) GV.drag.moved=true;
    GV.userPos[GV.drag.key]={x:Math.max(4,c.x-GV.drag.ox), y:Math.max(4,c.y-GV.drag.oy)};
    gvRender();
  }
}

function gvMouseUp(evt) {
  if (GV.conn) {
    const over=evt.target.closest('.gv-node');
    const conn=GV.conn; GV.conn=null;
    _hideHint();
    document.querySelectorAll('.gv-node.conn-target').forEach(n=>n.classList.remove('conn-target'));
    if (over && over.dataset.key!==conn.srcKey) {
      gvConnect(conn.srcKind, conn.srcName, over.dataset.kind, over.dataset.name);
    } else { renderGraph(); }
    return;
  }
  if (GV.drag) {
    const d=GV.drag; GV.drag=null;
    document.querySelectorAll('.gv-node.dragging').forEach(n=>n.classList.remove('dragging'));
    if (d.moved) { gvSavePos(); renderGraph(); }
    else { gvSelect(d.kind, d.name); }
  }
}

// connection-hint tooltip
function _gvShowHint(txt) {
  _hideHint();
  const wrap=document.getElementById('gv-canvas-wrap');
  const h=document.createElement('div'); h.className='gv-hint-conn'; h.id='gv-hint'; h.textContent=txt;
  wrap.parentNode.appendChild(h);
}
function _hideHint(){ document.getElementById('gv-hint')?.remove(); }

// ── Connection resolver: traduz uma ligação visual em patch de manifesto ──
async function gvConnect(sk, sn, dk, dn) {
  let patch=null, desc='', extra=null;
  if (sk==='Goal' && dk==='Tracker') {
    patch={kind:'Goal', name:sn, spec:{tracker:dn}};
    desc=`Goal '${sn}' agora monitora Tracker '${dn}'`;
  } else if (dk==='Routine') {
    patch={kind:sk, name:sn, labels:{routine:dn}};
    desc=`'${sk}/${sn}' vinculado à Routine '${dn}'`;
  } else if (sk==='Tracker' && dk==='Goal') {
    // ligação invertida: a meta passa a monitorar este tracker
    patch={kind:'Goal', name:dn, spec:{tracker:sn}};
    desc=`Goal '${dn}' agora monitora Tracker '${sn}'`;
  } else {
    // fallback: agrupar via labels.grupo
    const D=(GV.data[dk]||[]).find(r=>r.name===dn)||{};
    const g = D.labels?.grupo || dn;
    patch={kind:sk, name:sn, labels:{grupo:g}};
    if (!D.labels?.grupo) extra={kind:dk, name:dn, labels:{grupo:g}};
    desc=`'${sk}/${sn}' entrou no grupo '${g}'`;
  }
  try {
    if (extra) await gvApplyPatch(extra);
    await gvApplyPatch(patch);
    toast('✓ '+desc);
    await loadGraph();
  } catch(e) { toast('erro: '+e.message, true); }
}

// faz merge do patch no recurso atual e PUT na API
async function gvApplyPatch(patch) {
  const cur = (GV.data[patch.kind]||[]).find(r=>r.name===patch.name)
    || await apiFetch(API+'/'+patch.kind+'/'+patch.name).catch(()=>null);
  const labels = {...(cur?.labels||{}), ...(patch.labels||{})};
  const spec   = {...(cur?.spec||{}),   ...(patch.spec||{})};
  const status = {...(cur?.status||{})};
  await apiFetch(API+'/'+patch.kind+'/'+patch.name, {method:'PUT', body:JSON.stringify({labels,spec,status})});
}

// clicar numa conexão remove a relação
async function gvEdgeClick(i) {
  const e=GV._edges?.[i]; if(!e||!e.rel) return;
  const {kind,name,scope,key}=e.rel;
  if(!confirm(`Remover conexão ${scope}.${key} de ${kind}/${name}?`)) return;
  const cur=(GV.data[kind]||[]).find(r=>r.name===name); if(!cur) return;
  const labels={...(cur.labels||{})}, spec={...(cur.spec||{})}, status={...(cur.status||{})};
  if(scope==='labels') delete labels[key]; else delete spec[key];
  try {
    await apiFetch(API+'/'+kind+'/'+name,{method:'PUT',body:JSON.stringify({labels,spec,status})});
    toast('conexão removida');
    await loadGraph();
  } catch(err){ toast('erro: '+err.message,true); }
}

// ── Palette: um botão por Kind ──
function gvRenderPalette() {
  const pal=document.getElementById('gv-palette');
  if(!pal) return;
  const kinds=[...new Set([...Object.keys(_MANIFEST_TPL), ...Object.keys(GV.data)])]
    .filter(k=>k!=='Diff').sort();
  pal.innerHTML='<div class="gv-pal-ttl">＋ Blocos</div>'+kinds.map(k=>
    `<button class="gv-pal-btn" onclick="gvNewKind('${escJs(k)}')"><span class="gv-pal-dot" style="background:${gvColor(k)}"></span>${esc(k)}</button>`
  ).join('');
}

function gvNewKind(kind) {
  gvNew();
  const sel=document.getElementById('ep-kind');
  if(![...sel.options].some(o=>o.value===kind)) sel.add(new Option(kind,kind));
  sel.value=kind; epKindTpl();
  document.getElementById('ep-name').focus();
}

// ── Edit panel ──
let _epCtx = null; // {kind, name, isNew}

function epPopulateKindSel(selectedKind) {
  const sel = document.getElementById('ep-kind');
  const kinds = [...new Set([...Object.keys(_MANIFEST_TPL), ...Object.keys(GV.data)])].sort();
  sel.innerHTML = '<option value="">— selecione —</option>' +
    kinds.map(k=>`<option value="${k}"${k===selectedKind?' selected':''}>${k}</option>`).join('') +
    (selectedKind && !kinds.includes(selectedKind)
      ? `<option value="${selectedKind}" selected>${selectedKind}</option>` : '');
}

function epOpen(r, kind, name, isNew) {
  _epCtx = {kind, name, isNew};
  document.getElementById('ep-ttl').textContent = isNew ? 'Novo Recurso' : kind+'/'+name;
  document.getElementById('ep-del').style.display = isNew ? 'none' : '';
  epPopulateKindSel(kind);
  const nameEl = document.getElementById('ep-name');
  nameEl.value = name||''; nameEl.readOnly = !isNew;
  nameEl.style.opacity = isNew ? '1' : '.55';
  epRenderForm(kind, r);
  document.getElementById('ep').classList.add('open');
}

function epClose() {
  document.getElementById('ep').classList.remove('open');
  GV.sel = null; renderGraph();
}

function gvNew() {
  GV.sel = null; renderGraph();
  epPopulateKindSel('');
  document.getElementById('ep-ttl').textContent = 'Novo Recurso';
  document.getElementById('ep-del').style.display = 'none';
  const nameEl = document.getElementById('ep-name');
  nameEl.value = ''; nameEl.readOnly = false; nameEl.style.opacity = '1';
  epRenderForm('', {});
  _epCtx = {kind:'', name:'', isNew:true};
  document.getElementById('ep').classList.add('open');
  nameEl.focus();
}

function epKindTpl() {
  if (!_epCtx?.isNew) return;
  const k = document.getElementById('ep-kind').value;
  epRenderForm(k, _MANIFEST_TPL[k] || {});
}

// ── Form dirigido por schema: controles visuais por campo ──
function epRenderForm(kind, r) {
  const schema = _KIND_SCHEMA[kind];
  const labels = r.labels||{}, spec = r.spec||{}, status = r.status||{};

  // labels: campos do schema + extras freeform
  let lblHtml=''; const lblKeys=new Set();
  if (schema) for (const lf of schema.labels) {
    lblKeys.add(lf.k);
    lblHtml += epTypedHtml('labels', lf.k, labels[lf.k], {type:'text', label:lf.label, hint:lf.hint});
  }
  for (const [k,v] of Object.entries(labels)) if(!lblKeys.has(k)) lblHtml += epKVHtml('labels',k,String(v));
  document.getElementById('ep-labels').innerHTML = lblHtml;

  // spec: campos tipados do schema + extras freeform
  let specHtml=''; const specKeys=new Set();
  if (schema) for (const sf of schema.spec) {
    specKeys.add(sf.k);
    specHtml += epTypedHtml('spec', sf.k, spec[sf.k], sf);
  }
  for (const [k,v] of Object.entries(spec)) if(!specKeys.has(k))
    specHtml += epKVHtml('spec', k, typeof v==='object'?JSON.stringify(v):String(v));
  document.getElementById('ep-spec').innerHTML = specHtml;

  // status: freeform (gerenciado pelo sistema)
  document.getElementById('ep-status').innerHTML =
    Object.entries(status).map(([k,v])=>epKVHtml('status',k,String(v))).join('');
}

// gera o controle visual certo conforme o tipo do campo
function epTypedHtml(scope, key, value, def) {
  const t = def.type||'text';
  const hint = def.hint ? `<div class="ep-hint">${esc(def.hint)}</div>` : '';
  const lbl = `<label>${esc(def.label||key)} <span>${scope}.${esc(key)}</span></label>`;
  let ctrl='';
  if (t==='bool') {
    const on = value===true || value==='true';
    ctrl = `<div class="ep-toggle${on?' on':''}" data-scope="${scope}" data-key="${esc(key)}" data-type="bool" onclick="epToggle(this)">
      <div class="tg-track"><div class="tg-knob"></div></div>
      <span class="tg-label">${on?'ativado':'desativado'}</span></div>`;
  } else if (t==='select') {
    const cur = value==null?'':String(value);
    const opts = def.opts||[];
    const all = (opts.includes(cur)||cur==='') ? opts : [...opts, cur];
    ctrl = `<div class="ep-btngroup" data-scope="${scope}" data-key="${esc(key)}" data-type="select">
      ${all.map(o=>`<button type="button" class="${o===cur?'sel':''}" onclick="epPick(this)">${esc(o)}</button>`).join('')}</div>`;
  } else if (t==='number') {
    ctrl = `<input type="number" data-scope="${scope}" data-key="${esc(key)}" data-type="number" value="${esc(value==null?'':String(value))}">`;
  } else if (t==='area') {
    ctrl = `<textarea data-scope="${scope}" data-key="${esc(key)}" data-type="text" rows="3">${esc(value==null?'':String(value))}</textarea>`;
  } else if (t==='time') {
    ctrl = `<input type="time" data-scope="${scope}" data-key="${esc(key)}" data-type="text" value="${esc(value==null?'':String(value))}">`;
  } else if (t==='cron') {
    ctrl = _cronBuilderHtml(scope, key, value==null?'':String(value));
  } else {
    ctrl = `<input type="text" data-scope="${scope}" data-key="${esc(key)}" data-type="text" value="${esc(value==null?'':String(value))}">`;
  }
  return `<div class="ep-typed">${lbl}${ctrl}${hint}</div>`;
}

// ── Cron builder visual (presets + texto editável + descrição legível) ──
const _CRON_PRESETS = [
  ['Todo dia 9h','0 9 * * *'], ['Dias úteis 9h','0 9 * * 1-5'],
  ['Semanal (seg 10h)','0 10 * * 1'], ['Todo dia 21h','0 21 * * *'],
  ['A cada 1h','@every 1h'], ['A cada 15min','@every 15m'],
];
function _cronBuilderHtml(scope, key, value){
  const presets = _CRON_PRESETS.map(([l,v])=>
    `<button type="button" class="${v===value?'sel':''}" onclick="_cronSet(this,'${v}')">${esc(l)}</button>`).join('');
  return `<div class="cron-builder">
    <div class="cron-presets">${presets}</div>
    <input type="text" class="cron-text" data-scope="${scope}" data-key="${esc(key)}" data-type="text"
      value="${esc(value)}" placeholder="0 9 * * *" oninput="_cronSync(this)">
    <div class="cron-human">${esc(_cronHuman(value))}</div>
  </div>`;
}
function _cronSet(btn, expr){
  const b=btn.closest('.cron-builder');
  b.querySelectorAll('.cron-presets button').forEach(x=>x.classList.remove('sel'));
  btn.classList.add('sel');
  const inp=b.querySelector('.cron-text'); inp.value=expr;
  _cronSync(inp);
}
function _cronSync(inp){
  const b=inp.closest('.cron-builder');
  b.querySelector('.cron-human').textContent=_cronHuman(inp.value);
  b.querySelectorAll('.cron-presets button').forEach(x=>x.classList.toggle('sel', x.getAttribute('onclick').includes("'"+inp.value+"'")));
  if(typeof _formToJson==='function' && _edMode==='form') _formToJson();
}
function _cronHuman(expr){
  expr=(expr||'').trim();
  if(!expr) return 'sem agenda';
  if(expr.startsWith('@every ')) return 'a cada '+expr.slice(7);
  if(expr.startsWith('@daily ')) return 'todo dia às '+expr.slice(7);
  const p=expr.split(/\s+/); if(p.length!==5) return '⚠️ formato inválido';
  const [mi,ho,dm,mo,dw]=p;
  const dias={'0':'dom','1':'seg','2':'ter','3':'qua','4':'qui','5':'sex','6':'sáb','7':'dom'};
  let quando='';
  if(ho!=='*'&&mi!=='*') quando='às '+ho.padStart(2,'0')+':'+mi.padStart(2,'0');
  else if(mi.startsWith('*/')) quando='a cada '+mi.slice(2)+'min';
  else quando='min '+mi+' h '+ho;
  let q2='';
  if(dw!=='*'){ q2=' ('+dw.split(',').map(d=>d.includes('-')?d.split('-').map(x=>dias[x]||x).join('-'):(dias[d]||d)).join(',')+')'; }
  else if(dm!=='*'){ q2=' (dia '+dm+')'; }
  else q2=' (todo dia)';
  return quando+q2;
}

function epToggle(el) {
  const on = el.classList.toggle('on');
  el.querySelector('.tg-label').textContent = on?'ativado':'desativado';
}
function epPick(btn) {
  btn.parentNode.querySelectorAll('button').forEach(b=>b.classList.remove('sel'));
  btn.classList.add('sel');
}

function epKVHtml(sec, k='', v='') {
  return `<div class="ep-kv">
    <input type="text" placeholder="chave" value="${esc(k)}">
    <input type="text" placeholder="valor" value="${esc(v)}">
    <button class="ep-rm" onclick="this.closest('.ep-kv').remove()">✕</button>
  </div>`;
}

function epAddKV(sec) {
  document.getElementById('ep-'+sec).insertAdjacentHTML('beforeend', epKVHtml(sec));
}

// coleta valores: controles tipados + KV freeform
function epCollect(sec) {
  const obj = {};
  const root = document.getElementById('ep-'+sec);
  // controles visuais tipados
  root.querySelectorAll('[data-scope="'+sec+'"]').forEach(el => {
    const k = el.dataset.key, t = el.dataset.type;
    if (t==='bool') obj[k] = el.classList.contains('on');
    else if (t==='select') { const s=el.querySelector('button.sel'); if(s) obj[k]=s.textContent; }
    else if (t==='number') { const v=el.value.trim(); if(v!=='') obj[k]=isNaN(Number(v))?v:Number(v); }
    else { const v=el.value.trim(); if(v!=='') obj[k]=v; }
  });
  // pares chave-valor livres
  root.querySelectorAll('.ep-kv').forEach(row => {
    const ins = row.querySelectorAll('input');
    const k=ins[0].value.trim(), v=ins[1].value.trim();
    if (!k) return;
    if (v==='true') obj[k]=true;
    else if (v==='false') obj[k]=false;
    else if (v!==''&&!isNaN(Number(v))) obj[k]=Number(v);
    else obj[k]=v;
  });
  return obj;
}

async function epSave() {
  const kind = document.getElementById('ep-kind').value;
  const name = (_epCtx?.isNew ? document.getElementById('ep-name').value.trim() : _epCtx?.name)||'';
  if (!kind||!name) { toast('Kind e Name são obrigatórios', true); return; }
  const body = {labels:epCollect('labels'), spec:epCollect('spec'), status:epCollect('status')};
  try {
    await apiFetch(API+'/'+kind+'/'+name, {method:'PUT', body:JSON.stringify(body)});
    toast('✓ '+kind+'/'+name+' salvo');
    epClose();
    await loadGraph();
    // sync explorer tree
    allKinds = await apiFetch(API+'/').catch(()=>allKinds);
    for (const k of Object.keys(treeOpen)) {
      if (treeOpen[k]) treeData[k] = await apiFetch(API+'/'+k).catch(()=>[]);
    }
    updateStatus(); renderTree();
  } catch(e) { toast('erro: '+e.message, true); }
}

async function epDelete() {
  const {kind, name} = _epCtx||{};
  if (!kind||!name||!confirm('Deletar '+kind+'/'+name+'?')) return;
  try {
    const h={}; if(TOKEN) h['Authorization']='Bearer '+TOKEN;
    const r=await fetch(API+'/'+kind+'/'+name,{method:'DELETE',headers:h});
    if (!r.ok) throw new Error(await r.text());
    toast('deletado: '+kind+'/'+name);
    epClose();
    await loadGraph();
    allKinds=await apiFetch(API+'/').catch(()=>allKinds);
    for(const k of Object.keys(treeOpen)) if(treeOpen[k]) treeData[k]=await apiFetch(API+'/'+k).catch(()=>[]);
    updateStatus(); renderTree();
  } catch(e) { toast('erro: '+e.message, true); }
}

document.getElementById('gv-kind-filter').addEventListener('change', renderGraph);
(function(){
  const c=document.getElementById('gv-canvas');
  if(c){
    // mouse
    c.addEventListener('mousedown', gvMouseDown);
    window.addEventListener('mousemove', gvMouseMove);
    window.addEventListener('mouseup', gvMouseUp);
    // toque (celular): converte para o mesmo fluxo, usando elementFromPoint
    c.addEventListener('touchstart', e=>{
      const t=e.touches[0]; if(!t) return;
      gvMouseDown({clientX:t.clientX, clientY:t.clientY, target:e.target, preventDefault:()=>e.preventDefault()});
      if (GV.drag||GV.conn) e.preventDefault();  // segura o scroll só ao interagir com bloco/porta
    }, {passive:false});
    window.addEventListener('touchmove', e=>{
      if(!GV.drag && !GV.conn) return;
      const t=e.touches[0]; if(!t) return;
      e.preventDefault();
      const el=document.elementFromPoint(t.clientX, t.clientY);
      gvMouseMove({clientX:t.clientX, clientY:t.clientY, target:el||e.target, preventDefault:()=>{}});
    }, {passive:false});
    window.addEventListener('touchend', e=>{
      if(!GV.drag && !GV.conn) return;
      const t=e.changedTouches[0];
      const el=t?document.elementFromPoint(t.clientX, t.clientY):document.body;
      gvMouseUp({clientX:t?t.clientX:0, clientY:t?t.clientY:0, target:el||document.body, preventDefault:()=>{}});
    }, {passive:false});
  }
})();

// ── Painel de edição redimensionável (desktop) ──
(function(){
  const h=document.getElementById('ep-resize'), ep=document.getElementById('ep');
  if(!h||!ep) return;
  const saved=localStorage.getItem('atlas_ep_w');
  if(saved && window.innerWidth>760) ep.style.width=saved+'px';
  let drag=false;
  const start=e=>{ drag=true; h.classList.add('drag'); e.preventDefault(); };
  const move=e=>{
    if(!drag) return;
    const cx=e.clientX ?? (e.touches&&e.touches[0]?.clientX);
    if(cx==null) return;
    const w=Math.max(260, Math.min(660, window.innerWidth - cx));
    ep.style.width=w+'px';
  };
  const end=()=>{ if(!drag) return; drag=false; h.classList.remove('drag');
    localStorage.setItem('atlas_ep_w', parseInt(ep.style.width)||320); };
  h.addEventListener('mousedown', start);
  window.addEventListener('mousemove', move);
  window.addEventListener('mouseup', end);
  h.addEventListener('touchstart', start, {passive:false});
  window.addEventListener('touchmove', move, {passive:false});
  window.addEventListener('touchend', end);
})();

// ── Boot ──
cliAppend('Atlas CLI · Tab completa · ↑↓ histórico · Ctrl+K foca · Ctrl+L limpa', 'cli-sep');
cliAppend('─'.repeat(40), 'cli-sep');

if (TOKEN) { init(); } else { showTokenOverlay(); }

// restore view (default: status — ver o que está rodando ao abrir)
(function(){ const v=localStorage.getItem('atlas_view')||'status'; setView(v); })();

// Auto-refresh kinds a cada 20s
setInterval(async () => {
  try {
    allKinds = await apiFetch(API+'/');
    updateStatus(); renderTree();
  } catch(_){}
}, 20000);
