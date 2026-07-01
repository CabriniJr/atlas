/* Home / landing hub (repaginação do front).
 * Três zonas: 🤖 Construir com IA (atlas-builder), 📊 O que existe (rastreio),
 * 🎨 Quadro branco (galeria dos renders especializados).
 * Explorer/Graph/Status viram camada secundária (menu ☰ Mais).
 */

// ── Navegação: dropdown "Mais" ────────────────────────────────────────────────
function toggleNavMenu(force) {
  const dd = document.getElementById('nav-dropdown');
  if (!dd) return;
  const open = force === undefined ? !dd.classList.contains('open') : force;
  dd.classList.toggle('open', open);
}
document.addEventListener('click', (e) => {
  const menu = e.target.closest('.nav-menu');
  if (!menu) toggleNavMenu(false);
});

// ── Loader principal da Home ──────────────────────────────────────────────────
let _homeBuilderWired = false;

async function loadHome() {
  _wireHomeBuilder();
  _wireHomeTraducao();
  await Promise.all([_loadHomeTracking(), _loadHomeWhiteboard()]);
}

// ── Atalho: Traduzir um PDF (cria Traducao + upload + abre a view) ──────────────
let _homeTrWired = false;
function _wireHomeTraducao() {
  if (_homeTrWired) return;
  const inp = document.getElementById('home-tr-file');
  if (!inp) return;
  _homeTrWired = true;
  inp.addEventListener('change', () => {
    const f = inp.files && inp.files[0];
    inp.value = '';  // permite reenviar o mesmo arquivo depois
    if (f) _homeTrUpload(f);
  });
}

// Botão do hero: abre o seletor de arquivo.
function homeTraduzirPDF() {
  const inp = document.getElementById('home-tr-file');
  if (inp) inp.click();
}

async function _homeTrUpload(file) {
  const log = document.getElementById('home-tr-log');
  const btn = document.getElementById('home-tr-btn');
  const base = file.name.replace(/\.pdf$/i, '');
  let name = base.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40) || 'traducao';
  if (log) log.innerHTML = '<span style="color:var(--muted)">criando tradução e enviando o PDF…</span>';
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Enviando…'; }
  try {
    // nome único: se já existe, sufixa com um curto timestamp
    const existe = await apiFetch(`${API}/Traducao/${encodeURIComponent(name)}`).then(() => true).catch(() => false);
    if (existe) name = `${name}-${Date.now().toString(36).slice(-4)}`;

    await apiFetch(`${API}/Traducao/${encodeURIComponent(name)}`, {
      method: 'PUT',
      body: JSON.stringify({ labels: {}, spec: { idioma_origem: 'en', idioma_destino: 'pt-BR', motor: 'claude' }, status: {} }),
    });
    const buf = await file.arrayBuffer();
    await apiFetch(`${API}/_upload?name=${encodeURIComponent(file.name)}&label=${encodeURIComponent(name)}`, {
      method: 'POST', body: buf, headers: { 'Content-Type': 'application/pdf' },
    });
    if (log) log.innerHTML = `<span style="color:var(--green)">✓ ${esc(name)} criado — abrindo…</span>`;
    if (typeof setView === 'function') setView('explorer');
    if (typeof openResource === 'function') await openResource('Traducao', name);
  } catch (e) {
    if (log) log.innerHTML = `<span style="color:var(--red)">erro: ${esc(e.message)}</span>`;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '📄 Enviar PDF para traduzir'; }
  }
}

// ── Zona 1: Construir com IA ───────────────────────────────────────────────────
function _wireHomeBuilder() {
  if (_homeBuilderWired) return;
  _homeBuilderWired = true;
  const input = document.getElementById('home-ai-input');
  const btn = document.getElementById('home-ai-send');
  if (!input || !btn) return;
  btn.addEventListener('click', _runHomeBuilder);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); _runHomeBuilder(); }
  });
}

async function _runHomeBuilder() {
  const input = document.getElementById('home-ai-input');
  const btn = document.getElementById('home-ai-send');
  const logEl = document.getElementById('home-ai-log');
  const text = (input.value || '').trim();
  if (!text) return;
  input.value = '';
  btn.disabled = true; btn.textContent = '⏳ Executando…';

  // Sessão de log (reusa o visual do agente modo=code)
  logEl.innerHTML = `<div class="ag-code-session" id="home-ai-sess"></div>`;
  const sessEl = document.getElementById('home-ai-sess');

  function append(cls, html) {
    const d = document.createElement('div');
    d.className = `ag-code-log ${cls}`;
    d.innerHTML = html;
    sessEl.appendChild(d);
    sessEl.scrollTop = sessEl.scrollHeight;
  }

  let run;
  try {
    const r = await apiFetch(`${API}/_agent_run`, {
      method: 'POST', body: JSON.stringify({agente: 'atlas-builder', mensagem: text}),
    });
    if (r.error) throw new Error(r.error);
    run = r.run_id;
  } catch (e) {
    append('error', `⚠️ ${esc(e.message)}`);
    btn.disabled = false; btn.textContent = 'Executar ▶';
    return;
  }

  const es = new EventSource(`${API}/_agent_run/${run}/stream`);
  es.onmessage = (ev) => {
    let obj; try { obj = JSON.parse(ev.data); } catch { return; }
    // reusa o renderizador de eventos do agente (agente.js)
    if (typeof _appendCodeEventToEl === 'function') _appendCodeEventToEl(obj, sessEl);
    sessEl.scrollTop = sessEl.scrollHeight;
    if (obj.type === 'done' || obj.type === 'error') {
      es.close();
      btn.disabled = false; btn.textContent = 'Executar ▶';
      // recarrega rastreio e galeria — pode ter criado/alterado objetos
      _loadHomeTracking(); _loadHomeWhiteboard();
      if (typeof _refreshStore === 'function') _refreshStore();
    }
  };
  es.onerror = () => { /* EventSource reconecta sozinho até done */ };
}

// ── Zona 2: O que existe (rastreio) ────────────────────────────────────────────
async function _loadHomeTracking() {
  const el = document.getElementById('home-tracking');
  if (!el) return;
  let s;
  try { s = await apiFetch(`${API}/_status`); }
  catch (e) { el.innerHTML = `<div class="sv-empty">erro: ${esc(e.message)}</div>`; return; }

  // chips de contagem por kind (oculta kinds internos/aninhados)
  const HIDDEN = new Set(['Branch', 'Commit', 'Diff', 'Routine']);
  const kinds = Object.entries(s.kinds || {})
    .filter(([k, n]) => !HIDDEN.has(k) && n > 0)
    .sort((a, b) => b[1] - a[1]);
  const chips = kinds.map(([k, n]) =>
    `<button class="home-chip" onclick="openResourceList('${escJs(k)}')">
       <span class="home-chip-n">${n}</span> ${esc(k)}</button>`).join('');

  // rodando agora (timers)
  const running = (s.running || []).map(t =>
    `<span class="home-run">⏵ ${esc(t.name)}${t.since ? ' · ' + esc(_ago(t.since)) : ''}</span>`).join('');

  // jobs ativos / próximos
  const jobs = (s.routines || []).filter(r => r.active).slice(0, 6);
  const jobsHtml = jobs.length
    ? jobs.map(j => `<div class="home-job" onclick="openResource('Job','${escJs(j.name)}')">
        <span>🧩 ${esc(j.name)}</span>
        <span style="color:var(--muted);font-size:10px">${j.next_run ? _in((new Date(j.next_run) - Date.now())/1000) : (j.schedule || '')}</span>
      </div>`).join('')
    : '<span class="sv-empty" style="font-size:11px">nenhum job ativo</span>';

  el.innerHTML = `
    <div class="home-chips">${chips || '<span class="sv-empty">sem recursos</span>'}</div>
    ${running ? `<div class="home-running">${running}</div>` : ''}
    <div class="home-subhead">Jobs ativos</div>
    <div class="home-jobs">${jobsHtml}</div>`;
}

// ── Zona 3: Quadro branco (galeria de renders especializados) ──────────────────
async function _loadHomeWhiteboard() {
  const el = document.getElementById('home-whiteboard');
  if (!el) return;
  // Kinds que têm render especializada (quadro branco)
  const kinds = (typeof RENDER_REGISTRY !== 'undefined') ? Object.keys(RENDER_REGISTRY) : ['Repo', 'RepoGroup', 'Agente'];
  const icons = {Repo: '📦', RepoGroup: '🗂', Agente: '🤖', Job: '🧩', LLMProvider: '🔌', Traducao: '📖'};

  const groups = await Promise.all(kinds.map(async k => {
    const items = await apiFetch(`${API}/${k}`).catch(() => []);
    return {kind: k, items: items || []};
  }));

  let html = '';
  for (const g of groups) {
    if (!g.items.length) continue;
    const cards = g.items.map(r => {
      const sub = _wbSubtitle(g.kind, r);
      return `<div class="home-wb-card" onclick="openWhiteboard('${escJs(g.kind)}','${escJs(r.name)}')" title="Abrir ${esc(r.name)}">
        <div class="home-wb-icon">${icons[g.kind] || '📄'}</div>
        <div class="home-wb-body">
          <div class="home-wb-name">${esc(r.name)}</div>
          <div class="home-wb-sub">${sub}</div>
        </div>
      </div>`;
    }).join('');
    html += `<div class="home-wb-group">
      <div class="home-subhead">${icons[g.kind] || ''} ${esc(g.kind)} <span style="color:var(--muted)">${g.items.length}</span></div>
      <div class="home-wb-grid">${cards}</div>
    </div>`;
  }
  el.innerHTML = html || '<div class="sv-empty">nenhum item com render especializada ainda</div>';
}

function _wbSubtitle(kind, r) {
  const s = r.spec || {}, st = r.status || {};
  if (kind === 'Repo') {
    return st.last_commit_msg ? esc(String(st.last_commit_msg).slice(0, 48))
      : (s.url ? esc(String(s.url).replace(/^https?:\/\//, '')) : 'sem sync');
  }
  if (kind === 'RepoGroup') {
    const n = String(s.repos || '').split(',').filter(x => x.trim()).length;
    return `${n} repo${n !== 1 ? 's' : ''}`;
  }
  if (kind === 'Agente') {
    return `${esc(s.modo || 'chat')} · ${esc(s.modelo || s.provider || s.motor || 'claude')}`;
  }
  if (kind === 'Job') {
    const st = s.active ? '● ativo' : '○ inativo';
    return `${st}${s.schedule ? ' · 🕒 ' + esc(s.schedule) : ''}`;
  }
  if (kind === 'LLMProvider') {
    return `${esc(s.motor || '')} · ${esc(s.modelo || '')}`;
  }
  if (kind === 'Traducao') {
    const fase = st.fase;
    const origem = s.origem ? String(s.origem).split('/').pop() : 'sem PDF';
    if (fase === 'pronto') return '✓ pronto · ' + esc(origem);
    if (fase === 'traduzindo') return `⏳ ${st.progresso_pct || 0}% · ${esc(origem)}`;
    if (fase === 'erro') return '⚠️ erro · ' + esc(origem);
    return esc(origem);
  }
  return esc(s.description || '');
}

// Abre um item do quadro branco: vai pro Explorer e renderiza
function openWhiteboard(kind, name) {
  setView('explorer');
  if (typeof openResource === 'function') openResource(kind, name);
}

// Abre a listagem de um kind no Explorer (expande a árvore)
function openResourceList(kind) {
  setView('explorer');
  if (typeof treeOpen !== 'undefined') treeOpen[kind] = true;
  if (typeof _refreshStore === 'function') _refreshStore();
}
