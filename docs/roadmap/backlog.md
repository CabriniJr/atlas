---
titulo: Backlog
id: ROAD-BACKLOG
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Backlog

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação | PO/PM        |
| 1.1    | 2026-06-16 | Tech Lead | Lição de casa (itens 0–5): ADR-0013 + specs; épico E5 (interface/trackers via chat); detalhe de E1/E2 | — |
| 1.2    | 2026-06-16 | Tech Lead | Pool de ideias (ADR-0014, prioridade máxima) = épico E6; alarmes (E5-07) | PO/PM |

---

> Épicos → histórias, priorizados. O PO/PM define prioridade; o Tech Lead
> decompõe em specs de tarefa. Estados: `proposto` · `pronto` (DoR ok) ·
> `em-andamento` · `feito` · `bloqueado`.

## Épico E1 — Motor mínimo (M1)
| ID | História | Estado | ADR/doc |
|---|---|---|---|
| E1-01 | Auto-descoberta e carga de rotinas a partir de `routines/` | **feito** | [ciclo-de-vida](../arquitetura/ciclo-de-vida-rotina.md) |
| E1-02 | Schema SQLite + camada de acesso | **feito** | [ADR-0002](../arquitetura/adr/ADR-0002-modelo-de-dados.md) |
| E1-03 | Adapter Telegram (long-poll, `enviar`/`receber`, filtro de ID) | **feito (MVP)** | [seguranca](../arquitetura/seguranca.md) |
| E1-04 | Roteador determinístico + micro-sintaxe + fallback Haiku | **parcial (MVP)** — handler de comandos + registro; falta conflito de triggers e fallback Haiku | [ADR-0008](../arquitetura/adr/ADR-0008-roteamento-e-extracao.md) |
| E1-05 | Invocador de IA: modo análise (2a) e agente (2b). No Pi: verificar `claude -p` (cliente) em **arm64** + login ativo + rede — modelos rodam na nuvem, não no Pi | proposto | [ADR-0001](../arquitetura/adr/ADR-0001-ia-em-dois-modos.md), [ADR-0012](../arquitetura/adr/ADR-0012-empacotamento-docker.md) |
| E1-06 | Agendador + catch-up de runs perdidos | **feito** — core + **wiring no loop do `app`** (catch-up no boot + `tick` por janela de poll, disparo via executor notificando o dono) | [ADR-0006](../arquitetura/adr/ADR-0006-erro-e-resiliencia.md), [spec scheduler](../specs/scheduler.md) |
| E1-07 | Harness de teste de rotina | proposto | [ADR-0007](../arquitetura/adr/ADR-0007-contrato-de-teste.md) |
| E1-10 | Executor do ciclo de vida (`trigger→collect→gate→analyze→deliver`) + notificação no Telegram + gravação em `runs` | **feito** (core; fases injetadas) — wiring de `/rodar` fica em E5-02 (precisa do carregador + invocador E1-05) | [ciclo-de-vida](../arquitetura/ciclo-de-vida-rotina.md), [spec executor](../specs/executor-e-notificacao.md) |
| E1-11 | Barreira de entrada: registrar só com intenção explícita (reescreve `handler.py`) | proposto | [ADR-0013](../arquitetura/adr/ADR-0013-barreira-de-entrada.md), [spec barreira](../specs/barreira-entrada.md) |
| E1-08 | Observabilidade: gravar `usage` em `runs` + `/uso` | proposto | [ADR-0010](../arquitetura/adr/ADR-0010-observabilidade-claude-p.md) |
| E1-09 | Orçamento: teto global pré-despacho + disjuntor por rotina | proposto | [ADR-0005](../arquitetura/adr/ADR-0005-orcamento-reativo.md) |

## Épico E2 — Rotinas-âncora (M2)
| ID | História | Estado | ADR/doc |
|---|---|---|---|
| E2-01 | Rotina **resumo diário** (collect tudo do dia + análise 2a) | proposto | [personas](../visao/personas-e-uso.md) |
| E2-02 | **Meta-loop** fase 1 (planejamento no Telegram → `SPEC.md`) | proposto | [ADR-0009](../arquitetura/adr/ADR-0009-handoff-entre-modos.md) |
| E2-03 | **Meta-loop** fase 2 (geração via agente 2b, inativo por padrão) | proposto | [ADR-0003](../arquitetura/adr/ADR-0003-seguranca-meta-loop.md) |
| E2-04 | `/ativar` + fluxo de revisão e commit da rotina gerada | proposto | [ADR-0003](../arquitetura/adr/ADR-0003-seguranca-meta-loop.md), [spec meta-loop](../specs/meta-loop-chat.md) |

## Épico E5 — Interface de configuração e trackers via chat (prioridade atual)
> A "interface de configuração total via chat" (lição de casa, itens 4–5). O bot é
> o frontend do motor; tudo 0 IA, exceto a geração de rotina (E2).

| ID | História | Estado | ADR/doc |
|---|---|---|---|
| E5-01 | Comandos de listagem/inspeção: `/rotinas`, `/rotina <nome>`, `/uso`, `/status` (evoluir), `/ajuda` dinâmico | **parcial** — registro único de comandos (inglês), `/help` dinâmico + `setMyCommands`, `/status` evoluído, **sessão `/debug`** (status/runs/routines/db/env); falta `/rotinas`/`/uso` | [spec interface](../specs/interface-config-chat.md) |
| E5-02 | Ciclo de vida por chat: `/ativar`, `/desativar`, `/rodar <nome>` | proposto | [spec interface](../specs/interface-config-chat.md), [spec executor](../specs/executor-e-notificacao.md) |
| E5-03 | Edição de config interativa (`/rotina <nome> set <campo> <valor>`) com validação | proposto | [spec interface](../specs/interface-config-chat.md) |
| E5-04 | Tabela `trackers` + rotina genérica `tracking` (aplica em runtime) | proposto | [spec trackers](../specs/trackers-via-chat.md), [ADR-0002](../arquitetura/adr/ADR-0002-modelo-de-dados.md) |
| E5-05 | Wizard `/tracker novo` + `/trackers` + `/tracker <nome>` (ver/editar/remover) | proposto | [spec trackers](../specs/trackers-via-chat.md) |
| E5-06 | `/reg` (nota livre, com domínio opcional) | proposto | [ADR-0013](../arquitetura/adr/ADR-0013-barreira-de-entrada.md), [spec barreira](../specs/barreira-entrada.md) |
| E5-07 | Alarmes/lembretes: tabela `alarms` + rotina `alarme` + comandos `/alarme`/`/alarmes` | proposto | [spec alarmes](../specs/alarmes.md), [spec scheduler](../specs/scheduler.md) |

## Épico E6 — Pool de ideias e autoimplementação (PRIORIDADE MÁXIMA)
> Capturar ideias/tarefas/lições pelo Telegram e alimentar a geração automática de
> rotinas (ativação sempre humana). Decisão: [ADR-0014](../arquitetura/adr/ADR-0014-pool-de-ideias-desenvolvimento.md).

| ID | História | Estado | ADR/doc |
|---|---|---|---|
| E6-01 | Tabela `ideas` + migração idempotente de schema | **feito** | [ADR-0014](../arquitetura/adr/ADR-0014-pool-de-ideias-desenvolvimento.md), [spec pool](../specs/pool-de-ideias.md) |
| E6-02 | Captura via Telegram (`/ideia`, `/tarefa`/`/licao`, `/rotina_nova`) | **feito** | [spec pool](../specs/pool-de-ideias.md) |
| E6-03 | CRUD/priorização (`/ideias`, `/ideia <id>`, `prio`, `editar`, `feito`, `arquivar`, `remover`) | **feito** | [spec pool](../specs/pool-de-ideias.md) |
| E6-04 | Laço de desenvolvimento: agente livre + item `rotina` → dispara meta-loop (gera inativo) + notifica | bloqueado (depende de E1-10 + E2) | [ADR-0014](../arquitetura/adr/ADR-0014-pool-de-ideias-desenvolvimento.md), [spec meta-loop](../specs/meta-loop-chat.md) |

## Épico E3 — Tracking e metas (M3)
| ID | História | Estado | ADR/doc |
|---|---|---|---|
| E3-01 | Rotina físico (micro-sintaxe de treino) | proposto | — |
| E3-02 | Rotina estudos | proposto | — |
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
| E4-07 | Configurar `pyproject.toml` (ruff, pytest, deps) p/ a CI sair do no-op | proposto | [ci.yml](../../.github/workflows/ci.yml) |

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
