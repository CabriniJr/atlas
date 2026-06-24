/* RepoGroup render especializada (ADR-0020 / multirepo).
 * Dashboard que agrupa uma série de Repos: cards com status agregado,
 * resumo do grupo, clique abre o Repo. Abas: 📊 Visão | ⚙️ Config.
 * Fullscreen destacável.
 */

registerRender('RepoGroup', async function renderRepoGroup(r, container) {
  const name = r.name;
  container.innerHTML = _rgShell(r);
  _wireRepoGroup(name, r, container);
  _loadRgTab(name, r, 'overview', container);
});

// ── Shell ─────────────────────────────────────────────────────────────────────
function _rgShell(r) {
  const s = r.spec || {};
  const repos = _rgRepoNames(s);
  return `<div class="rk-wrap">
    <div class="rk-header">
      <span style="font-size:20px">🗂</span>
      <div style="flex:1;min-width:0">
        <div class="rk-title">${esc(r.name)}</div>
        <div style="font-size:11px;color:var(--muted)">${repos.length} repositório${repos.length !== 1 ? 's' : ''}</div>
      </div>
      <div class="rk-actions">
        <button class="btn" data-action="syncall" title="Sincronizar todos">↻ Sync todos</button>
        <button class="btn" data-action="refresh" title="Atualizar">⟳</button>
        <button class="btn rk-fullscreen-btn" onclick="toggleFullscreen()" title="Tela cheia">⤢</button>
      </div>
    </div>
    <div class="rk-tabbar">
      <button class="rk-tab active" data-tab="overview">📊 Visão</button>
      <button class="rk-tab" data-tab="config">⚙️ Config</button>
    </div>
    <div class="rk-body" id="rg-body-${esc(r.name)}">
      <div style="padding:20px;color:var(--muted)">carregando…</div>
    </div>
  </div>`;
}

function _wireRepoGroup(name, r, container) {
  container.querySelector('[data-action="refresh"]')
    ?.addEventListener('click', () => _loadRgTab(name, r, 'overview', container));
  container.querySelector('[data-action="syncall"]')
    ?.addEventListener('click', () => _rgSyncAll(name, r, container));
  container.querySelectorAll('.rk-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.rk-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      _loadRgTab(name, r, btn.dataset.tab, container);
    });
  });
}

function _rgRepoNames(spec) {
  return String(spec.repos || '')
    .split(',').map(s => s.trim()).filter(Boolean);
}

// ── Tab dispatcher ──────────────────────────────────────────────────────────────
async function _loadRgTab(name, r, tab, container) {
  const body = container.querySelector(`#rg-body-${CSS.escape(name)}`);
  if (!body) return;
  body.innerHTML = '<div style="padding:16px;color:var(--muted)">carregando…</div>';
  try {
    if (tab === 'overview') await _rgTabOverview(name, r, body);
    else if (tab === 'config') await _rgTabConfig(name, body);
  } catch (e) {
    body.innerHTML = `<div style="padding:16px;color:var(--red)">erro: ${esc(e.message)}</div>`;
  }
}

// ── Tab: Visão (cards dos repos + resumo) ───────────────────────────────────────
async function _rgTabOverview(name, r, el) {
  const repoNames = _rgRepoNames(r.spec || {});
  if (!repoNames.length) {
    el.innerHTML = `<div style="padding:24px 16px;color:var(--muted);font-size:13px">
      Nenhum repo no grupo. Adicione na aba ⚙️ Config (lista por vírgula).</div>`;
    return;
  }

  // Busca todos os repos + todas as branches em paralelo (1 fetch de Branch)
  const [repos, allBranches] = await Promise.all([
    Promise.all(repoNames.map(n =>
      apiFetch(`${API}/Repo/${encodeURIComponent(n)}`).catch(() => ({_missing: true, name: n})))),
    apiFetch(`${API}/Branch`).catch(() => []),
  ]);

  const branchCount = {};
  (allBranches || []).forEach(b => {
    const rp = b.labels?.repo;
    if (rp) branchCount[rp] = (branchCount[rp] || 0) + 1;
  });

  // Resumo agregado
  let totFiles = 0, totIns = 0, totDel = 0, totBranches = 0, active = 0;
  let lastActivity = '';
  repos.forEach(rp => {
    if (rp._missing) return;
    const st = rp.status || {};
    totFiles += Number(st.files_changed || 0);
    totIns += Number(st.insertions || 0);
    totDel += Number(st.deletions || 0);
    totBranches += branchCount[rp.name] || 0;
    if (st.last_sync || st.last_commit) active++;
    const act = st.last_sync || st.last_commit_date || '';
    if (act > lastActivity) lastActivity = act;
  });

  const summary = `<div class="rg-summary">
    <div class="rg-stat"><div class="rg-stat-n">${repos.length}</div><div class="rg-stat-l">repos</div></div>
    <div class="rg-stat"><div class="rg-stat-n">${active}</div><div class="rg-stat-l">com sync</div></div>
    <div class="rg-stat"><div class="rg-stat-n">${totBranches}</div><div class="rg-stat-l">branches</div></div>
    <div class="rg-stat"><div class="rg-stat-n" style="color:var(--green)">+${totIns}</div><div class="rg-stat-l">inserções</div></div>
    <div class="rg-stat"><div class="rg-stat-n" style="color:var(--red)">-${totDel}</div><div class="rg-stat-l">remoções</div></div>
    ${lastActivity ? `<div class="rg-stat"><div class="rg-stat-n" style="font-size:13px">${esc(_ago(lastActivity))}</div><div class="rg-stat-l">última atividade</div></div>` : ''}
  </div>`;

  const cards = repos.map(rp => {
    if (rp._missing) {
      return `<div class="rg-card rg-card-missing">
        <div class="rg-card-head"><span>📦</span><strong>${esc(rp.name)}</strong></div>
        <div style="color:var(--red);font-size:11px">⚠️ Repo não encontrado</div>
      </div>`;
    }
    const s = rp.spec || {}, st = rp.status || {};
    const bc = branchCount[rp.name] || 0;
    const sync = st.last_sync ? `sync ${_ago(st.last_sync)}`
      : (st.last_check ? `check ${_ago(st.last_check)}` : 'nunca sincronizado');
    const commit = st.last_commit
      ? `<code class="rg-sha">${esc(st.last_commit)}</code>
         <span class="rg-msg">${esc((st.last_commit_msg || '').slice(0, 60))}</span>`
      : '<span style="color:var(--muted);font-size:11px">sem commits</span>';
    const stats = (st.files_changed || st.insertions || st.deletions)
      ? `<span class="rg-card-stats">${st.files_changed || 0} ✱ <span style="color:var(--green)">+${st.insertions || 0}</span> <span style="color:var(--red)">-${st.deletions || 0}</span></span>`
      : '';
    return `<div class="rg-card" onclick="openResource('Repo','${escJs(rp.name)}')" title="Abrir ${esc(rp.name)}">
      <div class="rg-card-head">
        <span>📦</span><strong>${esc(rp.name)}</strong>
        <span class="rg-card-branches">🌿 ${bc}</span>
      </div>
      <div class="rg-card-commit">${commit}</div>
      <div class="rg-card-foot">
        <span style="font-size:10px;color:var(--muted)">${esc(sync)}</span>
        ${stats}
      </div>
    </div>`;
  }).join('');

  el.innerHTML = `<div class="rg-wrap">
    ${summary}
    <div class="rg-grid">${cards}</div>
  </div>`;
}

async function _rgSyncAll(name, r, container) {
  const repoNames = _rgRepoNames(r.spec || {});
  if (!repoNames.length) return;
  const btn = container.querySelector('[data-action="syncall"]');
  if (btn) { btn.disabled = true; btn.textContent = '↻ sincronizando…'; }
  // Dispara o Job <repo>-sync de cada repo (mesmo padrão do repo.js)
  await Promise.all(repoNames.map(n =>
    apiFetch(`${API}/_run`, {method: 'POST', body: JSON.stringify({routine: n + '-sync'})})
      .catch(() => null)));
  if (btn) { btn.disabled = false; btn.textContent = '↻ Sync todos'; }
  _loadRgTab(name, r, 'overview', container);
}

// ── Tab: Config ─────────────────────────────────────────────────────────────────
async function _rgTabConfig(name, el) {
  const schema = (allSchema && allSchema['RepoGroup']?.spec) || [
    {k: 'repos', type: 'text', label: 'Repos', hint: 'Nomes por vírgula'},
    {k: 'description', type: 'area', label: 'Descrição', hint: ''},
  ];
  let res;
  try {
    res = await apiFetch(`${API}/RepoGroup/${encodeURIComponent(name)}`);
  } catch (e) {
    el.innerHTML = `<div style="padding:16px;color:var(--red)">erro: ${esc(e.message)}</div>`;
    return;
  }
  const spec = res.spec || {};

  // Sugestão: lista de repos existentes para o usuário saber os nomes válidos
  const allRepos = await apiFetch(`${API}/Repo`).catch(() => []);
  const repoHint = (allRepos || []).map(r => r.name).join(', ');

  el.innerHTML = `<div class="rk-cfg-form">
    <div class="rk-section">
      <div class="rk-sec-title">⚙️ Configuração — ${esc(name)}</div>
      ${schema.map(f => _cfgFieldRg(f, spec[f.k])).join('')}
      ${repoHint ? `<div class="rk-cfg-hint" style="grid-column:1/-1;margin-top:4px">
        Repos disponíveis: ${esc(repoHint)}</div>` : ''}
    </div>
    <div class="rk-cfg-footer">
      <button class="btn" id="rg-cfg-save-${esc(name)}" style="color:var(--green);border-color:var(--green)">💾 Salvar</button>
      <span class="rk-cfg-status" id="rg-cfg-status-${esc(name)}"></span>
    </div>
  </div>`;

  const saveBtn = el.querySelector(`#rg-cfg-save-${CSS.escape(name)}`);
  const statusEl = el.querySelector(`#rg-cfg-status-${CSS.escape(name)}`);
  saveBtn.addEventListener('click', async () => {
    saveBtn.disabled = true;
    statusEl.textContent = 'salvando…'; statusEl.className = 'rk-cfg-status';
    try {
      const newSpec = {...spec};
      schema.forEach(f => {
        const inp = el.querySelector(`[data-k="${f.k}"]`);
        if (inp) newSpec[f.k] = inp.value;
      });
      await apiFetch(`${API}/RepoGroup/${encodeURIComponent(name)}`, {
        method: 'PUT',
        body: JSON.stringify({kind: 'RepoGroup', name, spec: newSpec, labels: res.labels || {}, status: res.status || {}}),
      });
      statusEl.textContent = '✅ Salvo — abra a aba Visão'; statusEl.className = 'rk-cfg-status ok';
    } catch (e) {
      statusEl.textContent = '❌ ' + e.message; statusEl.className = 'rk-cfg-status err';
    } finally { saveBtn.disabled = false; }
  });
}

function _cfgFieldRg(f, value) {
  const v = value == null ? '' : String(value);
  const input = f.type === 'area'
    ? `<textarea class="rk-cfg-input" data-k="${esc(f.k)}" rows="3">${esc(v)}</textarea>`
    : `<input class="rk-cfg-input" data-k="${esc(f.k)}" value="${esc(v)}">`;
  return `<div class="rk-cfg-row">
    <label class="rk-cfg-label">${esc(f.label || f.k)}</label>
    <div>${input}${f.hint ? `<div class="rk-cfg-hint">${esc(f.hint)}</div>` : ''}</div>
  </div>`;
}
