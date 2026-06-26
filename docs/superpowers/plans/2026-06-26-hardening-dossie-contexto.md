---
titulo: Dossiê de contexto — Endurecimento de segurança (modo `code` + plataforma)
id: CTX-HARDENING
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-26
---

# Dossiê de contexto — Endurecimento (hardening)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-26 | Tech Lead | Criação — prep para a próxima sessão executar o Tema 1 (Endurecimento) | PO/PM |

---

> **Para o dev despachado a frio.** Esta é a próxima rodada priorizada pelo PO (Tema 1 de
> [`proximos-passos.md`](../../roadmap/proximos-passos.md)). Leia este dossiê + o
> [CLAUDE.md](../../../CLAUDE.md) e o [dossiê de handoff](../../processos/dossie-handoff.md)
> antes de codar. Ele **aponta** os arquivos certos (não os repete). Instância da
> [diretriz de dossiê de contexto](../../processos/dossie-de-contexto.md).

## 0. Regras inegociáveis (não pule)
- **A doc é a fonte de verdade** ([CLAUDE.md](../../../CLAUDE.md)). Mudança de arquitetura
  vira **ADR** antes do código; atualize [índice de ADRs](../../arquitetura/adr/README.md) e backlog.
- **TDD sempre** ([definicao-de-pronto](../../processos/definicao-de-pronto.md)): teste primeiro, veja falhar, implemente.
- **Branch + PR + Conventional Commits** ([política](../../processos/politica-de-desenvolvimento.md)).
  Commits terminam com `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- **Degrade, não quebre** ([ADR-0006](../../arquitetura/adr/ADR-0006-erro-e-resiliencia.md)).
- **Store aditivo** ([ADR-0002](../../arquitetura/adr/ADR-0002-modelo-de-dados.md)); **config schema-driven** ([ADR-0017](../../arquitetura/adr/ADR-0017-gui-por-kind-abstrai-api.md)).
- **Gotcha de testes:** rode com o **Python do sistema** (`python -m pytest tests/ -q`,
  **490 testes** hoje), não o do venv (fixture `free_tcp_port`). Lint: `.venv/bin/ruff check src/ tests/`.

## 1. ADRs — o porquê (ordem de leitura)
| ADR | O que extrair |
|---|---|
| [ADR-0025 §Pendências](../../arquitetura/adr/ADR-0025-agente-modo-code.md) | **A lista-mãe do hardening.** Workspace restrito, gate de curadoria, auth, persistência de runs + concorrência, allow/deny de tools por Agente. É o escopo do item 1.1. |
| [ADR-0003](../../arquitetura/adr/ADR-0003-seguranca-meta-loop.md) | Segurança do meta-loop: código gerado por modelo **nunca** auto-executa sem revisão humana. Base do **gate de curadoria**. |
| [ADR-0013](../../arquitetura/adr/ADR-0013-barreira-de-entrada.md) | Barreira de entrada: só agir com intenção explícita — alinhar o gate a isto. |
| [ADR-0027](../../arquitetura/adr/ADR-0027-multiusuario-credenciais.md) | Auth/sessão e escopo por dono **já existem** (sessões em memória). Itens 1.2 (persistir sessões) e 1.4 (rotação de chave/UX de cadastro) saem das §Pendências dele. |
| [spec de endurecimento §2](../specs/2026-06-16-atlas-endurecimento-design.md) | Desenho original do 2b com workspace restrito e tools limitadas. |

## 2. Escopo desta rodada (Tema 1 — Endurecimento)
Da fila aprovada em [`proximos-passos.md`](../../roadmap/proximos-passos.md):

| # | Item | Fonte | Tam. |
|---|---|---|---|
| 1.1 | **E7-28 — endurecer o modo `code`**: workspace restrito, gate de curadoria humana, allow/deny de tools por Agente, limite de concorrência | ADR-0025 §Pendências | G |
| 1.2 | **Persistir sessões** (hoje em memória) | ADR-0027 §Pendências | P |
| 1.3 | **Persistir runs agênticos** (hoje em memória) | ADR-0025 §Pendências | M |
| 1.4 | **Rotação da chave mestra do cofre + UX de cadastro/convite de usuários** | ADR-0027 §Pendências | M |

> **Decisão de arquitetura provável (abrir ADR antes de codar):** o desenho do
> *workspace restrito* + *gate de curadoria* + *allow/deny de tools* muda o contrato do
> modo `code` → **proponha um ADR-0028 (endurecimento do Agente `code`)** consolidando
> ADR-0025 §Pendências. Os itens de persistência (1.2/1.3) e rotação de chave (1.4) são
> evoluções não-destrutivas que **não** exigem novo ADR (cabem nas §Pendências existentes),
> salvo se mudarem o modelo de dados.

## 3. Código — o onde
| Arquivo | Papel | O que olhar / mexer |
|---|---|---|
| [src/atlas/api.py](../../../src/atlas/api.py) | API + runs agênticos | `_PROJECT_DIR` (cwd hoje = raiz); `_run_agent_bg` (monta `claude … --dangerously-skip-permissions --add-dir <cwd>`); `_new_run`/`_runs` (dict **em memória**, `_RUNS_MAX`); endpoint `POST /_agent_run`. Aqui entram: workspace restrito (cwd + allow-list de paths), allow/deny de tools (`--allowedTools`/`--disallowedTools` do claude), limite de concorrência, persistência de runs. |
| [src/atlas/api_schema.py](../../../src/atlas/api_schema.py) | Schema do Kind `Agente` | Adicionar campos schema-driven: `workspace` (subdir permitido), `allowed_tools`/`denied_tools`, `gate` (curadoria on/off). Forms aparecem sozinhos no front (ADR-0017). |
| [src/atlas/sessions.py](../../../src/atlas/sessions.py) | Sessões (item 1.2) | Hoje dict em memória. Persistir: gravar no store (Kind `Session`? ou tabela) ou em disco; manter a API `create/resolve/destroy`. **Não** vazar o token. |
| [src/atlas/secrets_store.py](../../../src/atlas/secrets_store.py) | Cofre (item 1.4) | Adicionar rotação: re-cifrar todos os `secrets/credentials/*.enc` com uma chave nova; manter `reset_cache`. |
| [src/atlas/users.py](../../../src/atlas/users.py) | Usuários (item 1.4) | UX de cadastro/convite: endpoint/admin para criar+convidar; hoje só `create_user`/`POST /_auth/users`. |
| [src/atlas/scoping.py](../../../src/atlas/scoping.py) | Isolamento | Referência: o gate/workspace deve respeitar o dono da sessão (`self._owner()` no handler). |

## 4. Testes — as regras (padrões a copiar)
| Arquivo-modelo | Padrão |
|---|---|
| [tests/test_api_auth.py](../../../tests/test_api_auth.py) | Fixture de servidor HTTP com `_TOKEN` setado (loopback ≠ admin), `_req()` com cookie/bearer. Use para testar gate/escopo do `/_agent_run`. |
| [tests/test_sessions.py](../../../tests/test_sessions.py) | Sessão com `now` injetável (TTL). Estender para persistência (sobreviver a "restart" = recriar o módulo/store). |
| [tests/test_scoping.py](../../../tests/test_scoping.py) | Políticas puras testadas isoladamente — espelhe para as políticas de workspace/tools. |
| [tests/test_secrets_store.py](../../../tests/test_secrets_store.py) | `monkeypatch` de `ATLAS_SECRETS_DIR` + `reset_cache`. Use para testar rotação de chave. |

## 5. Modelo de dados alvo (provável)
- **`Agente.spec`** (novos campos, schema-driven): `workspace` (str, subdir relativo permitido), `allowed_tools` (csv), `denied_tools` (csv), `gate` (bool — exige curadoria antes de aplicar).
- **Persistência de sessão/run:** decidir entre Kind no store (P11 — `Session`/`AgentRun` ocultos) **ou** arquivo cifrado/JSON. Preferir **store** (é o estado do sistema, P4) salvo se o custo for alto.

## 6. Sequência sugerida das fatias (TDD, mergeáveis)
1. **ADR-0028** (endurecimento do `code`) — desenho do workspace restrito + gate + tools. *(doc primeiro)*
2. **Allow/deny de tools por Agente** — campos no schema + montar `--allowedTools/--disallowedTools` em `_run_agent_bg`. *(fatia pequena, testável)*
3. **Workspace restrito** — cwd/`--add-dir` confinados a `Agente.spec.workspace` sob a raiz; recusar paths fora. *(núcleo do risco)*
4. **Gate de curadoria** — runs marcados ficam "pendentes de revisão"; aplicar só após aprovação humana (alinhar ADR-0003/0013).
5. **Limite de concorrência + persistência de runs** — teto simultâneo; persistir `_runs`.
6. **Persistência de sessões** (item 1.2) e **rotação de chave + UX de cadastro** (1.4) — fatias independentes, podem vir em paralelo.

> **Dica de despacho:** comece pela fatia 1 (ADR-0028). Cada fatia: branch curta a partir
> de `main` → TDD → ruff → PR/merge. O CD da Rasp aplica `main` em ≤5 min.
