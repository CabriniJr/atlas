---
titulo: ADR-0002 — Modelo de dados SQLite
id: ADR-0002
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
substitui: —
substituido-por: —
---

# ADR-0002 — Modelo de dados SQLite

## Histórico de revisão
| Versão | Data       | Autor     | Mudança          | Aprovado por |
|--------|------------|-----------|------------------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Aceito (endurecimento A2) | PO/PM |

---

## Status
`aceito`.

## Contexto
O SQLite era citado em várias seções (collect lê o banco, runs, metas) mas o
**schema nunca foi definido**. As entidades são a fundação real do sistema e
precisam estar fixadas antes de qualquer implementação.

## Decisão
Adotar um schema mínimo (YAGNI): `activities`, `goals`, `goal_links`, `books`,
`runs`, `routine_state`. O específico de cada domínio vive em
`activities.dados_json` — **domínio nunca vira coluna** (mantém o motor agnóstico,
P3). O orçamento é **derivado de `runs`**, não tabela à parte. Detalhe completo em
[`../modelo-de-dados.md`](../modelo-de-dados.md).

## Alternativas consideradas
| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Tabela por domínio (workout, study…) | Consultas diretas | Acopla o core a domínios | Fere P3 (agnóstico) |
| Documento JSON único (sem SQL) | Simples no início | Consultas e metas ficam caras | Metas exigem relacionamento |
| Schema rico desde já | Antecipa necessidades | Especulação/over-engineering | Fere P7 (YAGNI) |

## Consequências
- **Positivas:** fundação concreta; `collect` e metas têm onde se apoiar; motor
  permanece agnóstico.
- **Negativas:** `dados_json` não é validado pelo banco — validação fica na rotina.
- **Impacto na constituição:** nova seção de arquitetura; decisão #9 depende deste.

## Pendências
Política de retenção de `runs`; estratégia de migração/versionamento do schema (M1).
