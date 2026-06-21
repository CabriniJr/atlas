---
titulo: ADR-0019 — Interfaces são clientes da API
id: ADR-0019
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-17
substitui: —
substituido-por: —
---

# ADR-0019 — Interfaces são clientes da API

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-17 | Tech Lead | Proposta + aceite | PO/PM |
| 1.1    | 2026-06-21 | Tech Lead | Dashboard embutido **restaurado temporariamente** por decisão do PO (ver Status) | PO/PM |

## Status
`aceito` — porém **parcialmente revertido na prática (transitório)**.

O `api.py` voltou a servir o dashboard embutido em `GET /` (mesma UI que rodava na
Pi), por decisão do PO em 2026-06-21: a versão standalone (SPA em `web/`) ainda não
tem paridade visual/funcional, então o front embutido segue sendo a interface de
uso enquanto a aplicação web separada amadurece. O endpoint `GET /_schema` foi
mantido. A direção de longo prazo do ADR (interfaces são clientes da API; web/
standalone no Vercel) **continua válida** — apenas adiada. Quando o SPA atingir
paridade, o dashboard embutido volta a sair.

## Contexto
O Atlas tem múltiplas formas de interação (CLI, Telegram, web) e planeja outras
(Android). Até aqui o dashboard web era servido pelo próprio `api.py` como uma
string HTML embutida (~3000 linhas), misturando interface e núcleo. O PO definiu:
"a API é o backend; Telegram, web e Android são interfaces — tudo isso tem que
ser tratado como interface".

## Decisão
1. O **núcleo + a API HTTP** são a fronteira única do sistema. Nenhuma interface
   carrega regra de negócio; toda interface consome a API (verbos/endpoints).
2. O `api.py` **não serve UI**. `GET /` devolve uma landing mínima; a web é um
   cliente externo (SPA em `web/`).
3. Metadata de UI por kind (schema de campos + ações) é **servida pela API**
   (`GET /_schema`), fonte única para qualquer interface.

## Alternativas consideradas
| Alternativa | Por que não |
|---|---|
| Manter UI embutida no `api.py` | mistura interface e núcleo; arquivo gigante; não escala p/ Android |
| Schema por kind duplicado em cada interface | divergência; viola fonte única |

## Consequências
- **Positivas:** fronteira clara; `api.py` enxuto; novas interfaces (Android)
  reusam o mesmo contrato e `/_schema`. Reforça ADR-0015 e ADR-0017.
- **Custos:** a web passa a precisar de deploy próprio (sub-projeto 2, F2–F5).
- **Impacto na constituição:** nenhuma decisão anterior muda; formaliza um
  princípio já implícito.
