---
titulo: ADR-0005 — Orçamento de token reativo
id: ADR-0005
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
substitui: —
substituido-por: —
---

# ADR-0005 — Orçamento de token reativo

## Histórico de revisão
| Versão | Data       | Autor     | Mudança          | Aprovado por |
|--------|------------|-----------|------------------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Aceito (endurecimento B5) | PO/PM |

---

## Status
`aceito`.

## Contexto
`budget_tokens` era tratado como teto pré-voo, mas o custo de uma chamada só é
conhecido **depois** que ela termina. Um cap pré-voo por execução é, na prática,
inaplicável.

## Decisão
- **Pré-voo:** limitar o *output* (`--max-turns 1` + teto de saída). O tamanho do
  *input* é responsabilidade da disciplina do `collect`.
- **Teto global (diário/mensal):** checado **no agendador antes de despachar** —
  se o consumo acumulado em `runs` já estourou, não despacha.
- **`budget_tokens` por rotina:** vira **disjuntor para runs futuros** (estouro
  bloqueia/avisa a próxima execução), não cap da execução atual.

## Alternativas consideradas
| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Hard cap pré-voo por execução | Intuitivo | Impossível: custo só é conhecido depois | Tecnicamente inviável |
| Sem orçamento | Simples | Sem proteção contra estouro da assinatura | Fere P1 |

## Consequências
- **Positivas:** proteção real e honesta do limite da assinatura.
- **Negativas:** o controle é reativo — uma execução pode estourar antes do
  disjuntor agir na próxima.
- **Impacto na constituição:** decisão #10; semântica de `budget_tokens`.

## Pendências
Valores default de teto global; comportamento ao estourar (enfileirar vs. avisar).
