---
titulo: Design — Cards especializados no dashboard embutido
id: SPEC-CARDS-ESPECIALIZADOS
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-22
---

# Design — Cards especializados no dashboard embutido

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-22 | Tech Lead | Criação (brainstorming) | PO/PM |

---

## Objetivo
Substituir o card genérico (dump JSON de `spec`/`status`) por **cards sob medida
por kind** no dashboard embutido (`api.py`), tornando a leitura útil — com
destaque para o **Repo** (contexto do projeto + diffs recentes + último commit),
agora que o repo-sync gera contexto rico. Vale para **todos os kinds**.

## Restrições e princípios
- **Front embutido:** o dashboard é JS numa string raw em `src/atlas/api.py`. Não
  há harness de teste JS neste repo (os testes de front são do `web/` React).
  **Verificação destes cards é manual no navegador** + a suíte Python do `api.py`
  segue verde (a página é servida intacta).
- **Abstração da API (ADR-0017/0019):** os cards só leem dados da API e disparam
  verbos existentes; sem regra de negócio nova.
- **Transparência (P5):** `spec`/`status` crus permanecem acessíveis num
  `<details>` colapsável universal — nada se perde.

## Arquitetura (JS do dashboard)
Refatorar `_cardHtml(r)`:
```
header (kind/name + ações: kindActionsHtml, Editar, CLI, 🗑)
+ kindDesc (do _KIND_SCHEMA)
+ _kindCard(r)              ← corpo especializado (dispatcher por kind)
+ chips de labels
+ <details> "spec / status (JSON)"   ← fallback universal colapsável
```
`_kindCard(r)` despacha por `r.kind` para uma função dedicada, com fallback ao
comportamento genérico atual. Funções: `_repoCard`, `_goalCard`, `_timerCard`,
`_trackerCard`, `_routineCard`, `_alarmCard`, `_diffCard`, `_docCard`,
`_promptCard`, `_poolCard` (Idea/Task/RoutineRequest). Reusa helpers existentes
(`esc`, `escJs`, `jsonStr`, `markdownToHtml`, `fmtDate`).

## Conteúdo por kind (lido dos campos do recurso)
- **Repo:** bloco de status — `last_commit` (sha7) · `last_commit_msg` · autor ·
  data; `🗂 files_changed +insertions/-deletions`; `last_sync`/`last_check`; URL
  (link). **Contexto do projeto:** seção que carrega `Doc/repo-<label>-contexto` e
  renderiza `spec.body` em markdown (colapsável; mostra `status.model` e
  `generated_at`; se ausente, nota "ainda não gerado"). **Atualizações recentes:**
  lista os `Diff` do repo (`subject` · `sha` · `+/-`), clicáveis (abrem o `Diff`).
- **Goal:** barra de progresso (`status.atual`/`spec.target`, `%` de
  `status.progresso`), `direction`, `unit`.
- **Timer:** estado **rodando/parado** em destaque (de `status`), e desde quando /
  última duração se houver.
- **Tracker:** último valor + `unit` + `count_today`; mantém a caixa de registrar.
- **Routine:** `schedule` (legível), `model`, `active`, `last_run`/`last_status`/
  `run_count`.
- **Alarm:** `time`/`hora`, `message`/`mensagem`, modo (`once`/daily), `active`,
  `last_fired`.
- **Diff:** `subject`/`author`/`date`, `+/-`, `files_list`, `diff_raw` em bloco
  ```diff, `explicacao` em markdown.
- **Doc:** `body` em markdown (já hoje) + `source`/`title`.
- **Prompt:** `template` (code), `model`, `fonte`, `status.last_output`.
- **Idea/Task/RoutineRequest:** `body` markdown, `priority`/`state`; Task mostra
  `done`.

## Fluxo de dados
- A maioria dos cards renderiza **do recurso único** já carregado (`r`), sem
  fetch extra.
- **Repo é a exceção:** após render, faz 2 chamadas à API — `GET
  /apis/atlas/v1/Doc/repo-<label>-contexto` (contexto) e `GET /apis/atlas/v1/Diff`
  (lista; filtra client-side `labels.repo===label`, mostra os mais recentes) — e
  injeta nos placeholders. Usa o mesmo `fetch` autenticado já existente no
  dashboard (helper `api()`), com tratamento de erro (mostra nota se falhar; não
  quebra o card).

## Tratamento de erro
- Campos ausentes → seções omitidas (sem "undefined" na tela).
- Fetch do contexto/diffs falhando → nota discreta ("contexto indisponível"),
  card segue renderizado.
- Markdown/JSON sempre via os helpers que já escapam conteúdo (`esc`).

## Testes / verificação
- **Manual (navegador):** abrir o dashboard em `:8080`, percorrer um recurso de
  cada kind (Repo/nora, Goal/peso-alvo, Timer/foco, Tracker/peso, Routine/treino,
  Doc, Diff, Prompt, Idea/Task) e conferir o card especializado + o `<details>`
  cru + as ações.
- **Automático:** `python -m pytest -q` (a página `/` continua servida; testes de
  `api.py` verdes) e `ruff check . && ruff format --check .` (Python; o JS é string
  e tem `E501` ignorado em `api.py`).

## Fora de escopo
- Gráficos/sparklines com histórico (o store guarda só `last_*`; sem série — YAGNI).
- Mudanças no app `web/` React (outra frente).
- Botão de "regerar contexto" (a regeneração é por criação/TTL — fora daqui).

## DoD
- `_cardHtml` refatorado com dispatcher; funções por kind para todos os kinds;
  `<details>` cru universal; Repo com contexto + diffs + commit.
- Suíte Python verde; lint OK; verificação manual no navegador feita.
