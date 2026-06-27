/* Render especializada do Kind Agente (ADR-0020 / E7-25).
 * Abas: 💬 Chat | 🔍 Curadoria | ⚙️ Config. Fullscreen destacável.
 * Chat: histórico em memória, POST /_chat, motor plugável (ADR-0022/0024).
 * Curadoria: runs gated do modo code → diff + aprovar (branch) / descartar
 *   (SPEC-CURADORIA-GATE / ADR-0028 §4).
 * Config: edição de todos os campos spec via formulário, PUT na API.
 */

registerRender('Agente', function renderAgente(r, container) {
  const name = r.name;
  const s = r.spec || {};

  container.innerHTML = _agenteShell(r);
  _wireAgente(name, s, container);
  _loadAgenteTab(name, s, 'chat', container);
  _updateCuradoriaBadge(name, container);
});

// ── Shell ─────────────────────────────────────────────────────────────────────
function _agenteShell(r) {
  const s = r.spec || {};
  const st = r.status || {};
  const motor = s.motor || 'claude';
  const modelo = s.modelo || s.provider || (motor === 'ollama' ? 'gemma4' : 'claude-haiku-4-5-20251001');
  const nivel = s.nivel_contexto || 'none';
  const runs = st.runs || 0;
  const custo = st.custo_total_usd != null ? Number(st.custo_total_usd) : null;
  const gasto = (runs || custo != null)
    ? `<span class="ag-badge cost" title="Gasto de IA acumulado deste agente">💰 ${custo != null ? '$' + custo.toFixed(4) : '—'} · ${runs} run${runs !== 1 ? 's' : ''}</span>`
    : '';
  return `<div class="ag-wrap">
    <div class="ag-header">
      <span style="font-size:18px">🤖</span>
      <div style="flex:1;min-width:0">
        <div class="ag-title">${esc(r.name)}</div>
        <div class="ag-meta">
          <span class="ag-badge ${motor}">${esc(motor)}</span>
          <span style="color:var(--muted)">${esc(modelo)}</span>
          <span style="color:var(--muted)">ctx: ${esc(nivel)}</span>
          ${gasto}
        </div>
      </div>
      <button class="btn rk-fullscreen-btn" onclick="toggleFullscreen()" title="Tela cheia">⤢</button>
    </div>
    <div class="ag-tabbar">
      <button class="ag-tab active" data-tab="chat">💬 Chat</button>
      <button class="ag-tab" data-tab="curadoria">🔍 Curadoria<span class="ag-cur-badge" id="ag-cur-badge-${esc(r.name)}"></span></button>
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
  if (tab === 'chat') {
    if (s.modo === 'code') _tabChatCode(name, s, body);
    else _tabChat(name, s, body);
  } else if (tab === 'curadoria') {
    _tabCuradoria(name, body, container);
  } else if (tab === 'config') {
    _tabAgenteConfig(name, body);
  }
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

// ── Tab: Chat (modo=code — Claude Code agêntico) ──────────────────────────────
// Histórico de sessões por agente (user msgs + sessões concluídas)
const _codeHist = {};
// Run ativo por agente: { run_id, events[], done, sessEl (pode ser null/detached) }
const _codeRuns = {};

function _tabChatCode(name, s, el) {
  if (!_codeHist[name]) _codeHist[name] = [];
  const hist = _codeHist[name];
  const modelo = s.modelo || 'claude-sonnet-4-6';
  const activeRun = _codeRuns[name] || null;

  el.innerHTML = `<div class="ag-chat-wrap">
    <div class="ag-toolbar">
      <span class="ag-badge code">⚡ Claude Code</span>
      <span style="color:var(--muted);font-size:11px">${esc(modelo)}</span>
      ${activeRun && !activeRun.done
        ? `<span class="ag-run-badge" id="agc-runbadge-${esc(name)}">⏳ executando…</span>`
        : ''}
      <button class="btn" id="agc-clear-${esc(name)}" style="font-size:11px;padding:2px 8px;margin-left:auto">🗑 Limpar</button>
    </div>
    <div class="ag-messages" id="agc-msgs-${esc(name)}">
      ${hist.length === 0 && !(activeRun && !activeRun.done)
        ? `<div class="ag-hint">Diga ao <strong>${esc(name)}</strong> o que fazer.<br>
           Ele pode ler, editar e criar arquivos do projeto.<br>
           <em>Ex: "adiciona o campo goal ao spec do Repo"</em></div>`
        : hist.map(m => m.type === 'user'
            ? _msgHtml('user', m.content)
            : `<div class="ag-code-session">${m.content}</div>`
          ).join('')
      }
    </div>
    <div class="ag-input-bar">
      <textarea class="ag-input" id="agc-input-${esc(name)}"
        placeholder="Descreva a tarefa… (Enter envia, Shift+Enter nova linha)" rows="2"></textarea>
      <button class="btn ag-send" id="agc-send-${esc(name)}"
        ${activeRun && !activeRun.done ? 'disabled' : ''}>Executar ↵</button>
    </div>
  </div>`;

  const msgsEl = el.querySelector(`#agc-msgs-${CSS.escape(name)}`);
  const inputEl = el.querySelector(`#agc-input-${CSS.escape(name)}`);
  const sendBtn = el.querySelector(`#agc-send-${CSS.escape(name)}`);
  const clearBtn = el.querySelector(`#agc-clear-${CSS.escape(name)}`);

  // Se há um run ativo, reconectar ao SSE stream e exibir eventos já acumulados
  if (activeRun && !activeRun.done) {
    const sessEl = _attachLiveSession(name, msgsEl, activeRun);
    _subscribeRunStream(name, activeRun, sessEl, msgsEl, sendBtn);
  }

  if (hist.length > 0) msgsEl.scrollTop = msgsEl.scrollHeight;

  clearBtn?.addEventListener('click', () => {
    if (_codeRuns[name] && !_codeRuns[name].done) return; // não limpa enquanto roda
    _codeHist[name] = [];
    msgsEl.innerHTML = '<div class="ag-hint">Log limpo.</div>';
  });

  async function runTask() {
    const text = inputEl.value.trim();
    if (!text) return;
    inputEl.value = '';
    sendBtn.disabled = true;
    sendBtn.textContent = '⏳ Iniciando…';

    hist.push({type: 'user', content: text});
    msgsEl.innerHTML += _msgHtml('user', text);

    let run;
    try {
      const r = await apiFetch(`${API}/_agent_run`, {
        method: 'POST',
        body: JSON.stringify({agente: name, mensagem: text}),
      });
      if (r.error) throw new Error(r.error);
      run = {run_id: r.run_id, events: [], done: false};
      _codeRuns[name] = run;
    } catch (e) {
      msgsEl.innerHTML += _msgHtml('error', `⚠️ ${esc(e.message)}`);
      sendBtn.disabled = false;
      sendBtn.textContent = 'Executar ↵';
      return;
    }

    // container para os eventos desta execução
    const sessEl = _attachLiveSession(name, msgsEl, run);
    sendBtn.textContent = '⏳ Executando…';

    // Atualiza badge
    const badge = el.querySelector(`#agc-runbadge-${CSS.escape(name)}`);
    if (!badge) {
      const tb = el.querySelector('.ag-toolbar');
      if (tb) {
        const b = document.createElement('span');
        b.className = 'ag-run-badge';
        b.id = `agc-runbadge-${name}`;
        b.textContent = '⏳ executando…';
        tb.insertBefore(b, clearBtn);
      }
    }

    _subscribeRunStream(name, run, sessEl, msgsEl, sendBtn);
  }

  sendBtn.addEventListener('click', runTask);
  inputEl.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); runTask(); }
  });
  if (!activeRun || activeRun.done) inputEl.focus();
}

function _attachLiveSession(name, msgsEl, run) {
  // Cria (ou reutiliza) o container de eventos do run atual
  const sessId = `agc-live-${CSS.escape(name)}`;
  let sessEl = msgsEl.querySelector(`#${sessId}`);
  if (!sessEl) {
    sessEl = document.createElement('div');
    sessEl.className = 'ag-code-session';
    sessEl.id = sessId;
    msgsEl.appendChild(sessEl);
  }
  // Replay de eventos já acumulados no run (caso o usuário tenha navegado)
  const rendered = sessEl.children.length;
  for (let i = rendered; i < run.events.length; i++) {
    _appendCodeEventToEl(run.events[i], sessEl);
  }
  msgsEl.scrollTop = msgsEl.scrollHeight;
  return sessEl;
}

function _subscribeRunStream(name, run, sessEl, msgsEl, sendBtn) {
  const streamUrl = `${API}/_agent_run/${run.run_id}/stream`;
  const es = new EventSource(streamUrl);

  es.onmessage = (e) => {
    let ev;
    try { ev = JSON.parse(e.data); } catch { return; }
    run.events.push(ev);
    _appendCodeEventToEl(ev, sessEl);
    msgsEl.scrollTop = msgsEl.scrollHeight;

    if (ev.type === 'done' || ev.type === 'error') {
      run.done = true;
      es.close();
      // Salva sessão no hist e limpa run ativo
      _codeHist[name].push({type: 'session', content: sessEl.innerHTML});
      delete _codeRuns[name];
      // Restaura UI
      if (sendBtn) { sendBtn.disabled = false; sendBtn.textContent = 'Executar ↵'; }
      const badge = document.getElementById(`agc-runbadge-${name}`);
      if (badge) badge.remove();
    }
  };

  es.onerror = () => {
    if (run.done) { es.close(); return; }
    // Reconecta automaticamente (EventSource faz retry nativo)
  };
}

function _appendCodeEventToEl(ev, sessEl) {
  const type = ev.type;
  let cls = null, html = null;

  if (type === 'init') {
    // Evento interno de início do run (criado por nós)
    cls = 'init'; html = `🚀 <strong>${esc(ev.agente)}</strong> · ${esc(ev.modelo)}`;
  } else if (type === 'done') {
    cls = 'done'; html = '✅ Concluído';
  } else if (type === 'error') {
    cls = 'error'; html = `⚠️ ${esc(ev.message || 'Erro desconhecido')}`;
  } else if (type === 'system') {
    // Apenas mostra o init do claude (lista de ferramentas disponíveis)
    if (ev.subtype === 'init') {
      const tools = (ev.tools || []).filter(t => !['Task','AskUserQuestion','mcp__'].some(p => t.startsWith(p)));
      if (tools.length) cls = 'init', html = `🛠 ${esc(tools.join(' · '))}`;
    }
    // hook_started/hook_response silenciados
  } else if (type === 'result') {
    // Resultado final do claude CLI
    if (ev.result && ev.result.trim()) {
      _appendCodeLog(sessEl, 'result', markdownToHtml(ev.result));
    }
    const cost = ev.total_cost_usd ?? ev.cost_usd;
    if (cost != null) {
      const usage = ev.usage || {};
      const inTok = usage.input_tokens || '?';
      const outTok = usage.output_tokens || '?';
      _appendCodeLog(sessEl, 'meta', `💰 $${Number(cost).toFixed(4)} · ${inTok} in / ${outTok} out tokens`);
    }
    return;
  } else if (type === 'assistant') {
    // Texto do assistente
    const content = Array.isArray((ev.message||{}).content) ? ev.message.content : [];
    for (const block of content) {
      if (block.type === 'text' && block.text && block.text.trim()) {
        _appendCodeLog(sessEl, 'text', markdownToHtml(block.text));
      } else if (block.type === 'tool_use') {
        _appendCodeToolUse(sessEl, block);
      }
    }
    return;
  } else if (type === 'tool_use') {
    _appendCodeToolUse(sessEl, ev.content_block || ev);
    return;
  } else if (type === 'raw' && ev.text) {
    cls = 'raw'; html = `<code>${esc(ev.text)}</code>`;
  }
  // Silencia: content_block_delta, content_block_start/stop, tool_result, rate_limit_event, message_*

  if (cls && html) _appendCodeLog(sessEl, cls, html);
}

function _appendCodeToolUse(sessEl, block) {
  const toolName = block.name || '?';
  const input = block.input || {};
  let detail = '';
  if (toolName === 'Read' || toolName === 'Write') detail = input.file_path || input.path || '';
  else if (toolName === 'Edit') detail = input.file_path || '';
  else if (toolName === 'Bash') detail = (input.command || '').slice(0, 80);
  else if (toolName === 'Glob' || toolName === 'Grep') detail = input.pattern || input.query || '';
  else if (toolName === 'TodoWrite') detail = (input.todos || []).length + ' itens';
  const icon = {Read:'📖',Write:'✍️',Edit:'✏️',Bash:'💻',Glob:'🔍',Grep:'🔍',TodoWrite:'📝',Task:'🤖',WebSearch:'🌐'}[toolName] || '🔧';
  _appendCodeLog(sessEl, 'tool',
    `${icon} <strong>${esc(toolName)}</strong>${detail ? ` <span class="ag-tool-detail">— ${esc(detail)}</span>` : ''}`
  );
}

function _appendCodeLog(sessEl, cls, html) {
  const div = document.createElement('div');
  div.className = `ag-code-log ${cls}`;
  div.innerHTML = html;
  sessEl.appendChild(div);
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

// ── Tab: Curadoria do gate (SPEC-CURADORIA-GATE / ADR-0028 §4) ──────────────────
// Lista os runs gated pendentes do agente; revisa o diff e aprova (branch) / descarta.

async function _pendingRuns(name) {
  const all = await apiFetch(`${API}/AgentRun`);
  return (all || [])
    .filter(r => (r.spec || {}).agente === name && (r.status || {}).review === 'pending')
    .sort((a, b) => ((b.spec || {}).started_at || '').localeCompare((a.spec || {}).started_at || ''));
}

async function _updateCuradoriaBadge(name, container) {
  const badge = container.querySelector(`#ag-cur-badge-${CSS.escape(name)}`);
  if (!badge) return;
  try {
    const n = (await _pendingRuns(name)).length;
    badge.textContent = n ? ` • ${n}` : '';
  } catch { badge.textContent = ''; }
}

async function _tabCuradoria(name, el, container) {
  el.innerHTML = `<div class="ag-cur" style="padding:12px"><div style="color:var(--muted)">Carregando runs pendentes…</div></div>`;
  let runs;
  try {
    runs = await _pendingRuns(name);
  } catch (e) {
    el.innerHTML = `<div style="padding:16px;color:var(--red)">Erro: ${esc(e.message)}</div>`;
    return;
  }
  if (!runs.length) {
    el.innerHTML = `<div style="padding:16px;color:var(--muted)">Nenhum run aguardando revisão. 🎉<br><span style="font-size:12px">Runs do modo <code>code</code> com gate ativo aparecem aqui ao terminar.</span></div>`;
    return;
  }
  el.innerHTML = `<div class="ag-cur" style="padding:8px">
    <div style="font-size:12px;color:var(--muted);padding:4px 6px">${runs.length} run${runs.length !== 1 ? 's' : ''} aguardando revisão</div>
    ${runs.map(r => _curItemHtml(r)).join('')}
  </div>`;

  runs.forEach(r => {
    const item = el.querySelector(`#cur-${CSS.escape(r.name)}`);
    item?.querySelector('.cur-review')?.addEventListener('click', () => _curLoadDiff(name, r, item, el, container));
  });
}

function _curItemHtml(r) {
  const sp = r.spec || {};
  const task = (sp.task || '').split('\n')[0];
  const when = (sp.started_at || '').replace('T', ' ').slice(0, 16);
  return `<div class="cur-item" id="cur-${esc(r.name)}" style="border:1px solid var(--border);border-radius:8px;margin:6px 0;padding:8px">
    <div style="display:flex;gap:8px;align-items:center">
      <code style="color:var(--muted)">#${esc(r.name)}</code>
      <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(sp.task || '')}">${esc(task || '(sem descrição)')}</span>
      <span style="font-size:11px;color:var(--muted)">${esc(when)}</span>
      <button class="btn cur-review">🔍 Revisar</button>
    </div>
    <div class="cur-diff-wrap"></div>
  </div>`;
}

async function _curLoadDiff(name, r, item, el, container) {
  const wrap = item.querySelector('.cur-diff-wrap');
  const btn = item.querySelector('.cur-review');
  btn.disabled = true; btn.textContent = '…';
  try {
    const res = await apiFetch(`${API}/_agent_run/${encodeURIComponent(r.name)}/diff`);
    const diff = (res.diff || '').trim();
    wrap.innerHTML = `
      <pre class="cur-diff" style="max-height:340px;overflow:auto;margin:8px 0;padding:8px;background:var(--bg2,#111);border-radius:6px;font-size:12px;line-height:1.4">${_diffHtml(diff)}</pre>
      <div style="display:flex;gap:8px;align-items:center">
        <button class="btn cur-discard" style="color:var(--red);border-color:var(--red)">🗑 Descartar</button>
        <button class="btn cur-approve" style="color:var(--green);border-color:var(--green)">✓ Aprovar → branch</button>
        <span class="cur-status" style="font-size:12px;color:var(--muted)"></span>
      </div>`;
    const statusEl = wrap.querySelector('.cur-status');
    wrap.querySelector('.cur-discard').addEventListener('click', () => _curAction(name, r, 'discard', wrap, item, el, container, statusEl));
    wrap.querySelector('.cur-approve').addEventListener('click', () => _curAction(name, r, 'approve', wrap, item, el, container, statusEl));
  } catch (e) {
    wrap.innerHTML = `<div style="color:var(--red);padding:6px">Erro ao carregar diff: ${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false; btn.textContent = '🔍 Revisar';
  }
}

async function _curAction(name, r, acao, wrap, item, el, container, statusEl) {
  const btns = wrap.querySelectorAll('button');
  btns.forEach(b => b.disabled = true);
  statusEl.textContent = acao === 'approve' ? 'aprovando…' : 'descartando…';
  try {
    const res = await apiFetch(`${API}/_agent_run/${encodeURIComponent(r.name)}/${acao}`, { method: 'POST' });
    if (acao === 'approve') {
      statusEl.innerHTML = `✅ aprovado → <code>${esc(res.branch || '')}</code>`;
    } else {
      statusEl.textContent = '🗑 descartado';
    }
    // Some o item da lista e atualiza o badge.
    setTimeout(() => { item.remove(); _updateCuradoriaBadge(name, container); _refreshCurEmpty(el); }, 900);
  } catch (e) {
    statusEl.innerHTML = `<span style="color:var(--red)">❌ ${esc(e.message)}</span>`;
    btns.forEach(b => b.disabled = false);
  }
}

function _refreshCurEmpty(el) {
  if (!el.querySelector('.cur-item')) {
    el.innerHTML = `<div style="padding:16px;color:var(--muted)">Nenhum run aguardando revisão. 🎉</div>`;
  }
}

function _diffHtml(diff) {
  if (!diff) return '<span style="color:var(--muted)">(sem mudanças não-commitadas no workspace)</span>';
  return diff.split('\n').map(line => {
    const c = esc(line);
    if (line.startsWith('+') && !line.startsWith('+++')) return `<span style="color:var(--green)">${c}</span>`;
    if (line.startsWith('-') && !line.startsWith('---')) return `<span style="color:var(--red)">${c}</span>`;
    if (line.startsWith('@@')) return `<span style="color:var(--accent,#6cf)">${c}</span>`;
    if (line.startsWith('diff ') || line.startsWith('index ')) return `<span style="color:var(--muted)">${c}</span>`;
    return c;
  }).join('\n');
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
