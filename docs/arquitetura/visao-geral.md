---
titulo: Arquitetura geral
id: ARQ-GERAL
status: aprovado
versao: 2.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Arquitetura geral

## Histórico de revisão
| Versão | Data       | Autor     | Mudança                                            | Aprovado por |
|--------|------------|-----------|----------------------------------------------------|--------------|
| 1.0    | 2026-06-16 | —         | Constituição monolítica (`atlas-arquitetura.md`)   | PO/PM        |
| 2.0    | 2026-06-16 | Tech Lead | Decomposição modular + endurecimento (10 ADRs)     | PO/PM        |

---

> Esta é a visão de alto nível. Os detalhes vivem nos documentos modulares
> referenciados, e cada decisão não-óbvia tem um [ADR](adr/README.md).

## Propósito

Um motor de **rotinas pessoais plugáveis** que roda no notebook (Linux, systemd,
sempre ligado), usa o Claude como motor de inteligência e fala pelo Telegram. Ver
[visão de produto](../visao/visao-produto.md).

## Diagrama

```
                          ┌──────────────────────────┐
        Celular  ◄──push──┤      Telegram (bot)       │
        (você)   ──cmd───►└────────────┬─────────────┘
                                       │ (long-poll, sem domínio/NAT)
                          ┌────────────▼─────────────┐
                          │     INTERFACE ADAPTER     │
                          └────────────┬─────────────┘
                                       │
        ┌──────────────────────────────▼──────────────────────────────┐
        │                          MOTOR (core)                         │
        │  ┌──────────┐   ┌──────────────┐   ┌────────────────────┐    │
        │  │ ROTEADOR │──►│ EXECUTOR DE   │──►│ AGENDADOR          │    │
        │  │(dispatch)│   │ ROTINAS       │   │ (cron / intervalos)│    │
        │  └──────────┘   └──────┬───────┘   └────────────────────┘    │
        │        ┌───────────────┼────────────────┐                    │
        │        ▼               ▼                ▼                     │
        │   ciclo de vida    BANCO (SQLite)   INVOCADOR de IA           │
        │   das rotinas      §modelo-de-dados  análise(2a)/agente(2b)   │
        └────────┬──────────────────────────────────┬──────────────────┘
                 │                                   │
        ┌────────▼─────────┐               ┌─────────▼──────────┐
        │  routines/        │               │  Sua assinatura    │
        │ (pastas plugáveis)│               │  Claude (Pro/Max)  │
        └───────────────────┘               └────────────────────┘
```

## Componentes

| Componente | Responsabilidade | Detalhe |
|---|---|---|
| **Interface Adapter** | Abstrai o canal (`enviar`/`receber`). Telegram via long-poll. | [seguranca](seguranca.md), P6 |
| **Roteador** | Decide qual rotina/ação atende a mensagem. Determinístico antes de IA. | [ADR-0008](adr/ADR-0008-roteamento-e-extracao.md) |
| **Executor de Rotinas** | Roda o ciclo de vida de uma rotina. | [ciclo-de-vida-rotina](ciclo-de-vida-rotina.md) |
| **Agendador** | Dispara rotinas por horário/intervalo; faz catch-up de runs perdidos. | [ADR-0006](adr/ADR-0006-erro-e-resiliencia.md) |
| **Banco (SQLite)** | Estado dinâmico: atividades, metas, livros, runs, estado de rotina. | [modelo-de-dados](modelo-de-dados.md) |
| **Invocador de IA** | Sobe `claude -p` em modo análise (2a) ou agente (2b). | [motor-de-ia](motor-de-ia.md) |
| **routines/** | As rotinas, cada uma uma pasta plugável. Estado expansível. | [ciclo-de-vida-rotina](ciclo-de-vida-rotina.md) |

## Os dois loops

- **Loop 1 — Operação:** mensagem curta → roteador → executor → resposta. A
  maioria é zero IA; a exceção é o resumo diário (sempre IA).
- **Loop 2 — Meta-loop:** você descreve uma rotina por conversa; o sistema gera o
  código via Claude Code agêntico. O diferencial: o sistema se expande a si mesmo.
  Ver [seguranca](seguranca.md) e [ADR-0003](adr/ADR-0003-seguranca-meta-loop.md).

## Camadas de execução (a economia)

| Camada | Custo | Quando |
|---|---|---|
| **0 — código puro** | 0 IA | Registrar, consultar, formatar, comparar |
| **1 — IA leve (Haiku)** | baixo | Intenção ambígua, palavra-chave não basta |
| **2a — análise single-turn** | médio | Análise de um prompt → uma resposta |
| **2b — agente (Claude Code)** | alto | Só o meta-loop (agir na máquina) |

Meta: ~80% das interações resolvem na Camada 0. Ver [ADR-0001](adr/ADR-0001-ia-em-dois-modos.md).

## Infraestrutura

Notebook Linux como serviço systemd, sem sleep, lid switch ignorado. Telegram via
long-poll dispensa domínio/IP/webhook. Evolução futura (mini-PC/VPS) não muda o
desenho. Detalhe operacional em [`../roadmap/planejamento.md`](../roadmap/planejamento.md).

## Onde aprofundar

- O que **não muda** sem ADR: [constituicao](constituicao.md)
- Decisões e seus porquês: [adr/README](adr/README.md)
