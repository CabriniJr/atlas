/* Render especializada do Kind Torrent (ADR-0049).
 * Mostra a fase, a barra de progresso (progresso_pct) e o resumo do scan.
 * A operação em si é conversacional pelo Telegram; aqui é só visibilidade +
 * polling do status enquanto baixa.
 */

const _TR_FASE = {
  verificando: ['🔎 verificando', 'var(--muted)'],
  aguardando_confirmacao: ['⏸️ aguardando confirmação', 'var(--yellow, #b58900)'],
  baixando: ['⬇️ baixando', 'var(--blue)'],
  concluido: ['✅ concluído', 'var(--green, #159f4a)'],
  erro: ['❌ erro', 'var(--red, #d1242f)'],
  recusado: ['🚫 recusado', 'var(--muted)'],
  cancelado: ['🛑 cancelado', 'var(--muted)'],
};

registerRender('Torrent', function renderTorrent(r, container) {
  container.innerHTML = _trtShell(r);
  const fase = (r.status || {}).fase;
  if (fase === 'baixando') _trtPoll(r.name, container);
});

function _trtShell(r) {
  const s = r.spec || {};
  const st = r.status || {};
  const [rotulo, cor] = _TR_FASE[st.fase] || [esc(st.fase || '—'), 'var(--muted)'];
  const pct = Math.max(0, Math.min(100, Number(st.progresso_pct || 0)));
  const barra = st.fase === 'baixando' || st.fase === 'concluido' ? `
    <div style="margin:10px 0">
      <div style="height:10px;background:var(--border,#ddd);border-radius:5px;overflow:hidden">
        <div style="height:100%;width:${pct}%;background:var(--blue);transition:width .4s"></div>
      </div>
      <div style="font-size:11px;color:var(--muted);margin-top:4px">
        ${pct.toFixed(1)}% · ${esc(st.velocidade || '—')} · seeds: ${esc(String(st.seeds || 0))}
      </div>
    </div>` : '';
  return `<div class="rk-wrap">
    <div class="rk-header">
      <span style="font-size:20px">📥</span>
      <div style="flex:1;min-width:0">
        <div class="rk-title">${esc(s.nome || r.name)}</div>
        <div style="font-size:11px;color:var(--muted)">${esc((r.name || '').slice(0, 16))}…</div>
      </div>
      <span style="font-size:12px;font-weight:600;color:${cor}">${rotulo}</span>
    </div>
    <div class="rk-body" style="padding:14px">
      ${barra}
      <pre style="white-space:pre-wrap;font-size:12px;color:var(--fg,#222);margin:8px 0">${esc(st.resumo || '')}</pre>
      ${st.mensagem ? `<div style="font-size:12px;color:var(--muted)">${esc(st.mensagem)}</div>` : ''}
      <div style="font-size:11px;color:var(--muted);margin-top:8px">
        📁 ${esc(s.destino || '')}${st.concluido_em ? ` · concluído ${esc(st.concluido_em)}` : ''}
      </div>
      <div style="font-size:11px;color:var(--muted);margin-top:6px">
        Operação pelo Telegram: mande o <code>.torrent</code>, responda <b>sim/não</b>,
        peça <b>progresso</b> ou <b>cancelar</b>.
      </div>
    </div>
  </div>`;
}

function _trtPoll(name, container) {
  if (container.__trtTimer) clearInterval(container.__trtTimer);
  container.__trtTimer = setInterval(async () => {
    if (!container.isConnected) { clearInterval(container.__trtTimer); return; }
    try {
      const r = await apiFetch(API + '/Torrent/' + encodeURIComponent(name));
      if (r) {
        container.innerHTML = _trtShell(r);
        if ((r.status || {}).fase !== 'baixando') { clearInterval(container.__trtTimer); }
      }
    } catch (e) { /* segue tentando */ }
  }, 2500);
}
