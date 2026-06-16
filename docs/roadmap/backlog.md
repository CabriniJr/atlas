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
| E1-05 | Invocador de IA: modo análise (2a) e agente (2b) | proposto | [ADR-0001](../arquitetura/adr/ADR-0001-ia-em-dois-modos.md) |
| E1-06 | Agendador + catch-up de runs perdidos | proposto | [ADR-0006](../arquitetura/adr/ADR-0006-erro-e-resiliencia.md) |
| E1-07 | Harness de teste de rotina | proposto | [ADR-0007](../arquitetura/adr/ADR-0007-contrato-de-teste.md) |
| E1-08 | Observabilidade: gravar `usage` em `runs` + `/uso` | proposto | [ADR-0010](../arquitetura/adr/ADR-0010-observabilidade-claude-p.md) |
| E1-09 | Orçamento: teto global pré-despacho + disjuntor por rotina | proposto | [ADR-0005](../arquitetura/adr/ADR-0005-orcamento-reativo.md) |

## Épico E2 — Rotinas-âncora (M2)
| ID | História | Estado | ADR/doc |
|---|---|---|---|
| E2-01 | Rotina **resumo diário** (collect tudo do dia + análise 2a) | proposto | [personas](../visao/personas-e-uso.md) |
| E2-02 | **Meta-loop** fase 1 (planejamento no Telegram → `SPEC.md`) | proposto | [ADR-0009](../arquitetura/adr/ADR-0009-handoff-entre-modos.md) |
| E2-03 | **Meta-loop** fase 2 (geração via agente 2b, inativo por padrão) | proposto | [ADR-0003](../arquitetura/adr/ADR-0003-seguranca-meta-loop.md) |
| E2-04 | `/ativar` + fluxo de revisão e commit da rotina gerada | proposto | [ADR-0003](../arquitetura/adr/ADR-0003-seguranca-meta-loop.md) |

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

## Decisões em aberto (viram ADR quando maduras)
- Teto de uso da assinatura Pro para rotinas pesadas / fallback.
- Formato do sync do Librera no setup do dono.
- Política de retenção/limpeza de `runs`.
- Janela de catch-up do resumo diário.
- Framework de teste e estratégia de migração de schema.
