---
titulo: ADR-0004 — Contrato tipado do collect
id: ADR-0004
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
substitui: —
substituido-por: —
---

# ADR-0004 — Contrato tipado do `collect`

## Histórico de revisão
| Versão | Data       | Autor     | Mudança          | Aprovado por |
|--------|------------|-----------|------------------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Aceito (endurecimento B4) | PO/PM |

---

## Status
`aceito`.

## Contexto
O retorno do `collect` era "um dicionário livre". Sem schema, a persistência (o
campo `store`) não tinha como saber o que gravar e onde. E substituir texto externo
(diff, JSON) direto no template de prompt é superfície de prompt injection.

## Decisão
O `collect` devolve um resultado **tipado**:

```
CollectResult = { data: dict, store: list[StoreOp] }
StoreOp       = { entity: str, fields: dict }
```

`data` alimenta a renderização do prompt; `store` é o mapeamento **explícito** de
persistência. Texto externo entra no prompt em **blocos delimitados como dados**,
neutralizado também por a análise rodar single-turn sem tools (2a).

## Alternativas consideradas
| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Dicionário livre | Flexível | Persistência por adivinhação; frágil | Indefinível e arriscado |
| ORM/objetos por entidade | Type-safe forte | Acopla collect ao schema; verboso | Fere P3/P7 |

## Consequências
- **Positivas:** persistência determinística; injeção mitigada; collect testável.
- **Negativas:** rotinas precisam declarar `store` explicitamente.
- **Impacto na constituição:** decisão #9; contrato no ciclo de vida.

## Pendências
Definir validação de `fields` contra as entidades de [ADR-0002](ADR-0002-modelo-de-dados.md).
