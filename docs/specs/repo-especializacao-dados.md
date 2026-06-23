---
titulo: Spec — Especialização do Repo (dados/pull, multi-branch, git-graph)
id: SPEC-REPO-DADOS
status: em-revisao
versao: 0.1
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-23
---

# Spec — Especialização do Repo (dados/pull, multi-branch, git-graph)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-06-23 | Tech Lead | Criação — spec (a) do [ADR-0023](../arquitetura/adr/ADR-0023-especializacao-kind-repo.md) | — |

---

> Materializa a **fundação de dados/pull** do épico **E7** (carro-chefe Repo).
> Implementa o lado **dados** do [ADR-0023](../arquitetura/adr/ADR-0023-especializacao-kind-repo.md):
> Kinds `Branch`/`Commit` ocultos, pull multi-branch, git-graph híbrido no store,
> serialização incremental por preset e backfill. A render no quadro branco (spec
> "b", E7-08/E7-10) **não** está nesta spec — depende do [ADR-0020](../arquitetura/adr/ADR-0020-views-especializadas-por-kind.md).

## Objetivo
Hoje a rotina `repo-sync` ([repo_sync.py](../../src/atlas/rotinas/repo_sync.py))
acompanha **uma única branch** (`origin/HEAD`), via `merge --ff-only` (muta a
working tree), e guarda 1 `Diff` por commit. Esta spec eleva o Repo a um
**agregado de cinco Kinds** ligados por label `repo=<label>`, com pull
**multi-branch sem checkout**, grafo de commits reconstruível offline do store,
serialização dos arquivos alterados (inclusive binários office/PDF) e análise de
IA **sob política** (degradada, sem o Kind `Agente` do [ADR-0024](../arquitetura/adr/ADR-0024-kind-agente.md)).

## Escopo
**Inclui:** E7-01 (Kinds `Branch`/`Commit`), E7-02 (pull multi-branch), E7-03
(git-graph híbrido), E7-04 (serialização incremental + binários), E7-05° (`analyze_policy`
**degradado**), E7-06 (backfill), e os campos de schema necessários (parte de E7-07).

**Exclui:** render no quadro branco (E7-08/E7-10 — ADR-0020); o Kind `Agente`
(E7-05 completo — ADR-0024); motor de IA plugável (ADR-0022); renomeação Job
(ADR-0021).

## Modelo de dados — 5 Kinds por label `repo=<label>`
Tudo é `Resource` (k8s-like, [ADR-0015](../arquitetura/adr/ADR-0015-core-api-de-objetos.md));
a relação é por **label**, nunca chave embutida.

| Kind | Visível | `name` | Papel / campos-chave |
|---|---|---|---|
| **Repo** | sim | `<label>` | Agregado. `spec`=config (abaixo); `status`=ponteiros + métricas-resumo (`default_branch`, `branches_total`, `branches_stale`, `commits_total`, `last_sync`, `last_activity`). |
| **Branch** | **oculto** | `<label>-<branch-slug>` | `labels`={repo,branch}; `status`={head, ahead, behind, commits, last_activity, stale}. |
| **Commit** | **oculto** | `<label>-<sha7>` | `labels`={repo,branch,commit}; `spec`={sha, subject, author, author_email, date, parents:[sha7…], files, insertions, deletions, is_merge}. **Sem** `diff_raw`. |
| **Diff** | **oculto** | `<label>-<sha7>` | (já existe) pesado: `diff_raw` + `explicacao`. Criado **sob `analyze_policy`/demanda**, não para todo commit. |
| **Doc** | sim | `repo-<label>-…` | (já existe) contexto + **serializados** (`repo-<label>-file-<slug>`) + por-commit. |

`Branch`/`Commit`/`Diff` recebem `meta.hidden=true` no schema (forward-compat com
ADR-0020; sem comportamento de render nesta spec).

## Configuração do Repo (`Repo.spec`, schema-driven)
| Campo | Tipo | Default | O que define |
|---|---|---|---|
| `url` | text | — | (existe) endereço do repo. |
| `default_branch` | text | auto (`origin/HEAD`) | branch de referência p/ ahead/behind e `auto`. |
| `branches_exclude` | text | — | globs separados por vírgula de branches a ignorar (ex.: `dependabot/*`). |
| `serialize` | select | `off` | `off` · `docs` · `docs+code`. |
| `serialize_globs` | text | — | globs extra a serializar além do preset. |
| `analyze_branches` | text | `default` | `default` (só a default) · `all` · allowlist por vírgula. |
| `analyze_skip_merges` | bool | `true` | pula commits com >1 parent. |
| `analyze_min_lines` | number | `20` | mínimo de linhas alteradas p/ rodar IA. |
| `analyze_max_per_run` | number | `5` | **disjuntor**: teto de análises de IA por execução. |
| `stale_days` | number | `30` | branch sem atividade há mais que isso → `stale`. |
| existentes | — | — | `context_ttl_days`, `context_corpus_max`, `diff_store_max`, `diff_prompt_max`, `model`. |

## Pipeline `collect` (0 IA) — multi-branch sem checkout
Respeita o contrato `collect` ([ADR-0004](../arquitetura/adr/ADR-0004-contrato-collect.md)): **collect não usa IA**.

1. `git fetch '+refs/heads/*:refs/remotes/origin/*'` (todas as remotas; sem checkout).
2. Resolve `default_branch` (config ou `origin/HEAD`).
3. `for-each-ref refs/remotes/origin` → lista de branches (aplica `branches_exclude`).
4. Por branch: `rev-list <head_materializado>..origin/<branch>` → commits novos
   (ou todos, na 1ª vez, limitado pela profundidade do clone).
5. Para cada commit novo: `git log -1 --numstat --format=…%P…` → materializa
   `Commit` **leve** (sha, subject, author, date, `parents`, stat, `is_merge`).
6. Atualiza `Branch` (head, `ahead/behind` vs default via
   `rev-list --left-right --count`, `commits`, `last_activity`, `stale`).
7. **Serializa** os arquivos alterados conforme o preset (§ Serialização) → `Doc`.
8. Atualiza `Repo.status` (ponteiros + métricas-resumo).
9. Monta a notificação rica **por branch** lendo só o store.

**Sem mudanças:** registra `last_check` e mantém metadados frescos (como hoje).
**Clone inicial:** mantém `--depth=100` e gera o `Doc` de contexto (Opus) como hoje.

## `analyze` — degradado, sob `analyze_policy`
Fase **separada** e barata por padrão. Para cada `Commit` novo, um gating decide se
roda IA:

- branch ∈ `analyze_branches` (`default`/`all`/allowlist);
- `not (analyze_skip_merges and is_merge)`;
- `linhas_alteradas >= analyze_min_lines`;
- **disjuntor:** no máximo `analyze_max_per_run` análises por execução.

Quando passa: `git show <sha>` (Diff **pesado**) → IA (Sonnet, reusa o `_analisar`
atual com o contexto do projeto represado) → `Diff/<label>-<sha7>` + `Doc`
arquivado. **O ponto de chamada da IA vive num seam isolado** (`analyze.py`),
pronto para virar `Agente` ([ADR-0024](../arquitetura/adr/ADR-0024-kind-agente.md)) sem tocar no resto.

## Serialização incremental (presets + extratores)
Atua só sobre arquivos **alterados** no pull. Registry por extensão (`script-primeiro`):

- **texto/código** (`.md`,`.rst`,`.txt`,`.py`,`.ts`,`.c`,…): lê direto (UTF-8, `errors=replace`).
- **office OOXML/ODF** (`.docx`,`.pptx`,`.odt`): `zipfile` + `xml.etree` da **stdlib**
  (concatena os nós de texto). **Zero dependência nova.**
- **PDF** (`.pdf`): via `pdftotext` (CLI poppler) **se disponível**; **degrada** (pula
  com nota) se ausente.
- **Nunca** binário compilado (sem valor textual).

Presets: `docs` = extensões de documentação; `docs+code` = + fontes; `+
serialize_globs`. Cada arquivo vira `Doc/repo-<label>-file-<slug>` (chaveado por
path, **atualiza in-place**), `labels`={repo, path, tipo:serial}.

## Backfill
Função `backfill(label)` + comando `/repo backfill <label>` + ação no schema:
`git fetch --unshallow` → varre o histórico completo de todas as branches →
materializa `Branch`/`Commit` leves retroativos. **Idempotente** (pula `Commit` já
existente). **0 IA por padrão** (Diff/análise retroativos só sob demanda).

## Contrato de código
- Refatorar `src/atlas/rotinas/repo_sync.py` → pacote `repo_sync/`:
  `__init__.py` (orquestra `@registrar("repo-sync")`), `git.py`, `materialize.py`,
  `serialize.py`, `analyze.py`, `context.py`, `backfill.py`. Entrypoint e
  comportamento de saída preservados.
- Novos campos em `_KIND_SCHEMA` (`api_schema.py`) + `meta.hidden` em
  `Branch`/`Commit`/`Diff` + ação `backfill` em `_ACTIONS`.
- Comando `/repo backfill <label>` no handler (Telegram/_cmd), 0 IA.

## Definição de Pronto (DoD)
- [ ] **TDD**: lógica git-pesada (multi-branch, parents/grafo, ahead/behind,
      backfill) testada contra **repos git reais em `tmp_path`**; IA mockada.
- [ ] `collect` materializa `Branch`/`Commit` corretos p/ ≥2 branches; grafo
      reconstruível de `Commit.parents`.
- [ ] Serialização produz `Doc` para texto, office (stdlib) e degrada sem `pdftotext`.
- [ ] `analyze_policy` respeita gating + disjuntor (nº de chamadas de IA ≤ teto).
- [ ] `backfill` idempotente (rodar 2× não duplica nem re-materializa).
- [ ] Testes existentes (`test_repo_sync`, `test_repo_contexto`) **verdes** (alvos
      de patch ajustados ao pacote).
- [ ] `ruff` + `pytest` completos verdes, com evidência.
- [ ] Doc atualizada: este arquivo, ADR-0023 → `aceito`, backlog (E7-01..06).

## Fora de escopo / pendências
- Render, dashboards e git-graph visual (spec "b" — ADR-0020).
- Kind `Agente` e motor plugável (ADR-0024/0022).
- Extração de binários mais rica (tabelas/imagens em PDF) — `pdftotext` basta agora.
- Paginação de backfill para históricos gigantes — verificar em campo.
