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

function _trProgresso(st, name) {
  const fase = st.fase;
  if (!fase) return '';
  if (fase === 'erro') {
    return `<div style="color:var(--red);font-size:13px">⚠️ ${esc(st.erro || 'falhou')}</div>`;
  }
  if (fase === 'pronto') {
    const pp = st.paginas_prontas != null ? st.paginas_prontas : '';
    const ga = (st.glossario_auto && st.glossario_auto.length)
      ? `<div style="color:var(--muted);font-size:12px;margin-top:6px">🔤 glossário auto: ${st.glossario_auto.map(esc).join(', ')}</div>`
      : '';
    return `<div style="color:var(--green);font-size:13px">✓ pronto — ${pp} página(s)</div>
      ${st.saida ? `<div style="margin-top:8px"><button class="btn" style="border-color:var(--green);color:var(--green)" onclick="trDownload('${escJs(name || '')}')">⬇️ Baixar tradução</button></div>
      <div style="color:var(--muted);font-size:12px;margin-top:4px;word-break:break-all">💾 ${esc(st.saida)}</div>` : ''}${ga}`;
  }
  // traduzindo
  const pct = st.progresso_pct != null ? st.progresso_pct : 0;
  const tot = st.paginas_total || 0;
  const pr = st.paginas_prontas || 0;
  return `<div style="font-size:13px;margin-bottom:6px">traduzindo… ${pr}/${tot} páginas</div>
    <div style="background:var(--border);border-radius:6px;height:10px;overflow:hidden">
      <div style="background:var(--blue);height:100%;width:${pct}%;transition:width .3s"></div>
    </div>`;
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

  let polling = null;
  async function poll() {
    try {
      const r = await apiFetch(API + '/Traducao/' + encodeURIComponent(name));
      const st = r.status || {};
      progBox.innerHTML = _trProgresso(st, name);
      if (st.fase !== 'traduzindo') {
        clearInterval(polling); polling = null;
        if (trBtn) trBtn.disabled = false;
      }
    } catch (e) { /* mantém tentando */ }
  }

  if (trBtn) trBtn.onclick = async () => {
    trBtn.disabled = true;
    progBox.innerHTML = _trProgresso({ fase: 'traduzindo', progresso_pct: 0, paginas_total: 0, paginas_prontas: 0 }, name);
    try {
      await apiFetch(API + '/_traduzir', { method: 'POST', body: JSON.stringify({ label: name }) });
      if (!polling) polling = setInterval(poll, 2000);
    } catch (err) {
      progBox.innerHTML = `<div style="color:var(--red);font-size:13px">erro: ${esc(err.message)}</div>`;
      trBtn.disabled = false;
    }
  };

  // Se já estava traduzindo ao abrir, retoma o polling.
  const cur = container.querySelector('#tr-progresso').textContent || '';
  if (cur.includes('traduzindo')) {
    if (trBtn) trBtn.disabled = true;
    polling = setInterval(poll, 2000);
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
