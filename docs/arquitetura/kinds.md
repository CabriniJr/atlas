---
titulo: Kinds do Atlas — catálogo e padrão de definição
id: ARQ-KINDS
status: aprovado
versao: 1.3
dono: Tech Lead
revisado-por: PO/PM
atualizado-em: 2026-06-17
---

# Kinds do Atlas

> Decisão de origem: [ADR-0015](adr/ADR-0015-core-api-de-objetos.md).
> Todo objeto no Atlas é um `Resource(kind, name, spec, status)`.
> Verbos são uniformes; kinds carregam o domínio.

## Histórico de revisão
| Versão | Data       | Autor     | Mudança       | Aprovado por |
|--------|------------|-----------|---------------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação       | PO/PM        |
| 1.1    | 2026-06-17 | Tech Lead | Kinds `Repo`, `Diff`, `Prompt`; arquivo de diffs em `Doc`; hierarquia por labels | PO/PM |
| 1.2    | 2026-06-17 | Tech Lead | Manifestos declarativos (`apply -f`) e grupos seed | PO/PM |
| 1.3 | 2026-06-21 | Tech Lead | Repo: contexto de projeto (Doc tipo=contexto) e campos de modelo/budget | PO/PM |

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
| `schedule` | string | Agenda: cron de 5 campos / `@every <n>` / `@daily HH:MM` — ver [scheduler](../specs/scheduler.md) |
| `model` | string | `none` \| `haiku` \| `opus` |
| `active` | bool | Ligada/desligada |

Status: `last_run`, `run_count`, `last_status`

#### `Repo` (collect `repo-sync`)
Repositório git monitorado. Credencial de repos privados via `secrets/git-credentials`.
| Campo spec | Tipo | Descrição |
|------------|------|-----------|
| `url` | string | URL (`https://github.com/user/repo`) |
| `model` | string | modelo do insight por diff (default `claude-sonnet-4-6`) |
| `context_model` | string | modelo do resumo de contexto (default `claude-opus-4-8`) |
| `context_ttl_days` | int | frescor do contexto em dias (default 7) |
| `context_corpus_max` | int | teto de chars do corpus do contexto (default 600000) |
| `diff_prompt_max` | int | teto de chars do diff enviado ao insight (default 120000) |
| `diff_store_max` | int | teto de chars do diff guardado no `Diff` (default 200000) |

Status: `last_commit`, `last_commit_msg`, `last_author`, `last_commit_date`,
`last_sync`, `last_check`, `files_changed`, `insertions`, `deletions`, `last_summary`.

#### `Diff` (auto — `repo-sync`)
Snapshot estruturado de uma atualização. `spec`: `commit`, `subject`, `author`,
`date`, `files_changed`, `insertions`, `deletions`, `files_list`, `diff_raw`,
`explicacao` (análise + sugestões da IA).

> Cada atualização também é **arquivada como `Doc`** (`Doc/repo-<label>-<sha7>`,
> `labels: topic=repo, repo=<label>, tipo=diff`) — histórico represado, navegável
> na hierarquia de Docs (agrupada por labels).

> **`Doc` especializado `tipo=contexto`:** `Doc/repo-<label>-contexto`
> (`labels: topic=repo, repo=<label>, tipo=contexto`) guarda o **resumo de
> contexto do projeto** (gerado por Opus na criação/TTL). É injetado integral no
> insight de cada diff. Ver [spec](../specs/2026-06-21-repo-contexto-projeto-design.md).

#### `Prompt` (IA plugável — [ADR-0016](adr/ADR-0016-ia-plugavel-kind-prompt.md))
Chamada de IA reutilizável que qualquer rotina invoca via `coletar = "prompt"`.
| Campo spec | Tipo | Descrição |
|------------|------|-----------|
| `template` | string | prompt; placeholders `{dados}` e `{agora}` |
| `model` | string | modelo (default `claude-haiku-4-5-20251001`) |
| `timeout` | int | segundos (default 90) |
| `fonte` | string | `{dados}`: `grupo:<g>` · `kind:<K>` · `repo:<r>` · `texto:<t>` |

Status: `last_run`, `last_ok`, `last_output`.

---

## Kinds atuais no store

| Kind | Origem | Migrado? |
|------|--------|----------|
| `Idea` | `/idea <texto>` | ✅ aditivo (E0-04) |
| `Task` | `/task <texto>` | ✅ aditivo (E0-04) |
| `Routine` | `/queue <texto>` | ✅ aditivo (E0-04) |
| `Tracker` | `/track new` | ❌ pendente (E0-04) |
| `Alarm` | `/alarm` | ❌ pendente (E0-04) |
| `Repo` | `/apply Repo <n> spec.url=…` | ✅ collect `repo-sync` |
| `Diff` | auto (`repo-sync`) | ✅ |
| `Prompt` | `/apply Prompt <n> spec.template=…` | ✅ collect `prompt` (ADR-0016) |
| `Doc` | sync de docs + arquivo de diffs | ✅ hierarquia por labels |

Qualquer kind pode ser criado diretamente com `/apply <Kind> <name> [k=v]` —
o store é genérico e não conhece domínios.

## Manifestos declarativos

Objetos podem ser definidos em arquivos YAML e aplicados em lote com
`python -m atlas apply -f <arquivo>` — ver [spec de manifestos](../specs/manifestos.md)
e [ADR-0018](adr/ADR-0018-manifestos-e-apply-f.md). Os grupos seed vivem em
`manifests/` e são agrupados por `labels.grupo`.

---

## Convenções

- `name` nunca contém espaço. Use `-` ou `_`.
- Prefixo automático para ideias: `idea-<id>`, `task-<id>`, `routine-<id>`.
- `status` é somente-leitura para o usuário — o motor escreve via `set_status`.
- Para filtrar por label: `/list Idea` (todos) — filtro por selector virá com E0-03 completo.
