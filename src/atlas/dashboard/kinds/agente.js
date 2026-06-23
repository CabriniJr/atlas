/* Render chat interativo do Kind Agente (ADR-0020 / E7-25).
 * Quadro branco com histórico de conversa e input de mensagem.
 * Usa POST /_chat via motor plugável (claude ou ollama, ADR-0022/0024).
 */

registerRender('Agente', function renderAgente(r, container) {
  const name = r.name;
  const s = r.spec || {};
  const motor = s.motor || 'claude';
  const modelo = s.modelo || (motor === 'ollama' ? 'gemma4' : 'claude-haiku-4-5-20251001');
  const nivel = s.nivel_contexto || 'none';

  // Histórico em memória (por sessão; não persiste)
  const hist = [];

  container.innerHTML = `<div class="ag-wrap">
    <div class="ag-header">
      <span style="font-size:18px">🤖</span>
      <div style="flex:1;min-width:0">
        <div class="ag-title">${esc(name)}</div>
        <div class="ag-meta">
          <span class="ag-badge ${motor}">${esc(motor)}</span>
          <span style="color:var(--muted)">${esc(modelo)}</span>
          <span style="color:var(--muted)">ctx: ${esc(nivel)}</span>
        </div>
      </div>
      <button class="btn" onclick="openResource('Agente','${escJs(name)}');document.querySelector('[data-action=edit]')?.click()">✏️ Config</button>
      <button class="btn" id="ag-clear-${esc(name)}">🗑 Limpar</button>
    </div>
    <div class="ag-messages" id="ag-msgs-${esc(name)}">
      <div class="ag-hint">Converse com o Agente <strong>${esc(name)}</strong>.<br>
        Motor: <strong>${esc(motor)}</strong> · Modelo: <strong>${esc(modelo)}</strong></div>
    </div>
    <div class="ag-input-bar">
      <textarea class="ag-input" id="ag-input-${esc(name)}"
        placeholder="Digite sua mensagem…" rows="2"></textarea>
      <button class="btn ag-send" id="ag-send-${esc(name)}">Enviar ↵</button>
    </div>
  </div>`;

  const msgsEl = container.querySelector(`#ag-msgs-${CSS.escape(name)}`);
  const inputEl = container.querySelector(`#ag-input-${CSS.escape(name)}`);
  const sendBtn = container.querySelector(`#ag-send-${CSS.escape(name)}`);
  const clearBtn = container.querySelector(`#ag-clear-${CSS.escape(name)}`);

  clearBtn?.addEventListener('click', () => {
    hist.length = 0;
    msgsEl.innerHTML = '<div class="ag-hint">Histórico limpo.</div>';
  });

  async function sendMessage() {
    const text = inputEl.value.trim();
    if (!text) return;
    inputEl.value = '';
    sendBtn.disabled = true;
    sendBtn.textContent = '…';

    _appendMsg(msgsEl, 'user', text);
    hist.push({role: 'user', content: text});

    // thinking indicator
    const thinkId = 'ag-think-' + Date.now();
    msgsEl.innerHTML += `<div id="${thinkId}" class="ag-msg assistant thinking">
      <span class="ag-spin"></span> pensando…</div>`;
    msgsEl.scrollTop = msgsEl.scrollHeight;

    try {
      const res = await apiFetch(`${API}/_chat`, {
        method: 'POST',
        body: JSON.stringify({agente: name, mensagem: text}),
      });
      document.getElementById(thinkId)?.remove();
      if (res.error) {
        _appendMsg(msgsEl, 'error', `⚠️ ${res.error}`);
      } else {
        _appendMsg(msgsEl, 'assistant', res.response || '(sem resposta)');
        hist.push({role: 'assistant', content: res.response || ''});
      }
    } catch (e) {
      document.getElementById(thinkId)?.remove();
      _appendMsg(msgsEl, 'error', `⚠️ ${e.message}`);
    }

    sendBtn.disabled = false;
    sendBtn.textContent = 'Enviar ↵';
    msgsEl.scrollTop = msgsEl.scrollHeight;
  }

  sendBtn.addEventListener('click', sendMessage);
  inputEl.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  inputEl.focus();
});

function _appendMsg(el, role, text) {
  const isUser = role === 'user';
  const isError = role === 'error';
  const mdContent = (!isUser && !isError) ? markdownToHtml(text) : esc(text);
  el.innerHTML += `<div class="ag-msg ${role}">
    <div class="ag-bubble">${mdContent}</div>
  </div>`;
}
