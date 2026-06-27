---
titulo: Spec de design — UI de curadoria do gate (Agente modo `code`)
id: SPEC-CURADORIA-GATE
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-26
---

# Spec de design — UI de curadoria do gate

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-26 | Tech Lead | Criação — desenho aprovado pelo PO (fecha o E7-28 / ADR-0028 §4) | PO/PM |

---

> Fecha a última pendência do **E7-28** ([ADR-0028](../../arquitetura/adr/ADR-0028-endurecimento-agente-code.md)
> §4 + §Pendências "UI de curadoria"). O backend de endurecimento (workspace
> restrito, tools, concorrência, gate, persistência de runs) já está em
> `feat/hardening-agente-code`.

## Problema

O Agente modo `code` ([ADR-0025](../../arquitetura/adr/ADR-0025-agente-modo-code.md))
escreve **direto na working tree** do repositório (o `cwd` confinado do run). Com
`gate=true` ([ADR-0028](../../arquitetura/adr/ADR-0028-endurecimento-agente-code.md) §4),
nada é auto-comitado — mas hoje **não há onde revisar** o que o agente produziu. O
gate é só uma flag. Falta a curadoria humana (CLAUDE.md §6; ADR-0003/0013): ver o
diff e decidir **aprovar** (promover) ou **descartar**.

## Decisões (aprovadas pelo PO)

1. **Ações:** ver o diff + **Descartar** / **Aprovar-e-commitar em branch**.
2. **Lugar:** aba **"Curadoria"** no render do Agente (`kinds/agente.js`), ao lado de
   Chat/Code/Config, com badge da contagem de runs pendentes.

## Modelo de dados

O Kind `AgentRun` (persistido em `persist_agent_run`, ADR-0028 §5) ganha:
- **`spec.workspace`** — o `cwd` absoluto efetivamente usado no run (já resolvido por
  `resolve_workspace`). Necessário para escopar diff/discard/approve.
- **`status.review`** — `pending` | `approved` | `discarded`. Definido na persistência:
  `pending` **apenas** se o run foi `gated` **e** terminou em `done`; caso contrário
  ausente (erros e runs não-gated não pedem revisão).
- **`status.branch`** — preenchido no approve (`agent/<id>`).

Como `AgentRun` é um Kind, a API genérica escopada por dono (ADR-0027) já serve a
lista — a aba consome `GET /apis/atlas/v1/AgentRun` e filtra por `spec.agente` +
`status.review=="pending"`.

## Backend — módulo `curadoria.py`

Funções puras sobre git (via `rotinas/repo_sync/gitcmd.git`), testáveis com um repo
temporário. `repo` = raiz do projeto (`_PROJECT_DIR`); `path` = workspace relativo.

- **`workspace_diff(repo, path) -> str`**: `git add -N -- <path>` (intent-to-add,
  reversível, faz arquivos novos aparecerem no diff) seguido de `git diff -- <path>`.
  Retorna o diff textual (inclui arquivos novos). String vazia = sem mudanças.
- **`discard_workspace(repo, path) -> None`**: `git restore --worktree -- <path>`
  (reverte rastreados) + `git clean -fd -- <path>` (remove novos não-rastreados).
- **`approve_to_branch(repo, path, branch, message) -> str`**: cria `branch` a partir
  do HEAD atual, comita **só** `<path>` lá e volta para a branch original (working
  tree limpa do que foi promovido). Retorna o nome da branch. Idempotência mínima:
  se a branch já existe, erro claro.

### Endpoints (em `api.py`, atrás de `_auth()` + escopo por dono)
- `GET  /_agent_run/{id}/diff` → `{diff}` do workspace do run.
- `POST /_agent_run/{id}/discard` → reverte; marca `review=discarded`.
- `POST /_agent_run/{id}/approve` → branch `agent/<id>`, commit
  `agent(<agente>): <task truncada>` (+ `Co-Authored-By: Claude`); marca
  `review=approved`, grava `status.branch`.

Cada endpoint resolve o `AgentRun` pelo `{id}`, checa visibilidade pelo dono
(`labels.owner` vs sessão; alheio → **404**, como `scoping.py`) e usa
`spec.workspace`.

## Frontend — aba "Curadoria" (`kinds/agente.js`)

- Nova aba com badge = nº de runs `pending` do agente.
- Lista os runs pendentes (`#id`, task, data). "Revisar" → `GET …/diff`, mostra o
  diff num `<pre>` com realce simples (linhas `+`/`-`), botões **Descartar** e
  **Aprovar → branch**.
- Após a ação: toast/estado com o resultado (nome da branch no approve), botão em
  estado "…" durante a chamada, e atualização da lista. Alinha com o pedido de UX
  dinâmica (E8) sem escopo extra.

## Limitações (documentadas, não bloqueiam)

- **Working tree compartilhada:** o diff de um run = o estado não-commitado **atual**
  do seu workspace. Dois runs no mesmo workspace não têm autoria separável →
  recomendação: workspaces distintos por agente (`spec.workspace`).
- **Repo vivo (Rasp):** `approve` troca de branch por um instante no repo que roda o
  servidor → risco operacional. Curadoria é primariamente **dev-time**. Pendência:
  isolar via git worktree no futuro.

## Testes

- `tests/test_curadoria.py`: repo git real em `tmp_path` — `workspace_diff` (vê
  arquivo novo e edição), `discard_workspace` (reverte rastreado + remove novo),
  `approve_to_branch` (cria branch, comita só o path, volta limpo).
- Escopo: diff/approve/discard de run de outro dono → 404 (espelha
  `tests/test_api_auth.py`).

## Fora de escopo (vira backlog)

- Inbox global de curadoria (todos os agentes).
- Isolamento por git worktree do run.
- Aprovar abrindo PR no GitHub automaticamente (hoje pára na branch local).
