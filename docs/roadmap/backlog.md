---
titulo: Backlog
id: ROAD-BACKLOG
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-23
---

# Backlog

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação | PO/PM        |
| 1.1    | 2026-06-16 | Tech Lead | Lição de casa (itens 0–5): ADR-0013 + specs; épico E5 (interface/trackers via chat); detalhe de E1/E2 | — |
| 1.2    | 2026-06-16 | Tech Lead | Pool de ideias (ADR-0014, prioridade máxima) = épico E6; alarmes (E5-07) | PO/PM |
| 1.3    | 2026-06-16 | Tech Lead | Atualização de estados: E0-01/03/04 feitos; E1-11/E5-06/E2-01 feitos; E5-03/E3-01 feitos | — |
| 1.4    | 2026-06-16 | Tech Lead | E1-05 scaffold feito; E4-07 feito; kinds Timer+CheckIn+labels adicionados ao core | — |
| 1.5    | 2026-06-23 | Tech Lead | Épico E7 (carro-chefe Repo) + ADR-0023 proposto; ADRs irmãos 0020/0021/0022/0024; estado atual do repo-sync marcado como feito | — |
| 1.6    | 2026-06-23 | Tech Lead | ADRs irmãos 0020/0021/0022/0024 escritos (proposto); links atualizados | — |
| 1.7    | 2026-06-23 | Tech Lead | ADR-0023 **aceito**; spec (a) dados/pull ([SPEC-REPO-DADOS](../specs/repo-especializacao-dados.md)) em implementação (E7-01..06 em-andamento) | PO/PM |

---

> Épicos → histórias, priorizados. O PO/PM define prioridade; o Tech Lead
> decompõe em specs de tarefa. Estados: `proposto` · `pronto` (DoR ok) ·
> `em-andamento` · `feito` · `bloqueado`.

## ⭐ Épico E0 — Core como API de objetos (K8s-like) — **PRIORIDADE MÁXIMA**
> Motor central: tudo é objeto, verbos uniformes, `describe` em tudo. Interfaces
> (Telegram, web) viram adapters. Ver [ADR-0015](../arquitetura/adr/ADR-0015-core-api-de-objetos.md)
> e [spec core-api-objetos](../specs/core-api-objetos.md).

| ID | História | Estado | ADR/doc |
|---|---|---|---|
| E0-01 | **Core de objetos**: `Resource` + `ResourceStore` (verbos uniformes get/list/apply/patch/delete) sobre tabela `resources` (aditiva) | **feito** | [ADR-0015](../arquitetura/adr/ADR-0015-core-api-de-objetos.md), [spec](../specs/core-api-objetos.md) |
| E0-02 | **API HTTP** (stdlib) expondo os verbos: `GET/POST/PUT/PATCH/DELETE /apis/atlas/v1/<kind>[/<name>]` | proposto | [ADR-0015](../arquitetura/adr/ADR-0015-core-api-de-objetos.md) |
| E0-03 | **Verbos uniformes no chat** (`/resources`, `/list`, `/get`, `/describe`, `/apply`, `/delete`) | **feito** — `verbos.py` + roteado em `handler.py` | [ADR-0015](../arquitetura/adr/ADR-0015-core-api-de-objetos.md) |
| E0-04 | **Migrar kinds** legados (Idea/Task/RoutineRequest, Tracker, Alarm, Routine) para o store — boot sync + CRUD espelhado | **feito** — `sync.py` + todos os módulos leem/escrevem no store | [ADR-0015](../arquitetura/adr/ADR-0015-core-api-de-objetos.md) |
| E0-05 | **AuthN/Z da API** (token) — pré-requisito para expor a HTTP — **CRÍTICO p/ Claude Code SSH** | proposto | [seguranca](../arquitetura/seguranca.md) |
| E0-06 | **CLI SSH** (vs Vercel) consumindo API auth — **CRÍTICO p/ dev noturno autônomo** | proposto | [ADR-0015](../arquitetura/adr/ADR-0015-core-api-de-objetos.md), [[autonomous-dev-loop]] |

## Épico E1 — Motor mínimo (M1)
| ID | História | Estado | ADR/doc |
|---|---|---|---|
| E1-01 | Auto-descoberta e carga de rotinas a partir de `routines/` | **feito** | [ciclo-de-vida](../arquitetura/ciclo-de-vida-rotina.md) |
| E1-02 | Schema SQLite + camada de acesso | **feito** | [ADR-0002](../arquitetura/adr/ADR-0002-modelo-de-dados.md) |
| E1-03 | Adapter Telegram (long-poll, `enviar`/`receber`, filtro de ID) | **feito (MVP)** | [seguranca](../arquitetura/seguranca.md) |
| E1-04 | Roteador determinístico + micro-sintaxe + fallback Haiku | **parcial (MVP)** — handler de comandos + registro; falta conflito de triggers e fallback Haiku | [ADR-0008](../arquitetura/adr/ADR-0008-roteamento-e-extracao.md) |
| E1-05 | Invocador de IA: modo análise (2a) e agente (2b). No Pi: verificar `claude -p` (cliente) em **arm64** + login ativo + rede — modelos rodam na nuvem, não no Pi | **parcial** — `atlas.ia.invocar` via `claude -p` implementado; pendente field-test no Pi (arm64 + login) | [ADR-0001](../arquitetura/adr/ADR-0001-ia-em-dois-modos.md), [ADR-0012](../arquitetura/adr/ADR-0012-empacotamento-docker.md) |
| E1-06 | Agendador + catch-up de runs perdidos | **feito** — core + **wiring no loop do `app`** (catch-up no boot + `tick` por janela de poll, disparo via executor notificando o dono) | [ADR-0006](../arquitetura/adr/ADR-0006-erro-e-resiliencia.md), [spec scheduler](../specs/scheduler.md) |
| E1-07 | Harness de teste de rotina | proposto | [ADR-0007](../arquitetura/adr/ADR-0007-contrato-de-teste.md) |
| E1-10 | Executor do ciclo de vida (`trigger→collect→gate→analyze→deliver`) + notificação no Telegram + gravação em `runs` | **feito** (core; fases injetadas) — wiring de `/rodar` fica em E5-02 (precisa do carregador + invocador E1-05) | [ciclo-de-vida](../arquitetura/ciclo-de-vida-rotina.md), [spec executor](../specs/executor-e-notificacao.md) |
| E1-11 | Barreira de entrada: registrar só com intenção explícita (reescreve `handler.py`) | **feito** | [ADR-0013](../arquitetura/adr/ADR-0013-barreira-de-entrada.md), [spec barreira](../specs/barreira-entrada.md) |
| E1-08 | Observabilidade: gravar `usage` em `runs` + `/uso` | proposto | [ADR-0010](../arquitetura/adr/ADR-0010-observabilidade-claude-p.md) |
| E1-09 | Orçamento: teto global pré-despacho + disjuntor por rotina | proposto | [ADR-0005](../arquitetura/adr/ADR-0005-orcamento-reativo.md) |

## Épico E2 — Rotinas-âncora (M2)
| ID | História | Estado | ADR/doc |
|---|---|---|---|
| E2-01 | Rotina **resumo diário** (collect tudo do dia; análise 2a bloqueada por E1-05) | **feito (camada 0)** — `rotinas/resumo_diario.py` + `routines/resumo-diario/routine.toml`; agenda 21h | [personas](../visao/personas-e-uso.md) |
| E2-02 | **Meta-loop** fase 1 (planejamento no Telegram → `SPEC.md`) | proposto | [ADR-0009](../arquitetura/adr/ADR-0009-handoff-entre-modos.md) |
| E2-03 | **Meta-loop** fase 2 (geração via agente 2b, inativo por padrão) — **CRÍTICO p/ dev noturno** | proposto | [ADR-0003](../arquitetura/adr/ADR-0003-seguranca-meta-loop.md) |
| E2-04 | `/ativar` + fluxo de revisão e commit da rotina gerada | proposto | [ADR-0003](../arquitetura/adr/ADR-0003-seguranca-meta-loop.md), [spec meta-loop](../specs/meta-loop-chat.md) |

## Épico E5 — Interface de configuração e trackers via chat (prioridade atual)
> A "interface de configuração total via chat" (lição de casa, itens 4–5). O bot é
> o frontend do motor; tudo 0 IA, exceto a geração de rotina (E2).

| ID | História | Estado | ADR/doc |
|---|---|---|---|
| E5-01 | Comandos de listagem/inspeção: `/rotinas`, `/rotina <nome>`, `/uso`, `/status` (evoluir), `/ajuda` dinâmico | **parcial** — registro único de comandos (inglês), `/help` dinâmico + `setMyCommands`, `/status` evoluído, **sessão `/debug`** (status/runs/routines/db/env); falta `/rotinas`/`/uso` | [spec interface](../specs/interface-config-chat.md) |
| E5-02 | Ciclo de vida por chat: `/activate`, `/deactivate`, `/run <name>` (+ `/routines`, `/routine <name>`) | **feito** — ativação via override no DB (persiste no volume; agendamento aplica no restart) | [spec interface](../specs/interface-config-chat.md), [spec executor](../specs/executor-e-notificacao.md) |
| E5-03 | Edição de config interativa (`/routine <name> set <field> <value>`) com validação | **feito** — campo `agenda` (cron 5 parts); override persiste em `routine_state` | [spec interface](../specs/interface-config-chat.md) |
| E5-04 | Tabela `trackers` + registro genérico `tracking` (micro-sintaxe aplica em runtime) | **feito** | [spec trackers](../specs/trackers-via-chat.md), [ADR-0002](../arquitetura/adr/ADR-0002-modelo-de-dados.md) |
| E5-05 | Comandos `/track` (list/new/detalhe+stats/rm) + log por `nome: valor` | **feito** (single-line; wizard interativo e metas ficam p/ depois) | [spec trackers](../specs/trackers-via-chat.md) |
| E5-06 | `/reg` (nota livre, com domínio opcional) | **feito** — `/reg <texto>` e `/reg #<domínio> <texto>`; domínios: sono/saude/fisico/estudo/leitura/trabalho/geral | [ADR-0013](../arquitetura/adr/ADR-0013-barreira-de-entrada.md), [spec barreira](../specs/barreira-entrada.md) |
| E5-07 | Alarmes/lembretes: tabela `alarms` + `tick_alarmes` no loop + `/alarm`/`/alarms` | **feito** — diário/uma-vez, dispara e notifica o dono; persiste no volume | [spec alarmes](../specs/alarmes.md), [spec scheduler](../specs/scheduler.md) |

## Épico E6 — Pool de ideias e autoimplementação (PRIORIDADE MÁXIMA)
> Capturar ideias/tarefas/lições pelo Telegram e alimentar a geração automática de
> rotinas (ativação sempre humana). Decisão: [ADR-0014](../arquitetura/adr/ADR-0014-pool-de-ideias-desenvolvimento.md).

| ID | História | Estado | ADR/doc |
|---|---|---|---|
| E6-01 | Tabela `ideas` + migração idempotente de schema | **feito** | [ADR-0014](../arquitetura/adr/ADR-0014-pool-de-ideias-desenvolvimento.md), [spec pool](../specs/pool-de-ideias.md) |
| E6-02 | Captura via Telegram (`/ideia`, `/tarefa`/`/licao`, `/rotina_nova`) | **feito** | [spec pool](../specs/pool-de-ideias.md) |
| E6-03 | CRUD/priorização (`/ideias`, `/ideia <id>`, `prio`, `editar`, `feito`, `arquivar`, `remover`) | **feito** | [spec pool](../specs/pool-de-ideias.md) |
| E6-04 | Pool → geração: item `rotina` dispara meta-loop (agente 2b gera inativo) — **CRÍTICO p/ loop autônomo** | pronto (spec) | [ADR-0014](../arquitetura/adr/ADR-0014-pool-de-ideias-desenvolvimento.md), [spec meta-loop](../specs/meta-loop-chat.md) |

## ⭐ Épico E7 — Repo como carro-chefe (multi-branch, git-graph, progresso) — **PRIORIDADE ALTA**
> Especializar a capacidade mais importante do produto. Decisão: [ADR-0023](../arquitetura/adr/ADR-0023-especializacao-kind-repo.md).
> Depende dos ADRs irmãos 0020 (quadro branco), 0022 (motor plugável) e 0024 (Agente)
> para a experiência completa; o Repo materializa dados e degrada sem eles.
>
> **Ao despachar um modelo desenvolvedor neste épico, aponte-o para o
> [dossiê de contexto E7](../superpowers/plans/2026-06-23-repo-e7-dossie-contexto.md)** —
> agrega ADRs, código, plano e padrões de teste em ordem de leitura.

### Já feito (estado atual do `repo-sync`)
| ID | História | Estado | ADR/doc |
|---|---|---|---|
| E7-00a | Kind **Repo** + rotina `repo-sync`: clone raso, pull de `origin/HEAD`, diff single-branch | **feito** | [repo_sync/](../../src/atlas/rotinas/repo_sync/) |
| E7-00b | Kind **Diff** por commit com explicação de IA (Sonnet) | **feito** | [repo_sync/](../../src/atlas/rotinas/repo_sync/) |
| E7-00c | **Doc** de contexto do projeto (Opus, corpus README+docs+metadados, TTL) + **Doc** por commit | **feito** | [repo_sync/](../../src/atlas/rotinas/repo_sync/) |
| E7-00d | `Repo.status` com metadados do HEAD (last_commit/autor/data/stat) + schema/ações no `/_schema` | **feito** | [api_schema.py](../../src/atlas/api_schema.py), [ADR-0017](../arquitetura/adr/ADR-0017-gui-por-kind-abstrai-api.md) |
| E7-00e | Card de Repo no dashboard (contexto + diffs recentes) | **feito** | [api.py](../../src/atlas/api.py) |

### A fazer (ADR-0023)
| ID | História | Estado | ADR/doc |
|---|---|---|---|
| E7-01 | Kinds **`Branch`** e **`Commit`** (ocultos), agregados por label `repo=<label>` | **feito** | [materialize.py](../../src/atlas/rotinas/repo_sync/materialize.py), [spec](../specs/repo-especializacao-dados.md) |
| E7-02 | Pull **multi-branch**: fetch de todas as branches remotas + materialização de `Branch`/`Commit` leves | **feito** | [gitcmd.py](../../src/atlas/rotinas/repo_sync/gitcmd.py), [spec](../specs/repo-especializacao-dados.md) |
| E7-03 | **Git-graph híbrido**: grafo reconstruído de `Commit.parents`+ponteiros (store, offline); `Diff` pesado sob demanda | **feito** (dados; render visual = E7-08) | [ADR-0023](../arquitetura/adr/ADR-0023-especializacao-kind-repo.md), [spec](../specs/repo-especializacao-dados.md) |
| E7-04 | **Serialização incremental por preset** (`off`/`docs`/`docs+code`) dos arquivos alterados → `Doc`; nunca binário compilado | **feito** (texto/office-stdlib/pdf-cli) | [serialize.py](../../src/atlas/rotinas/repo_sync/serialize.py), [spec](../specs/repo-especializacao-dados.md) |
| E7-05 | **`analyze_policy`** (branch default=auto, demais=manual, pular merges, `min_lines`, allowlist) + disjuntor de budget — **versão degradada** (sem Kind `Agente` ainda) | **feito** (degradado; troca p/ Agente quando ADR-0024 entrar) | [analyze.py](../../src/atlas/rotinas/repo_sync/analyze.py), [ADR-0005](../arquitetura/adr/ADR-0005-orcamento-reativo.md), [spec](../specs/repo-especializacao-dados.md) |
| E7-06 | **Backfill** (`repo backfill`): `--unshallow` + varredura do histórico; idempotente; 0 IA por padrão | **feito** | [backfill.py](../../src/atlas/rotinas/repo_sync/backfill.py), [spec](../specs/repo-especializacao-dados.md) |
| E7-07 | Config **schema-driven** dos campos novos do Repo (branches, serialize, analyze, goal) — blocos visuais, sem manifesto cru | **parcial** — campos de branches/serialize/analyze no schema; `goal` fica p/ E7-09 | [api_schema.py](../../src/atlas/api_schema.py), [ADR-0017](../arquitetura/adr/ADR-0017-gui-por-kind-abstrai-api.md) |
| E7-08 | **Render do Repo** no quadro branco: aba Repos, git-graph, dashboards de progresso (4 eixos), timeline, ações | **feito** | [ADR-0023](../arquitetura/adr/ADR-0023-especializacao-kind-repo.md), [ADR-0020](../arquitetura/adr/ADR-0020-views-especializadas-por-kind.md) |
| E7-09 | **Progresso vs. meta**: amarrar Repo a um `Goal` (label) e mostrar avanço | proposto | [ADR-0023](../arquitetura/adr/ADR-0023-especializacao-kind-repo.md) |
| E7-10 | **Modularização do front embutido** por Kind (`dashboard/kinds/repo/*`), servido pela API | **feito** | [ADR-0023](../arquitetura/adr/ADR-0023-especializacao-kind-repo.md), [ADR-0020](../arquitetura/adr/ADR-0020-views-especializadas-por-kind.md) |
| E7-11 | **Telegram do Repo**: notificações ricas (pool), prompts stateful opt-in, comandos simples, digest periódico | proposto | [ADR-0023](../arquitetura/adr/ADR-0023-especializacao-kind-repo.md), [ADR-0019](../arquitetura/adr/ADR-0019-interfaces-clientes-da-api.md) |

### ADRs irmãos (mesmo brainstorm)
| ID | História | Estado | ADR/doc |
|---|---|---|---|
| E7-20 | **ADR-0020** — Views especializadas por Kind (quadro branco genérico: slot de render, kinds ocultos/aninhados, aba) | **feito** | [ADR-0020](../arquitetura/adr/ADR-0020-views-especializadas-por-kind.md), [dashboard/](../../src/atlas/dashboard/) |
| E7-21 | **ADR-0021** — Renomeação Rotina → **Job** em código/docs/API/front | **feito** | [ADR-0021](../arquitetura/adr/ADR-0021-rotina-para-job.md) |
| E7-22 | **ADR-0022** — Motor de IA selecionável e plugável (incl. Ollama/Gemma local) | **feito** | [ia.py](../../src/atlas/ia.py), [ADR-0022](../arquitetura/adr/ADR-0022-motor-de-ia-plugavel.md) |
| E7-23 | **ADR-0024** — Kind **`Agente`** (analisador configurável: motor + nível de contexto + prompt + política) | **feito** (schema + `/_chat`) | [api_schema.py](../../src/atlas/api_schema.py), [ADR-0024](../arquitetura/adr/ADR-0024-kind-agente.md) |
| E7-24 | **Agente Builder**: prompt natural → configura Kind Agente automaticamente — **CRÍTICO p/ curadoria automática** | pronto (design) | [ADR-0024](../arquitetura/adr/ADR-0024-kind-agente.md), [ADR-0013](../arquitetura/adr/ADR-0013-barreira-de-entrada.md), [[autonomous-dev-loop]] |
| E7-25 | **Render chat do Agente** (quad. branco): interface interativa via motor plugável — **CRÍTICO p/ IDE integrado** | **feito** | [kinds/agente.js](../../src/atlas/dashboard/kinds/agente.js) |
| E7-26 | **Adapter Ollama** em `atlas.ia`: integra endpoint local testado (192.168.86.22:11434, gemma4) — **CRÍTICO p/ dev na Rasp via Tailnet** | **feito** | [ia.py](../../src/atlas/ia.py) |
| E7-27 | **ADR-0025** — Agente **modo `code`** (Claude Code agêntico 2b no workspace): campo `modo`, `POST /_agent_run` + SSE `GET /_agent_run/{id}/stream`, `ThreadingHTTPServer`, runs assíncronos p/ multitarefa. Atende "ser um Claude Code". | **feito** (núcleo); pendências de segurança no ADR | [ADR-0025](../arquitetura/adr/ADR-0025-agente-modo-code.md), [api.py](../../src/atlas/api.py), [kinds/agente.js](../../src/atlas/dashboard/kinds/agente.js) |
| E7-28 | **Endurecimento do modo `code`**: workspace restrito, gate de curadoria humana, persistência de runs, allow/deny de tools por Agente | proposto | [ADR-0025](../arquitetura/adr/ADR-0025-agente-modo-code.md) §Pendências, [ADR-0003](../arquitetura/adr/ADR-0003-seguranca-meta-loop.md) |
| E7-29 | **Agente segue o modelo de objetos da API**: injeta schema vivo (kinds+spec) + instruções no system-prompt do modo `code`, fazendo o agente criar/editar recursos via API REST (não SQLite/arquivos) | **feito** | [api.py](../../src/atlas/api.py) (`_agent_api_context`) |
| E7-30 | **Multirepo (Kind `RepoGroup`)**: dashboard que agrupa uma série de Repos — resumo agregado + grid de cards clicáveis + "Sync todos" | **feito** | [kinds/repogroup.js](../../src/atlas/dashboard/kinds/repogroup.js), [api_schema.py](../../src/atlas/api_schema.py), [ADR-0023](../arquitetura/adr/ADR-0023-especializacao-kind-repo.md) |
| E7-31 | **Serialização: snapshot sob demanda + aba Files**: serializa a árvore inteira atual do repo (`/repo snapshot`, `gitcmd.list_tree` + `serialize.snapshot_tree`) p/ acompanhar o conteúdo de dentro do repo; aba 📁 Files navega os arquivos por pasta | **feito** | [serialize.py](../../src/atlas/rotinas/repo_sync/serialize.py), [comandos_repo.py](../../src/atlas/comandos_repo.py), [kinds/repo.js](../../src/atlas/dashboard/kinds/repo.js) |
| E7-32 | **Repaginação do front (landing Hub)**: Home como view padrão (Construir com IA + rastreio + galeria do quadro branco); Explorer/Graph/Status no menu ☰ Mais (camada "por baixo do capô") | **feito** | [home.js](../../src/atlas/dashboard/home.js), [ADR-0020](../arquitetura/adr/ADR-0020-views-especializadas-por-kind.md) |
| E7-33 | **Sistema multiusuário (isolamento total)** — desenhado no [ADR-0027](../arquitetura/adr/ADR-0027-multiusuario-credenciais.md). Decisões: isolamento total por `labels.owner`; Claude compartilhado (host) c/ custo por usuário; GitHub device flow; credenciais cifradas. **Faseado** (ver ADR §Fases) | em andamento (ADR + Fase 1 feitos) | [ADR-0027](../arquitetura/adr/ADR-0027-multiusuario-credenciais.md) |
| E7-33a | **Fase 1 — Cofre de segredos cifrados** (`secrets_store`, Fernet/AES via `cryptography`): chave mestra em `ATLAS_SECRET_KEY` ou `secrets/secret.key` (0600); blobs cifrados em `secrets/credentials/<id>.enc`; segredo nunca no spec/front | **feito** | [secrets_store.py](../../src/atlas/secrets_store.py), [test_secrets_store.py](../../tests/test_secrets_store.py) |
| E7-33b | **Fase 2 — Kinds `User` + `Credential`** (metadados; segredo no cofre via `credentials.save_credential`/`get_secret`; vínculo por `labels.owner`) | **feito** | [credentials.py](../../src/atlas/credentials.py), [api_schema.py](../../src/atlas/api_schema.py), [test_credentials.py](../../tests/test_credentials.py) |
| E7-33c | **Fase 3 — GitHub device flow** (start/poll → Credential cifrada + git helper escopado; fallback PAT) | **feito** | [github_auth.py](../../src/atlas/github_auth.py), [api.py](../../src/atlas/api.py) (`/_github/*`), [gitcmd.py](../../src/atlas/rotinas/repo_sync/gitcmd.py) (`auth_args`), [test_github_auth.py](../../tests/test_github_auth.py) |
| E7-33d | **Fase 4 — Auth/sessão** (login por senha local + login via GitHub; sessão em cookie httpOnly; admin via token/loopback) | **feito** | [users.py](../../src/atlas/users.py), [sessions.py](../../src/atlas/sessions.py), [api.py](../../src/atlas/api.py) (`/_auth/*`, `_identity`), [test_api_auth.py](../../tests/test_api_auth.py) |
| E7-33e | **Fase 5 — Isolamento por `labels.owner`** no store/API + migração | proposto | [ADR-0027](../arquitetura/adr/ADR-0027-multiusuario-credenciais.md) |
| E7-34 | **SSO no front p/ GitHub e Claude**: absorvido pelo ADR-0027 (GitHub device flow; Claude compartilhado por ora — login por-usuário é evolução) | absorvido em E7-33 | [ADR-0027](../arquitetura/adr/ADR-0027-multiusuario-credenciais.md) |
| E7-35 | **ADR-0026 — Kind `LLMProvider`**: config de IA reutilizável (motor/modelo/endpoint/token_env); `Agente.provider` referencia e o provider dita o modelo; resolver com override por agente; seeds claude-default/claude-fast/ollama-local | **feito** | [ADR-0026](../arquitetura/adr/ADR-0026-llm-provider.md), [api_schema.py](../../src/atlas/api_schema.py), [api.py](../../src/atlas/api.py) (`_resolve_engine`) |
| E7-36 | **Análise de repo por Agente** (ADR-0024 regra 2): `Repo.spec.analyze_agente` (default `repo-analyzer`); insight **manual** e **automático no sync** dirigidos pelo Agente; front deixa claro manual×automático no Repo e RepoGroup | **feito** | [api.py](../../src/atlas/api.py) (`_ai_insight`), [analyze.py](../../src/atlas/rotinas/repo_sync/analyze.py), [kinds/repo.js](../../src/atlas/dashboard/kinds/repo.js), [kinds/repogroup.js](../../src/atlas/dashboard/kinds/repogroup.js) |
| E7-37 | **Fix: relação Repo→Job de sync por LABEL (P11)**, não por nome `<repo>-sync`. `_resolve_repo_sync_job` (spec.coletar=repo-sync + spec.label=<repo>); `POST /_run` aceita `{repo}`; Jobs do store (criados pela IA) passam a rodar (`_rotina_from_job`); RAG do builder reforçado com a seção de relações por label | **feito** | [api.py](../../src/atlas/api.py), [kinds/repo.js](../../src/atlas/dashboard/kinds/repo.js), [kinds/repogroup.js](../../src/atlas/dashboard/kinds/repogroup.js) |
| E7-38 | **Render especializado do Kind `Job`** (quadro branco) + **aba 🧩 Jobs no Repo** (lista Jobs vinculados por label, executar/sync); galeria do Hub inclui Job e LLMProvider | **feito** | [kinds/job.js](../../src/atlas/dashboard/kinds/job.js), [kinds/repo.js](../../src/atlas/dashboard/kinds/repo.js), [home.js](../../src/atlas/dashboard/home.js) |
| E7-39 | **Cobertura de testes do trabalho recente**: `_resolve_engine` (precedência provider×agente), `_resolve_repo_sync_job` (match por label), `_rotina_from_job`, `snapshot_tree`/`should_serialize` (+15 testes) | **feito** | [test_provider_engine.py](../../tests/test_provider_engine.py), [test_serialize_snapshot.py](../../tests/test_serialize_snapshot.py) |
| E7-41 | **RepoGroup vira dash manager de projetos**: abas Visão \| 🎯 Objetivos \| 🔍 Análises \| Config. Objetivos = Goals vinculados ao grupo por `labels.group` (P11), com **barras de progresso** ligadas a Trackers + criar objetivo a partir de um Tracker + recalcular; Análises = últimas análises/insights por repo (com gerar) | **feito** | [kinds/repogroup.js](../../src/atlas/dashboard/kinds/repogroup.js), [metas.py](../../src/atlas/metas.py) |
| E7-44 | **Tracking de gasto de IA por Agente**: ao evocar (modo `code`), acumula no `status` do Agente `runs`, `custo_total_usd`, `ultimo_custo_usd`, `ultimo_modelo` (do `total_cost_usd` do claude). Visível no render do Agente (badge 💰). Base p/ orçamento/meta | **feito** | [api.py](../../src/atlas/api.py) (`_registrar_gasto_agente`), [kinds/agente.js](../../src/atlas/dashboard/kinds/agente.js) |
| E7-43 | **Auto-deploy (CD) na Rasp**: timer systemd verifica `main` a cada 5 min → `git pull` + reinstala deps se mudaram + `systemctl --user restart atlas`. Configurável p/ acompanhar tags (`ATLAS_DEPLOY_TRACK=tags`) | **feito** | [scripts/atlas-deploy.sh](../../scripts/atlas-deploy.sh), [scripts/atlas-deploy.timer](../../scripts/atlas-deploy.timer), [RASP.md](../../RASP.md) |
| E7-42 | **Kinds criáveis no ＋Novo a partir do schema** (P11: qualquer Kind não-oculto é criável; +templates RepoGroup/LLMProvider) + **fluxo de produção** no RepoGroup: botão "🔔 Sync diário" cria, por repo do grupo, um Job `repo-sync` com `schedule=@daily`, `saida=telegram`, `active=true` (vínculo por label). 1º uso em prod: avaliar múltiplos repos, gerar insights, metas e notificar via Telegram | **feito** | [main.js](../../src/atlas/dashboard/main.js), [kinds/repogroup.js](../../src/atlas/dashboard/kinds/repogroup.js) |
| E7-40 | **Unificação schema do Job × spec gravado.** Schema/form (`api_schema.py` e `main.js`) passam a usar `schedule`/`model`/`active` (convenção do store, lida por `sync.py`/renders/scheduler), eliminando o divergência com `agenda`/`modelo`/`ativa`. Jobs criados via ＋Novo agora gravam as chaves corretas | **feito** | [api_schema.py](../../src/atlas/api_schema.py), [main.js](../../src/atlas/dashboard/main.js), [test_api_schema.py](../../tests/test_api_schema.py) |

## Épico E3 — Tracking e metas (M3)
| ID | História | Estado | ADR/doc |
|---|---|---|---|
| E3-01 | Rotina físico — collect treino (domínio fisico + trackers fitness) | **feito** — `rotinas/treino.py` + agenda 20h; log via `/reg #fisico` ou tracker | — |
| E3-02 | Rotina estudos — collect de atividades de estudo + trackers | proposto | — |
| E3-03 | Rotina leitura (Librera; depende do formato de sync) | bloqueado | [constituicao](../arquitetura/constituicao.md) (em aberto) |
| E3-04 | Sistema de metas + `goal_links` + checkup semanal | proposto | [modelo-de-dados](../arquitetura/modelo-de-dados.md) |

## Épico E4 — Infra e CI/CD (transversal)
| ID | História | Estado | ADR/doc |
|---|---|---|---|
| E4-00 | Empacotamento Docker (imagem + compose `restart: always` + script) | **feito** | [ADR-0012](../arquitetura/adr/ADR-0012-empacotamento-docker.md) |
| E4-01 | Serviço systemd, sem sleep, lid switch ignorado | proposto | [visao-geral](../arquitetura/visao-geral.md) |
| E4-02 | Gestão de segredos fora do versionamento | proposto | [seguranca](../arquitetura/seguranca.md) |
| E4-03 | Setup GitHub: criar repo, remote, `gh`, rename `master`→`main`, branch protection | proposto | [ADR-0011](../arquitetura/adr/ADR-0011-ci-cd-versionamento.md) |
| E4-04 | Units systemd `atlas-dev` (main) e `atlas-prod` (tag) | proposto | [politica-de-desenvolvimento](../processos/politica-de-desenvolvimento.md) |
| E4-05 | Poller de deploy (timer systemd) + ativar `scripts/deploy.sh` | proposto | [politica-de-desenvolvimento](../processos/politica-de-desenvolvimento.md) |
| E4-06 | Ativar release automation (release-please) + versão inicial | proposto | [ADR-0011](../arquitetura/adr/ADR-0011-ci-cd-versionamento.md) |
| E4-07 | Configurar `pyproject.toml` (ruff, pytest, deps) p/ a CI sair do no-op | **feito** — pyproject.toml + ci.yml ativos; ruff+pytest rodando | [ci.yml](../../.github/workflows/ci.yml) |

## Dívida de documentação
| ID | Item | Estado |
|---|---|---|
| D-01 | ADRs retroativos das decisões travadas (Telegram, assinatura, script-primeiro, pastas plugáveis) | proposto |
| D-02 | Template de `SPEC.md` para o meta-loop | proposto |
| D-03 | Gramática da micro-sintaxe de entrada | proposto |
| D-04 | ADR de modelo de dados para a tabela `ideas`/`trackers`/`alarms` (estende [ADR-0002](../arquitetura/adr/ADR-0002-modelo-de-dados.md)) | proposto |

## Decisões em aberto (viram ADR quando maduras)
- Teto de uso da assinatura Pro para rotinas pesadas / fallback.
- Formato do sync do Librera no setup do dono.
- Política de retenção/limpeza de `runs`.
- Janela de catch-up do resumo diário.
- Framework de teste e estratégia de migração de schema.

## Direção futura (capturada, sem prioridade agora)
> Ideias do PO/PM (lição de casa) **despriorizadas** em favor das capacidades de
> interação do core (E5/E6). Registradas para não se perderem; viram ADR/épico
> quando entrarem na fila.

- **Agnosticismo de provider de IA** — Claude/assinatura como adapter plugável.
- **Open-source** — código livre; diretriz "usa IA, não assinatura".
- **Kernel/API + extensões** — núcleo como API; rotinas como extensões; "loja"; app
  mobile/nativo como outro frontend do mesmo motor.
- **Migração para Rust** — motor leve e nativo; extensões locais, só IA sai.
- **Observabilidade OTel** — instrumentação/export e métricas via bot (sessão de debug).
- **Score do dia** — avaliação determinística (modelo matemático, não inferência).
- **Rotinas-semente concretas** — calendário, aviso do dia, clima na rota, lembrete
  de dormir. (Serão rotinas geradas via meta-loop, não código do core.)
