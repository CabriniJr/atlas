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
  const motor = s.motor || 'claude';
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
      <button class="btn" id="tr-traduzir" style="border-color:var(--green);color:var(--green)" ${origem ? '' : 'disabled'}>▶ Traduzir</button>
    </div>
    <div id="tr-estimativa"></div>
    <div id="tr-progresso">${_trProgresso(st, r.name)}</div>
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

function _trProgresso(st, name) {
  const fase = st.fase;
  if (!fase) return '';
  if (fase === 'erro') {
    return `<div style="color:var(--red);font-size:13px">⚠️ ${esc(st.erro || 'falhou')}</div>${_trLog(st)}`;
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
      <button class="btn" title="Exportar como EPUB (requer pandoc)" onclick="trExport('${escJs(name || '')}','epub')">📚 .epub</button></div>
      <div style="color:var(--muted);font-size:12px;margin-top:4px;word-break:break-all">💾 ${esc(st.saida)}</div>` : ''}${ga}${_trLog(st)}`;
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
    ${_trLog(st)}`;
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

  const ATIVO = new Set(['preparando', 'traduzindo']);
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
      if (!ATIVO.has(st.fase)) {
        clearInterval(polling); polling = null;
        if (trBtn) trBtn.disabled = false;
      }
    } catch (e) { /* mantém tentando */ }
  }

  if (trBtn) trBtn.onclick = async () => {
    trBtn.disabled = true;
    progBox.innerHTML = _trProgresso({ fase: 'preparando', progresso_pct: 0, atividade: 'iniciando…', iniciado_em: new Date().toISOString(), log: [] }, name);
    try {
      await apiFetch(API + '/_traduzir', { method: 'POST', body: JSON.stringify({ label: name }) });
      if (!polling) { polling = setInterval(poll, 1500); poll(); }
    } catch (err) {
      progBox.innerHTML = `<div style="color:var(--red);font-size:13px">erro: ${esc(err.message)}</div>`;
      trBtn.disabled = false;
    }
  };

  // Se já estava em andamento ao abrir, retoma o polling.
  const cur = container.querySelector('#tr-progresso').textContent || '';
  if (cur.includes('traduzindo') || cur.includes('preparando') || cur.includes('detectando')) {
    if (trBtn) trBtn.disabled = true;
    polling = setInterval(poll, 1500);
  }
  _autoScrollLog();
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
