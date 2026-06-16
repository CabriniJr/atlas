---
titulo: ADR-0009 — Handoff entre modos via SPEC.md
id: ADR-0009
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
substitui: —
substituido-por: —
---

# ADR-0009 — Handoff entre modos via `SPEC.md`

## Histórico de revisão
| Versão | Data       | Autor     | Mudança          | Aprovado por |
|--------|------------|-----------|------------------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Aceito (endurecimento C9) | PO/PM |

---

## Status
`aceito`.

## Contexto
O princípio "operação e desenvolvimento nunca se misturam" (P5) entra em tensão
com o meta-loop, que planeja no Telegram (operação) e dispara o desenvolvimento. O
handoff entre as duas sessões não estava desenhado.

## Decisão
A comunicação entre os modos é por **arquivo**, não por estado de runtime:
- O planejamento (Telegram, operação) escreve um **`SPEC.md`** em `routines/<nome>/`.
- O meta-loop (desenvolvimento) **lê esse `SPEC.md`** e gera o resto da pasta.

A fronteira fica limpa: operação produz spec; desenvolvimento consome spec e
produz código. Nenhum estado compartilhado em memória entre as sessões.

## Alternativas consideradas
| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Estado em memória compartilhado | Sem arquivo extra | Acopla os dois modos | Fere P5 |
| Fila/mensageria | Desacoplado | Infra extra no notebook | Fere P7 |

## Consequências
- **Positivas:** P5 preservado; o spec fica versionado e auditável no repo.
- **Negativas:** um artefato a mais por rotina (`SPEC.md`).
- **Impacto na constituição:** decisão #5; anatomia da pasta da rotina.

## Pendências
Template do `SPEC.md` que o planejamento deve produzir.
