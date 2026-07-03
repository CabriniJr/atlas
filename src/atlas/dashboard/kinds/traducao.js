/* Render especializada do Kind Traducao (ADR-0030).
 * Prévia grátis de custo (GET /_estimar), disparo da tradução em background
 * (POST /_traduzir) e barra de progresso via polling do status (progresso_pct).
 */

registerRender('Traducao', function renderTraducao(r, container) {
  container.innerHTML = _trShell(r);
  _trWire(r.name, container);
});

function _trShell(r) {
  const s = r.spec || {};
  const st = r.status || {};
  const origem = s.origem || '';
  const io = s.idioma_origem || 'en';
  const id = s.idioma_destino || 'pt-BR';
  const motor = s.motor || 'ollama';
  return `<div class="tr-wrap" style="padding:16px;max-width:720px">
    <div class="tr-header" style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
      <span style="font-size:20px">📖</span>
      <div style="flex:1;min-width:0">
        <div style="font-weight:600;font-size:16px">${esc(r.name)}</div>
        <div style="color:var(--muted);font-size:12px">
          <span class="ag-badge ${esc(motor)}">${esc(motor)}</span>
          ${esc(io)} → ${esc(id)}
        </div>
      </div>
      <button class="btn danger" title="Apagar esta tradução e seus arquivos gerados"
        onclick="deleteResource('Traducao','${escJs(r.name)}')"
        style="font-size:12px;padding:4px 10px">🗑 Apagar</button>
    </div>
    <div style="color:var(--muted);font-size:13px;margin-bottom:12px;word-break:break-all">
      ${origem ? '📄 ' + esc(origem) : '<span style="color:var(--red)">sem PDF de origem (edite o spec)</span>'}
    </div>
    <div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap">
      <input type="file" id="tr-file" accept="application/pdf" style="display:none">
      <button class="btn" id="tr-upload">⬆️ Enviar PDF</button>
      <button class="btn" id="tr-estimar" ${origem ? '' : 'disabled'}>💵 Estimar</button>
      <button class="btn" id="tr-config-toggle">⚙️ Config</button>
      <button class="btn" id="tr-render" title="Re-renderiza o PDF a partir do cache já pago — não gasta IA" ${origem ? '' : 'disabled'}>🎨 Só re-renderizar (grátis)</button>
      <button class="btn" id="tr-previa" title="Renderiza uma prévia do que já foi traduzido, mesmo com a tradução rodando" ${origem ? '' : 'disabled'}>📸 Prévia agora</button>
      <button class="btn" id="tr-traduzir" style="border-color:var(--green);color:var(--green)" ${origem ? '' : 'disabled'}>▶ Traduzir</button>
      <button class="btn" id="tr-pausar" title="Pausa entre páginas (ADR-0045) — retoma de onde parou" style="display:none;border-color:var(--yellow,#d9a441);color:var(--yellow,#d9a441)">⏸ Pausar</button>
    </div>
    <div id="tr-config" style="display:none">${_trConfig(s)}</div>
    <div id="tr-pool">${_trPoolPanel()}</div>
    <div id="tr-estimativa"></div>
    <div id="tr-progresso">${_trProgresso(st, r.name)}</div>
  </div>`;
}

// Pool de execução de traduções (ADR-0038): visibilidade agregada (quem roda/na
// fila) + escalonamento em runtime ("réplicas"). Aparece em qualquer Traducao
// aberta — é estado global da instância, não deste recurso.
function _trPoolPanel() {
  return `<div style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:10px 12px;margin-bottom:12px;font-size:12px">
    <div style="color:var(--muted)">🧵 carregando pool de tradução…</div>
  </div>`;
}

function _trPoolHtml(p) {
  const chip = (label, cor) => `<span class="ag-badge" style="cursor:pointer;border-color:${cor};color:${cor}"
    title="abrir ${esc(label)}" onclick="loadAndRender('Traducao','${escJs(label)}')">${esc(label)}</span>`;
  const rodando = (p.rodando || []).map(l => chip(l, 'var(--green)')).join(' ')
    || '<span style="color:var(--muted)">—</span>';
  const fila = (p.fila || []).map(l => chip(l, 'var(--yellow,#d9a441)')).join(' ')
    || '<span style="color:var(--muted)">—</span>';
  return `<div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:8px;flex-wrap:wrap">
      <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px">🧵 Pool de tradução</div>
      <div style="display:flex;gap:6px;align-items:center">
        <span style="color:var(--muted);font-size:11px">réplicas (concorrência)</span>
        <input id="tr-pool-max" type="number" min="1" value="${esc(String(p.max_concorrente))}" style="width:48px">
        <button class="btn" id="tr-pool-escalar" style="font-size:11px;padding:2px 8px">⇕ escalar</button>
        <span id="tr-pool-msg" style="font-size:11px;color:var(--muted)"></span>
      </div>
    </div>
    <div style="display:flex;gap:18px;flex-wrap:wrap">
      <div>▶ rodando (${(p.rodando || []).length}/${p.max_concorrente}): ${rodando}</div>
      <div>⏳ fila (${(p.fila || []).length}): ${fila}</div>
    </div>`;
}

// Painel de controle da criação (ADR-0034/0035 + E9): modelo por estágio e params.
// spec.traducao afeta o cache de IA; spec.render (min_fonte/notas) não (E9-05).
function _trConfig(s) {
  const v = (k, d) => (s[k] != null ? s[k] : d);
  const bool = (k, d) => (v(k, d) === true || v(k, d) === 'true');
  const row = (lbl, inner) => `<label style="display:flex;justify-content:space-between;align-items:center;gap:10px;font-size:13px;margin:4px 0"><span style="color:var(--muted)">${lbl}</span>${inner}</label>`;
  const inp = (id, val, ph = '', w = 150) => `<input id="${id}" value="${esc(String(val ?? ''))}" placeholder="${esc(ph)}" style="width:${w}px">`;
  const chk = (id, on) => `<input type="checkbox" id="${id}" ${on ? 'checked' : ''}>`;
  return `<div style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px 14px;margin-bottom:12px">
    <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Tradução (afeta a IA — mudar re-traduz)</div>
    ${row('Motor', `<select id="cfg-motor" style="width:150px"><option ${v('motor','ollama')==='ollama'?'selected':''}>ollama</option><option ${v('motor','ollama')==='claude'?'selected':''}>claude</option></select>`)}
    ${row('Modelo (refino)', inp('cfg-modelo', v('modelo',''), 'default'))}
    ${row('Refinar (LLM)', chk('cfg-refino', bool('refino', true)))}
    ${row('Blocos por lote', inp('cfg-lote', v('lote_refino', 60), '', 80))}
    ${row('Comparador de consistência', chk('cfg-comparador', bool('comparador', false)))}
    ${row('Modelo do comparador', inp('cfg-modelo-comp', v('modelo_comparador',''), 'default (Opus)'))}
    <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin:10px 0 6px">Render (não gasta IA — grátis iterar)</div>
    ${row('Motor de render', `<select id="cfg-motor-render" style="width:150px"><option value="html" ${v('render_motor','html')==='html'?'selected':''}>editorial (HTML)</option><option value="pymupdf" ${v('render_motor')==='pymupdf'?'selected':''}>in-place (pymupdf)</option></select>`)}
    ${row('Fonte mínima (% legibilidade)', inp('cfg-minfonte', v('min_fonte_pct', 90), '', 80))}
    ${row('Notas de rodapé (termos mantidos)', chk('cfg-notas', bool('notas_rodape', false)))}
    <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin:10px 0 6px">Automação (ADR-0035)</div>
    ${row('Retomada após escassez (segundos)', inp('cfg-janela', v('janela_retomada_seg', 18000), '5h = 18000', 100))}
    <div style="display:flex;gap:8px;margin-top:10px">
      <button class="btn" id="tr-config-save" style="border-color:var(--green);color:var(--green)">💾 Salvar config</button>
      <span id="tr-config-msg" style="font-size:12px;color:var(--muted);align-self:center"></span>
    </div>
  </div>`;
}

function _trDur(seg) {
  if (seg == null || seg < 0) return '';
  seg = Math.round(seg);
  const m = Math.floor(seg / 60), s = seg % 60;
  return m ? `${m}m${String(s).padStart(2, '0')}s` : `${s}s`;
}

function _trLog(st) {
  const log = st.log || [];
  if (!log.length) return '';
  const linhas = log.slice(-30).map(e => {
    const t = (e.t || '').slice(11, 19);
    return `<div style="display:flex;gap:8px"><span style="color:var(--muted);flex:0 0 auto">${esc(t)}</span><span>${esc(e.msg || '')}</span></div>`;
  }).join('');
  return `<div style="margin-top:12px">
    <div style="font-size:11px;color:var(--muted);margin-bottom:4px">📋 atividade</div>
    <div id="tr-log" style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:8px 10px;font-size:12px;font-family:monospace;max-height:200px;overflow-y:auto;line-height:1.6">${linhas}</div>
  </div>`;
}

// Bloco da prévia (snapshot renderizado durante a tradução) + link de download.
function _trPreviaBox(st, name) {
  if (st.previa_gerando) {
    return `<div style="margin-top:8px;font-size:12px;color:var(--blue)">📸 gerando prévia do que já foi traduzido…</div>`;
  }
  if (st.previa_erro) {
    return `<div style="margin-top:8px;font-size:12px;color:var(--red)">📸 prévia falhou: ${esc(st.previa_erro)}</div>`;
  }
  if (st.previa) {
    const q = st.previa_em ? ` (${esc(String(st.previa_em).slice(11, 16))})` : '';
    return `<div style="margin-top:8px"><button class="btn" style="border-color:var(--blue);color:var(--blue)" onclick="trDownloadPrevia('${escJs(name || '')}')">⬇️ Baixar prévia${q}</button></div>`;
  }
  return '';
}

// Log fino das chamadas de IA no refino (visibilidade do gasto): lote, blocos, ms, ✓/✗.
function _trLogIa(st) {
  const l = st.log_ia || [];
  if (!l.length) return '';
  const linhas = l.slice(-40).map(e => {
    const t = (e.t || '').slice(11, 19);
    const cor = e.ok === false ? 'var(--red)' : 'var(--muted)';
    return `<div style="display:flex;gap:8px"><span style="color:var(--muted);flex:0 0 auto">${esc(t)}</span><span style="color:${cor}">${esc(e.msg || '')}</span></div>`;
  }).join('');
  return `<div style="margin-top:12px">
    <div style="font-size:11px;color:var(--muted);margin-bottom:4px">🔬 chamadas de IA (refino)</div>
    <div id="tr-logia" style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:8px 10px;font-size:12px;font-family:monospace;max-height:220px;overflow-y:auto;line-height:1.6">${linhas}</div>
  </div>`;
}

function _trExtras(st, name) {
  return _trPreviaBox(st, name) + _trLogIa(st);
}

// Controles reais (ADR-0045): recomeçar do zero (apaga cache) ou re-refinar
// (mantém a MT bruta, descarta só o refinado — força um novo passe de IA).
function _trBtnsControle(name) {
  return `<button class="btn" title="Apaga o cache (MT bruta + refinado) e recomeça do zero"
      onclick="trRecomecar('${escJs(name || '')}')">🔁 Recomeçar do zero</button>
    <button class="btn" title="Descarta só o refinado (mantém a MT bruta); útil após trocar de agente/modelo"
      onclick="trRerefinar('${escJs(name || '')}')">♻️ Re-refinar</button>`;
}

async function trRecomecar(name) {
  if (!confirm(`Apagar todo o cache de "${name}" e recomeçar do zero?`)) return;
  try {
    await apiFetch(API + '/_traduzir_recomecar', { method: 'POST', body: JSON.stringify({ label: name }) });
    await loadAndRender('Traducao', name);
  } catch (err) {
    alert('recomeçar falhou: ' + err.message);
  }
}

async function trRerefinar(name) {
  try {
    await apiFetch(API + '/_traduzir_rerefinar', { method: 'POST', body: JSON.stringify({ label: name }) });
    await loadAndRender('Traducao', name);
  } catch (err) {
    alert('re-refinar falhou: ' + err.message);
  }
}

function _trProgresso(st, name) {
  const fase = st.fase;
  if (!fase) return '';
  if (fase === 'erro') {
    return `<div style="color:var(--red);font-size:13px">⚠️ ${esc(st.erro || 'falhou')}</div>${_trLog(st)}`;
  }
  if (fase === 'pausado' || fase === 'retomando') {
    const manual = fase === 'pausado' && !st.retoma_em;
    const hora = st.retoma_em ? new Date(st.retoma_em).toLocaleTimeString().slice(0, 5) : '';
    const pp = st.paginas_prontas != null ? st.paginas_prontas : '';
    const retomando = fase === 'retomando';
    const cabec = retomando
      ? `<div style="color:var(--blue);font-size:13px">🔄 retomando de onde parou…</div>`
      : manual
      ? `<div style="color:var(--yellow,#d9a441);font-size:13px">⏸ pausado manualmente — ${pp} pág prontas<br><span style="font-size:12px;color:var(--muted)">retome quando quiser.</span></div>`
      : `<div style="color:var(--yellow,#d9a441);font-size:13px">⏸ pausado por escassez de token — ${pp} pág prontas<br><span style="font-size:12px;color:var(--muted)">retoma sozinho${hora ? ' às ' + esc(hora) : ''} (ADR-0035); ou retome agora.</span></div>`;
    const btns = `<div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap">
      ${retomando ? '' : `<button class="btn" style="border-color:var(--blue);color:var(--blue)" onclick="document.getElementById('tr-traduzir').click()">▶ Retomar agora</button>`}
      ${st.saida ? `<button class="btn" style="border-color:var(--green);color:var(--green)" onclick="trDownload('${escJs(name || '')}')">⬇️ Baixar (parcial)</button>` : ''}
      ${retomando ? '' : _trBtnsControle(name)}
    </div>`;
    return `${cabec}${btns}${_trExtras(st, name)}${_trLog(st)}`;
  }
  if (fase === 'pronto' || fase === 'parcial') {
    const parcial = fase === 'parcial';
    const pp = st.paginas_prontas != null ? st.paginas_prontas : '';
    const bl = st.blocos_traduzidos != null ? ` · ${st.blocos_traduzidos} blocos` : '';
    const dur = st.iniciado_em ? _trDur((Date.now() - new Date(st.iniciado_em)) / 1000) : '';
    const ga = (st.glossario_auto && st.glossario_auto.length)
      ? `<div style="color:var(--muted);font-size:12px;margin-top:6px">🔤 glossário auto: ${st.glossario_auto.map(esc).join(', ')}</div>`
      : '';
    const cabec = parcial
      ? `<div style="color:var(--yellow,#d9a441);font-size:13px">⏸ parcial — ${pp} pág${bl}${dur ? ' · ' + dur : ''}<br><span style="font-size:12px;color:var(--muted)">tokens acabaram no meio; o PDF saiu completo com a tradução bruta. Continue para refinar o restante.</span></div>`
      : `<div style="color:var(--green);font-size:13px">✓ pronto — ${pp} página(s)${bl}${dur ? ' · ' + dur : ''}</div>`;
    const btnContinuar = parcial
      ? `<button class="btn" style="border-color:var(--blue);color:var(--blue)" onclick="document.getElementById('tr-traduzir').click()">▶ Continuar refino</button>`
      : '';
    return `${cabec}
      ${st.saida ? `<div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap">${btnContinuar}<button class="btn" style="border-color:var(--green);color:var(--green)" onclick="trDownload('${escJs(name || '')}')">⬇️ Baixar ${parcial ? '(bruto)' : 'tradução'}</button>
      <button class="btn" title="Exportar como Markdown" onclick="trExport('${escJs(name || '')}','md')">📝 .md</button>
      <button class="btn" title="Exportar como EPUB (requer pandoc)" onclick="trExport('${escJs(name || '')}','epub')">📚 .epub</button>${_trBtnsControle(name)}</div>
      <div style="color:var(--muted);font-size:12px;margin-top:4px;word-break:break-all">💾 ${esc(st.saida)}</div>` : ''}${ga}${_trExtras(st, name)}${_trLog(st)}`;
  }
  // preparando (ex.: detectando glossário) ou traduzindo
  const pct = st.progresso_pct != null ? st.progresso_pct : 0;
  const tot = st.paginas_total || 0;
  const pr = st.paginas_prontas || 0;
  const atividade = st.atividade || (fase === 'preparando' ? 'preparando…' : `traduzindo… ${pr}/${tot} páginas`);
  const elapsed = st.iniciado_em ? _trDur((Date.now() - new Date(st.iniciado_em)) / 1000) : '';
  const eta = (st.eta_seg != null && fase === 'traduzindo') ? _trDur(st.eta_seg) : '';
  const tempo = [elapsed && '⏱ ' + elapsed, eta && 'faltam ~' + eta].filter(Boolean).join(' · ');
  return `<div style="display:flex;justify-content:space-between;align-items:baseline;font-size:13px;margin-bottom:6px">
      <span>${fase === 'preparando' ? '⚙️ ' : '📄 '}${esc(atividade)}</span>
      <span style="color:var(--muted);font-size:11px">${esc(tempo)}</span>
    </div>
    <div style="background:var(--border);border-radius:6px;height:10px;overflow:hidden">
      <div style="background:var(--blue);height:100%;width:${pct}%;transition:width .3s"></div>
    </div>
    <div style="text-align:right;color:var(--muted);font-size:11px;margin-top:3px">${pct}%${tot ? ` · ${pr}/${tot} pág` : ''}</div>
    ${_trExtras(st, name)}${_trLog(st)}`;
}

function _trWire(name, container) {
  const estBtn = container.querySelector('#tr-estimar');
  const trBtn = container.querySelector('#tr-traduzir');
  const estBox = container.querySelector('#tr-estimativa');
  const progBox = container.querySelector('#tr-progresso');
  const upBtn = container.querySelector('#tr-upload');
  const fileInput = container.querySelector('#tr-file');

  if (upBtn && fileInput) {
    upBtn.onclick = () => fileInput.click();
    fileInput.onchange = async () => {
      const f = fileInput.files && fileInput.files[0];
      if (!f) return;
      upBtn.disabled = true; upBtn.textContent = '⬆️ enviando…';
      try {
        const buf = await f.arrayBuffer();
        await apiFetch(API + '/_upload?name=' + encodeURIComponent(f.name) + '&label=' + encodeURIComponent(name),
          { method: 'POST', body: buf, headers: { 'Content-Type': 'application/pdf' } });
        await loadAndRender('Traducao', name);  // recarrega com a origem já preenchida
      } catch (err) {
        upBtn.disabled = false; upBtn.textContent = '⬆️ Enviar PDF';
        estBox.innerHTML = `<div style="color:var(--red);font-size:13px">upload falhou: ${esc(err.message)}</div>`;
      }
    };
  }

  if (estBtn) estBtn.onclick = async () => {
    estBtn.disabled = true; estBox.innerHTML = '<div style="color:var(--muted);font-size:13px">estimando…</div>';
    try {
      const e = await apiFetch(API + '/_estimar?label=' + encodeURIComponent(name));
      const custo = e.motor === 'ollama' ? 'grátis (local)' : '~$' + e.custo_usd_estimado;
      estBox.innerHTML = `<div class="tr-est" style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:10px 12px;font-size:13px;margin-bottom:12px">
        <b>Prévia</b> · ${e.paginas} pág · ${e.blocos_traduziveis} blocos · ${e.caracteres.toLocaleString()} chars<br>
        ~${e.tokens_estimados.toLocaleString()} tokens · custo estimado: <b>${custo}</b>
      </div>`;
    } catch (err) {
      estBox.innerHTML = `<div style="color:var(--red);font-size:13px">erro: ${esc(err.message)}</div>`;
    }
    estBtn.disabled = false;
  };

  const ATIVO = new Set(['preparando', 'traduzindo', 'retomando']);
  const pausarBtn = container.querySelector('#tr-pausar');
  let polling = null;
  function _autoScrollLog() {
    const el = container.querySelector('#tr-log');
    if (el) el.scrollTop = el.scrollHeight;
  }
  async function poll() {
    try {
      const r = await apiFetch(API + '/Traducao/' + encodeURIComponent(name));
      const st = r.status || {};
      progBox.innerHTML = _trProgresso(st, name);
      _autoScrollLog();
      const ativo = ATIVO.has(st.fase);
      if (pausarBtn) {
        pausarBtn.style.display = (st.fase === 'traduzindo' || st.fase === 'preparando') ? '' : 'none';
        pausarBtn.disabled = !!st.pausar_solicitado;
        pausarBtn.textContent = st.pausar_solicitado ? '⏸ pausando…' : '⏸ Pausar';
      }
      if (!ativo && !st.previa_gerando) {
        clearInterval(polling); polling = null;
        if (trBtn) trBtn.disabled = false;
      }
    } catch (e) { /* mantém tentando */ }
  }

  // Config: toggle + salvar (PUT do spec merjado). spec.render não invalida o cache.
  const cfgToggle = container.querySelector('#tr-config-toggle');
  const cfgBox = container.querySelector('#tr-config');
  if (cfgToggle && cfgBox) cfgToggle.onclick = () => {
    cfgBox.style.display = cfgBox.style.display === 'none' ? 'block' : 'none';
  };
  const cfgSave = container.querySelector('#tr-config-save');
  if (cfgSave) cfgSave.onclick = async () => {
    const msg = container.querySelector('#tr-config-msg');
    const num = (id, d) => { const n = parseInt(container.querySelector(id).value, 10); return isNaN(n) ? d : n; };
    const patch = {
      motor: container.querySelector('#cfg-motor').value,
      modelo: container.querySelector('#cfg-modelo').value.trim(),
      refino: container.querySelector('#cfg-refino').checked,
      lote_refino: num('#cfg-lote', 60),
      comparador: container.querySelector('#cfg-comparador').checked,
      modelo_comparador: container.querySelector('#cfg-modelo-comp').value.trim(),
      render_motor: container.querySelector('#cfg-motor-render').value,
      min_fonte_pct: num('#cfg-minfonte', 90),
      notas_rodape: container.querySelector('#cfg-notas').checked,
      janela_retomada_seg: num('#cfg-janela', 18000),
    };
    msg.textContent = 'salvando…';
    try { await _trPutSpec(name, patch); msg.textContent = '✓ salvo'; }
    catch (err) { msg.textContent = '⚠️ ' + err.message; }
  };

  async function iniciar(renderOnly) {
    trBtn.disabled = true;
    const rBtn = container.querySelector('#tr-render'); if (rBtn) rBtn.disabled = true;
    const ativ = renderOnly ? 're-renderizando (sem IA)…' : 'iniciando…';
    progBox.innerHTML = _trProgresso({ fase: 'preparando', progresso_pct: 0, atividade: ativ, iniciado_em: new Date().toISOString(), log: [] }, name);
    try {
      await _trPutSpec(name, { somente_render: !!renderOnly });  // flag lida pela rotina
      await apiFetch(API + '/_traduzir', { method: 'POST', body: JSON.stringify({ label: name }) });
      if (!polling) { polling = setInterval(poll, 1500); poll(); }
    } catch (err) {
      progBox.innerHTML = `<div style="color:var(--red);font-size:13px">erro: ${esc(err.message)}</div>`;
      trBtn.disabled = false; if (rBtn) rBtn.disabled = false;
    }
  }

  if (trBtn) trBtn.onclick = () => iniciar(false);
  const rBtn = container.querySelector('#tr-render');
  if (rBtn) rBtn.onclick = () => iniciar(true);

  if (pausarBtn) pausarBtn.onclick = async () => {
    pausarBtn.disabled = true;
    try {
      await apiFetch(API + '/_traduzir_pausar', { method: 'POST', body: JSON.stringify({ label: name }) });
    } catch (err) {
      alert('pausar falhou: ' + err.message);
      pausarBtn.disabled = false;
    }
  };

  // Prévia agora: renderiza um snapshot do cache atual sem interromper a tradução.
  const pvBtn = container.querySelector('#tr-previa');
  if (pvBtn) pvBtn.onclick = async () => {
    pvBtn.disabled = true;
    try {
      await apiFetch(API + '/_previa', { method: 'POST', body: JSON.stringify({ label: name }) });
      if (!polling) { polling = setInterval(poll, 1500); }
      poll();
    } catch (err) {
      alert('prévia falhou: ' + err.message);
    } finally {
      setTimeout(() => { pvBtn.disabled = false; }, 1500);
    }
  };

  // Pool de tradução (ADR-0038): 1 timer global (evita empilhar ao trocar de aba).
  const poolBox = container.querySelector('#tr-pool');
  async function _pollPool() {
    if (!poolBox || !poolBox.isConnected) { clearInterval(window._trPoolTimer); return; }
    try {
      const p = await apiFetch(API + '/_traducao_pool');
      poolBox.innerHTML = _trPoolHtml(p);
      const escBtn = poolBox.querySelector('#tr-pool-escalar');
      const msg = poolBox.querySelector('#tr-pool-msg');
      if (escBtn) escBtn.onclick = async () => {
        const n = parseInt(poolBox.querySelector('#tr-pool-max').value, 10);
        if (!n || n < 1) return;
        escBtn.disabled = true;
        try {
          await apiFetch(API + '/_traducao_pool/escalar', { method: 'POST', body: JSON.stringify({ max_concorrente: n }) });
          await _pollPool();
        } catch (err) { if (msg) msg.textContent = '⚠️ ' + err.message; }
        finally { escBtn.disabled = false; }
      };
    } catch (e) { /* mantém tentando */ }
  }
  if (window._trPoolTimer) clearInterval(window._trPoolTimer);
  _pollPool();
  window._trPoolTimer = setInterval(_pollPool, 3000);

  // Se já estava em andamento ao abrir, retoma o polling.
  const cur = container.querySelector('#tr-progresso').textContent || '';
  if (cur.includes('traduzindo') || cur.includes('preparando') || cur.includes('detectando') || cur.includes('retomando')) {
    if (trBtn) trBtn.disabled = true;
    polling = setInterval(poll, 1500);
  }
  _autoScrollLog();
}

// Salva o spec merjando um patch (PUT do recurso inteiro, como o editor genérico).
async function _trPutSpec(name, patch) {
  const r = await apiFetch(API + '/Traducao/' + encodeURIComponent(name));
  const spec = { ...(r.spec || {}), ...patch };
  const labels = r.labels || {};
  await apiFetch(API + '/Traducao/' + encodeURIComponent(name),
    { method: 'PUT', body: JSON.stringify({ labels, spec, status: r.status || {} }) });
}

// Baixa a prévia (snapshot parcial) renderizada durante a tradução.
async function trDownloadPrevia(name) {
  try {
    const h = {}; if (typeof TOKEN !== 'undefined' && TOKEN) h['Authorization'] = 'Bearer ' + TOKEN;
    const r = await fetch(API + '/_download?previa=1&label=' + encodeURIComponent(name),
      { credentials: 'same-origin', headers: h });
    if (!r.ok) throw new Error(await r.text());
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = name + '.previa.pdf';
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    alert('download da prévia falhou: ' + err.message);
  }
}

// Baixa o PDF traduzido (blob + auth); global p/ o onclick do botão de progresso.
async function trDownload(name) {
  try {
    const h = {}; if (typeof TOKEN !== 'undefined' && TOKEN) h['Authorization'] = 'Bearer ' + TOKEN;
    const r = await fetch(API + '/_download?label=' + encodeURIComponent(name),
      { credentials: 'same-origin', headers: h });
    if (!r.ok) throw new Error(await r.text());
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name + '.pdf';
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    alert('download falhou: ' + err.message);
  }
}

// Exporta a tradução como .md ou .epub (ADR-0032); serializa no servidor + baixa.
async function trExport(name, fmt) {
  try {
    const h = {}; if (typeof TOKEN !== 'undefined' && TOKEN) h['Authorization'] = 'Bearer ' + TOKEN;
    const r = await fetch(API + '/_exportar?fmt=' + encodeURIComponent(fmt) + '&label=' + encodeURIComponent(name),
      { credentials: 'same-origin', headers: h });
    if (!r.ok) {
      let msg = await r.text();
      try { msg = JSON.parse(msg).error || msg; } catch (e) { /* texto cru */ }
      throw new Error(msg);
    }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name + '.' + fmt;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    alert('exportar ' + fmt + ' falhou: ' + err.message);
  }
}
