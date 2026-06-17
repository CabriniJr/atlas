---
titulo: Spec — Core API de objetos (K8s-like)
id: SPEC-CORE-API
status: em-revisao
versao: 0.1
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Spec — Core API de objetos (K8s-like)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-06-16 | Tech Lead | Criação (prioridade máxima) | — |

---

> Implementa [ADR-0015](../arquitetura/adr/ADR-0015-core-api-de-objetos.md).
> **Prioridade máxima.** Esta spec cobre o **passo 1** (core de objetos); os passos
> 2–5 (HTTP, migração, Telegram, web) terão specs/seções próprias.

## Objetivo
Estabelecer o **modelo de objetos uniforme** e a **persistência genérica** que
viram o motor central. Tudo é `Resource`; verbos uniformes operam qualquer `kind`.

## Resource (o objeto)
```python
@dataclass
class Resource:
    kind: str                       # "Routine", "Tracker", "Idea", ...
    name: str                       # único dentro do kind
    api_version: str = "atlas/v1"
    labels: dict[str, str] = {}     # para seleção/filtragem
    spec: dict = {}                 # estado desejado (usuário)
    status: dict = {}               # estado observado (sistema)
    criado_em: str | None = None    # ISO; preenchido na criação
    atualizado_em: str | None = None
```
- Identidade = `(kind, name)`.
- `to_dict()` / `from_dict()` para (de)serialização espelhando a forma K8s
  (`apiVersion`, `kind`, `metadata`, `spec`, `status`).

## ResourceStore (persistência)
Tabela genérica:
```sql
CREATE TABLE IF NOT EXISTS resources (
    kind          TEXT NOT NULL,
    name          TEXT NOT NULL,
    api_version   TEXT NOT NULL DEFAULT 'atlas/v1',
    labels_json   TEXT,
    spec_json     TEXT,
    status_json   TEXT,
    criado_em     TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    PRIMARY KEY (kind, name)
);
```

### Verbos (uniformes para todo kind)
| Verbo | Assinatura | Comportamento |
|---|---|---|
| `create` | `create(res, agora) -> Resource` | insere; **erro** se `(kind,name)` já existe |
| `get` | `get(kind, name) -> Resource \| None` | devolve o objeto ou `None` |
| `list` | `list(kind, selector=None) -> list[Resource]` | lista do kind; filtra por labels |
| `apply` | `apply(res, agora) -> Resource` | upsert: cria, ou atualiza `spec`/`labels`/`status` preservando `criado_em` |
| `patch` | `patch(kind, name, spec_patch, agora) -> Resource` | merge raso em `spec`; **erro** se não existe |
| `set_status` | `set_status(kind, name, status, agora)` | só o motor escreve `status` |
| `delete` | `delete(kind, name) -> bool` | remove; `False` se não existia |
| `kinds` | `kinds() -> list[str]` | kinds distintos presentes (para "describe tudo") |

- `agora: datetime` é **injetado** (testabilidade — padrão já usado no projeto).
- Erros de domínio: `ResourceJaExiste`, `ResourceNaoEncontrado` (mensagens claras).
- Resiliência (ADR-0006): operações são atômicas por objeto; erro em um não afeta
  outros.

### Selector (filtragem por labels)
`selector` é um `dict[str,str]`; um resource casa se contém todos os pares (match
exato). Vazio/None = todos. (Igualdade simples agora; operadores avançados depois.)

## Fora de escopo deste passo
- API HTTP (passo 2).
- Migração das tabelas legadas (`ideas`, `trackers`, `alarms`, …) para `resources`
  (passo 3) — o store novo é **aditivo**; nada existente é tocado agora.
- AuthN/Z, web app, conectividade Vercel.

## Casos de erro
| Caso | Comportamento |
|---|---|
| `create` com `(kind,name)` existente | levanta `ResourceJaExiste` |
| `patch`/`set_status` em inexistente | levanta `ResourceNaoEncontrado` |
| `get`/`delete` em inexistente | `None` / `False` (não é erro) |
| JSON corrompido no banco | erro claro na leitura daquele objeto, não derruba o `list` |

## Testes (TDD — escrever primeiro)
- `Resource.to_dict/from_dict` ida-e-volta preserva campos (forma K8s).
- `create` insere e devolve com `criado_em`/`atualizado_em`; duplicado levanta erro.
- `get` devolve o objeto; `None` se ausente.
- `list` por kind; isolamento entre kinds; filtro por `selector`.
- `apply` cria quando ausente; atualiza `spec` preservando `criado_em` quando existe.
- `patch` faz merge raso; erro se ausente.
- `set_status` escreve status; `get` reflete.
- `delete` remove (`True`) e é `False` na segunda vez.
- `kinds` lista os tipos presentes.
- Resiliência: objeto com JSON inválido não quebra o `list` dos demais.

## DoD
- `atlas/core/resource.py` e `atlas/core/store.py` com os verbos acima, testados.
- Tabela `resources` criada idempotentemente (não quebra bancos existentes).
- Suíte verde, lint limpo. Bot em produção **intacto** (nada legado tocado).
