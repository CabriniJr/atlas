---
titulo: ADR-0010 — Observabilidade via claude -p JSON
id: ADR-0010
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
substitui: —
substituido-por: —
---

# ADR-0010 — Observabilidade via `claude -p` JSON

## Histórico de revisão
| Versão | Data       | Autor     | Mudança          | Aprovado por |
|--------|------------|-----------|------------------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Aceito (endurecimento C10) | PO/PM |

---

## Status
`aceito` (com pendência de verificação empírica).

## Contexto
A observabilidade e o orçamento (ADR-0005) dependem de o `claude -p` expor uso de
token de forma parseável. Sem isso, não há `/uso` nem disjuntor.

## Decisão
Usar `claude -p --output-format json`, que retorna um objeto de resultado com
`usage` (input/output/cache tokens), `total_cost_usd`, `duration_ms`, `num_turns`,
`session_id`, `is_error`. Gravar esses campos em `runs`
([modelo-de-dados](../modelo-de-dados.md)).

**Ressalva:** na autenticação por assinatura (não API key), `total_cost_usd` é
**nocional**. Tratar **tokens** como a métrica de verdade e o custo como
estimativa.

## Alternativas consideradas
| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Parsear saída em texto | Sem flag extra | Frágil, muda entre versões | Não-robusto |
| Estimar tokens localmente | Independe da CLI | Impreciso | Pior que a fonte real |

## Consequências
- **Positivas:** observabilidade real (§ orçamento, `/uso`).
- **Negativas:** custo em dólar não confiável na assinatura.
- **Impacto na constituição:** campos de `runs`; semântica de custo.

## Pendências
**Verificar empiricamente** na máquina alvo: `claude -p "ping" --output-format
json` e confirmar o shape do objeto e dos campos de `usage`.
