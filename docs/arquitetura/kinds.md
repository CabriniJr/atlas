---
titulo: Kinds do Atlas — catálogo e padrão de definição
id: ARQ-KINDS
status: aprovado
versao: 1.0
dono: Tech Lead
revisado-por: PO/PM
atualizado-em: 2026-06-16
---

# Kinds do Atlas

> Decisão de origem: [ADR-0015](adr/ADR-0015-core-api-de-objetos.md).
> Todo objeto no Atlas é um `Resource(kind, name, spec, status)`.
> Verbos são uniformes; kinds carregam o domínio.

## Histórico de revisão
| Versão | Data       | Autor     | Mudança       | Aprovado por |
|--------|------------|-----------|---------------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação       | PO/PM        |

---

## Como usar os verbos no chat (kubectl-like)

```
/resources                         # lista todos os kinds presentes no store
/list <Kind>                       # lista todos os objetos do kind
/get <Kind> <name>                 # busca um objeto pelo nome
/describe <Kind> <name>            # detalhe completo (spec + status + labels)
/apply <Kind> <name> [k=v …]       # cria ou atualiza (upsert)
/delete <Kind> <name>              # remove
```

**Exemplos:**
```
/resources
/list Idea
/get Idea idea-3
/describe Tracker weight
/apply Idea minha-ideia body=Fazer UI do Atlas priority=10
/delete Idea idea-obsoleta
```

---

## Padrão de definição de um Kind

Todo kind deve especificar:

| Campo | Descrição |
|-------|-----------|
| **Kind** | PascalCase, singular (ex.: `Idea`, `Tracker`, `Routine`) |
| **name** | slug kebab-case, único dentro do kind |
| **labels** | pares `chave=valor` para filtragem (ex.: `tipo=ideia`, `estado=capturada`) |
| **spec** | intenção do usuário — campos declarativos que o usuário controla |
| **status** | estado observado — preenchido pelo motor, não pelo usuário |

### Campos obrigatórios de spec por kind

#### `Idea` / `Task` / `Routine` (pool — E6)
| Campo spec | Tipo | Descrição |
|------------|------|-----------|
| `body` | string | Corpo completo da ideia/tarefa |
| `title` | string | Primeira linha do body |
| `priority` | int | 0 = urgente, 100 = default |

Status: `state` = `capturada` \| `ativada` \| `arquivada` \| `descartada`

#### `Tracker` (E5-04/05)
| Campo spec | Tipo | Descrição |
|------------|------|-----------|
| `unit` | string | Unidade de medida (ex.: `kg`, `h`) |
| `type` | string | `number` \| `duration` \| `count` \| `text` |
| `syntax` | string | Prefixo de micro-sintaxe (ex.: `weight:`) |
| `aggregation` | string | `sum` \| `mean` \| `last` \| `count` |

Status: `last_value`, `last_ts`, `count_today`

#### `Alarm` (E5-07)
| Campo spec | Tipo | Descrição |
|------------|------|-----------|
| `time` | `HH:MM` | Horário de disparo |
| `mode` | string | `daily` \| `once` |
| `message` | string | Texto a enviar |

Status: `last_fired`, `active`

#### `Routine` (E1-01)
| Campo spec | Tipo | Descrição |
|------------|------|-----------|
| `schedule` | string | Expressão de agenda (cron / @every) |
| `model` | string | `none` \| `haiku` \| `opus` |
| `active` | bool | Ligada/desligada |

Status: `last_run`, `run_count`, `last_status`

---

## Kinds atuais no store

| Kind | Origem | Migrado? |
|------|--------|----------|
| `Idea` | `/idea <texto>` | ✅ aditivo (E0-04) |
| `Task` | `/task <texto>` | ✅ aditivo (E0-04) |
| `Routine` | `/queue <texto>` | ✅ aditivo (E0-04) |
| `Tracker` | `/track new` | ❌ pendente (E0-04) |
| `Alarm` | `/alarm` | ❌ pendente (E0-04) |

Qualquer kind pode ser criado diretamente com `/apply <Kind> <name> [k=v]` —
o store é genérico e não conhece domínios.

---

## Convenções

- `name` nunca contém espaço. Use `-` ou `_`.
- Prefixo automático para ideias: `idea-<id>`, `task-<id>`, `routine-<id>`.
- `status` é somente-leitura para o usuário — o motor escreve via `set_status`.
- Para filtrar por label: `/list Idea` (todos) — filtro por selector virá com E0-03 completo.
