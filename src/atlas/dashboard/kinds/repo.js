/* Repo render especializada (ADR-0020 / E7-08).
 * Registra-se no RENDER_REGISTRY e substitui o card genérico quando se abre
 * um recurso do Kind Repo. Lê apenas da API e chama verbos — sem lógica de
 * domínio no front.
 */

registerRender('Repo', async function renderRepo(r, container) {
  const name = r.name;
  const s = r.spec || {};
  const st = r.status || {};

  container.innerHTML = _repoShell(r);

  // wire action buttons
  container.querySelector('[data-action="edit"]')
    ?.addEventListener('click', () => switchSubTab('manifest'));
  container.querySelector('[data-action="backfill"]')
    ?.addEventListener('click', () => _runBackfill(name));
  container.querySelector('[data-action="sync"]')
    ?.addEventListener('click', () => _runSync(name));

  // wire tabs
  container.querySelectorAll('.rk-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.rk-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      _loadRepoTab(name, btn.dataset.tab, container);
    });
  });

  // load default tab
  _loadRepoTab(name, 'overview', container);
});

// ── Shell HTML ────────────────────────────────────────────────────────────────
function _repoShell(r) {
  const s = r.spec || {}, st = r.status || {};
  const lastCommit = st.last_commit
    ? `<code style="color:var(--orange);font-size:11px">${esc(st.last_commit)}</code>
       <span style="font-size:11px;color:var(--muted)">${esc(st.last_commit_msg || '')}</span>`
    : '<span style="color:var(--muted);font-size:12px">sem sync</span>';
  const syncInfo = st.last_sync
    ? `sync ${_ago(st.last_sync)}`
    : (st.last_check ? `check ${_ago(st.last_check)}` : 'nunca sincronizado');

  return `<div class="rk-wrap">
    <div class="rk-header">
      <span style="font-size:20px">📦</span>
      <div style="flex:1;min-width:0">
        <div class="rk-title">${esc(r.name)}</div>
        ${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener"
          style="font-size:11px;color:var(--blue)">${esc(s.url)}</a>` : ''}
      </div>
      <div class="rk-actions">
        <button class="btn" data-action="sync" title="Executar repo-sync">↻ Sync</button>
        <button class="btn" data-action="backfill" title="/repo backfill">⏮ Backfill</button>
        <button class="btn" data-action="edit">✏️ Editar</button>
      </div>
    </div>
    <div class="rk-meta-bar">
      ${lastCommit}
      <span style="flex:1"></span>
      <span style="font-size:10px;color:var(--muted)">${esc(syncInfo)}</span>
    </div>
    <div class="rk-tabbar">
      <button class="rk-tab active" data-tab="overview">📊 Overview</button>
      <button class="rk-tab" data-tab="branches">🌿 Branches</button>
      <button class="rk-tab" data-tab="commits">📝 Commits</button>
      <button class="rk-tab" data-tab="graph">⬡ Graph</button>
    </div>
    <div class="rk-body" id="rk-body-${esc(r.name)}">
      <div style="padding:20px;color:var(--muted)">carregando…</div>
    </div>
  </div>`;
}

// ── Tab dispatcher ────────────────────────────────────────────────────────────
async function _loadRepoTab(name, tab, container) {
  const body = container.querySelector(`#rk-body-${CSS.escape(name)}`);
  if (!body) return;
  body.innerHTML = '<div style="padding:16px;color:var(--muted)">carregando…</div>';
  try {
    switch (tab) {
      case 'overview':  await _tabOverview(name, body); break;
      case 'branches':  await _tabBranches(name, body); break;
      case 'commits':   await _tabCommits(name, body); break;
      case 'graph':     await _tabGraph(name, body); break;
    }
  } catch (e) {
    body.innerHTML = `<div style="padding:16px;color:var(--red)">erro: ${esc(e.message)}</div>`;
  }
}

// ── Tab: Overview (contexto + diffs recentes) ─────────────────────────────────
async function _tabOverview(name, el) {
  el.innerHTML = `
    <div class="rk-section">
      <div class="rk-sec-title">🧠 Contexto do projeto</div>
      <div id="rk-ctx-${esc(name)}" style="color:var(--muted)">carregando…</div>
    </div>
    <div class="rk-section">
      <div class="rk-sec-title">🔄 Diffs recentes</div>
      <div id="rk-diffs-${esc(name)}" style="color:var(--muted)">carregando…</div>
    </div>`;

  const [ctxEl, diffsEl] = [
    el.querySelector(`#rk-ctx-${CSS.escape(name)}`),
    el.querySelector(`#rk-diffs-${CSS.escape(name)}`),
  ];

  // context doc
  apiFetch(`${API}/Doc/repo-${encodeURIComponent(name)}-contexto`)
    .then(doc => {
      const md = doc.spec?.body ? markdownToHtml(String(doc.spec.body))
        : '<span style="color:var(--muted)">vazio</span>';
      const gen = doc.status?.generated_at
        ? `<div style="font-size:10px;color:var(--muted);margin-bottom:6px">
             modelo: ${esc(doc.status.model || '-')} · ${esc(fmtDt(doc.status.generated_at))}
           </div>` : '';
      if (ctxEl) ctxEl.innerHTML = `${gen}<details open>
        <summary style="cursor:pointer;color:var(--blue);font-size:11px">ver/ocultar</summary>
        <div class="md">${md}</div></details>`;
    })
    .catch(() => { if (ctxEl) ctxEl.textContent = 'contexto ainda não gerado'; });

  // recent diffs
  apiFetch(`${API}/Diff`)
    .then(all => {
      const mine = (all || [])
        .filter(d => d.labels?.repo === name)
        .sort((a, b) => String(b.criado_em || '').localeCompare(String(a.criado_em || '')))
        .slice(0, 10);
      if (!diffsEl) return;
      diffsEl.innerHTML = mine.length
        ? mine.map(d => {
            const sp = d.spec || {};
            return `<div class="rk-diff-row" onclick="openResource('Diff','${escJs(d.name)}')">
              <div style="font-size:12px">${esc(sp.subject || sp.commit || d.name)}</div>
              <div style="font-size:10px;color:var(--muted)">
                ${esc(sp.commit || '')} · +${sp.insertions ?? 0}/-${sp.deletions ?? 0}
              </div>
            </div>`;
          }).join('')
        : '<span style="color:var(--muted)">sem diffs ainda</span>';
    })
    .catch(() => { if (diffsEl) diffsEl.textContent = 'diffs indisponíveis'; });
}

// ── Tab: Branches ─────────────────────────────────────────────────────────────
async function _tabBranches(name, el) {
  const branches = await _fetchByLabel('Branch', 'repo', name);
  if (!branches.length) {
    el.innerHTML = '<div style="padding:16px;color:var(--muted)">Nenhuma branch materializada. Execute Sync ou Backfill.</div>';
    return;
  }

  // sort: default first, then alphabetical
  branches.sort((a, b) => {
    const ad = a.status?.is_default ? 0 : 1;
    const bd = b.status?.is_default ? 0 : 1;
    return ad - bd || (a.spec?.branch || '').localeCompare(b.spec?.branch || '');
  });

  el.innerHTML = `<div class="rk-branch-list">
    ${branches.map(b => {
      const st = b.status || {}, sp = b.spec || {};
      const bname = sp.branch || b.name;
      const isDefault = st.is_default;
      const stale = st.stale;
      const ahead = st.ahead ?? 0, behind = st.behind ?? 0;
      const activity = st.last_activity ? _ago(st.last_activity) : '—';
      return `<div class="rk-branch-row${stale ? ' stale' : ''}">
        <div class="rk-branch-name">
          ${isDefault ? '<span class="rk-badge default">default</span>' : ''}
          ${stale ? '<span class="rk-badge stale">stale</span>' : ''}
          <code>${esc(bname)}</code>
        </div>
        <div class="rk-branch-meta">
          <span title="head">${esc(st.head || '—')}</span>
          ${ahead ? `<span style="color:var(--green)">↑${ahead}</span>` : ''}
          ${behind ? `<span style="color:var(--red)">↓${behind}</span>` : ''}
          <span>${st.commits ?? '?'} commits</span>
          <span style="color:var(--muted)">${esc(activity)}</span>
        </div>
      </div>`;
    }).join('')}
  </div>`;
}

// ── Tab: Commits ──────────────────────────────────────────────────────────────
async function _tabCommits(name, el) {
  const commits = await _fetchByLabel('Commit', 'repo', name);
  if (!commits.length) {
    el.innerHTML = '<div style="padding:16px;color:var(--muted)">Nenhum commit materializado. Execute Sync ou Backfill.</div>';
    return;
  }

  // sort by date desc
  commits.sort((a, b) =>
    String(b.spec?.date || '').localeCompare(String(a.spec?.date || '')));

  el.innerHTML = `<div class="rk-commit-list">
    ${commits.slice(0, 150).map(c => {
      const sp = c.spec || {};
      const isMerge = sp.is_merge;
      const adds = sp.insertions ?? 0, dels = sp.deletions ?? 0;
      const bLabel = (c.labels?.branch) ? `<span class="rk-badge branch">${esc(c.labels.branch)}</span>` : '';
      return `<div class="rk-commit-row${isMerge ? ' merge' : ''}">
        <code class="rk-sha">${esc(sp.sha ? sp.sha.slice(0, 7) : c.name.split('-').pop())}</code>
        <div class="rk-commit-body">
          <div class="rk-commit-subj">${esc(sp.subject || '(sem mensagem)')}</div>
          <div class="rk-commit-meta">
            <span>${esc(sp.author || '')}</span>
            <span style="color:var(--muted)">${sp.date ? _ago(sp.date) : ''}</span>
            ${adds || dels ? `<span style="color:var(--green)">+${adds}</span>
              <span style="color:var(--red)">-${dels}</span>` : ''}
            ${bLabel}
          </div>
        </div>
      </div>`;
    }).join('')}
    ${commits.length > 150 ? `<div style="padding:8px 12px;color:var(--muted);font-size:11px">
      … mais ${commits.length - 150} commits</div>` : ''}
  </div>`;
}

// ── Tab: Graph (SVG git-graph) ────────────────────────────────────────────────
async function _tabGraph(name, el) {
  const commits = await _fetchByLabel('Commit', 'repo', name);
  if (!commits.length) {
    el.innerHTML = '<div style="padding:16px;color:var(--muted)">Nenhum commit para desenhar.</div>';
    return;
  }

  // Build sha7 → commit map
  const byShа = {};
  commits.forEach(c => {
    const sha7 = c.spec?.sha ? c.spec.sha.slice(0, 7) : c.name.split('-').pop();
    byShа[sha7] = c;
  });

  // Sort commits by date desc for display
  const sorted = [...commits].sort((a, b) =>
    String(b.spec?.date || '').localeCompare(String(a.spec?.date || '')));

  // Lane assignment (greedy): sha7 → lane index
  const lanes = {};
  const activeLanes = []; // each slot: sha7 of the "tip" or null
  sorted.forEach(c => {
    const sha7 = c.spec?.sha ? c.spec.sha.slice(0, 7) : c.name.split('-').pop();
    // pick first free lane or first parent's lane
    const parents = (c.spec?.parents || []).filter(p => byShа[p]);
    let lane = parents.length
      ? (lanes[parents[0]] ?? activeLanes.findIndex(s => s === null))
      : -1;
    if (lane < 0) lane = activeLanes.length;
    lanes[sha7] = lane;
    activeLanes[lane] = sha7;
  });

  const COL = 16, ROW = 28, R = 5;
  const maxLane = Math.max(...Object.values(lanes), 0);
  const W = (maxLane + 1) * COL + 200;
  const H = sorted.length * ROW + 8;

  const LANE_COLORS = ['#58a6ff','#3fb950','#f78166','#d2a8ff','#ffa657','#79c0ff','#56d364'];
  const lc = l => LANE_COLORS[l % LANE_COLORS.length];

  let edges = '', nodes = '', labels = '';

  sorted.forEach((c, i) => {
    const sha7 = c.spec?.sha ? c.spec.sha.slice(0, 7) : c.name.split('-').pop();
    const lane = lanes[sha7] ?? 0;
    const cx = lane * COL + R + 2;
    const cy = i * ROW + ROW / 2 + 4;
    const color = lc(lane);

    // draw edges to parents
    (c.spec?.parents || []).forEach(psha => {
      if (!byShа[psha]) return;
      const pidx = sorted.findIndex(x =>
        (x.spec?.sha?.slice(0, 7) || x.name.split('-').pop()) === psha);
      if (pidx < 0) return;
      const plane = lanes[psha] ?? 0;
      const px = plane * COL + R + 2;
      const py = pidx * ROW + ROW / 2 + 4;
      edges += `<path d="M${cx},${cy} C${cx},${(cy+py)/2} ${px},${(cy+py)/2} ${px},${py}"
        fill="none" stroke="${lc(lane)}" stroke-width="1.5" opacity=".7"/>`;
    });

    // draw node
    nodes += `<circle cx="${cx}" cy="${cy}" r="${R}" fill="${color}"/>`;

    // label
    const sp = c.spec || {};
    const subj = (sp.subject || '').slice(0, 60);
    const meta = `${esc(sp.author?.split(' ')[0] || '')} ${sp.date ? _ago(sp.date) : ''}`;
    labels += `<text x="${(maxLane + 1) * COL + 8}" y="${cy + 4}"
      font-size="11" fill="var(--text)" font-family="monospace">
      <tspan fill="${color}">${esc(sha7)}</tspan>
      <tspan dx="6" fill="var(--text)">${esc(subj)}</tspan>
      <tspan dx="8" fill="var(--muted)" font-size="10">${esc(meta)}</tspan>
    </text>`;
  });

  el.innerHTML = `<div style="overflow:auto;height:100%;padding:8px">
    <svg width="${W}" height="${H}" style="min-width:${W}px">
      <g>${edges}</g>
      <g>${nodes}</g>
      <g>${labels}</g>
    </svg>
  </div>`;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
async function _fetchByLabel(kind, labelKey, labelVal) {
  const all = await apiFetch(`${API}/${kind}`);
  return (all || []).filter(r => r.labels?.[labelKey] === labelVal);
}

async function _runBackfill(name) {
  toast(`⏮ backfill ${name}…`);
  try {
    const r = await apiFetch(`${API}/_cmd`, {
      method: 'POST',
      body: JSON.stringify({text: `/repo backfill ${name}`}),
    });
    toast(r.output || 'ok');
  } catch (e) { toast('erro: ' + e.message, true); }
}

async function _runSync(name) {
  toast(`↻ sync ${name}…`);
  try {
    const r = await apiFetch(`${API}/_run`, {
      method: 'POST',
      body: JSON.stringify({routine: 'repo-sync'}),
    });
    toast(r.ok ? 'sync ok' : 'sync: ' + (r.output || 'erro'), !r.ok);
  } catch (e) { toast('erro: ' + e.message, true); }
}
