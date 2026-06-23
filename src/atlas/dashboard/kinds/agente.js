/* Render especializada do Kind Agente (ADR-0020 / E7-25).
 * Abas: 💬 Chat | ⚙️ Config. Fullscreen destacável.
 * Chat: histórico em memória, POST /_chat, motor plugável (ADR-0022/0024).
 * Config: edição de todos os campos spec via formulário, PUT na API.
 */

registerRender('Agente', function renderAgente(r, container) {
  const name = r.name;
  const s = r.spec || {};

  container.innerHTML = _agenteShell(r);
  _wireAgente(name, s, container);
  _loadAgenteTab(name, s, 'chat', container);
});

// ── Shell ─────────────────────────────────────────────────────────────────────
function _agenteShell(r) {
  const s = r.spec || {};
  const motor = s.motor || 'claude';
  const modelo = s.modelo || (motor === 'ollama' ? 'gemma4' : 'claude-haiku-4-5-20251001');
  const nivel = s.nivel_contexto || 'none';
  return `<div class="ag-wrap">
    <div class="ag-header">
      <span style="font-size:18px">🤖</span>
      <div style="flex:1;min-width:0">
        <div class="ag-title">${esc(r.name)}</div>
        <div class="ag-meta">
          <span class="ag-badge ${motor}">${esc(motor)}</span>
          <span style="color:var(--muted)">${esc(modelo)}</span>
          <span style="color:var(--muted)">ctx: ${esc(nivel)}</span>
        </div>
      </div>
      <button class="btn rk-fullscreen-btn" onclick="toggleFullscreen()" title="Tela cheia">⤢</button>
    </div>
    <div class="ag-tabbar">
      <button class="ag-tab active" data-tab="chat">💬 Chat</button>
      <button class="ag-tab" data-tab="config">⚙️ Config</button>
    </div>
    <div class="ag-body" id="ag-body-${esc(r.name)}"></div>
  </div>`;
}

function _wireAgente(name, s, container) {
  container.querySelectorAll('.ag-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.ag-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      _loadAgenteTab(name, s, btn.dataset.tab, container);
    });
  });
}

// ── Tab dispatcher ────────────────────────────────────────────────────────────
function _loadAgenteTab(name, s, tab, container) {
  const body = container.querySelector(`#ag-body-${CSS.escape(name)}`);
  if (!body) return;
  if (tab === 'chat') _tabChat(name, s, body);
  else if (tab === 'config') _tabAgenteConfig(name, body);
}

// ── Tab: Chat ─────────────────────────────────────────────────────────────────
const _agenteHist = {}; // name → [{role, content}]

function _tabChat(name, s, el) {
  if (!_agenteHist[name]) _agenteHist[name] = [];
  const hist = _agenteHist[name];
  const motor = s.motor || 'claude';
  const modelo = s.modelo || (motor === 'ollama' ? 'gemma4' : 'claude-haiku-4-5-20251001');

  el.innerHTML = `<div class="ag-chat-wrap">
    <div class="ag-toolbar">
      <span style="font-size:11px;color:var(--muted)">
        ${hist.length} mensagem${hist.length !== 1 ? 's' : ''} na sessão
      </span>
      <button class="btn" id="ag-clear-${esc(name)}" style="font-size:11px;padding:2px 8px">🗑 Limpar</button>
    </div>
    <div class="ag-messages" id="ag-msgs-${esc(name)}">
      ${hist.length === 0
        ? `<div class="ag-hint">Converse com <strong>${esc(name)}</strong>.<br>
           Motor: <strong>${esc(motor)}</strong> · Modelo: <strong>${esc(modelo)}</strong></div>`
        : hist.map(m => _msgHtml(m.role, m.content)).join('')
      }
    </div>
    <div class="ag-input-bar">
      <textarea class="ag-input" id="ag-input-${esc(name)}"
        placeholder="Digite sua mensagem… (Enter envia, Shift+Enter nova linha)" rows="2"></textarea>
      <button class="btn ag-send" id="ag-send-${esc(name)}">Enviar ↵</button>
    </div>
  </div>`;

  const msgsEl = el.querySelector(`#ag-msgs-${CSS.escape(name)}`);
  const inputEl = el.querySelector(`#ag-input-${CSS.escape(name)}`);
  const sendBtn = el.querySelector(`#ag-send-${CSS.escape(name)}`);
  const clearBtn = el.querySelector(`#ag-clear-${CSS.escape(name)}`);

  // scroll to bottom if history exists
  if (hist.length > 0) msgsEl.scrollTop = msgsEl.scrollHeight;

  clearBtn?.addEventListener('click', () => {
    _agenteHist[name] = [];
    msgsEl.innerHTML = '<div class="ag-hint">Histórico limpo.</div>';
    const toolbar = el.querySelector('.ag-toolbar span');
    if (toolbar) toolbar.textContent = '0 mensagens na sessão';
  });

  async function sendMessage() {
    const text = inputEl.value.trim();
    if (!text) return;
    inputEl.value = '';
    sendBtn.disabled = true;
    sendBtn.textContent = '…';

    hist.push({role: 'user', content: text});
    msgsEl.innerHTML += _msgHtml('user', text);
    msgsEl.scrollTop = msgsEl.scrollHeight;

    const thinkId = 'ag-think-' + Date.now();
    msgsEl.innerHTML += `<div id="${thinkId}" class="ag-msg thinking">
      <div class="ag-bubble"><span class="ag-spin"></span>pensando…</div></div>`;
    msgsEl.scrollTop = msgsEl.scrollHeight;

    try {
      const res = await apiFetch(`${API}/_chat`, {
        method: 'POST',
        body: JSON.stringify({agente: name, mensagem: text}),
      });
      document.getElementById(thinkId)?.remove();
      if (res.error) {
        _appendAgMsg(msgsEl, 'error', `⚠️ ${res.error}`);
      } else {
        const reply = res.response || '(sem resposta)';
        hist.push({role: 'assistant', content: reply});
        _appendAgMsg(msgsEl, 'assistant', reply);
        // destacar comandos /apply detectados (E7-24 builder)
        if (res.commands && res.commands.length) {
          _appendCmdButtons(msgsEl, res.commands);
        }
      }
    } catch (e) {
      document.getElementById(thinkId)?.remove();
      _appendAgMsg(msgsEl, 'error', `⚠️ ${e.message}`);
    }

    sendBtn.disabled = false;
    sendBtn.textContent = 'Enviar ↵';
    msgsEl.scrollTop = msgsEl.scrollHeight;
    const toolbar = el.querySelector('.ag-toolbar span');
    if (toolbar) toolbar.textContent = `${hist.length} mensagem${hist.length !== 1 ? 's' : ''} na sessão`;
  }

  sendBtn.addEventListener('click', sendMessage);
  inputEl.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  inputEl.focus();
}

function _msgHtml(role, text) {
  const isUser = role === 'user';
  const isError = role === 'error';
  const content = (!isUser && !isError) ? markdownToHtml(text) : esc(text);
  return `<div class="ag-msg ${role}"><div class="ag-bubble">${content}</div></div>`;
}

function _appendAgMsg(el, role, text) {
  el.innerHTML += _msgHtml(role, text);
}

// Botões de execução para comandos /apply detectados na resposta (E7-24)
function _appendCmdButtons(msgsEl, commands) {
  const id = 'ag-cmds-' + Date.now();
  msgsEl.innerHTML += `<div class="ag-cmd-group" id="${id}">
    <div class="ag-cmd-label">⚡ Comandos detectados:</div>
    ${commands.map((cmd, i) => `
      <div class="ag-cmd-row">
        <code class="ag-cmd-code">${esc(cmd)}</code>
        <button class="btn ag-cmd-run" data-cmd="${esc(cmd)}" data-id="${id}-${i}">▶ Aplicar</button>
        <span class="ag-cmd-result" id="${id}-${i}"></span>
      </div>`).join('')}
  </div>`;

  msgsEl.querySelectorAll('.ag-cmd-run').forEach(btn => {
    btn.addEventListener('click', async () => {
      const cmd = btn.dataset.cmd;
      const resultEl = document.getElementById(btn.dataset.id);
      btn.disabled = true;
      if (resultEl) resultEl.textContent = '…';
      try {
        const r = await apiFetch(`${API}/_cmd`, {
          method: 'POST',
          body: JSON.stringify({text: cmd}),
        });
        if (resultEl) {
          resultEl.textContent = r.output ? r.output.slice(0, 80) : '✅ ok';
          resultEl.className = 'ag-cmd-result ok';
        }
        // refresca a árvore
        apiFetch(API + '/').then(k => { allKinds = k; renderTree(); }).catch(() => {});
      } catch (e) {
        if (resultEl) { resultEl.textContent = '❌ ' + e.message; resultEl.className = 'ag-cmd-result err'; }
        btn.disabled = false;
      }
    });
  });
}

// ── Tab: Config ───────────────────────────────────────────────────────────────
async function _tabAgenteConfig(name, el) {
  const agSchema = (allSchema && allSchema['Agente']?.spec) || _agenteDefaultFields();
  let res;
  try {
    res = await apiFetch(`${API}/Agente/${encodeURIComponent(name)}`);
  } catch (e) {
    el.innerHTML = `<div style="padding:16px;color:var(--red)">Erro: ${esc(e.message)}</div>`;
    return;
  }
  const spec = res.spec || {};

  el.innerHTML = `<div class="rk-cfg-form">
    <div class="rk-section">
      <div class="rk-sec-title">⚙️ Configuração — ${esc(name)}</div>
      ${agSchema.map(f => _cfgField(f, spec[f.k])).join('')}
    </div>
    <div class="rk-cfg-footer">
      <button class="btn" id="ag-cfg-save-${esc(name)}" style="color:var(--green);border-color:var(--green)">💾 Salvar</button>
      <button class="btn" id="ag-cfg-reset-${esc(name)}">↺ Resetar</button>
      <span class="rk-cfg-status" id="ag-cfg-status-${esc(name)}"></span>
    </div>
  </div>`;

  const saveBtn = el.querySelector(`#ag-cfg-save-${CSS.escape(name)}`);
  const statusEl = el.querySelector(`#ag-cfg-status-${CSS.escape(name)}`);

  saveBtn.addEventListener('click', async () => {
    saveBtn.disabled = true;
    statusEl.textContent = 'salvando…';
    statusEl.className = 'rk-cfg-status';
    try {
      const newSpec = _readCfgForm(el, agSchema, spec);
      await apiFetch(`${API}/Agente/${encodeURIComponent(name)}`, {
        method: 'PUT',
        body: JSON.stringify({
          kind: 'Agente', name,
          spec: newSpec,
          labels: res.labels || {},
          status: res.status || {},
        }),
      });
      statusEl.textContent = '✅ Salvo — recarregue o chat para aplicar';
      statusEl.className = 'rk-cfg-status ok';
    } catch (e) {
      statusEl.textContent = '❌ ' + e.message;
      statusEl.className = 'rk-cfg-status err';
    } finally {
      saveBtn.disabled = false;
    }
  });

  el.querySelector(`#ag-cfg-reset-${CSS.escape(name)}`)
    ?.addEventListener('click', () => _tabAgenteConfig(name, el));
}

function _agenteDefaultFields() {
  return [
    {k:'motor', type:'select', label:'Motor', opts:['claude','ollama'], hint:'Provider de IA'},
    {k:'modelo', type:'text', label:'Modelo', hint:'claude-haiku-4-5-20251001 / gemma4'},
    {k:'nivel_contexto', type:'select', label:'Nível de contexto', opts:['none','resumo','completo'], hint:'Quanto contexto do projeto entra no prompt'},
    {k:'prompt', type:'area', label:'Prompt / template', hint:'Use {mensagem} e {agora}'},
    {k:'endpoint', type:'text', label:'Endpoint Ollama', hint:'http://192.168.86.22:11434'},
    {k:'timeout', type:'number', label:'Timeout (s)', hint:'Default: 60'},
  ];
}
