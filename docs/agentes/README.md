---
titulo: Catálogo de agentes
id: AGT-INDEX
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Catálogo de agentes especializados

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação | PO/PM        |

---

> Esta aplicação é construída **100% por agentes Claude**. Cada agente tem uma
> ficha que define papel, modelo, entradas, saídas e limites. Todo agente lê
> primeiro [`diretrizes-gerais.md`](diretrizes-gerais.md) e o
> [`CLAUDE.md`](../../CLAUDE.md) da raiz.

## Papéis

| Agente | Modelo | Quando atua | Ficha |
|---|---|---|---|
| **Tech Lead** | Opus | Sempre — orquestra, decide, curadora, valida contra a doc | [tech-lead.md](tech-lead.md) |
| **Dev** | Sonnet (N em paralelo) | Implementa uma tarefa; várias instâncias com visões diferentes | [dev.md](dev.md) |
| **Revisor/Curador** | Opus | Funde o melhor das soluções paralelas; valida DoD | [revisor-curador.md](revisor-curador.md) |

## Especializações (a criar conforme o backlog evolui)

Especializações são variações de **Dev** com contexto extra. Candidatas:
- **Dev-Motor** — core (roteador, executor, agendador, invocador).
- **Dev-Rotina** — rotinas plugáveis (collect/gate/prompt).
- **Dev-Infra** — systemd, energia, empacotamento.
- **Dev-Telegram** — adapter de interface.

Cada especialização nova ganha sua ficha aqui, seguindo o mesmo formato.

## Formato de uma ficha de agente

1. **Papel e objetivo** — uma frase.
2. **Modelo** — Opus/Sonnet/Haiku e por quê.
3. **Entradas** — o que recebe (tarefa, docs, contexto).
4. **Saídas** — o que entrega (código, ADR, análise).
5. **Limites** — o que **não** pode fazer.
6. **Critérios de pronto** — quando a tarefa está completa.

## Como o Tech Lead despacha os Devs

O fluxo background + best-of-two está em
[`../processos/fluxo-de-desenvolvimento.md`](../processos/fluxo-de-desenvolvimento.md).
Regra: **N Devs (geralmente 2) resolvem a MESMA tarefa em paralelo**, em
background; o Tech Lead/Curador funde o melhor das soluções.
