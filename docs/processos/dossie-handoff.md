---
titulo: Dossiê de handoff — estado atual e como continuar
id: PROC-HANDOFF
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-26
---

# Dossiê de handoff — estado atual e como continuar

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-26 | Tech Lead | Criação — handoff do trabalho recente (E7-24..44, ADR-0025/0026/0027) p/ outro agente | — |
| 1.1    | 2026-06-26 | Tech Lead | Épico multiusuário (ADR-0027) concluído e mergeado em `main` (Fases 1–5 + UI); estado/branches/testes atualizados | — |
| 1.2    | 2026-06-26 | Tech Lead | E7-28 em curso (ADR-0028): workspace restrito + allow/deny de tools + teto de concorrência + flag de gate | — |
| 1.3    | 2026-07-01 | Tech Lead | Épico E9 (tradutor editorial): fixes de store/resume + export md/epub; ADR-0033 + spec + plano do render editorial; E9-01 tarefas 1–4 feitas | — |
| 1.4    | 2026-07-02 | Tech Lead | E9-01..E9-12 concluídos (render editorial HTML/WeasyPrint, TOC/hyperlinks/folio, fallback claude↔ollama). Nova frente **E9-13** (ADR-0041, fidelidade tipográfica + paginação adaptativa) iniciada — 2/12 tarefas feitas | — |
| 1.5    | 2026-07-02 | Tech Lead | **Agente modo `code` via Ollama nativo** (ADR-0042/E7-45, pedido do PO, prioridade máxima) e **recuperação de órfãos no boot + serialização de chamadas Ollama** (ADR-0043/E9-14) — ambos commitados em `main`; não fazem parte do E9-13 | — |
| 1.6    | 2026-07-02 | Tech Lead | **Qualidade/auto mode do Agente via Ollama** (ADR-0044/E7-46): grep/glob reais, CLAUDE.md injetado, `max_turnos`, `POST /_self_restart`, aba 🤖 Auto. `atlas-builder` passou a usar `provider=ollama-local` (gemma4) | — |

---

## ⭐ Estado atual (2026-07-02) — E9-13: fidelidade tipográfica + paginação adaptativa

**Contexto:** o PO revisou o render editorial (motor `render_motor=html`,
ADR-0036) e apontou perda de informação real: fonte genérica (não a do PDF),
ênfase inline (negrito/itálico no meio do parágrafo) descartada, cor de link
forçada em azul, listas numeradas perdidas, notas de rodapé nativas do original
em risco de serem descartadas junto com o fólio, numeração de página inventada
(não a do original) e quebra de página sem relação com o padrão do documento
original. Decisão registrada em [ADR-0041](../arquitetura/adr/ADR-0041-fidelidade-tipografica-e-paginacao-adaptativa.md)
+ seção "Fidelidade avançada" da [spec](../specs/traducao-render-editorial.md).
Backlog: [`roadmap/backlog.md` §E9-13](../roadmap/backlog.md#épico-tradutor-editorial).

**E9-01..E9-12 — feito e commitado em `main`** (motor editorial HTML/WeasyPrint
default, TOC+hyperlinks+folio fiéis, pool de execução, paralelismo de páginas,
fallback claude↔ollama). Ver linhas E9-01..E9-12 no backlog pra detalhe de cada.

**Em andamento — E9-13, 2/12 tarefas do [plano](../superpowers/plans/2026-07-02-fidelidade-editorial-avancada.md):**
- ✅ Task 1 `extracao.py` marca ênfase inline (`**bold**`/`_italic_`) no texto do
  bloco (commit `8c93880`).
- ✅ Task 2 `traducao_ia.montar_prompt_refino` instrui a IA a preservar os
  marcadores de ênfase (commit `ce0ebc3`).
- ⏳ Task 3 `tipografia.py` (**novo módulo**) — `converter_enfase` (marcador →
  `<b>`/`<i>`); ⏳ Task 4 clustering de heading (`clusters_titulo`/`nivel_titulo`)
  + `taxa_abre_pagina`; ⏳ Task 5 `extrair_fontes`/`gerar_font_faces` (fonte real
  embutida via PyMuPDF).
- ⏳ Task 6 `editorial_html.py` liga fonte real + ênfase inline no `_elemento`;
  ⏳ Task 7 listas numeradas (`<ol>`) + zero bloco descartado sem tradução;
  ⏳ Task 8 nota de rodapé nativa (distinta do fólio); ⏳ Task 9 **fólio
  dinâmico** via `string-set` (número igual ao original, escala sozinho no
  reflow); ⏳ Task 10 quebra de página por nível **extraída do PDF** (não regra
  fixa); ⏳ Task 11 `@font-face` real no CSS + link herda cor (remove azul
  fixo); ⏳ Task 12 regressão de fidelidade end-to-end + re-render do PDF de
  controle (observability).

**Como retomar (spec-driven, subagent-driven-development):**
1. Ler [ADR-0041](../arquitetura/adr/ADR-0041-fidelidade-tipografica-e-paginacao-adaptativa.md)
   + seção "Fidelidade avançada" da [spec](../specs/traducao-render-editorial.md).
2. Abrir o [plano](../superpowers/plans/2026-07-02-fidelidade-editorial-avancada.md)
   e continuar nas tarefas com `[ ]` (cada task já tem o código completo — TDD,
   um commit por task). Tasks 3-12 têm dependência sequencial (mesmos arquivos
   editados cumulativamente) — não paralelizar.
3. Trabalho é **direto em `main`**, sem worktree/branch (convenção deste repo,
   CLAUDE.md §0) — mesmo em subagent-driven-development.
4. `handoff-auto.md` (gerado por `scripts/handoff-snapshot.sh`) traz o snapshot
   mecânico mais recente (commits, testes, checkboxes).

**Trabalho concorrente já resolvido:** o WIP paralelo de 2026-07-02
(`agente_ollama.py`, `ADR-0042`, dispatch por motor em `api.py`/`app.py`,
serialização Ollama em `ia.py`, recuperação de órfãos em `retomada.py`) foi
commitado separado do E9-13 — ver [ADR-0042](../arquitetura/adr/ADR-0042-agente-code-via-ollama.md)
(E7-45) e [ADR-0043](../arquitetura/adr/ADR-0043-recuperacao-orfaos-boot-e-serializacao-ollama.md)
(E9-14). Ao retomar o E9-13, ainda vale rodar `git status` antes de tocar em
`README.md`/`backlog.md`/qualquer arquivo compartilhado — outros processos
concorrentes podem surgir de novo.

**Ambiente:** local via `python -m atlas` (env `ATLAS_DB_PATH=data/atlas.sqlite`,
`ATLAS_API_PORT=8080`) → `http://atlas.local:8080`. Já reiniciado no código novo.
**Pendência do PO:** `sudo dnf install -y pandoc` (botão EPUB). Sub-projetos B/C/D
(qualidade AI-augmented, Agente editor + judge, configs de qualidade) = E9-02..04.

---

> **Para quem assume o desenvolvimento.** Este é o ponto de entrada. Leia nesta
> ordem: (1) [`CLAUDE.md`](../../CLAUDE.md), (2) [`docs/visao/principios.md`](../visao/principios.md)
> (em especial **P11**), (3) os ADRs [0024](../arquitetura/adr/ADR-0024-kind-agente.md)/
> [0025](../arquitetura/adr/ADR-0025-agente-modo-code.md)/[0026](../arquitetura/adr/ADR-0026-llm-provider.md)/
> [0027](../arquitetura/adr/ADR-0027-multiusuario-credenciais.md), (4) este dossiê, (5)
> o [backlog](../roadmap/backlog.md) (épico E7 e fases do multiusuário).

## 1. Onde o desenvolvimento está

Trabalho recente (épico E7 — IDE/agente integrado + produção) e o épico
**multiusuário** (ADR-0027). **Tudo em `main`** (o CD da Rasp acompanha `main`):

| Entregue | O quê | ADR |
|---|---|---|
| Agente modo `code` | Claude Code agêntico dentro do app; `POST /_agent_run` + SSE `/_agent_run/{id}/stream`; `ThreadingHTTPServer`; runs em background (multitarefa) | ADR-0025 |
| Agente modo `code` via Ollama | Segundo motor 2b: loop de tool-calling nativo (`agente_ollama.py`) contra `POST /api/chat`; `_run_agent_bg` despacha por motor resolvido, fallback pro claude se o endpoint cair antes do 1º turno; erro de tool vira `warning` não-fatal; custo 0 | ADR-0042 |
| Agente segue a API | system-prompt injeta o schema vivo + seção de relações (P11); o agente cria recursos **pela API** | ADR-0025 |
| LLMProvider | Kind de config de IA; `Agente.provider` dita o modelo; `_resolve_engine` | ADR-0026 |
| Análise de repo por Agente | `Repo.spec.analyze_agente` (default `repo-analyzer`); insight manual + automático no sync | ADR-0024 §2 |
| Multirepo `RepoGroup` | dash manager: Visão \| 🎯 Objetivos (Goals×Trackers, barras) \| 🔍 Análises \| Config; "🔔 Sync diário" | — |
| Serialização snapshot | `/repo snapshot` serializa a árvore inteira → Doc; aba 📁 Files | — |
| Landing Hub | Home (Construir com IA + rastreio + quadro branco); Explorer/Graph/Status no menu ☰ Mais | — |
| Render de Job + aba Jobs no Repo | vínculo por **label** (`spec.label`), não por nome | — |
| Fix sync por label | `_resolve_repo_sync_job`; `POST /_run {repo}`; Jobs do store rodam (`_rotina_from_job`) | — |
| Tracking de gasto de IA | acumula `custo_total_usd`/`runs` no status do Agente quando evocado | — |
| CD na Rasp | `scripts/atlas-deploy.{sh,service,timer}` — pull main + restart a cada 5 min | — |
| Job schema unificado | `schedule`/`model`/`active` (era `agenda`/`modelo`/`ativa`) | — |
| **Multiusuário (completo)** | ADR-0027 — cofre cifrado, User/Credential, GitHub device flow, auth/sessão, isolamento por dono + UI de login | ADR-0027 |

**Sem branches de feature abertas** do multiusuário — Fases 1–5 + UI mergeadas em
`main` (PR #4 das Fases 1–2 + rebase das Fases 3–5/UI). O ADR-0027 está **aceito**.

## 2. Como rodar, testar e fazer deploy

**Dois ambientes** (ver [`RASP.md`](../../RASP.md)): local dev (`python -m atlas`,
`http://atlas.local:8080`) e Rasp pseudo-prod (`atlas.service` systemd user,
`http://atlas:8080`, DB em `data/atlas.sqlite`).

**Servidor local roda como serviço systemd** — após mudar código:
```bash
systemctl --user restart atlas.service
journalctl --user -u atlas -f
```

**Testes (gotcha resolvido):** a suíte roda com **qualquer Python** — `python -m
pytest` (sistema) **ou** `.venv/bin/pytest` (venv). O fixture `free_tcp_port` agora
é definido em [`tests/conftest.py`](../../tests/conftest.py) (não depende mais do
plugin do `anyio` no Python do sistema), e `pythonpath=["src","."]` no
`pyproject.toml` faz o `pytest` puro do CI achar `tests.repohelpers`.

```bash
.venv/bin/pytest -q                 # 526 testes, devem passar (igual ao CI)
.venv/bin/ruff check .              # repo inteiro, deve passar limpo
.venv/bin/ruff format --check .     # idem (CI também checa)
```

**CD (Rasp):** o timer `atlas-deploy.timer` puxa `main` e reinicia sozinho. Para
ir a produção: merge em `main` (o CD aplica em ≤5 min). Instalação do CD: ver RASP.md.

## 3. Arquitetura essencial (o que você precisa saber)

- **Tudo é objeto (P11).** API REST estilo K8s: `GET/PUT/DELETE /apis/atlas/v1/<Kind>/<name>`.
  Recursos se relacionam **por labels/selectors**, nunca por convenção de nome. Novo
  tipo de coisa = **novo Kind**. A fonte da verdade do store é o SQLite via `ResourceStore`.
- **Kinds atuais:** Tracker, Goal, Alarm, Job (ex-Routine), RepoGroup, Repo, Branch,
  Commit, Diff, Idea, Task, Doc, RoutineRequest, Timer, Prompt, LLMProvider, Agente.
  Schema (forms/ações) em [`src/atlas/api_schema.py`](../../src/atlas/api_schema.py).
- **Renders especializados** ("quadro branco", ADR-0020): `src/atlas/dashboard/kinds/*.js`
  registram via `registerRender('Kind', fn)`. Hoje: repo, repogroup, agente, job.
  O resto cai no editor genérico. Front é cliente da API (ADR-0019).
- **Motor de IA (ADR-0001/0022):** `claude` CLI via `src/atlas/ia.py`
  (`invocar`/`invocar_ollama`). 2a = análise single-turn; 2b = agente com tools
  (modo `code`, só Agentes marcados). `_resolve_engine(spec, store)` resolve
  motor/modelo/endpoint a partir do `LLMProvider` (ou campos do Agente).
- **Endpoints especiais** (em `api.py`, `do_POST`/`do_GET`): `/_run`, `/_cmd`,
  `/_chat`, `/_insight`, `/_agent_run` (+ `/stream`), `/_status`, `/_schema`, `/_complete`,
  `/_self_restart` (admin-only, ADR-0044 — reinício destacado do processo local).

## 4. O agente que constrói (atlas-builder)

`Agente/atlas-builder` (modo `code`, provider `claude-default`) é o "Claude Code"
dentro do app. Fluxo: `POST /_agent_run {agente, mensagem}` → roda
`claude -p --output-format stream-json --verbose --dangerously-skip-permissions
--add-dir <projeto> --append-system-prompt <prompt+contexto>` em background; eventos
via SSE. O system-prompt inclui `_agent_api_context(store)` (schema vivo + como criar
recursos via API + relações por label). **Risco de segurança:** escrita livre sob a
raiz do projeto — endurecer é E7-28 (workspace restrito, gate de curadoria).

## 5. Multiusuário — épico concluído (ADR-0027, aceito)

Decisões do PO: **isolamento total** por usuário; **Claude compartilhado** (host)
com custo por usuário; **GitHub via device flow**; **credenciais cifradas**. Todas as
fases + a UI estão em `main`.

| Fase | O quê | Estado |
|---|---|---|
| 1 | Cofre cifrado `secrets_store` (Fernet) | **feito** (em `main`) |
| 2 | Kinds `User` + `Credential` (metadados; segredo no cofre) | **feito** (em `main`) |
| 3 | GitHub device flow (start/poll → Credential cifrada + git helper escopado; fallback PAT) | **feito** (em `main`) |
| 4 | Auth/sessão (login por senha local + login via GitHub; cookie httpOnly; admin via token/loopback) | **feito** (em `main`) |
| 5 | Isolamento por `labels.owner` no store/API + migração | **feito** (em `main`) |
| 6 | UI multiusuário no front (login + Conectar GitHub + logout) | **feito** (em `main`) |

**Fase 1 entregue:** [`src/atlas/secrets_store.py`](../../src/atlas/secrets_store.py) —
`encrypt/decrypt`, `put/get/delete_secret`. Chave em `ATLAS_SECRET_KEY` ou
`secrets/secret.key` (0600). Segredo **nunca** no spec nem no front. Dep nova:
`cryptography` (no `pyproject.toml`). Testes: `tests/test_secrets_store.py`.

**Fase 3 entregue** (em `main`):
[`src/atlas/github_auth.py`](../../src/atlas/github_auth.py) — device flow
(`start_device_flow`/`poll_access_token`/`complete_device_login`), fallback PAT
(`connect_via_pat`), resolução de token (`token_for_owner`) e git helper escopado
(`git_auth_args` → `gitcmd.git(..., auth_args=...)`, sem persistir o token no
`.git/config`). Endpoints: `POST /_github/device/start`, `/_github/device/poll`,
`/_github/pat`. O repo-sync resolve o token do dono (`labels.owner`) e autentica
clone/fetch (`_auth_args_for_repo`). Config: `ATLAS_GITHUB_CLIENT_ID` (OAuth App);
sem ele, só o fallback de PAT funciona. HTTP é stdlib (`urllib`), injetável em teste.

**Fase 4 entregue** (em `main`):
[`users.py`](../../src/atlas/users.py) (senha local: PBKDF2 cifrado no cofre,
`create_user`/`verify_password`), [`sessions.py`](../../src/atlas/sessions.py)
(sessão em memória, token opaco + TTL) e a auth da API: `_identity()` resolve
`(user, role)` de **admin** (token/loopback) **ou** sessão (cookie `atlas_session`
httpOnly); `_auth()` exige um dos dois. Endpoints **públicos** (pré-gate):
`POST /_auth/login` (senha), `/_auth/logout`, `/_auth/github/start|poll` (login via
device flow — cria o `User`, salva a credencial e abre sessão), `GET /_auth/me`, e
`POST /_auth/users` (**admin** cria usuário + define senha — bootstrap do sistema).

**Fase 5 entregue** (em `main`):
[`scoping.py`](../../src/atlas/scoping.py) (políticas puras `can_see`/`can_write`/
`stamp_owner`/`visible` + `migrate_unowned`). A API escopa **list/get/put/delete**
pelo dono da sessão: o admin vê/altera tudo; o member só os seus recursos (recurso
alheio ⇒ **404**, não revela existência); `labels.scope=system` é global (read-only a
não-admin); no create, o dono é **carimbado** (member não escolhe). Migração no boot
([`app.py`](../../src/atlas/app.py)): recursos antigos sem dono vão para `ATLAS_DEFAULT_OWNER`
(default `admin`), idempotente. **Importante:** o isolamento roda na camada **HTTP**;
usos internos do store (sync, rotinas, scheduler) **não** são escopados.

**UI multiusuário no front (feito).** Tela de login ([index.html](../../src/atlas/dashboard/index.html)
+ [main.js](../../src/atlas/dashboard/main.js)): senha local, **Conectar com GitHub**
(device flow), e token de API como opção avançada (admin/script); chip de usuário +
logout no titlebar; botão **🔗 Conectar GitHub** (credencial p/ repo-sync do usuário
logado). `init()` checa `GET /_auth/me` e abre o login no 401. Local (loopback) segue
admin sem tela de login.

**Pendências do épico (não-bloqueantes, viram backlog):** ~~persistência de sessões~~
(feito, item 1.2); rotação/backup da chave mestra do cofre. Ver ADR-0027 §Pendências.

## 6. Convenções de trabalho (não-negociáveis)

- **Doc é o contrato.** Código que diverge da doc exige ADR (regra de ouro do CLAUDE.md).
- **Branch + PR + Conventional Commits.** Commits terminam com
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- **TDD ao implementar.** Atualize a doc junto com o código.
- **Toda decisão de arquitetura vira ADR** antes de virar código; atualize o
  [índice de ADRs](../arquitetura/adr/README.md) e o [backlog](../roadmap/backlog.md).
- **Nunca commitar segredos.** Tokens vão cifrados no cofre / `secrets/` (gitignored).

## 7. Pendências/known issues abertas

- **E7-28** — endurecer o modo `code`. **Feito** (ADR-0028, branch
  `feat/hardening-agente-code`): **workspace restrito**
  (`resolve_workspace` confina cwd/`--add-dir`, recusa traversal/symlink),
  **allow/deny de tools** (`build_tool_args` → `--allowedTools`/`--disallowedTools`,
  campos `allowed_tools`/`denied_tools` no schema), **teto de concorrência**
  (`active_runs_count` + `ATLAS_AGENT_MAX_CONCURRENT`, default 3 → 429), **gate**
  (`spec.gate`, carimbada no `init`), **persistência de runs**
  (`persist_agent_run` → Kind `AgentRun` escopado por `labels.owner`) e **UI de
  curadoria** ([curadoria.py](../../src/atlas/curadoria.py) + aba 🔍 Curadoria no
  Agente: diff → aprovar em branch `agent/<id>` / descartar; endpoints
  `GET/POST /_agent_run/{id}/diff|discard|approve` escopados por dono).
  **Limitações documentadas** (SPEC-CURADORIA): working tree compartilhada; `approve`
  no repo vivo da Rasp é dev-time.
- ~~**Sessões em memória**~~ — **resolvido** (item 1.2): `sessions.py` persiste em
  `sessions.json` (só o hash sha256 do token; escrita atômica; degrade em IO/arquivo
  corrompido) → sobrevivem a restart. Path: `ATLAS_SESSIONS_PATH` ou `<dir do DB>/sessions.json`.
- ~~**Chave mestra do cofre** — sem rotação/backup~~ — **resolvido** (item 1.4):
  `secrets_store.rotate_key()` + `scripts/rotate_secret_key.py` (re-cifra tudo,
  backup automático da chave antiga).
- ~~**UX de cadastro de usuários**~~ — **resolvido** (item 1.4b): **auto-registro com
  código** (`ATLAS_SIGNUP_CODE` habilita "criar conta" na tela de login;
  `POST /_auth/register`; papel sempre `member`). Convite individual por link e
  rate-limit de brute-force ficam em backlog (SPEC-AUTO-REGISTRO).

> Os **próximos passos priorizáveis** estão consolidados em
> [`docs/roadmap/proximos-passos.md`](../roadmap/proximos-passos.md).
