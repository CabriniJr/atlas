---
titulo: Dossiê de contexto — Épico E7 (Repo como carro-chefe)
id: CTX-E7-REPO
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-23
---

# Dossiê de contexto — Épico E7 (Repo como carro-chefe)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-23 | Tech Lead | Criação — agregação de contexto para despachar devs no E7 | PO/PM |

---

> **Para que serve.** Quando um modelo desenvolvedor é despachado para trabalhar no
> épico **E7 (especialização do Kind Repo)**, **cole o link deste dossiê** no prompt.
> Ele agrega, em ordem de leitura, os arquivos certos — ADRs (o porquê), código (o
> onde), plano (o como) e contratos/testes (as regras) — para o dev ganhar contexto
> rico sem garimpar o repositório. Leia também o [CLAUDE.md](../../../CLAUDE.md) na raiz.
>
> Instância da [diretriz de dossiê de contexto](../../processos/dossie-de-contexto.md).

## 0. Regras inegociáveis (resumo — não pule)

- **A doc é a fonte de verdade.** Código que diverge da doc está errado, ou precisa de
  um ADR. Ver [CLAUDE.md](../../../CLAUDE.md) e [docs/README.md](../../README.md).
- **TDD sempre** ([definicao-de-pronto](../../processos/definicao-de-pronto.md),
  [ADR-0007](../../arquitetura/adr/ADR-0007-contrato-de-teste.md)): teste primeiro.
- **Branch + PR + Conventional Commits** ([política](../../processos/politica-de-desenvolvimento.md)).
  Trabalhe em `feat/repo-contexto` (ou branch curta a partir dela); commits `tipo(escopo): assunto`.
- **`collect` não usa IA** ([ADR-0004](../../arquitetura/adr/ADR-0004-contrato-collect.md)): coleta/serialização são Python puro; IA é fase separada.
- **Degrade, não quebre** ([ADR-0006](../../arquitetura/adr/ADR-0006-erro-e-resiliencia.md)): falha de IA/git por branch não derruba o resto.
- **Store é aditivo** ([ADR-0002](../../arquitetura/adr/ADR-0002-modelo-de-dados.md)): nunca migração destrutiva; novos campos/Kinds convivem com os antigos.
- **Config é schema-driven** ([ADR-0017](../../arquitetura/adr/ADR-0017-gui-por-kind-abstrai-api.md)): campo novo entra em `_KIND_SCHEMA`; o front não tem lógica de negócio.

## 1. Leia primeiro — o "porquê" (ADRs)

| Ordem | Arquivo | O que extrair |
|---|---|---|
| 1 | [ADR-0015 — Core como API de objetos](../../arquitetura/adr/ADR-0015-core-api-de-objetos.md) | Tudo é `Resource` (kind/spec/status); verbos uniformes do store. A base mental k8s-like. |
| 2 | [ADR-0023 — Especialização do Kind Repo](../../arquitetura/adr/ADR-0023-especializacao-kind-repo.md) | **A decisão central do E7.** Modelo de 5 Kinds, pipeline multi-branch híbrido, serialização, `analyze_policy`, backfill, Telegram. |
| 3 | [ADR-0020 — Views especializadas por Kind](../../arquitetura/adr/ADR-0020-views-especializadas-por-kind.md) | Quadro branco genérico + atributo `hidden`/`nested`. Necessário para a render do Repo e os Kinds ocultos. |
| 4 | [ADR-0024 — Kind Agente](../../arquitetura/adr/ADR-0024-kind-agente.md) | O analisador configurável que a `analyze_policy` referencia. |
| 5 | [ADR-0022 — Motor de IA plugável](../../arquitetura/adr/ADR-0022-motor-de-ia-plugavel.md) | Seleção de motor; ponto de extensão para local (Ollama/Gemma). |
| 6 | [ADR-0021 — Rotina → Job](../../arquitetura/adr/ADR-0021-rotina-para-job.md) | Renomeação transversal (afeta terminologia em todo o E7). |

## 2. O "como" — spec, plano e roadmap

| Arquivo | O que extrair |
|---|---|
| [SPEC-REPO-DADOS](../../specs/repo-especializacao-dados.md) | **Autoritativa (comece por aqui).** Spec (a) dados/pull do ADR-0023: modelo dos 5 Kinds, campos de schema, pipeline multi-branch **sem checkout**, `analyze_policy` + disjuntor, serialização (stdlib + `pdftotext`), backfill, **contrato de código (pacote `repo_sync/`)** e DoD. |
| [Plano E7-01 — fundação multi-branch](2026-06-23-repo-fundacao-multibranch.md) | Apoio TDD ilustrativo das primitivas (slug, métricas, materialização). **Superado pela spec** quanto a estrutura (pacote) e estratégia de teste (git real) — use como referência de lógica, siga a spec na arquitetura. |
| [Backlog — épico E7](../../roadmap/backlog.md) | Estado de cada história (feito × a-fazer), dependências e ordem. |

## 3. O "onde" — código a conhecer

| Arquivo | Papel | O que olhar |
|---|---|---|
| [src/atlas/rotinas/repo_sync.py](../../../src/atlas/rotinas/repo_sync.py) | **A rotina-alvo.** | Anatomia: `collect` (entrada), `_clonar`/`_sincronizar`, `_reportar`, `_salvar_diff`/`_salvar_doc`, `_gerar_contexto`, wrapper `_git`. Clone é `--depth=100` (raso) e só segue `origin/HEAD` hoje. **A spec manda refatorar isto num pacote** `repo_sync/` (`git.py`, `materialize.py`, `serialize.py`, `analyze.py`, `context.py`, `backfill.py`) preservando o entrypoint `@registrar("repo-sync")`. |
| [src/atlas/core/resource.py](../../../src/atlas/core/resource.py) | Forma do `Resource` | `kind`, `name`, `labels`, `spec`, `status`. Identidade = `(kind, name)`. |
| [src/atlas/core/store.py](../../../src/atlas/core/store.py) | Persistência | Verbos `get/list/apply/patch/set_status/delete`; `list(kind, labels=...)` filtra por label (AND exato). |
| [src/atlas/executor.py](../../../src/atlas/executor.py) | `ContextoExecucao` e `CollectResult` | O que `collect` recebe (`ctx.agora`, `ctx.store`, `ctx.rotina`, `ctx.db`) e devolve (`CollectResult(data=...)`). |
| [src/atlas/routines.py](../../../src/atlas/routines.py) | `Rotina` + carga TOML | Campos da rotina (`label`, `coletar`, `agenda`, `modelo`, `ativa`). |
| [src/atlas/api_schema.py](../../../src/atlas/api_schema.py) | `_KIND_SCHEMA` + `_ACTIONS` (`GET /_schema`) | Onde declarar schema/ações de Kinds (incl. o futuro `hidden` dos Kinds ocultos). Entrada `Repo` em `:104` e `:184`. |
| [src/atlas/api.py](../../../src/atlas/api.py) | Dashboard embutido | `_kindCard`/`_repoCard` (render do Repo, ~`:1658-1684`). É o front que será modularizado (E7-10). |
| [src/atlas/ia.py](../../../src/atlas/ia.py) | `invocar(prompt, modelo, timeout)` | A fronteira de IA (modo análise 2a). Sempre mockada em teste. |

## 4. As regras de teste — padrões a copiar

| Arquivo | O que extrair |
|---|---|
| [tests/test_repo_sync.py](../../../tests/test_repo_sync.py) | **Padrão canônico.** Fixtures `db`/`store`; `_mk(stdout, rc, stderr)`; mock de `subprocess.run` por inspeção de `" ".join(args)`; mock de `invocar` via `patch("atlas.rotinas.repo_sync.invocar", ...)`. `_fake_run_rico()` devolve diff com `--stat` + `git log`. |
| [tests/test_repo_contexto.py](../../../tests/test_repo_contexto.py) | Testes do `Doc` de contexto (Opus), TTL e corpus. |
| [tests/test_core_store.py](../../../tests/test_core_store.py) | Como exercitar o store isolado (útil para testar materialização de `Branch`/`Commit`). |

**Estratégia de teste (autoritativa — DoD da spec):** a lógica git-pesada nova
(multi-branch, parents/grafo, ahead/behind, backfill) é testada contra **repositórios
git reais criados em `tmp_path`** (`git init`, commits, branches de verdade), com a
**IA mockada**. Os testes legados de `test_repo_sync.py` (mock de `subprocess.run`)
continuam válidos para o caminho single-branch e devem permanecer verdes após a
refatoração (ajustando os alvos de `patch` ao novo pacote).

## 5. Modelo de dados alvo (referência rápida — ADR-0023 §1)

Agregados por label `repo=<label>`. `Branch`/`Commit`/`Diff` são **ocultos**.

```
Repo/<label>      spec: {url, branches, serialize, analyze{agente,policy}, goal}
                  status: {default_branch, heads, totais, last_sync}
Branch/<label>-<slug>   labels:{repo,branch}  status:{head,ahead,behind,commits,last_activity,stale}
Commit/<label>-<sha7>   labels:{repo,branch,commit}  spec:{sha,subject,author,date,parents,stat}   # leve, sem diff_raw
Diff/<label>-<sha7>     labels:{repo,commit}  spec:{diff_raw, explicacao}   # pesado, sob analyze_policy/demanda
Doc/<label>-…           labels:{repo,topic:repo,tipo}  # contexto, serializados, por-commit
```

## 6. Sequência das fatias do E7

- **Dados/pull — E7-01..E7-06** → coberto pela [SPEC-REPO-DADOS](../../specs/repo-especializacao-dados.md)
  (Kinds `Branch`/`Commit`, pull multi-branch sem checkout, git-graph híbrido,
  serialização, `analyze_policy` degradado, backfill, pacote `repo_sync/`). **Em andamento.**
- **Front — E7-07/E7-08/E7-10** → spec "b" (render no quadro branco + modularização);
  depende do [ADR-0020](../../arquitetura/adr/ADR-0020-views-especializadas-por-kind.md). *A escrever.*
- **Agente/motor — E7-05 completo** → depende dos ADRs [0024](../../arquitetura/adr/ADR-0024-kind-agente.md)/[0022](../../arquitetura/adr/ADR-0022-motor-de-ia-plugavel.md). *A escrever.*
- **Telegram — E7-11** → pool/stateful/digest. *A escrever.*

> As specs/planos ainda não escritos (front, Agente, Telegram) são pedidos ao Tech
> Lead (Opus) quando a fatia entrar na fila — cada uma é uma spec/plano próprio.

## 7. Armadilhas conhecidas

- **Clone raso:** `--depth=100`. Git-graph completo/backfill exigem `--unshallow` (E7-06). Não assuma histórico completo.
- **Nomes de branch com `/`** (`feat/x`) não compõem `name` de Resource — use slug (`feat-x`). Ver Task 1 do plano.
- **Grafo é offline:** reconstruído de `Commit.parents` + ponteiros de `Branch` no store, não do clone em runtime (ADR-0023 §3).
- **Custo de IA:** todas as branches multiplicam análise — a `analyze_policy` é o que segura o gasto (ADR-0023 §2; [ADR-0005](../../arquitetura/adr/ADR-0005-orcamento-reativo.md)).
- **Não-quebrante:** `Diff`/`Doc`/`Repo.status` atuais devem continuar funcionando; materialização nova é aditiva.
