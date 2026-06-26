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

---

> **Para quem assume o desenvolvimento.** Este é o ponto de entrada. Leia nesta
> ordem: (1) [`CLAUDE.md`](../../CLAUDE.md), (2) [`docs/visao/principios.md`](../visao/principios.md)
> (em especial **P11**), (3) os ADRs [0024](../arquitetura/adr/ADR-0024-kind-agente.md)/
> [0025](../arquitetura/adr/ADR-0025-agente-modo-code.md)/[0026](../arquitetura/adr/ADR-0026-llm-provider.md)/
> [0027](../arquitetura/adr/ADR-0027-multiusuario-credenciais.md), (4) este dossiê, (5)
> o [backlog](../roadmap/backlog.md) (épico E7 e fases do multiusuário).

## 1. Onde o desenvolvimento está

Trabalho recente (épico E7 — IDE/agente integrado + produção). Tudo já em `main`,
exceto o multiusuário (branch ativa):

| Entregue | O quê | ADR |
|---|---|---|
| Agente modo `code` | Claude Code agêntico dentro do app; `POST /_agent_run` + SSE `/_agent_run/{id}/stream`; `ThreadingHTTPServer`; runs em background (multitarefa) | ADR-0025 |
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
| **Multiusuário (em andamento)** | ADR-0027 + Fase 1 (cofre cifrado) na branch `feat/multiuser-credentials` | ADR-0027 |

**Branches ativas:** `feat/multiuser-credentials` (Fases 1–2, PR aberto) e
`feat/github-device-flow` (Fase 3, empilhada sobre a anterior). Resto em `main`.

## 2. Como rodar, testar e fazer deploy

**Dois ambientes** (ver [`RASP.md`](../../RASP.md)): local dev (`python -m atlas`,
`http://atlas.local:8080`) e Rasp pseudo-prod (`atlas.service` systemd user,
`http://atlas:8080`, DB em `data/atlas.sqlite`).

**Servidor local roda como serviço systemd** — após mudar código:
```bash
systemctl --user restart atlas.service
journalctl --user -u atlas -f
```

**⚠️ Gotcha de testes (importante):** rode os testes com o **Python do sistema**
(`python -m pytest`), **não** o do venv — o fixture `free_tcp_port` (usado em
`test_api.py`) só existe no Python do sistema. O `cryptography` precisa estar nos
**dois** (venv e sistema). Lint usa o venv: `.venv/bin/ruff check src/`.

```bash
python -m pytest tests/ -q        # 417 testes, devem passar
.venv/bin/ruff check src/ tests/  # deve passar limpo
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
  `/_chat`, `/_insight`, `/_agent_run` (+ `/stream`), `/_status`, `/_schema`, `/_complete`.

## 4. O agente que constrói (atlas-builder)

`Agente/atlas-builder` (modo `code`, provider `claude-default`) é o "Claude Code"
dentro do app. Fluxo: `POST /_agent_run {agente, mensagem}` → roda
`claude -p --output-format stream-json --verbose --dangerously-skip-permissions
--add-dir <projeto> --append-system-prompt <prompt+contexto>` em background; eventos
via SSE. O system-prompt inclui `_agent_api_context(store)` (schema vivo + como criar
recursos via API + relações por label). **Risco de segurança:** escrita livre sob a
raiz do projeto — endurecer é E7-28 (workspace restrito, gate de curadoria).

## 5. Multiusuário — o épico em curso (ADR-0027)

Decisões do PO: **isolamento total** por usuário; **Claude compartilhado** (host)
com custo por usuário; **GitHub via device flow**; **credenciais cifradas**.

| Fase | O quê | Estado |
|---|---|---|
| 1 | Cofre cifrado `secrets_store` (Fernet) | **feito** (branch) |
| 2 | Kinds `User` + `Credential` (metadados; segredo no cofre) | **feito** (branch) |
| 3 | GitHub device flow (start/poll → Credential cifrada + git helper escopado; fallback PAT) | **feito** (branch `feat/github-device-flow`) |
| 4 | Auth/sessão (login; admin via token/loopback) | a fazer |
| 5 | Isolamento por `labels.owner` no store/API + migração | a fazer |

**Fase 1 entregue:** [`src/atlas/secrets_store.py`](../../src/atlas/secrets_store.py) —
`encrypt/decrypt`, `put/get/delete_secret`. Chave em `ATLAS_SECRET_KEY` ou
`secrets/secret.key` (0600). Segredo **nunca** no spec nem no front. Dep nova:
`cryptography` (no `pyproject.toml`). Testes: `tests/test_secrets_store.py`.

**Fase 3 entregue** (branch `feat/github-device-flow`):
[`src/atlas/github_auth.py`](../../src/atlas/github_auth.py) — device flow
(`start_device_flow`/`poll_access_token`/`complete_device_login`), fallback PAT
(`connect_via_pat`), resolução de token (`token_for_owner`) e git helper escopado
(`git_auth_args` → `gitcmd.git(..., auth_args=...)`, sem persistir o token no
`.git/config`). Endpoints: `POST /_github/device/start`, `/_github/device/poll`,
`/_github/pat`. O repo-sync resolve o token do dono (`labels.owner`) e autentica
clone/fetch (`_auth_args_for_repo`). Config: `ATLAS_GITHUB_CLIENT_ID` (OAuth App);
sem ele, só o fallback de PAT funciona. HTTP é stdlib (`urllib`), injetável em teste.

**Como continuar (Fase 4 — auth/sessão):** login → sessão (token opaco, cookie
httpOnly) identifica o usuário por request; `ATLAS_API_TOKEN`/loopback segue como
admin. Hoje o dono das credenciais/recursos vem do corpo do request ou de
`ATLAS_DEFAULT_OWNER` (default `admin`); a Fase 4 troca isso pela sessão e a Fase 5
escopa o store por `labels.owner`. Ver ADR-0027 §Fases.

## 6. Convenções de trabalho (não-negociáveis)

- **Doc é o contrato.** Código que diverge da doc exige ADR (regra de ouro do CLAUDE.md).
- **Branch + PR + Conventional Commits.** Commits terminam com
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- **TDD ao implementar.** Atualize a doc junto com o código.
- **Toda decisão de arquitetura vira ADR** antes de virar código; atualize o
  [índice de ADRs](../arquitetura/adr/README.md) e o [backlog](../roadmap/backlog.md).
- **Nunca commitar segredos.** Tokens vão cifrados no cofre / `secrets/` (gitignored).

## 7. Pendências/known issues abertas

- **E7-28** — endurecer o modo `code` (workspace restrito, gate de curadoria humana,
  persistência de runs, allow/deny de tools por Agente).
- **Multiusuário** — fases 2–5 (acima).
- **Runs agênticos em memória** — perdidos no restart (sem persistência ainda).
- **Auth atual** — token único/loopback; será estendida na Fase 4.
