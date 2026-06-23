---
titulo: ADR-0023 — Especialização do Kind Repo (multi-branch, git-graph, serialização e análise profundas)
id: ADR-0023
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-23
substitui: —
substituido-por: —
---

# ADR-0023 — Especialização do Kind Repo (multi-branch, git-graph, serialização e análise profundas)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-06-23 | Tech Lead | Proposta (brainstorm com PO/PM) | — |
| 1.0    | 2026-06-23 | Tech Lead | Aceito pelo PO/PM; spec (a) dados/pull em implementação ([SPEC-REPO-DADOS](../../specs/repo-especializacao-dados.md)) | PO/PM |

---

## Status
`aceito`. A spec (a) **dados/pull** está em implementação
([repo-especializacao-dados](../../specs/repo-especializacao-dados.md)). A spec (b)
**front/git-graph** depende do ADR-0020 e fica para depois.

## Contexto

A rotina `repo-sync` ([repo_sync.py](../../../src/atlas/rotinas/repo_sync.py)) é hoje
a capacidade mais importante do Atlas e, ao mesmo tempo, a mais rasa: acompanha
**uma única branch** (`origin/HEAD`), guarda uma linha de `Diff` por commit e gera
um `Doc` de contexto (Opus) e um `Doc` por commit. Não há noção de múltiplas
branches, de grafo de commits, de progresso ao longo do tempo, nem de serialização
dos documentos do repositório. As mensagens são simples e a configuração mais rica
exige editar o manifesto na mão.

O PO definiu a ambição: o Repo deve virar o **carro-chefe** do produto —
acompanhamento profundo de múltiplos repositórios, com git-graph por objeto,
dashboards de progresso, análise de IA controlável e acessível também pelo
Telegram, respeitando os invariantes do projeto (a API é k8s-like, o repositório é
o estado, economia do recurso escasso, configuração visual schema-driven).

Esta decisão integra um conjunto de cinco ADRs nascidos do mesmo brainstorm:

| ADR | Decide | Relação com o Repo |
|---|---|---|
| 0020 | Views especializadas por Kind (o "quadro branco" genérico) | fornece o **slot de render** que o Repo ocupa |
| 0021 | Renomeação Rotina → **Job** | terminologia ("jobs de repo") |
| 0022 | Motor de IA selecionável e plugável (incl. Ollama/Gemma local) | motor que o `Agente` usa |
| **0023** | **(este)** Especialização do Kind Repo | — |
| 0024 | Kind `Agente` (analisador configurável: motor + contexto + prompt + política) | é **referenciado** pela `analyze_policy` |

Este ADR decide **apenas o domínio Repo**. O mecanismo de render é do ADR-0020, o
motor plugável é do ADR-0022 e o analisador configurável é do ADR-0024. Princípios e
decisões afetadas: [`principios`](../../visao/principios.md) e os ADRs
[0015](ADR-0015-core-api-de-objetos.md), [0016](ADR-0016-ia-plugavel-kind-prompt.md),
[0017](ADR-0017-gui-por-kind-abstrai-api.md), [0019](ADR-0019-interfaces-clientes-da-api.md).

## Decisão

> **Resumo.** O Repo deixa de ser um único objeto raso e passa a ser um **agregado
> de cinco Kinds** (`Repo` + `Branch`/`Commit`/`Diff` ocultos + `Doc`), ligados por
> label `repo=<label>`. O pull vira **multi-branch** e materializa um grafo leve no
> store (git-graph offline); o detalhe pesado (`Diff`) e a análise de IA ficam **sob
> demanda/política**. Configuração 100% visual (schema-driven); render própria no
> quadro branco; Telegram como pool de notificações e ações stateful.

### 1. Modelo de dados — cinco Kinds agregados por label `repo=<label>`

Tudo é `Resource` (k8s-like, [ADR-0015](ADR-0015-core-api-de-objetos.md)). A relação
entre objetos é feita por **labels** (`repo`, `branch`, `commit`, `tipo`), nunca por
chaves embutidas.

| Kind | Visibilidade | Papel |
|---|---|---|
| **Repo** | visível (topo) | Agregado/índice. `spec` = configuração (§2); `status` = ponteiros + métricas-resumo (branch default, HEAD por branch, totais, `last_sync`). |
| **Branch** | **oculto** | Uma branch remota. `status`: head, ahead/behind vs default, contagem de commits, `last_activity`, `stale`, métricas de atividade. |
| **Commit** | **oculto** | Resumo **leve** de um commit (parte materializada do híbrido). `spec`: sha, subject, author, date, `parents`, branch(es), stat. **Sem** `diff_raw`. |
| **Diff** | **oculto** | Detalhe **pesado** por commit (já existe): `diff_raw` + explicação de IA. Criado sob `analyze_policy` ou sob demanda — não para todo commit. |
| **Doc** | visível (topo) | Já existe: contexto do projeto + documentos serializados + arquivo por commit. Rotulado `repo=<label>`. |

**Relações (tudo por label):**

```
Repo/<label>                          visível · agregado/índice
  └── repo=<label>
        ├── Branch/<label>-<branch>   oculto · 1 por branch remota
        ├── Commit/<label>-<sha7>     oculto · resumo leve; spec.parents reconstrói o grafo
        ├── Diff/<label>-<sha7>       oculto · pesado; só sob analyze_policy/demanda
        └── Doc/<label>-…             visível · contexto, serializados, por-commit
```

**Exemplo (ilustrativo):**

```yaml
kind: Branch
name: nora-feat-x
labels: { repo: nora, branch: feat/x }
status: { head: 1a2b3c4, ahead: 12, behind: 3, commits: 40, stale: false }
---
kind: Commit
name: nora-1a2b3c4
labels: { repo: nora, branch: feat/x, commit: 1a2b3c4 }
spec: { sha: 1a2b3c4, subject: "refactor store", author: "...", parents: [9f8e7d6], stat: { files: 5, ins: 120, del: 40 } }
```

**Kinds ocultos.** `Branch`, `Commit` e `Diff` são objetos de primeira classe na API
(CRUD/list/describe normais), mas marcados como `hidden: true` no schema para **não
poluírem** o explorer ao lado de Kinds rotineiros (Tracker, Timer). A UI só os exibe
**aninhados** dentro da render do Repo. O atributo de visibilidade é genérico e
alimenta o ADR-0020.

### 2. Configuração do Repo — 100% schema-driven (blocos visuais)

Toda configuração é feita por **bloquinhos visuais** dirigidos pelo schema
(`_KIND_SCHEMA` em [api_schema.py](../../../src/atlas/api_schema.py)), servidos por
`GET /_schema` — **nunca** escrevendo manifesto cru. Reforça
[ADR-0017](ADR-0017-gui-por-kind-abstrai-api.md): zero lógica de negócio no front; o
front é abstração fiel da API. Campos de `Repo.spec`:

| Campo | O que define |
|---|---|
| `url` | Endereço do repositório (texto). |
| `branches` | Descoberta: **todas as remotas** (default) + globs de exclusão opcionais. |
| `serialize` | Preset de serialização incremental (ver abaixo). |
| `analyze` | Referência a um `Agente` (ADR-0024) + `analyze_policy`. |
| `goal` | Label de um `Goal` opcional → alimenta "progresso vs. meta". |
| existentes | `context_ttl_days`, tetos de corpus/diff. |

**Presets de `serialize`** (atuam só sobre arquivos **que mudaram** no pull — ver §3):

- `off` — não serializa.
- `docs` — documentação textual/binária (ex.: `.md`, `.docx`, `.pptx`, `.odt`, `.pdf`).
- `docs+code` — acima + fontes de código (ex.: `.py`, `.c`, `.ts`, …).
- `+` globs extra por repo. **Nunca** serializa binários compilados (sem valor textual).

**`analyze_policy`** (quando a fase de IA roda — ilustrativo):

```yaml
analyze:
  agente: revisor-padrao        # ADR-0024
  policy:
    branches: { default: auto, outras: manual }   # ou allowlist
    pular_merges: true
    min_lines: 20
```

### 3. Pipeline do pull (multi-branch, híbrido)

Respeita o contrato `collect` ([ADR-0004](ADR-0004-contrato-collect.md)): **collect
não usa IA**; a análise é fase separada e barata por padrão.

**collect (0 IA), por branch:**
1. `fetch` de **todas as branches remotas** (`+refs/heads/*:refs/remotes/origin/*`).
2. Detecta commits novos desde o head materializado de cada branch.
3. Materializa/atualiza `Branch` (head, ahead/behind, contagens, `last_activity`, `stale`).
4. Materializa `Commit` **leve** dos novos (sha, subject, author, date, `parents`, stat).
5. **Serializa** os arquivos alterados conforme o preset `serialize` (§2) → `Doc`.
6. Atualiza `Repo.status` (ponteiros + métricas-resumo).

**analyze (IA, sob `analyze_policy` + `Agente`):** para commits/branches que casam a
política (§2), monta o `Diff` **pesado** e roda o `Agente` (ADR-0024) com o nível de
contexto regulado → `Diff.explicacao` + `Doc` arquivado.

**deliver (0 IA):** monta as mensagens ricas por branch (referenciando o `Doc`) e
alimenta o digest (§6).

**Híbrido (git-graph).** O grafo é reconstruído de `Commit.parents` + ponteiros de
`Branch` lidos **do store** — funciona offline, coerente com "o repositório é o
estado". O `Diff` pesado é puxado **sob demanda** quando o usuário abre um commit.

### 4. Backfill de repos existentes

Ação `repo backfill <label>` (botão no web + comando no Telegram/`atlasctl`): faz
`git fetch --unshallow`, varre o histórico completo de todas as branches e
materializa `Branch`/`Commit` **leves** retroativos. É **idempotente** (pula shas já
materializados) e **0 IA por padrão** — `Diff`/análise retroativos só sob política
explícita ou sob demanda. Permite reconstruir todo o progresso de um repositório que
já existia antes desta decisão.

### 5. Render do Repo no quadro branco (front da API, modularizado)

O **mecanismo** do quadro branco (slot de render por Kind, kinds ocultos/aninhados,
aba dedicada) é do ADR-0020. Este ADR entrega o **conteúdo da render do Repo**, que
pluga nesse slot e é **priorizado** como o carro-chefe:

- **Aba "Repos"** (multi-repo) com **dashboards de progresso** lidos do store, em
  quatro eixos: *atividade temporal* (heatmap/série de commits, +/−), *vs. meta*
  (avanço rumo ao `Goal`), *saúde/qualidade* (riscos/sugestões abertas, hotspots),
  *estado das branches* (ativas/stale, ahead/behind).
- **Sub-view por Repo:** **git-graph** de todas as branches (de `Commit.parents` +
  ponteiros de `Branch`); clicar num nó abre o `Commit` e puxa o `Diff` sob demanda.
  Timeline por branch com a análise do `Agente` quando existe; contexto do projeto e
  documentos serializados.
- **Ações** (botões que só chamam a API): ▶ sync · 🧠 analisar branch/commit · ⟲
  regenerar contexto · ⏬ backfill.
- **Modularização:** o front embutido é quebrado em módulos por responsabilidade
  (ex.: `dashboard/kinds/repo/{graph,progress,branches,commit}`), continua servido
  pela API mas organizado; cada Kind registra sua render.

### 6. Telegram — pool de notificações + interação stateful

O Telegram é, principalmente, um **pool de notificações para acompanhar o sistema** e
**comandos simples**; operações complexas vivem no `atlasctl`/`_cmd` (caminho de
poder/legado/debug). Ele **pode** chamar IA, mas **sempre stateful, contextualizado e
opt-in** — nunca IA implícita por mensagem. Para o Repo:

- **Notificações ricas (pool):** card por branch com atividade, carregando a análise
  **já computada** no job (a mensagem não dispara IA).
- **Prompts stateful opt-in:** ex. "nova branch `feat/x` com 40 commits — quer que eu
  analise? responda **sim**" → o bot aguarda e dispara o verbo (a IA roda no job).
- **Comandos simples (0 IA):** listar repos, status/progresso, último diff de uma
  branch — leitura do store.
- **Digest periódico (0 IA):** consolidado multi-repo num card (o que andou, branches
  ativas/stale, riscos abertos).
- **Complexo → `atlasctl`:** backfill com flags, edição fina de `analyze_policy`.

Coerente com [ADR-0019](ADR-0019-interfaces-clientes-da-api.md): Telegram e web chamam
os mesmos verbos da API.

## Alternativas consideradas

| Alternativa | Prós | Contras | Veredito |
|---|---|---|---|
| **B — Novos Kinds `Branch`/`Commit` ocultos + híbrido** | tudo é resource consultável; git-graph/progresso/Telegram offline; cada Kind ganha render no quadro branco; custo de IA sob política | +2 Kinds para manter (schema + ações + render) | **escolhida** |
| A — Estender só os Kinds atuais; `Repo.status` carrega o grafo | mínima mudança; reusa tudo | `status` vira JSON gigante; git-graph/progresso espremidos; consultar "branches stale" exige varrer | não escala p/ multi-branch |
| C — Agregado único enriquecido (só `Repo`; diffs sob demanda do clone) | simples de listar | documento pesado; escrita concorrente no pull; sem granularidade | granularidade insuficiente |
| Git-graph renderizado do clone sob demanda | menos armazenamento | depende do clone; não serve Telegram offline; re-deriva sempre | viola "repositório é o estado" |
| Análise automática em todas as branches | simples | custo de IA explode em repos movimentados | quebra a economia do recurso escasso |

## Consequências

- **Positivas:** progresso multi-repo rastreável pelo store local (offline, k8s-like);
  git-graph multi-branch e dashboards sem re-derivar; serialização amplia o que a IA
  enxerga; custo de IA sob `analyze_policy` + `Agente`; configuração visual sem
  manifesto cru; backfill recupera repos antigos; o Repo vira a render-referência do
  quadro branco.
- **Negativas / custos:** +2 Kinds (`Branch`, `Commit`) a manter; pull multi-branch
  escreve mais no store; backfill com `--unshallow` puxa histórico grande; a
  experiência completa depende dos ADRs 0020/0022/0024 (mas degrada de forma útil sem
  eles).
- **Impacto na constituição:** nenhuma decisão anterior muda; **reforça** "o
  repositório é o estado", "agnóstico e plugável" e "economia do recurso escasso". A
  terminologia "job" depende do ADR-0021.

## Pendências

- **Dependências:** ADR-0020 (slot de render + atributo `hidden`), ADR-0022 (motor
  plugável) e ADR-0024 (Kind `Agente`) precisam ser aceitos para a experiência
  completa. Até lá, o Repo materializa dados e degrada a render/análise.
- **Spec de implementação:** desdobra-se em duas specs — (a) dados/pull (Kinds,
  materialização, serialização, backfill) e (b) front/git-graph (render, dashboards,
  modularização). A decompor com a skill writing-plans.
- **`analyze_policy`:** defaults exatos (default=auto, demais=manual, pular merges,
  `min_lines`) a validar empiricamente.
- **Backfill pesado:** estratégia de paginação/limite para histórico muito grande a
  verificar em campo.
- **Extração de texto:** biblioteca de serialização (docx/pdf/pptx) a escolher na
  spec, respeitando "script-primeiro".
- **Agente Builder** (prompt → configura o Kind nos conformes do projeto → curadoria):
  capturado no backlog como evolução do ADR-0024; não bloqueia este ADR.
