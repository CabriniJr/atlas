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
        <button class="btn" data-action="daily" title="Garante Job de sync diário + Telegram p/ cada repo">🔔 Sync diário</button>
        <button class="btn" data-action="syncall" title="Sincronizar todos agora">↻ Sync todos</button>
        <button class="btn" data-action="refresh" title="Atualizar">⟳</button>
        <button class="btn rk-fullscreen-btn" onclick="toggleFullscreen()" title="Tela cheia">⤢</button>
      </div>
    </div>
    <div class="rk-tabbar">
      <button class="rk-tab active" data-tab="overview">📊 Visão</button>
      <button class="rk-tab" data-tab="goals">🎯 Objetivos</button>
      <button class="rk-tab" data-tab="analyses">🔍 Análises</button>
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
  container.querySelector('[data-action="daily"]')
    ?.addEventListener('click', () => _rgSetupDaily(name, r, container));
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
    else if (tab === 'goals') await _rgTabGoals(name, r, body);
    else if (tab === 'analyses') await _rgTabAnalyses(name, r, body);
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
    return `<div class="rg-card">
      <div class="rg-card-clickable" onclick="openResource('Repo','${escJs(rp.name)}')" title="Abrir ${esc(rp.name)}">
        <div class="rg-card-head">
          <span>📦</span><strong>${esc(rp.name)}</strong>
          <span class="rg-card-branches">🌿 ${bc}</span>
        </div>
        <div class="rg-card-commit">${commit}</div>
        <div class="rg-card-foot">
          <span style="font-size:10px;color:var(--muted)">${esc(sync)}</span>
          ${stats}
        </div>
      </div>
      <div class="rg-card-actions">
        <button class="btn rg-insight-btn" data-repo="${esc(rp.name)}" title="Gerar insight (IA) deste repo">🧠 Insight</button>
        <span class="rg-insight-out" id="rg-ins-${esc(rp.name)}"></span>
      </div>
    </div>`;
  }).join('');

  el.innerHTML = `<div class="rg-wrap">
    ${summary}
    <div class="home-subhead" style="margin-top:0">🧠 Análise por IA — cada repo usa seu Agente configurado (manual aqui; automático no sync)</div>
    <div class="rg-grid">${cards}</div>
  </div>`;

  // Insight por repo (manual) — não propaga o clique do card
  el.querySelectorAll('.rg-insight-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const repo = btn.dataset.repo;
      const out = el.querySelector(`#rg-ins-${CSS.escape(repo)}`);
      btn.disabled = true; btn.textContent = '🧠 …';
      if (out) { out.textContent = 'analisando…'; out.className = 'rg-insight-out'; }
      try {
        const r = await apiFetch(`${API}/_insight`, {
          method: 'POST', body: JSON.stringify({scope: 'repo', name: repo}),
        });
        if (r.error) throw new Error(r.error);
        if (out) { out.textContent = `✅ via ${r.agente || 'IA'} (${r.model || ''})`; out.className = 'rg-insight-out ok'; }
        toast(`insight de ${repo} gerado`);
      } catch (err) {
        if (out) { out.textContent = '❌ ' + err.message; out.className = 'rg-insight-out err'; }
      }
      btn.disabled = false; btn.textContent = '🧠 Insight';
    });
  });
}

async function _rgSyncAll(name, r, container) {
  const repoNames = _rgRepoNames(r.spec || {});
  if (!repoNames.length) return;
  const btn = container.querySelector('[data-action="syncall"]');
  if (btn) { btn.disabled = true; btn.textContent = '↻ sincronizando…'; }
  // Dispara o sync de cada repo — resolvido POR LABEL no backend (não por nome)
  await Promise.all(repoNames.map(n =>
    apiFetch(`${API}/_run`, {method: 'POST', body: JSON.stringify({repo: n})})
      .catch(() => null)));
  if (btn) { btn.disabled = false; btn.textContent = '↻ Sync todos'; }
  _loadRgTab(name, r, 'overview', container);
}

// Garante, para cada repo do grupo, um Job de sync diário com saída Telegram
// (vínculo por label, P11). Produção: avaliar repos diariamente + notificar.
async function _rgSetupDaily(name, r, container) {
  const repoNames = _rgRepoNames(r.spec || {});
  if (!repoNames.length) { toast('grupo sem repos', true); return; }
  const btn = container.querySelector('[data-action="daily"]');
  if (btn) { btn.disabled = true; btn.textContent = '🔔 configurando…'; }

  const allJobs = await apiFetch(`${API}/Job`).catch(() => []);
  let criados = 0, jaTinha = 0;
  for (const repo of repoNames) {
    const exists = (allJobs || []).some(j =>
      (j.spec?.coletar === 'repo-sync') && (j.spec?.label === repo));
    if (exists) { jaTinha++; continue; }
    try {
      await apiFetch(`${API}/Job/${encodeURIComponent(repo + '-sync')}`, {
        method: 'PUT',
        body: JSON.stringify({
          kind: 'Job', name: repo + '-sync',
          spec: {
            coletar: 'repo-sync', label: repo, schedule: '@daily 09:00',
            model: 'none', saida: 'telegram', active: true,
            description: `Sync diário de ${repo} (insights + Telegram)`,
          },
          labels: {domain: 'dev'},
        }),
      });
      criados++;
    } catch (e) { /* segue */ }
  }
  if (btn) { btn.disabled = false; btn.textContent = '🔔 Sync diário'; }
  toast(`sync diário: ${criados} criado(s), ${jaTinha} já existia(m)`);
  if (typeof _refreshStore === 'function') _refreshStore();
  _loadRgTab(name, r, 'overview', container);
}

// ── Tab: Objetivos (Goals do grupo, por label, com barras de progresso) ─────────
function _pctOf(goal) {
  // status.progress é "NN%"; senão calcula de current/target/start
  const p = (goal.status?.progress || '').replace('%', '').trim();
  const n = parseFloat(p);
  if (!isNaN(n)) return Math.max(0, Math.min(100, n));
  return null;
}

async function _rgTabGoals(name, r, el) {
  const [goals, trackers] = await Promise.all([
    apiFetch(`${API}/Goal`).catch(() => []),
    apiFetch(`${API}/Tracker`).catch(() => []),
  ]);
  // Vínculo por label (P11): Goals com labels.group == este grupo
  const mine = (goals || []).filter(g => (g.labels?.group || '') === name);

  const bars = mine.length ? mine.map(g => {
    const s = g.spec || {}, st = g.status || {};
    const pct = _pctOf(g);
    const cur = st.current != null ? st.current : '—';
    const dir = s.direction === 'up' ? '↑' : '↓';
    return `<div class="rg-goal">
      <div class="rg-goal-head">
        <span class="rg-goal-name" onclick="openResource('Goal','${escJs(g.name)}')">🎯 ${esc(g.name)}</span>
        <span class="rg-goal-nums">${esc(String(cur))}${esc(s.unit || '')} ${dir} ${esc(String(s.target ?? '?'))}${esc(s.unit || '')}</span>
        <button class="btn rg-goal-recalc" data-goal="${esc(g.name)}" title="Recalcular do tracker">↻</button>
      </div>
      <div class="rg-goal-bar"><div class="rg-goal-fill" style="width:${pct == null ? 0 : pct}%"></div>
        <span class="rg-goal-pct">${pct == null ? 'sem dados' : pct + '%'}</span></div>
      <div class="rg-goal-sub">tracker: <code>${esc(s.tracker || '—')}</code></div>
    </div>`;
  }).join('') : '<div class="sv-empty">Nenhum objetivo neste grupo ainda.</div>';

  // form de criar objetivo a partir de um tracker
  const trackerOpts = (trackers || []).map(t =>
    `<option value="${esc(t.name)}">${esc(t.name)}${t.spec?.unit ? ' (' + esc(t.spec.unit) + ')' : ''}</option>`).join('');

  el.innerHTML = `<div class="rg-wrap">
    <div class="home-subhead" style="margin-top:0">🎯 Objetivos do grupo — barras ligadas a Trackers (P11: labels.group=${esc(name)})</div>
    <div class="rg-goals">${bars}</div>

    <div class="rg-newgoal">
      <div class="home-subhead">＋ Novo objetivo a partir de um Tracker</div>
      ${(trackers || []).length ? `<div class="rg-newgoal-form">
        <input class="rk-cfg-input" id="rg-g-name" placeholder="nome do objetivo">
        <select class="rk-cfg-input" id="rg-g-tracker">${trackerOpts}</select>
        <input class="rk-cfg-input" id="rg-g-target" placeholder="target" style="width:90px">
        <input class="rk-cfg-input" id="rg-g-start" placeholder="início" style="width:90px">
        <select class="rk-cfg-input" id="rg-g-dir" style="width:120px"><option value="down">↓ menor é melhor</option><option value="up">↑ maior é melhor</option></select>
        <button class="btn" id="rg-g-add" style="color:var(--green);border-color:var(--green)">Criar</button>
        <span id="rg-g-status" style="font-size:11px"></span>
      </div>` : '<div class="sv-empty">Crie um Tracker antes (＋ Novo · Tracker).</div>'}
    </div>
  </div>`;

  // recalcular cada goal
  el.querySelectorAll('.rg-goal-recalc').forEach(btn => {
    btn.addEventListener('click', async () => {
      btn.disabled = true; btn.textContent = '…';
      try {
        await apiFetch(`${API}/_cmd`, {method: 'POST', body: JSON.stringify({text: `/goal check ${btn.dataset.goal}`})});
        _rgTabGoals(name, r, el);
      } catch (e) { toast('❌ ' + e.message, true); btn.disabled = false; btn.textContent = '↻'; }
    });
  });

  // criar objetivo
  const addBtn = el.querySelector('#rg-g-add');
  addBtn?.addEventListener('click', async () => {
    const gname = el.querySelector('#rg-g-name').value.trim();
    const tracker = el.querySelector('#rg-g-tracker').value;
    const target = el.querySelector('#rg-g-target').value.trim();
    const start = el.querySelector('#rg-g-start').value.trim();
    const dir = el.querySelector('#rg-g-dir').value;
    const st = el.querySelector('#rg-g-status');
    if (!gname || !target) { st.textContent = 'nome e target obrigatórios'; return; }
    const trackerRes = (trackers || []).find(t => t.name === tracker);
    const unit = trackerRes?.spec?.unit || '';
    addBtn.disabled = true; st.textContent = 'criando…';
    try {
      const spec = {tracker, target, direction: dir, unit};
      if (start) spec.start = start;
      await apiFetch(`${API}/Goal/${encodeURIComponent(gname)}`, {
        method: 'PUT',
        body: JSON.stringify({kind: 'Goal', name: gname, spec, labels: {group: name}}),
      });
      // já calcula o progresso do último valor do tracker
      await apiFetch(`${API}/_cmd`, {method: 'POST', body: JSON.stringify({text: `/goal check ${gname}`})}).catch(() => {});
      _rgTabGoals(name, r, el);
    } catch (e) { st.textContent = '❌ ' + e.message; addBtn.disabled = false; }
  });
}

// ── Tab: Análises (últimas análises/insights por repo do grupo) ─────────────────
async function _rgTabAnalyses(name, r, el) {
  const repoNames = _rgRepoNames(r.spec || {});
  if (!repoNames.length) {
    el.innerHTML = '<div class="sv-empty">Nenhum repo no grupo.</div>';
    return;
  }
  const docs = await apiFetch(`${API}/Doc`).catch(() => []);
  const blocks = repoNames.map(repo => {
    const insights = (docs || [])
      .filter(d => d.labels?.repo === repo && d.labels?.tipo === 'insight')
      .sort((a, b) => String(b.status?.gerado_em || b.criado_em || '').localeCompare(String(a.status?.gerado_em || a.criado_em || '')));
    const last = insights[0];
    return `<div class="rg-an-block">
      <div class="rg-an-head">
        <span onclick="openResource('Repo','${escJs(repo)}')" style="cursor:pointer">📦 <strong>${esc(repo)}</strong></span>
        <button class="btn rg-an-gen" data-repo="${esc(repo)}" style="border-color:var(--purple);color:var(--purple)">🧠 Analisar</button>
      </div>
      ${last
        ? `<div class="rg-an-body"><div style="font-size:10px;color:var(--muted);margin-bottom:4px">${esc(fmtDt(last.status?.gerado_em || last.criado_em))} · ${insights.length} análise(s)</div><div class="md">${markdownToHtml(String(last.spec?.body || ''))}</div></div>`
        : '<div class="sv-empty" style="font-size:11px">sem análises ainda</div>'}
    </div>`;
  }).join('');

  el.innerHTML = `<div class="rg-wrap">
    <div class="home-subhead" style="margin-top:0">🔍 Últimas análises por repo (Agente de análise de cada Repo)</div>
    ${blocks}
  </div>`;

  el.querySelectorAll('.rg-an-gen').forEach(btn => {
    btn.addEventListener('click', async () => {
      const repo = btn.dataset.repo;
      btn.disabled = true; btn.textContent = '🧠 …';
      try {
        await apiFetch(`${API}/_insight`, {method: 'POST', body: JSON.stringify({scope: 'repo', name: repo})});
        _rgTabAnalyses(name, r, el);
      } catch (e) { toast('❌ ' + e.message, true); btn.disabled = false; btn.textContent = '🧠 Analisar'; }
    });
  });
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
