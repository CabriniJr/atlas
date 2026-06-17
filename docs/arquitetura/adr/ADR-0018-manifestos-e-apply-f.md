---
titulo: ADR-0018 — Manifestos declarativos e `apply -f` (interface como cliente da API)
id: ADR-0018
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-17
substitui: —
substituido-por: —
---

# ADR-0018 — Manifestos declarativos e `apply -f`

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-17 | Tech Lead | Proposta + aceite | PO/PM |

## Status
`aceito`.

## Contexto
Objetos de domínio (Tracker, Goal, Timer agrupados por `labels.grupo`) precisavam
ser criados repetidamente para tornar a plataforma usável. Criar um a um por
comando é frágil e não versionável. O PO definiu também que **toda interface é
cliente da API** (Telegram, web, futuro Android) — o núcleo não conhece interface.

## Decisão
1. Manifestos declarativos em **YAML multi-doc**, shape flat
   `{kind, name, labels, spec, status}` (o mesmo do editor de manifesto da web).
2. Um loader `atlas apply -f <arquivo>` que **atua como cliente HTTP da API**:
   parseia o YAML e faz `PUT /apis/atlas/v1/<kind>/<name>` por objeto. **Não**
   escreve no store direto — preserva a fronteira interface↔núcleo (ADR-0015/0017).
3. Adoção da **primeira dependência** do projeto, **PyYAML**, restrita ao parse de
   manifestos. Justificada por legibilidade e paridade com o padrão K8s; HTTP/JSON
   seguem em stdlib.

## Alternativas consideradas
| Alternativa | Por que não |
|---|---|
| Loader escreve no store direto | fura a fronteira interface↔núcleo |
| Manifesto JSON (zero dep) | menos legível à mão; PO preferiu YAML |
| Manifesto TOML (zero dep) | formato diverge do editor web (shape K8s) |
| Sem loader (só `/apply` manual) | não versionável; frágil |

## Consequências
- **Positivas:** objetos versionados no repo (P4); reaplicação idempotente; o
  mesmo manifesto serve qualquer ambiente; reforça "interfaces são clientes da API".
- **Custos:** primeira dependência a manter (PyYAML); o loader exige a API no ar
  e token para aplicar.
- **Impacto na constituição:** nenhuma decisão anterior muda; reforça P2/P3/P4.

## Pendências
- ADR amplo "todas as interfaces são clientes da API" (web/Android) — sub-projeto 2.
