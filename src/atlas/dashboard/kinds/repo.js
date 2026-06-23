/* Repo render especializada (ADR-0020 / E7-08).
 * Features: 5 abas (Overview/Branches/Commits/Graph/Config), log de execução
 * em tempo real, fullscreen destacável, edição de spec via formulário.
 */

// Estado de log por repo: name → {lines:[], running:bool}
const _repoLogs = {};

registerRender('Repo', async function renderRepo(r, container) {
  const name = r.name;
  container.innerHTML = _repoShell(r);
  _wireRepo(name, container);
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
        <button class="btn" data-action="sync" title="Executar nora-sync">↻ Sync</button>
        <button class="btn" data-action="backfill" title="/repo backfill">⏮ Backfill</button>
        <button class="btn rk-fullscreen-btn" onclick="toggleFullscreen()" title="Tela cheia">⤢</button>
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
      <button class="rk-tab" data-tab="log" id="rk-log-tab-${esc(r.name)}">📋 Log</button>
      <button class="rk-tab" data-tab="config">⚙️ Config</button>
    </div>
    <div class="rk-body" id="rk-body-${esc(r.name)}">
      <div style="padding:20px;color:var(--muted)">carregando…</div>
    </div>
  </div>`;
}

function _wireRepo(name, container) {
  container.querySelector('[data-action="backfill"]')
    ?.addEventListener('click', () => _runBackfill(name, container));
  container.querySelector('[data-action="sync"]')
    ?.addEventListener('click', () => _runSync(name, container));

  container.querySelectorAll('.rk-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.rk-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      _loadRepoTab(name, btn.dataset.tab, container);
    });
  });
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
      case 'log':       _tabLog(name, body); break;
      case 'config':    await _tabConfig(name, body); break;
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

  commits.sort((a, b) =>
    String(b.spec?.date || '').localeCompare(String(a.spec?.date || '')));

  el.innerHTML = `<div class="rk-commit-list">
    ${commits.slice(0, 150).map(c => {
      const sp = c.spec || {};
      const isMerge = sp.is_merge;
      const adds = sp.insertions ?? 0, dels = sp.deletions ?? 0;
      const bLabel = c.labels?.branch
        ? `<span class="rk-badge branch">${esc(c.labels.branch)}</span>` : '';
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

// ── Tab: Graph (git-graph com cards expansíveis) ─────────────────────────────
async function _tabGraph(name, el) {
  el.innerHTML = '<div style="padding:16px;color:var(--muted)">Carregando…</div>';

  const [commits, diffs, branches] = await Promise.all([
    _fetchByLabel('Commit', 'repo', name),
    _fetchByLabel('Diff', 'repo', name).catch(() => []),
    _fetchByLabel('Branch', 'repo', name).catch(() => []),
  ]);

  if (!commits.length) {
    el.innerHTML = '<div style="padding:16px;color:var(--muted)">Sem commits. Execute Sync ou Backfill primeiro.</div>';
    return;
  }

  // Normaliza sha7 em cada commit
  commits.forEach(c => {
    c._sha7 = (c.spec?.sha || c.name.split('-').pop()).slice(0, 7);
  });

  // Índice sha7 → commit e diff
  const bySha = {};
  commits.forEach(c => { bySha[c._sha7] = c; });
  const diffBySha = {};
  diffs.forEach(d => {
    const s = (d.labels?.commit || d.spec?.sha || '').slice(0, 7);
    if (s) diffBySha[s] = d;
  });
  // sha7 → [branch name] (da última branch que aponta para esse commit)
  const branchBySha = {};
  branches.forEach(b => {
    const s = (b.spec?.last_commit || b.status?.last_commit || '').slice(0, 7);
    if (!s) return;
    if (!branchBySha[s]) branchBySha[s] = [];
    branchBySha[s].push(b.spec?.branch || b.name);
  });

  // Ordena: mais recente primeiro
  const sorted = [...commits].sort((a, b) =>
    String(b.spec?.date || '').localeCompare(String(a.spec?.date || '')));

  // ── Lane algorithm ──────────────────────────────────────────────────────────
  // openSlots[i] = sha7 que essa lane está esperando (null = livre)
  const openSlots = [];
  const laneOf = {};

  sorted.forEach(c => {
    const sha7 = c._sha7;
    const parents = (c.spec?.parents || [])
      .map(p => p.slice(0, 7)).filter(p => bySha[p]);

    // Encontra o slot que estava esperando por este commit
    let slot = openSlots.indexOf(sha7);
    if (slot < 0) {
      slot = openSlots.indexOf(null);
      if (slot < 0) slot = openSlots.length;
    }
    openSlots[slot] = null;
    laneOf[sha7] = slot;

    // Primeiro pai continua no mesmo slot; demais abrem novos
    parents.forEach((p, i) => {
      if (i === 0) {
        openSlots[slot] = p;
      } else {
        let pSlot = openSlots.indexOf(p);
        if (pSlot < 0) { pSlot = openSlots.indexOf(null); }
        if (pSlot < 0) { pSlot = openSlots.length; }
        openSlots[pSlot] = p;
      }
    });
  });

  const maxLane = Math.max(...Object.values(laneOf), 0);
  const COLORS = ['#58a6ff','#3fb950','#f78166','#d2a8ff','#ffa657','#79c0ff','#56d364','#e3b341'];
  const lc = l => COLORS[l % COLORS.length];

  // ── Inline SVG por linha (colunas de lanes) ─────────────────────────────────
  // Pré-calcula o estado das lanes em cada linha (quais estão abertas)
  const laneStates = []; // index i → Set of sha7s "em trânsito" após processar commit i
  const openAfter = [];  // cópia do openSlots após cada commit
  {
    const slots = [];
    sorted.forEach((c, i) => {
      const sha7 = c._sha7;
      const parents = (c.spec?.parents || [])
        .map(p => p.slice(0, 7)).filter(p => bySha[p]);
      const slot = laneOf[sha7];
      // Reset slot e atribui pais
      slots[slot] = null;
      parents.forEach((p, j) => {
        if (j === 0) { slots[slot] = p; }
        else {
          let ps = slots.indexOf(p);
          if (ps < 0) ps = slots.indexOf(null);
          if (ps < 0) ps = slots.length;
          slots[ps] = p;
        }
      });
      openAfter[i] = [...slots];
    });
  }

  function _graphSvg(i) {
    const c = sorted[i];
    const sha7 = c._sha7;
    const lane = laneOf[sha7];
    const nLanes = maxLane + 1;
    const W = nLanes * 14 + 4;
    const H = 36;
    const cx = lane * 14 + 8;
    const cy = H / 2;
    const color = lc(lane);

    let lines = '';
    // Traços verticais dos lanes ativos ANTES deste commit (linha de cima)
    const before = i > 0 ? openAfter[i - 1] : [];
    before.forEach((sha, l) => {
      if (!sha) return;
      const x = l * 14 + 8;
      lines += `<line x1="${x}" y1="0" x2="${x}" y2="${cy}" stroke="${lc(l)}" stroke-width="1.5" opacity=".6"/>`;
    });

    // Traços verticais dos lanes ativos DEPOIS deste commit (linha de baixo)
    const after = openAfter[i] || [];
    after.forEach((sha, l) => {
      if (!sha) return;
      const x = l * 14 + 8;
      lines += `<line x1="${x}" y1="${cy}" x2="${x}" y2="${H}" stroke="${lc(l)}" stroke-width="1.5" opacity=".6"/>`;
    });

    // Curvas para pais em lanes diferentes
    const parents = (c.spec?.parents || []).map(p => p.slice(0, 7)).filter(p => bySha[p]);
    parents.forEach((p, j) => {
      if (j === 0 && laneOf[p] === lane) return; // mesmo lane — já coberto pela linha
      const pLane = laneOf[p] ?? 0;
      const px = pLane * 14 + 8;
      if (j === 0) {
        // Primeiro pai em lane diferente (movimento de lane)
        lines += `<path d="M${cx},${cy} Q${cx},${H} ${px},${H}" fill="none" stroke="${color}" stroke-width="1.5" opacity=".7"/>`;
      } else {
        // Merge: curva do lane do pai até a posição do commit
        lines += `<path d="M${cx},${cy} Q${px},${cy} ${px},${H}" fill="none" stroke="${lc(pLane)}" stroke-width="1.5" opacity=".6"/>`;
      }
    });

    // Dot
    lines += `<circle cx="${cx}" cy="${cy}" r="4.5" fill="${color}" stroke="var(--bg)" stroke-width="1.5"/>`;

    return `<svg width="${W}" height="${H}" style="flex-shrink:0;overflow:visible">${lines}</svg>`;
  }

  // ── Renderiza cards ─────────────────────────────────────────────────────────
  const rows = sorted.map((c, i) => {
    const sha7 = c._sha7;
    const sp = c.spec || {};
    const lane = laneOf[sha7];
    const color = lc(lane);
    const diff = diffBySha[sha7];
    const brs = branchBySha[sha7] || [];
    const ago = sp.date ? _ago(sp.date) : '';
    const author = (sp.author || '').split('<')[0].trim();
    const subject = sp.subject || sp.message || sha7;

    const brTags = brs.map(b =>
      `<span class="rk-gv-br" style="background:${color}22;color:${color};border-color:${color}55">${esc(b)}</span>`
    ).join('');

    const stats = (sp.files_changed || sp.insertions || sp.deletions)
      ? `<span class="rk-gv-stats">${sp.files_changed||0} ✱ +${sp.insertions||0} -${sp.deletions||0}</span>` : '';

    const hasDiff = !!diff;
    const expandable = hasDiff ? ' rk-gv-expandable' : '';

    return `<div class="rk-gv-row${expandable}" data-i="${i}">
      <div class="rk-gv-graph-col">${_graphSvg(i)}</div>
      <div class="rk-gv-info">
        <div class="rk-gv-top">
          <span class="rk-gv-sha" style="color:${color}">${esc(sha7)}</span>
          ${brTags}
          <span class="rk-gv-msg">${esc(subject)}</span>
          ${hasDiff ? '<span class="rk-gv-arrow">▶</span>' : ''}
        </div>
        <div class="rk-gv-meta">${esc(author)}${ago ? ' · ' + esc(ago) : ''}${stats}</div>
        ${hasDiff ? `<div class="rk-gv-detail">
          ${diff.spec?.explicacao ? `<div class="rk-gv-explain">${markdownToHtml(diff.spec.explicacao)}</div>` : ''}
          ${diff.spec?.diff_raw ? `<pre class="rk-gv-diff">${esc(diff.spec.diff_raw.slice(0, 4000))}</pre>` : ''}
        </div>` : ''}
      </div>
    </div>`;
  }).join('');

  el.innerHTML = `<div class="rk-gv-wrap"><div class="rk-gv-list">${rows}</div></div>`;

  // Click para expandir/colapsar
  el.querySelectorAll('.rk-gv-expandable').forEach(row => {
    row.addEventListener('click', () => {
      row.classList.toggle('open');
      const arrow = row.querySelector('.rk-gv-arrow');
      if (arrow) arrow.textContent = row.classList.contains('open') ? '▼' : '▶';
    });
  });
}

// ── Tab: Log (progresso/resultado de operações) ───────────────────────────────
function _tabLog(name, el) {
  const state = _repoLogs[name];
  if (!state) {
    el.innerHTML = `<div style="padding:24px 16px;color:var(--muted);font-size:13px">
      Nenhuma operação registrada. Use ↻ Sync ou ⏮ Backfill para iniciar.</div>`;
    return;
  }
  const spin = state.running
    ? `<div class="rk-log-spinner"><span class="ag-spin"></span>em execução…</div>` : '';
  const lines = (state.lines || []).map(l => {
    const cls = l.startsWith('❌') || l.startsWith('⚠') ? 'err'
               : l.startsWith('✅') || l.startsWith('📦') || l.startsWith('↻') ? 'ok'
               : '';
    return `<div class="rk-log-line ${cls}">${esc(l)}</div>`;
  }).join('');
  el.innerHTML = `<div class="rk-log">
    ${spin}
    <div class="rk-log-lines">${lines || '<span style="color:var(--muted)">sem saída</span>'}</div>
  </div>`;
}

// ── Tab: Config (formulário de spec do Repo) ──────────────────────────────────
async function _tabConfig(name, el) {
  const repoSchema = (allSchema && allSchema['Repo']?.spec) || [];
  let res;
  try {
    res = await apiFetch(`${API}/Repo/${encodeURIComponent(name)}`);
  } catch (e) {
    el.innerHTML = `<div style="padding:16px;color:var(--red)">Erro ao carregar: ${esc(e.message)}</div>`;
    return;
  }
  const spec = res.spec || {};
  const fields = repoSchema.length ? repoSchema : _repoDefaultFields();

  el.innerHTML = `<div class="rk-cfg-form">
    <div class="rk-section">
      <div class="rk-sec-title">⚙️ Configuração — ${esc(name)}</div>
      ${fields.map(f => _cfgField(f, spec[f.k])).join('')}
    </div>
    <div class="rk-cfg-footer">
      <button class="btn" id="rk-cfg-save-${esc(name)}" style="color:var(--green);border-color:var(--green)">💾 Salvar</button>
      <button class="btn" id="rk-cfg-reset-${esc(name)}">↺ Resetar</button>
      <span class="rk-cfg-status" id="rk-cfg-status-${esc(name)}"></span>
    </div>
  </div>`;

  const saveBtn = el.querySelector(`#rk-cfg-save-${CSS.escape(name)}`);
  const resetBtn = el.querySelector(`#rk-cfg-reset-${CSS.escape(name)}`);
  const statusEl = el.querySelector(`#rk-cfg-status-${CSS.escape(name)}`);

  saveBtn.addEventListener('click', async () => {
    saveBtn.disabled = true;
    statusEl.textContent = 'salvando…';
    statusEl.className = 'rk-cfg-status';
    try {
      const newSpec = _readCfgForm(el, fields, spec);
      await apiFetch(`${API}/Repo/${encodeURIComponent(name)}`, {
        method: 'PUT',
        body: JSON.stringify({
          kind: 'Repo', name,
          spec: newSpec,
          labels: res.labels || {},
          status: res.status || {},
        }),
      });
      statusEl.textContent = '✅ Salvo';
      statusEl.className = 'rk-cfg-status ok';
    } catch (e) {
      statusEl.textContent = '❌ ' + e.message;
      statusEl.className = 'rk-cfg-status err';
    } finally {
      saveBtn.disabled = false;
    }
  });

  resetBtn.addEventListener('click', () => _tabConfig(name, el));
}

function _cfgField(f, value) {
  const v = value ?? '';
  const hint = f.hint ? `<div class="rk-cfg-hint">${esc(f.hint)}</div>` : '';
  let inp;
  if (f.type === 'bool') {
    inp = `<label class="rk-cfg-toggle">
      <input type="checkbox" data-k="${f.k}" ${v ? 'checked' : ''}>
      <span>${esc(f.label)}</span>
    </label>`;
    return `<div class="rk-cfg-row">${inp}${hint}</div>`;
  }
  if (f.type === 'select') {
    inp = `<select data-k="${f.k}" class="rk-cfg-input">
      ${(f.opts || []).map(o => `<option${o === String(v) ? ' selected' : ''}>${esc(o)}</option>`).join('')}
    </select>`;
  } else if (f.type === 'area') {
    inp = `<textarea data-k="${f.k}" class="rk-cfg-input" rows="3">${esc(String(v))}</textarea>`;
  } else {
    inp = `<input type="${f.type === 'number' ? 'number' : 'text'}" data-k="${f.k}" class="rk-cfg-input" value="${esc(String(v))}">`;
  }
  return `<div class="rk-cfg-row">
    <label class="rk-cfg-label">${esc(f.label)}</label>
    ${inp}
    ${hint}
  </div>`;
}

function _readCfgForm(el, fields, existingSpec) {
  const spec = Object.assign({}, existingSpec);
  fields.forEach(f => {
    const inp = el.querySelector(`[data-k="${f.k}"]`);
    if (!inp) return;
    if (f.type === 'bool') spec[f.k] = inp.checked;
    else if (f.type === 'number') spec[f.k] = inp.value !== '' ? Number(inp.value) : undefined;
    else spec[f.k] = inp.value;
    if (spec[f.k] === '' || spec[f.k] === undefined) delete spec[f.k];
  });
  return spec;
}

function _repoDefaultFields() {
  return [
    {k:'url', type:'text', label:'URL', hint:'https://github.com/user/repo'},
    {k:'default_branch', type:'text', label:'Branch default', hint:'Vazio = detecta do remoto'},
    {k:'serialize', type:'select', label:'Serializar arquivos', opts:['off','docs','docs+code'], hint:'Extrai texto dos arquivos alterados'},
    {k:'analyze_branches', type:'text', label:'Analisar branches', hint:'default · all · lista por vírgula'},
    {k:'analyze_skip_merges', type:'bool', label:'Pular merges na análise', hint:''},
    {k:'analyze_min_lines', type:'number', label:'Mín. linhas p/ analisar', hint:'Ignora diffs menores'},
    {k:'analyze_max_per_run', type:'number', label:'Máx. análises por run', hint:'Disjuntor de budget IA'},
    {k:'stale_days', type:'number', label:'Dias p/ branch stale', hint:'Sem atividade além disso = stale'},
  ];
}

// ── Helpers ───────────────────────────────────────────────────────────────────
async function _fetchByLabel(kind, labelKey, labelVal) {
  const all = await apiFetch(`${API}/${kind}`);
  return (all || []).filter(r => r.labels?.[labelKey] === labelVal);
}

function _activateLogTab(name, container) {
  container.querySelectorAll('.rk-tab').forEach(b => b.classList.remove('active'));
  const logTab = container.querySelector('#rk-log-tab-' + CSS.escape(name));
  if (logTab) logTab.classList.add('active');
  const body = container.querySelector(`#rk-body-${CSS.escape(name)}`);
  if (body) _tabLog(name, body);
}

function _appendLog(name, line) {
  if (!_repoLogs[name]) _repoLogs[name] = {lines: [], running: false};
  _repoLogs[name].lines.push(line);
}

async function _runBackfill(name, container) {
  _repoLogs[name] = {lines: [`⏮ backfill ${name}…`], running: true};
  _activateLogTab(name, container);
  try {
    const r = await apiFetch(`${API}/_cmd`, {
      method: 'POST',
      body: JSON.stringify({text: `/repo backfill ${name}`}),
    });
    const out = r.output || (r.ok ? '✅ ok' : '❌ sem saída');
    out.split('\n').forEach(l => l && _appendLog(name, l));
    if (!r.ok && !out.includes('❌')) _appendLog(name, '❌ falhou');
  } catch (e) {
    _appendLog(name, `❌ ${e.message}`);
  } finally {
    _repoLogs[name].running = false;
    _activateLogTab(name, container);
  }
}

async function _runSync(name, container) {
  const jobName = name + '-sync';
  _repoLogs[name] = {lines: [`↻ iniciando ${jobName}…`], running: true};
  _activateLogTab(name, container);
  try {
    const r = await apiFetch(`${API}/_run`, {
      method: 'POST',
      body: JSON.stringify({routine: jobName}),
    });
    if (r.ok) {
      _appendLog(name, '✅ sync concluído');
      const out = r.output || '';
      out.split('\n').forEach(l => l.trim() && _appendLog(name, l));
    } else {
      _appendLog(name, `❌ ${r.error || r.output || 'falhou'}`);
    }
  } catch (e) {
    _appendLog(name, `❌ ${e.message}`);
  } finally {
    _repoLogs[name].running = false;
    _activateLogTab(name, container);
  }
}
