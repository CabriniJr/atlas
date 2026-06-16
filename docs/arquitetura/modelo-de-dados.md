---
titulo: Modelo de dados (SQLite)
id: ARQ-DADOS
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Modelo de dados (SQLite)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação (vindo de [ADR-0002](adr/ADR-0002-modelo-de-dados.md)) | PO/PM |

---

> O SQLite é o **estado dinâmico** do sistema (os dados); o repositório é o estado
> *estrutural* (o que o sistema é capaz de fazer). Decisão: [ADR-0002](adr/ADR-0002-modelo-de-dados.md).

## Princípio do schema

Mínimo (YAGNI). O específico de cada domínio vive em `activities.dados_json` —
**domínio nunca vira coluna**, para manter o motor agnóstico (P3).

## Tabelas

### `activities` — log genérico de tudo que acontece
| Campo | Tipo | Nota |
|---|---|---|
| `id` | int PK | |
| `ts` | datetime | quando aconteceu |
| `dominio` | text | ex.: `fisico`, `estudo`, `leitura` |
| `rotina` | text | rotina que gerou o registro |
| `texto_cru` | text | a mensagem original (auditoria) |
| `dados_json` | json | parâmetros estruturados específicos do domínio |

### `goals` — as metas (camada transversal)
| Campo | Tipo | Nota |
|---|---|---|
| `id` | int PK | |
| `titulo` | text | |
| `categoria` | text | |
| `horizonte` | text | `curto` \| `longo` |
| `alvo` | real | valor mensurável |
| `unidade` | text | ex.: `dias/semana`, `horas`, `páginas` |
| `progresso` | real | valor atual |
| `prazo` | date | |
| `status` | text | `ativa` \| `pausada` \| `concluida` \| `falhou` |

### `goal_links` — liga atividade → meta (sem acoplar)
| Campo | Tipo | Nota |
|---|---|---|
| `id` | int PK | |
| `activity_id` | int FK → activities | |
| `goal_id` | int FK → goals | |
| `contribuicao` | real | quanto a atividade somou à meta |

### `books` — estado da leitura (Librera)
| Campo | Tipo | Nota |
|---|---|---|
| `id` | int PK | |
| `titulo` | text | |
| `pagina_atual` | int | |
| `total_paginas` | int | |
| `percentual` | real | derivado |
| `ultimo_visto_ts` | datetime | base do gate "houve progresso?" |

### `runs` — observabilidade (base do orçamento)
| Campo | Tipo | Nota |
|---|---|---|
| `id` | int PK | |
| `rotina` | text | |
| `iniciado_em` / `terminado_em` | datetime | |
| `status` | text | `ok` \| `failed` \| `skipped` |
| `camada` | text | `0` \| `1` \| `2a` \| `2b` |
| `gate_passou` | bool | |
| `tokens_in` / `tokens_out` | int | do `claude -p --output-format json` |
| `custo_usd` | real | **nocional** na assinatura ([ADR-0010](adr/ADR-0010-observabilidade-claude-p.md)) |
| `ref_saida` | text | ponteiro para o resultado entregue |

### `routine_state` — "último run" e checkpoints
| Campo | Tipo | Nota |
|---|---|---|
| `rotina` | text | |
| `chave` | text | |
| `valor` | json | |
| `atualizado_em` | datetime | |

Fornece os dados do "último run" que o contrato do `collect` exige
([ciclo-de-vida-rotina](ciclo-de-vida-rotina.md)) e guarda checkpoints (ex.: último
estado do Librera).

## Derivações (não são tabelas)

- **Orçamento** (diário/mensal/por rotina) é **derivado de `runs`**, não uma
  tabela à parte. Ver [ADR-0005](adr/ADR-0005-orcamento-reativo.md).
- **Checkup semanal de metas** é uma agregação sobre `activities` + `goal_links`.

## Pendências

- Política de retenção de `runs` (valor de corte) — backlog.
- Migrações: estratégia de versionamento do schema — a definir no M1.
