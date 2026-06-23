# Cards especializados no dashboard embutido — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trocar o card genérico (dump JSON) por cards sob medida por kind no dashboard embutido (`src/atlas/api.py`), com destaque ao Repo (contexto do projeto + diffs recentes + commit).

**Architecture:** Tudo no JS embutido de `api.py`. `_cardHtml(r)` passa a montar: header+ações → `_kindCard(r)` (dispatcher por kind, fallback genérico) → chips de labels → `<details>` "spec/status (JSON)" universal. Cards leem do recurso já carregado; o Repo faz 2 fetches extras (contexto + diffs) hidratados após o render. Sem TDD JS (front embutido): verificação = suíte Python verde + checagem no navegador.

**Tech Stack:** JS no template de `api.py` (helpers existentes: `apiFetch`, `esc`, `escJs`, `jsonStr`, `markdownToHtml`, `openResource`, `kindActionsHtml`). Spec: [docs/superpowers/specs/2026-06-22-cards-especializados-dashboard-design.md](../specs/2026-06-22-cards-especializados-dashboard-design.md).

> Contexto de helpers (já no arquivo): `apiFetch(path)` → JSON (lança em erro);
> `openResource(kind,name)` abre/renderiza; `esc`/`escJs` escapam; `jsonStr(obj)`
> JSON formatado; `markdownToHtml(md)`; `kindActionsHtml(r)` botões de ação.
> `_cardHtml(r)` está por volta da linha 1099; `renderResource`/`_renderSubContent`
> por volta de 1088–1095.

---

### Task 1: Helper de data, dispatcher `_kindCard` e `<details>` cru universal

**Files:**
- Modify: `src/atlas/api.py` (JS: `_cardHtml` e novas funções)

- [ ] **Step 1: Adicionar helper de data e o dispatcher**

No JS, perto dos outros helpers (ex.: após `function jsonStr(...)`), inserir:
```javascript
function fmtDt(s){ return s ? String(s).slice(0,16).replace('T',' ') : ''; }

function _rawDetails(r){
  const spec = Object.keys(r.spec||{}).length ? `<div class="sec-title">spec</div><pre class="json">${jsonStr(r.spec)}</pre>` : '';
  const status = Object.keys(r.status||{}).length ? `<div class="sec-title" style="margin-top:8px">status</div><pre class="json">${jsonStr(r.status)}</pre>` : '';
  if(!spec && !status) return '';
  return `<details class="r-section" style="margin-top:12px"><summary style="cursor:pointer;color:var(--muted);font-size:11px">spec / status (JSON)</summary><div style="margin-top:8px">${spec}${status}</div></details>`;
}

function _kindCard(r){
  switch(r.kind){
    case 'Repo':    return _repoCard(r);
    case 'Goal':    return _goalCard(r);
    case 'Timer':   return _timerCard(r);
    case 'Tracker': return _trackerCard(r);
    case 'Routine': return _routineCard(r);
    case 'Alarm':   return _alarmCard(r);
    case 'Diff':    return _diffCard(r);
    case 'Doc':     return _docCard(r);
    case 'Prompt':  return _promptCard(r);
    case 'Idea': case 'Task': case 'RoutineRequest': return _poolCard(r);
    default:        return _genericCard(r);
  }
}

function _genericCard(r){
  let html='';
  if(Object.keys(r.spec||{}).length) html += `<div class="r-section"><div class="sec-title">spec</div><pre class="json">${jsonStr(r.spec)}</pre></div>`;
  if(Object.keys(r.status||{}).length) html += `<div class="r-section"><div class="sec-title">status</div><pre class="json">${jsonStr(r.status)}</pre></div>`;
  return html;
}
```

- [ ] **Step 2: Refatorar `_cardHtml` para usar o dispatcher**

Substituir o corpo de `_cardHtml(r)` (da construção de `meta`/`labels` até o
`return`) de modo que o `return` final fique:
```javascript
  const meta = [
    ['kind', r.kind], ['name', r.name],
    ['criado_em', fmtDt(r.criado_em)], ['atualizado_em', fmtDt(r.atualizado_em)],
  ].filter(([,v])=>v).map(([k,v])=>`<div class="meta-item"><div class="mi-key">${k}</div><div class="mi-val">${esc(String(v))}</div></div>`).join('');
  const labels = Object.entries(r.labels||{}).map(([k,v])=>`<span class="label-chip lc-${k}-${v}">${esc(k)}=${esc(v)}</span>`).join('');
  const schema = _KIND_SCHEMA[r.kind];
  const kindDesc = schema?.meta?.desc ? `<div style="font-size:11px;color:var(--muted);margin-bottom:12px">${esc(schema.meta.desc)}</div>` : '';
  return `<div class="r-card">
    <div class="r-header">
      <span class="r-kind">${esc(r.kind)}</span>
      <span class="r-name-big">${esc(r.name)}</span>
      <div class="r-actions">
        ${kindActionsHtml(r)}
        <button class="btn" onclick="switchSubTab('manifest')">✏️ Editar</button>
        <button class="btn" onclick="copyApply()">📋 CLI</button>
        <button class="btn danger" onclick="deleteResource('${esc(r.kind)}','${escJs(r.name)}')">🗑</button>
      </div>
    </div>
    ${kindDesc}
    <div class="r-meta">${meta}</div>
    ${labels ? `<div class="labels-row">${labels}</div>` : ''}
    ${_kindCard(r)}
    ${_rawDetails(r)}
  </div>`;
```
(Remove o `specHtml`/`statusHtml`/`trackerInput` antigos — agora vêm de
`_kindCard`/`_rawDetails`. As funções por kind são adicionadas nas próximas tasks;
até lá, `_kindCard` chamará funções ainda inexistentes — então **implemente as
Tasks 2–4 antes de servir/testar** ou adicione stubs temporários retornando ''.)

> Para manter cada commit válido, adicione **stubs** vazios de `_repoCard`,
> `_goalCard`, `_timerCard`, `_trackerCard`, `_routineCard`, `_alarmCard`,
> `_diffCard`, `_docCard`, `_promptCard`, `_poolCard` (cada um `return '';`) nesta
> Task 1, e troque o corpo real nas Tasks seguintes.

- [ ] **Step 3: Verificar que a página serve e a suíte passa**

Run: `python -m pytest tests/test_api.py -q && curl -s http://127.0.0.1:8080/ | grep -c "_kindCard"`
Expected: testes verdes; grep ≥ 1 (a função está no HTML servido).
(Se a API não estiver no ar, suba: `set -a; . ./.env; set +a; nohup .venv/bin/python -m atlas >/tmp/atlas.log 2>&1 &` e aguarde `/health`.)

- [ ] **Step 4: Commit**

```bash
git add src/atlas/api.py
git commit -m "feat(dashboard): dispatcher _kindCard + details cru universal"
```

---

### Task 2: Cards de domínio — Goal, Timer, Tracker, Routine, Alarm

**Files:**
- Modify: `src/atlas/api.py` (substituir os stubs)

- [ ] **Step 1: Implementar as funções (substituir os stubs)**

```javascript
function _goalCard(r){
  const s=r.spec||{}, st=r.status||{};
  const target=s.target, atual=(st.atual!=null?st.atual:st.current);
  const unit=s.unit||'';
  let pct=null;
  const m=String(st.progresso||st.progress||'').match(/(\d+)/); if(m) pct=Math.min(100,+m[1]);
  const bar = pct!=null ? `<div style="background:var(--bg3);border-radius:6px;height:14px;overflow:hidden;margin:8px 0"><div style="width:${pct}%;height:100%;background:var(--green)"></div></div><div style="font-size:11px;color:var(--muted)">${pct}%</div>` : '';
  return `<div class="r-section">
    <div class="sec-title">🎯 progresso</div>
    <div style="font-size:18px">${esc(String(atual??'?'))}${esc(unit)} <span style="color:var(--muted)">→ ${esc(String(target??'?'))}${esc(unit)}</span></div>
    ${bar}
    ${s.direction?`<div style="font-size:11px;color:var(--muted)">direção: ${esc(s.direction)}</div>`:''}
  </div>`;
}

function _timerCard(r){
  const st=r.status||{};
  const rodando = st.running===true || st.state==='running' || !!st.started_at;
  const cor = rodando?'var(--green)':'var(--muted)';
  const desde = st.started_at?` desde ${fmtDt(st.started_at)}`:'';
  const ult = st.last_duration||st.ultima_duracao;
  return `<div class="r-section">
    <div class="sec-title">⏱ estado</div>
    <div style="font-size:18px;color:${cor}">${rodando?'▶ rodando'+esc(desde):'⏹ parado'}</div>
    ${ult?`<div style="font-size:11px;color:var(--muted)">última duração: ${esc(String(ult))}</div>`:''}
  </div>`;
}

function _trackerCard(r){
  const s=r.spec||{}, st=r.status||{};
  const syn=s.syntax||r.name+':';
  const unit=s.unit?' ('+esc(s.unit)+')':'';
  const last=(st.ultimo_valor!=null?st.ultimo_valor:(st.last_value!=null?st.last_value:null));
  const hoje=(st.count_today!=null?st.count_today:null);
  return `<div class="r-section">
    <div class="sec-title">📊 ${esc(s.unit||s.type||'tracker')}</div>
    <div style="font-size:18px">${last!=null?esc(String(last))+(s.unit?' '+esc(s.unit):''):'<span style="color:var(--muted)">sem registro</span>'}</div>
    ${hoje!=null?`<div style="font-size:11px;color:var(--muted)">hoje: ${esc(String(hoje))}</div>`:''}
    <div class="tk-input" style="margin-top:8px">
      <input id="tk-val" type="text" inputmode="decimal" autocomplete="off" placeholder="${esc(syn)} valor${unit}" onkeydown="if(event.key==='Enter')_tkLog('${escJs(syn)}')">
      <button class="btn" style="border-color:var(--green);color:var(--green)" onclick="_tkLog('${escJs(syn)}')">registrar</button>
    </div>
  </div>`;
}

function _routineCard(r){
  const s=r.spec||{}, st=r.status||{};
  const ativo = s.active===true || s.ativa===true;
  return `<div class="r-section">
    <div class="sec-title">🧩 rotina</div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px">
      ${_mi('agenda', s.schedule||s.agenda||'-')}
      ${_mi('modelo', s.model||s.modelo||'none')}
      ${_mi('ativo', ativo?'on':'off')}
      ${_mi('último run', fmtDt(st.last_run)||'-')}
      ${_mi('status', st.last_status||'-')}
      ${_mi('execuções', st.run_count!=null?st.run_count:'-')}
    </div>
  </div>`;
}

function _alarmCard(r){
  const s=r.spec||{}, st=r.status||{};
  return `<div class="r-section">
    <div class="sec-title">⏰ alarme</div>
    <div style="font-size:18px">${esc(String(s.time||s.hora||'--:--'))}</div>
    <div style="margin:4px 0">${esc(String(s.message||s.mensagem||''))}</div>
    <div style="font-size:11px;color:var(--muted)">${s.once?'uma vez':'diário'} · ${(s.active!==false)?'ativo':'inativo'}${st.last_fired?' · disparou '+fmtDt(st.last_fired):''}</div>
  </div>`;
}

function _mi(k,v){ return `<div class="meta-item"><div class="mi-key">${esc(k)}</div><div class="mi-val">${esc(String(v))}</div></div>`; }
```

- [ ] **Step 2: Verificar**

Run: `python -m pytest tests/test_api.py -q && curl -s http://127.0.0.1:8080/ | grep -c "_goalCard"`
Expected: verde; grep ≥ 1.

- [ ] **Step 3: Commit**

```bash
git add src/atlas/api.py
git commit -m "feat(dashboard): cards de Goal, Timer, Tracker, Routine, Alarm"
```

---

### Task 3: Cards de conteúdo — Doc, Diff, Prompt, pool (Idea/Task/RoutineRequest)

**Files:**
- Modify: `src/atlas/api.py` (substituir os stubs)

- [ ] **Step 1: Implementar**

```javascript
function _docCard(r){
  const s=r.spec||{};
  const body = s.body ? `<div class="md">${markdownToHtml(String(s.body))}</div>` : '<div style="color:var(--muted)">(sem corpo)</div>';
  return `<div class="r-section">
    ${s.title?`<div class="sec-title">${esc(s.title)}</div>`:''}
    ${body}
    ${s.source?`<div style="margin-top:8px;font-size:10px;color:var(--muted)">src: ${esc(s.source)}</div>`:''}
  </div>`;
}

function _diffCard(r){
  const s=r.spec||{};
  const head = `${esc(s.subject||s.commit||'')} <span style="color:var(--muted)">${esc(s.commit||'')}</span>`;
  const stat = `🗂 ${esc(String(s.files_changed??'?'))} arq · +${esc(String(s.insertions??0))}/-${esc(String(s.deletions??0))}`;
  const arquivos = Array.isArray(s.files_list)&&s.files_list.length ? `<div style="font-size:11px;color:var(--muted);margin:4px 0">${s.files_list.map(esc).join(', ')}</div>` : '';
  const expl = s.explicacao ? `<div class="sec-title" style="margin-top:10px">🧠 análise</div><div class="md">${markdownToHtml(String(s.explicacao))}</div>` : '';
  const diff = s.diff_raw ? `<div class="sec-title" style="margin-top:10px">diff</div><pre class="json">${esc(String(s.diff_raw))}</pre>` : '';
  return `<div class="r-section">
    <div style="font-size:14px">${head}</div>
    <div style="font-size:11px;color:var(--muted)">${s.author?esc(s.author)+' · ':''}${esc(fmtDt(s.date))}</div>
    <div style="margin-top:6px">${stat}</div>
    ${arquivos}${expl}${diff}
  </div>`;
}

function _promptCard(r){
  const s=r.spec||{}, st=r.status||{};
  return `<div class="r-section">
    <div class="sec-title">🧠 template</div>
    <pre class="json">${esc(String(s.template||''))}</pre>
    <div style="font-size:11px;color:var(--muted);margin-top:6px">modelo: ${esc(s.model||'-')} · fonte: ${esc(s.fonte||'-')}</div>
    ${st.last_output?`<div class="sec-title" style="margin-top:10px">última saída</div><div class="md">${markdownToHtml(String(st.last_output))}</div>`:''}
  </div>`;
}

function _poolCard(r){
  const s=r.spec||{}, st=r.status||{};
  const body = s.body ? `<div class="md">${markdownToHtml(String(s.body))}</div>` : '';
  const done = (r.kind==='Task') ? `<div style="font-size:12px;margin-top:6px">${s.done?'✅ feita':'⬜ pendente'}</div>` : '';
  const meta = [];
  if(s.priority!=null) meta.push('prioridade: '+esc(String(s.priority)));
  if(st.state||st.estado) meta.push('estado: '+esc(String(st.state||st.estado)));
  return `<div class="r-section">
    ${body||'<div style="color:var(--muted)">(vazio)</div>'}
    ${done}
    ${meta.length?`<div style="font-size:11px;color:var(--muted);margin-top:6px">${meta.join(' · ')}</div>`:''}
  </div>`;
}
```

- [ ] **Step 2: Verificar**

Run: `python -m pytest tests/test_api.py -q && curl -s http://127.0.0.1:8080/ | grep -c "_diffCard"`
Expected: verde; grep ≥ 1.

- [ ] **Step 3: Commit**

```bash
git add src/atlas/api.py
git commit -m "feat(dashboard): cards de Doc, Diff, Prompt e pool"
```

---

### Task 4: Card de Repo + hidratação (contexto + diffs recentes)

**Files:**
- Modify: `src/atlas/api.py` (substituir o stub `_repoCard`; wiring no render)

- [ ] **Step 1: Implementar `_repoCard` (síncrono, com placeholders) + hidratação**

```javascript
function _repoCard(r){
  const s=r.spec||{}, st=r.status||{};
  const commit = st.last_commit ? `<div style="font-size:14px">${esc(st.last_commit_msg||'(sem mensagem)')} <span style="color:var(--muted)">${esc(st.last_commit)}</span></div>
    <div style="font-size:11px;color:var(--muted)">${st.last_author?esc(st.last_author)+' · ':''}${esc(fmtDt(st.last_commit_date))}</div>` : '<div style="color:var(--muted)">sem sync ainda</div>';
  const stat = (st.files_changed!=null) ? `<div style="margin-top:6px">🗂 ${esc(String(st.files_changed))} arq · +${esc(String(st.insertions??0))}/-${esc(String(st.deletions??0))}</div>` : '';
  const sync = `<div style="font-size:11px;color:var(--muted);margin-top:4px">${st.last_sync?'sync '+fmtDt(st.last_sync):''}${st.last_check?' · check '+fmtDt(st.last_check):''}</div>`;
  const url = s.url ? `<div style="margin-top:6px"><a href="${esc(s.url)}" target="_blank" rel="noopener" style="color:var(--blue)">${esc(s.url)}</a></div>` : '';
  const nm = escJs(r.name);
  return `<div class="r-section">
    <div class="sec-title">📦 repositório</div>
    ${commit}${stat}${sync}${url}
  </div>
  <div class="r-section">
    <div class="sec-title">🧠 contexto do projeto</div>
    <div id="repo-ctx-${nm}" style="color:var(--muted)">carregando contexto…</div>
  </div>
  <div class="r-section">
    <div class="sec-title">🔄 atualizações recentes</div>
    <div id="repo-diffs-${nm}" style="color:var(--muted)">carregando diffs…</div>
  </div>`;
}

async function _hydrateRepoCard(name){
  const ctxEl = document.getElementById('repo-ctx-'+name);
  const diffEl = document.getElementById('repo-diffs-'+name);
  // contexto
  try {
    const doc = await apiFetch(API+'/Doc/repo-'+name+'-contexto');
    const md = doc.spec&&doc.spec.body ? markdownToHtml(String(doc.spec.body)) : '<span style="color:var(--muted)">vazio</span>';
    const gen = doc.status&&doc.status.generated_at ? `<div style="font-size:10px;color:var(--muted);margin-bottom:6px">modelo: ${esc((doc.status.model)||'-')} · ${esc(fmtDt(doc.status.generated_at))}</div>` : '';
    if(ctxEl) ctxEl.innerHTML = `${gen}<details open><summary style="cursor:pointer;color:var(--blue);font-size:11px">ver/ocultar</summary><div class="md">${md}</div></details>`;
  } catch(e){
    if(ctxEl) ctxEl.innerHTML = '<span style="color:var(--muted)">contexto ainda não gerado</span>';
  }
  // diffs recentes do repo
  try {
    const all = await apiFetch(API+'/Diff');
    const meus = (all||[]).filter(d=>d.labels&&d.labels.repo===name)
      .sort((a,b)=>String(b.criado_em||'').localeCompare(String(a.criado_em||''))).slice(0,8);
    if(diffEl){
      diffEl.innerHTML = meus.length ? meus.map(d=>{
        const sp=d.spec||{};
        return `<div style="padding:4px 0;border-bottom:1px solid var(--border);cursor:pointer" onclick="openResource('Diff','${escJs(d.name)}')">
          <div style="font-size:12px">${esc(sp.subject||sp.commit||d.name)}</div>
          <div style="font-size:10px;color:var(--muted)">${esc(sp.commit||'')} · +${esc(String(sp.insertions??0))}/-${esc(String(sp.deletions??0))}</div>
        </div>`;
      }).join('') : '<span style="color:var(--muted)">sem atualizações ainda</span>';
    }
  } catch(e){
    if(diffEl) diffEl.innerHTML = '<span style="color:var(--muted)">diffs indisponíveis</span>';
  }
}
```

- [ ] **Step 2: Chamar a hidratação após o render**

Localizar `_renderSubContent(r, mode)` (por volta da linha 1071–1090). No ramo que
renderiza o card (`mode!=='manifest'`, onde faz `ec.innerHTML = subtabs + ... _cardHtml(r) ...`),
**após** atribuir o `innerHTML`, inserir:
```javascript
    if (r.kind === 'Repo') _hydrateRepoCard(r.name);
```
(Garanta que isso roda só no modo card, não no editor de manifesto.)

- [ ] **Step 3: Verificar (página + suíte)**

Run: `python -m pytest tests/test_api.py -q && curl -s http://127.0.0.1:8080/ | grep -c "_hydrateRepoCard"`
Expected: verde; grep ≥ 1.

- [ ] **Step 4: Commit**

```bash
git add src/atlas/api.py
git commit -m "feat(dashboard): card de Repo com contexto e diffs recentes"
```

---

### Task 5: Verificação final

**Files:** —

- [ ] **Step 1: Suíte + lint**

Run: `python -m pytest -q && ruff check . && ruff format --check .`
Expected: tudo verde.

- [ ] **Step 2: Smoke headless do dashboard (erros de JS)**

Se houver `node`/navegador headless, carregar `http://127.0.0.1:8080/` e checar o
console por erros (sintaxe). Caso contrário, abrir manualmente o dashboard e:
- abrir `Repo/nora` → ver commit + contexto (markdown) + diffs;
- `Goal/peso-alvo` → barra; `Timer/foco` → estado; `Tracker/peso` → valor+registro;
- `Doc`, `Diff`, `Prompt`, `Idea/Task` → cards próprios;
- conferir o `<details>` "spec/status (JSON)" em todos.
Expected: cada kind renderiza seu card; nenhum "undefined" gritante; sem erro no
console.

---

## Notas de verificação para o curador
- **Sem TDD JS:** o dashboard é string embutida; a verificação é a suíte Python
  (página servida) + navegador. Conferir que `curl /` contém as novas funções.
- **Fallback preservado:** `_genericCard` + `<details>` cru garantem que kinds não
  cobertos ou campos extras ainda aparecem.
- **Repo:** os 2 fetches extras degradam (mensagem) se contexto/diffs faltarem.
- **Nada de backend tocado** além do JS de `api.py`.
