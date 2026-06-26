/* Job render especializada (ADR-0020).
 * Abas: 📊 Visão (info + executar + log + execuções) | ⚙️ Config.
 * Relações por label (P11): se spec.label aponta para um Repo, vira link.
 * Fullscreen destacável.
 */

const _jobLog = {}; // name → {lines:[], running:bool}

registerRender('Job', async function renderJob(r, container) {
  const name = r.name;
  container.__jobRes = r;
  container.innerHTML = _jobShell(r);
  _wireJob(name, r, container);
  _loadJobTab(name, r, 'overview', container);
});

function _jobShell(r) {
  const s = r.spec || {};
  const active = s.active;
  return `<div class="rk-wrap">
    <div class="rk-header">
      <span style="font-size:20px">🧩</span>
      <div style="flex:1;min-width:0">
        <div class="rk-title">${esc(r.name)}</div>
        <div style="font-size:11px;color:var(--muted)">${esc(s.description || s.coletar || '')}</div>
      </div>
      <div class="rk-actions">
        <button class="btn" data-action="run" title="Executar agora">▶ Executar</button>
        <button class="btn" data-action="toggle">${active ? '⏸ Desativar' : '▶ Ativar'}</button>
        <button class="btn rk-fullscreen-btn" onclick="toggleFullscreen()" title="Tela cheia">⤢</button>
      </div>
    </div>
    <div class="rk-meta-bar">
      ${active ? '<span class="rk-job-on">● ativo</span>' : '<span class="rk-job-off">○ inativo</span>'}
      ${s.schedule ? `<span style="font-size:11px;color:var(--muted)">🕒 ${esc(s.schedule)}</span>` : ''}
      ${s.coletar ? `<span style="font-size:11px;color:var(--muted)">⚙ <code>${esc(s.coletar)}</code></span>` : ''}
      <span style="flex:1"></span>
      ${s.label ? `<span style="font-size:11px">🔗 <strong onclick="openWhiteboard('Repo','${escJs(s.label)}')" style="color:var(--blue);cursor:pointer">${esc(s.label)}</strong></span>` : ''}
    </div>
    <div class="rk-tabbar">
      <button class="rk-tab active" data-tab="overview">📊 Visão</button>
      <button class="rk-tab" data-tab="config">⚙️ Config</button>
    </div>
    <div class="rk-body" id="job-body-${esc(r.name)}"><div style="padding:20px;color:var(--muted)">carregando…</div></div>
  </div>`;
}

function _wireJob(name, r, container) {
  container.querySelector('[data-action="run"]')?.addEventListener('click', () => _jobRun(name, container));
  container.querySelector('[data-action="toggle"]')?.addEventListener('click', () => _jobToggle(name, r, container));
  container.querySelectorAll('.rk-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.rk-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      _loadJobTab(name, r, btn.dataset.tab, container);
    });
  });
}

async function _loadJobTab(name, r, tab, container) {
  const body = container.querySelector(`#job-body-${CSS.escape(name)}`);
  if (!body) return;
  body.innerHTML = '<div style="padding:16px;color:var(--muted)">carregando…</div>';
  try {
    if (tab === 'overview') await _jobOverview(name, r, body);
    else if (tab === 'config') await _jobConfig(name, body);
  } catch (e) {
    body.innerHTML = `<div style="padding:16px;color:var(--red)">erro: ${esc(e.message)}</div>`;
  }
}

// ── Visão: info + log + execuções recentes ────────────────────────────────────
async function _jobOverview(name, r, el) {
  const s = r.spec || {};
  const info = [
    ['Agenda', s.schedule || '—'],
    ['Collect', s.coletar || '—'],
    ['Modelo', s.model && s.model !== 'none' ? s.model : 'sem IA'],
    ['Saída', s.saida || s.output || '—'],
    ['Label (vínculo)', s.label || '—'],
    ['Ativo', s.active ? 'sim' : 'não'],
  ].map(([k, v]) => `<div class="job-info-row"><span class="job-info-k">${esc(k)}</span><span class="job-info-v">${esc(v)}</span></div>`).join('');

  el.innerHTML = `
    <div class="rk-section">
      <div class="rk-sec-title">📋 Informações</div>
      <div class="job-info">${info}</div>
    </div>
    <div class="rk-section">
      <div class="rk-sec-title">📜 Execuções recentes</div>
      <div id="job-runs-${esc(name)}" style="color:var(--muted)">carregando…</div>
    </div>
    <div class="rk-section">
      <div class="rk-sec-title">📤 Saída da última execução manual</div>
      <div id="job-out-${esc(name)}" class="rk-log-lines" style="max-height:240px">${_jobLog[name]?.lines?.map(l => `<div class="rk-log-line">${esc(l)}</div>`).join('') || '<span style="color:var(--muted)">execute para ver a saída</span>'}</div>
    </div>`;

  // execuções recentes (do /_status, filtrando por este job)
  apiFetch(`${API}/_status`).then(st => {
    const runs = (st.recent_runs || []).filter(x => x.rotina === name).slice(0, 10);
    const box = el.querySelector(`#job-runs-${CSS.escape(name)}`);
    if (!box) return;
    box.innerHTML = runs.length
      ? runs.map(x => `<div class="job-run-row">
          <span class="${x.status === 'ok' ? 'rk-job-on' : 'rk-job-off'}">${x.status === 'ok' ? '✅' : '❌'} ${esc(x.status)}</span>
          <span style="color:var(--muted);font-size:11px">${esc(x.camada || '')}</span>
          <span style="color:var(--muted);font-size:11px;margin-left:auto">${esc(fmtDt(x.terminado_em || x.iniciado_em))}</span>
        </div>`).join('')
      : '<span style="color:var(--muted)">nenhuma execução registrada</span>';
  }).catch(() => {});
}

async function _jobRun(name, container) {
  _jobLog[name] = {lines: [`▶ executando ${name}…`], running: true};
  // garante aba Visão ativa
  container.querySelectorAll('.rk-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === 'overview'));
  const r = container.__jobRes || {name, spec: {}};
  const body = container.querySelector(`#job-body-${CSS.escape(name)}`);
  if (body) await _jobOverview(name, r, body);
  const out = container.querySelector(`#job-out-${CSS.escape(name)}`);
  try {
    const res = await apiFetch(`${API}/_run`, {method: 'POST', body: JSON.stringify({routine: name})});
    const lines = [res.ok ? '✅ concluído' : `❌ ${res.error || 'falhou'}`];
    (res.output || '').split('\n').forEach(l => l.trim() && lines.push(l));
    _jobLog[name] = {lines, running: false};
    if (out) out.innerHTML = lines.map(l => `<div class="rk-log-line ${l.startsWith('❌') ? 'err' : l.startsWith('✅') ? 'ok' : ''}">${esc(l)}</div>`).join('');
  } catch (e) {
    if (out) out.innerHTML = `<div class="rk-log-line err">❌ ${esc(e.message)}</div>`;
  }
}

async function _jobToggle(name, r, container) {
  const cur = !!(r.spec || {}).active;
  try {
    await apiFetch(`${API}/Job/${encodeURIComponent(name)}`, {
      method: 'PUT',
      body: JSON.stringify({kind: 'Job', name, spec: {active: !cur}, labels: r.labels || {}, status: r.status || {}}),
    });
    toast(`${name}: ${!cur ? 'ativado' : 'desativado'}`);
    const fresh = await apiFetch(`${API}/Job/${encodeURIComponent(name)}`);
    container.__jobRes = fresh;
    container.innerHTML = _jobShell(fresh);
    _wireJob(name, fresh, container);
    _loadJobTab(name, fresh, 'overview', container);
  } catch (e) { toast('❌ ' + e.message, true); }
}

// ── Config ────────────────────────────────────────────────────────────────────
async function _jobConfig(name, el) {
  const res = await apiFetch(`${API}/Job/${encodeURIComponent(name)}`);
  const s = res.spec || {};
  const fields = [
    {k: 'description', label: 'Descrição', type: 'text'},
    {k: 'schedule', label: 'Agenda (cron/preset)', type: 'text'},
    {k: 'coletar', label: 'Collect (fn)', type: 'text'},
    {k: 'label', label: 'Label (vínculo, ex.: nome do Repo)', type: 'text'},
    {k: 'model', label: 'Modelo IA (none = sem IA)', type: 'text'},
    {k: 'saida', label: 'Saída (telegram/none)', type: 'text'},
    {k: 'active', label: 'Ativo', type: 'bool'},
  ];
  el.innerHTML = `<div class="rk-cfg-form">
    <div class="rk-section">
      <div class="rk-sec-title">⚙️ Configuração — ${esc(name)}</div>
      ${fields.map(f => {
        const v = s[f.k];
        if (f.type === 'bool') {
          return `<div class="rk-cfg-row"><label class="rk-cfg-label">${esc(f.label)}</label>
            <label class="rk-cfg-toggle"><input type="checkbox" data-k="${f.k}" ${v ? 'checked' : ''}> ${v ? 'sim' : 'não'}</label></div>`;
        }
        return `<div class="rk-cfg-row"><label class="rk-cfg-label">${esc(f.label)}</label>
          <input class="rk-cfg-input" data-k="${f.k}" value="${esc(v == null ? '' : String(v))}"></div>`;
      }).join('')}
    </div>
    <div class="rk-cfg-footer">
      <button class="btn" id="job-save-${esc(name)}" style="color:var(--green);border-color:var(--green)">💾 Salvar</button>
      <span class="rk-cfg-status" id="job-status-${esc(name)}"></span>
    </div>
  </div>`;

  el.querySelector(`#job-save-${CSS.escape(name)}`).addEventListener('click', async () => {
    const st = el.querySelector(`#job-status-${CSS.escape(name)}`);
    st.textContent = 'salvando…'; st.className = 'rk-cfg-status';
    try {
      const spec = {...s};
      fields.forEach(f => {
        const inp = el.querySelector(`[data-k="${f.k}"]`);
        if (!inp) return;
        spec[f.k] = f.type === 'bool' ? inp.checked : inp.value;
      });
      await apiFetch(`${API}/Job/${encodeURIComponent(name)}`, {
        method: 'PUT',
        body: JSON.stringify({kind: 'Job', name, spec, labels: res.labels || {}, status: res.status || {}}),
      });
      st.textContent = '✅ salvo'; st.className = 'rk-cfg-status ok';
    } catch (e) { st.textContent = '❌ ' + e.message; st.className = 'rk-cfg-status err'; }
  });
}
