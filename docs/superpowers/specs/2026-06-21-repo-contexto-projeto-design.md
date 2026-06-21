---
titulo: Design — Contexto de projeto no Repo (alimenta o insight de IA)
id: SPEC-REPO-CONTEXTO
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-21
---

# Design — Contexto de projeto no Repo

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-21 | Tech Lead | Criação (brainstorming) | PO/PM |

---

## Objetivo

Dar ao `repo-sync` **entendimento do projeto**. Hoje o insight por diff só vê o
diff — sem contexto, a análise é rasa. A feature: na criação do `Repo` (e
periodicamente), varrer a documentação/metadados do projeto, gerar com um modelo
**potente (Opus)** um **resumo de contexto rico**, **represá-lo** num `Doc`
especializado, e **injetá-lo integralmente** no prompt de cada análise de diff —
junto com o diff. Assim o insight explica melhor "o que mudou" e dá sugestões com
conhecimento real do projeto (o propósito central do repo-sync).

## Princípios
- **P1 (economia de IA):** Opus roda só na criação e a cada `context_ttl_days`
  (default 7). O insight por diff roda quando há mudança (análise genuína).
- **P3 (plugável):** continua um `Doc` (especialização por label `tipo=contexto`),
  sem kind novo.
- **ADR-0006 (resiliência):** falha de IA degrada — o sync segue; o insight roda
  sem contexto se ele faltar.

## Decisões fechadas (brainstorming)
1. **Modelo do contexto:** `claude-opus-4-8` (chamada rara, alto valor).
2. **Modelo do insight por diff:** `claude-sonnet-4-6` (era Haiku — análise mais
   forte). Configurável via `Repo.spec.model`.
3. **Atualização:** criação + periódico (TTL).
4. **Limites:** contexto represado e injetado **integrais** (sem truncar); diff e
   corpus com tetos altos perto da janela do modelo, **configuráveis por Repo**.
5. **Doc especializado:** `Doc/repo-<label>-contexto`, `labels.tipo=contexto`.

---

## Componentes (em `src/atlas/rotinas/repo_sync.py`)

### A. Coleta do corpus — `_coletar_contexto(repo_dir) -> tuple[str, list[str]]`
Varre o clone em disco e monta um corpus com cabeçalho por arquivo:
- `README*` na raiz;
- todos os `*.md`/`*.mdx`/`*.rst` sob `docs/**`;
- metadados de projeto (allowlist): `pyproject.toml`, `package.json`,
  `Cargo.toml`, `go.mod`, `pom.xml`, `composer.json`, `*.csproj`, `README` raiz.
Concatena até `context_corpus_max` (default **600 000** chars); se exceder,
prioriza `README` + `docs/**` (metadados depois) e anexa aviso de truncamento.
Devolve `(corpus, lista_de_arquivos)`.

### B. Geração do resumo — `_gerar_contexto(label, repo_dir, store, ctx)`
Monta o corpus (A) e chama `invocar(prompt, modelo=context_model, timeout=180)`
(`context_model` default `claude-opus-4-8`). O prompt pede um **contexto rico e
abrangente para revisão de código**: o que é o projeto, arquitetura, módulos-chave,
fluxos, convenções, domínio e termos — **sem teto de palavras** (resposta longa é
desejável). Salva integral em:
- `Doc/repo-<label>-contexto`, `labels {topic: repo, repo: <label>, tipo: contexto}`,
  `spec.title`, `spec.body = <resumo integral>`, `status {generated_at, model,
  source_files}`.
Em falha do Opus: não cria/atualiza o Doc, loga aviso, segue (degrada).

### C. Frescor — `_contexto_obsoleto(label, store, agora, ttl_days) -> bool`
`True` se o `Doc` de contexto não existe **ou** `status.generated_at` é mais antigo
que `ttl_days` (default **7**). Usado para o gatilho periódico.

### D. Leitura — `_contexto_atual(label, store) -> str`
Devolve `spec.body` do `Doc` de contexto (string vazia se ausente). **Sem
truncar** na leitura.

### E. Gatilhos (em `collect` / `_clonar` / `_sincronizar`)
- **Criação:** após `_clonar`, chama `_gerar_contexto`.
- **Periódico:** no início do `collect` (após resolver o `Repo` e o clone existir),
  se `_contexto_obsoleto(...)` → `_gerar_contexto`. (Na 1ª execução o clone já gera;
  nas seguintes, regenera só quando vence o TTL.)

### F. Injeção no insight — `_analisar(diff, label, modelo, contexto)`
Passa a receber `contexto` e montar o prompt como **contexto íntegro + diff**:
```
## Contexto do projeto (resumo represado)
{contexto}

## Diff a analisar
```diff
{diff}
```
(instruções: explique o que mudou e por quê, riscos, e sugestões acionáveis)
```
`modelo` default `claude-sonnet-4-6` (de `Repo.spec.model`). O diff injetado
respeita `diff_prompt_max` (default **120 000** chars).

## Campos novos no `Repo` (spec) — todos opcionais com default
| Campo | Default | Uso |
|---|---|---|
| `model` | `claude-sonnet-4-6` | modelo do insight por diff |
| `context_model` | `claude-opus-4-8` | modelo do resumo de contexto |
| `context_ttl_days` | `7` | frescor do contexto |
| `context_corpus_max` | `600000` | teto de chars do corpus enviado ao Opus |
| `diff_prompt_max` | `120000` | teto de chars do diff enviado ao insight |
| `diff_store_max` | `200000` | teto de chars do diff guardado no `Diff` |

Status novo no `Repo`: `last_context_at`.

## Limites (revisados — generosos, perto da janela do modelo)
- **Contexto represado:** guardado **integral** (sem truncar) no `Doc`.
- **Contexto injetado:** lido e injetado **integral** no prompt do insight.
- **Corpus / diff:** tetos altos configuráveis (tabela acima), não cortes
  apertados. Substituem os antigos `_MAX_DIFF_PROMPT=5000` / `_MAX_DIFF_STORE=8000`.

## nora-sync remodelado
- `routine.toml`: descrição/comentário atualizados (monitora + contexto rico).
- `Repo/nora` herda os defaults; na próxima execução gera o contexto (Opus 1×) e
  passa a usá-lo nos insights (Sonnet).

## Fluxo de dados
```
criação Repo / TTL vencido
   └─ _coletar_contexto(clone: README+docs/**+metadados, ≤corpus_max)
        └─ invocar(Opus) → resumo rico → Doc/repo-<label>-contexto (integral)
diff novo
   └─ _analisar(modelo=Sonnet, prompt = contexto íntegro + diff[≤diff_prompt_max])
        └─ explica mudanças + sugere, com entendimento do projeto
```

## Tratamento de erro (ADR-0006)
| Caso | Comportamento |
|---|---|
| Opus falha na geração do contexto | não grava Doc; loga; sync segue |
| Contexto ausente no `_analisar` | injeta só o diff; insight roda (degrada) |
| Sonnet falha no insight | mantém comportamento atual (`_(IA indisponível)_`) |
| `docs/` inexistente | corpus = README/metadados; se vazio, contexto = nota mínima |

## Testes (TDD — IA mockada via `invocar`)
- `_coletar_contexto`: lê `README` + `docs/**/*.md` + metadados; respeita
  `context_corpus_max` (prioriza docs/README ao truncar).
- `_gerar_contexto`: cria `Doc/repo-<label>-contexto` com `labels.tipo=contexto`,
  `spec.body` = saída integral do mock, `status.generated_at/model`.
- `_contexto_obsoleto`: ausente → True; `generated_at` velho > ttl → True; fresco
  → False.
- gatilho: 1º clone gera contexto; execução com contexto fresco **não** regenera;
  com TTL vencido regenera.
- `_analisar`: prompt contém o contexto íntegro **e** o diff; usa `spec.model`
  (Sonnet) ; respeita `diff_prompt_max`.
- resiliência: Opus levantando erro não cria Doc e não quebra o sync; `_analisar`
  sem contexto ainda roda.
- limites configuráveis: valores de `Repo.spec` sobrepõem os defaults.

## Documentação
- `docs/arquitetura/kinds.md`: campos novos do `Repo`; `Doc tipo=contexto`.
- Esta spec; nota no `docs/specs/api-http-contrato.md` se necessário (sem mudança
  de endpoint — só comportamento do collect).

## Fora de escopo
- Regeneração automática a cada mudança em `docs/` (ficou periódico, não event-driven).
- Embeddings/RAG (resumo textual é suficiente agora — YAGNI).
- Mudanças na UI (tratadas separadamente).

## DoD
- `repo_sync.py` com coleta/geração/frescor/leitura/injeção, defaults
  configuráveis, contexto represado e injetado integrais; testes verdes.
- `Repo` com campos novos; `Doc tipo=contexto` documentado em `kinds.md`.
- nora-sync remodelado; suíte + lint verdes; bot intacto.
