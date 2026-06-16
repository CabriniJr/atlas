---
titulo: ADR-0007 — Contrato de teste da rotina
id: ADR-0007
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
substitui: —
substituido-por: —
---

# ADR-0007 — Contrato de teste da rotina

## Histórico de revisão
| Versão | Data       | Autor     | Mudança          | Aprovado por |
|--------|------------|-----------|------------------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Aceito (endurecimento B7) | PO/PM |

---

## Status
`aceito`.

## Contexto
A documentação não dizia como testar uma rotina antes de ativá-la. Sem isso, o
fluxo best-of-two não tem critério objetivo de qualidade.

## Decisão
Testabilidade por fase, derivada da pureza do ciclo de vida:
- **`collect`** é puro dado um contexto injetado (relógio, handle do DB,
  `routine_state` do último run) → testável com fixtures, sem rede real.
- **`gate`** é predicado puro → trivialmente testável.
- **`analyze`** → mocka o invocador de IA; testa a **renderização do prompt**, não
  o modelo.
- O motor expõe um **harness de teste de rotina** que injeta o contexto e roda as
  fases isoladas. Rotinas podem trazer fixtures opcionais.

## Alternativas consideradas
| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Testes end-to-end com IA real | Realista | Caro, não-determinístico | Fere P1; instável |
| Sem testes | Rápido | Sem critério de DoD | Inaceitável p/ fábrica de agentes |

## Consequências
- **Positivas:** DoD objetivo; base para curadoria best-of-two; collect/gate
  determinísticos.
- **Negativas:** exige injeção de contexto no design do motor.
- **Impacto na constituição:** entra na [Definição de Pronto](../../processos/definicao-de-pronto.md).

## Pendências
Escolha do framework de teste (M1) e formato das fixtures de rotina.
