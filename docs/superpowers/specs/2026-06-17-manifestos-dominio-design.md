---
titulo: Design — Manifestos de domínio + loader `apply -f`
id: SPEC-MANIFESTOS-DOMINIO
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-17
---

# Design — Manifestos de domínio + loader `apply -f`

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-17 | Tech Lead | Criação (brainstorming) | PO/PM |

---

> **Sub-projeto 1 de 2.** O sub-projeto 2 ("web como interface cliente da API" +
> deploy Vercel + ADR amplo "interfaces são clientes da API") tem spec própria,
> em ciclo seguinte. Esta spec **não** toca a web.

## Objetivo

Tornar a plataforma imediatamente usável entregando **objetos de domínio
declarativos** para três grupos — **academia**, **saúde**, **produtividade** —
reusando exclusivamente kinds existentes (`Tracker`, `Goal`, `Timer`, `Task`,
`Routine`) e o agrupamento por `labels.grupo` que a rotina
[`coletar-por-label`](../../../src/atlas/rotinas/coletar_por_label.py) já consome.

A entrega introduz um mecanismo de **manifesto declarativo** (`apply -f`) que
trata a si mesmo como **mais uma interface cliente da API HTTP** — sem lógica de
negócio no loader, honrando a fronteira núcleo↔interface (ADR-0015, ADR-0017).

## Princípios aplicados
- **P2 (script-primeiro)** e **P3 (agnóstico/plugável)**: o loader só traduz
  arquivo→verbos existentes; o motor não ganha conhecimento de domínio.
- **P4 (o repositório é o estado)**: rotinas de check-in vivem como
  `routines/<nome>/routine.toml`, lidas pelo scheduler.
- **P7 (simplicidade/YAGNI)**: nenhum kind novo; nenhum endpoint novo.
- **P9 (rastreável e reversível)**: decisão registrada em ADR; rotinas nascem
  **inativas**.

## Decisões fechadas (brainstorming)
1. **Ordem:** manifestos primeiro; migração web é sub-projeto 2.
2. **Mecanismo:** arquivos declarativos + loader `apply -f`.
3. **Profundidade:** catálogo completo + uma `Routine` de check-in por grupo.
4. **Loader:** CLI Python `atlas apply -f`, cliente HTTP da API (não escreve no
   store direto — preserva a fronteira interface↔núcleo).
5. **Formato:** YAML multi-doc no shape K8s (`{kind, name, labels, spec,
   status}`), o mesmo do editor de manifesto da web. Introduz a **primeira
   dependência** do projeto (PyYAML) — decisão consciente do PO, justificada em
   ADR.

---

## Componentes

### 1. Artefatos de manifesto — `manifests/`
YAML multi-doc; um Resource por documento (`---`). Todos com
`metadata.labels.grupo = <grupo>`.

#### `manifests/academia.yaml` (`grupo=academia`)
| Kind/name | spec |
|---|---|
| `Tracker/peso` | `unit=kg, type=number, syntax="peso:", aggregation=last` |
| `Tracker/treino` | `type=text, syntax="treino:"` (entry textual do treino) |
| `Goal/peso-alvo` | `target=<n>, unit=kg` |

#### `manifests/saude.yaml` (`grupo=saude`)
| Kind/name | spec |
|---|---|
| `Tracker/agua` | `unit=copos, type=count, syntax="agua:", aggregation=sum` |
| `Tracker/sono` | `unit=h, type=duration, syntax="sono:", aggregation=mean` |

#### `manifests/produtividade.yaml` (`grupo=produtividade`)
| Kind/name | spec |
|---|---|
| `Tracker/estudo` | `unit=h, type=duration, syntax="estudo:", aggregation=sum` |
| `Timer/foco` | timer de foco (pomodoro); ações start/stop já existentes |

> **Task manager:** o kind `Task` já existe (`/task`). Documenta-se a convenção
> `labels.grupo=produtividade` para que as tasks apareçam no grupo; **não** há
> objeto seed (YAGNI — tasks são criadas pelo usuário).

Campos obrigatórios de spec por kind seguem [kinds.md](../../arquitetura/kinds.md).

### 2. Rotinas de check-in — `routines/check-<grupo>/routine.toml`
Três pastas novas (`check-academia`, `check-saude`, `check-produtividade`).
Cada `routine.toml`:
```toml
nome      = "check-<grupo>"
descricao = "Check-in diário do grupo <grupo>."
label     = "<grupo>"
coletar   = "coletar-por-label"
agenda    = "0 20 * * *"   # ajustável pelo usuário
modelo    = "none"
saida     = "telegram"
ativa     = false          # P9: inativa por padrão; liga com /ativar
```
Reusa 100% `coletar_por_label.py`. Zero código novo de rotina.

### 3. Loader — `atlas apply -f` (`src/atlas/apply.py` + subcomando em `__main__`)
```
atlas apply -f <arquivo.yaml> [--api-url URL] [--token T] [--dry-run]
```
- **URL default:** `http://127.0.0.1:8080` (porto da API, `ATLAS_API_PORT`; ou
  `ATLAS_API_URL`); **token:**
  `--token` ou `ATLAS_API_TOKEN`.
- Lê YAML multi-doc → lista de manifestos. Para cada um:
  `PUT {api-url}/apis/atlas/v1/<kind>/<name>` com corpo `{"labels":…, "spec":…}`
  e header `Authorization: Bearer <token>` (quando houver).
- **Idempotente:** `PUT` já é upsert no store; reaplicar é seguro.
- **`--dry-run`:** valida e imprime o que faria, sem nenhuma chamada HTTP.
- **Sem lógica de negócio:** só traduz arquivo→verbo existente.
- HTTP via `urllib.request` (stdlib) — só o parse de YAML usa PyYAML.

### 4. Dependência + documentação
- `pyproject.toml`: `dependencies = ["pyyaml>=6"]` (primeira dep).
- **ADR-0018** — "Manifestos declarativos e `apply -f` (interface como cliente da
  API)": registra o loader, a fronteira interface↔núcleo e a justificativa da 1ª
  dependência. (O ADR amplo "todas as interfaces são clientes da API", para
  web/Android, fica para o sub-projeto 2.)
- `docs/specs/manifestos.md`: formato do manifesto, uso do loader, exemplos.
- `docs/arquitetura/kinds.md`: nota sobre manifestos declarativos + grupos seed
  (header + histórico de revisão atualizados).

---

## Fluxo de dados
```
manifests/academia.yaml
   │  atlas apply -f
   ▼
[loader: parse YAML → dicts]  ── PUT /apis/atlas/v1/Tracker/peso ─▶ API HTTP
                                                                     │ _store.apply
                                                                     ▼
                                                              resources (store)
                                                                     ▲
            scheduler ─▶ routine check-academia ─▶ coletar-por-label ┘
                         (lê Tracker/Goal com labels.grupo=academia)
```

## Tratamento de erro (ADR-0006)
| Caso | Comportamento |
|---|---|
| API fora do ar / conexão recusada | erro claro com a URL tentada; exit ≠0 |
| 401 (token inválido/ausente) | mensagem orientando `--token`/`ATLAS_API_TOKEN`; exit ≠0 |
| manifesto sem `kind` ou `name` | erro de validação apontando o documento; nada é enviado |
| YAML malformado | erro de parse com o arquivo; nada é enviado |
| falha num objeto (ex.: 500) | reporta o objeto, **continua** os demais; exit ≠0 ao final |

## Testes (TDD — escrever primeiro)
**Loader (`apply.py`):**
- parse de YAML multi-doc → N manifestos (separados por `---`).
- monta `PUT` correto por objeto (URL/kind/name/corpo) — HTTP mockado.
- inclui header `Authorization: Bearer` quando há token; omite quando não há.
- erro de validação se falta `kind`/`name` (não chama HTTP).
- `--dry-run` não realiza nenhuma chamada HTTP.
- falha parcial: um objeto falha, os outros seguem; retorno final ≠0.

**Manifestos (conteúdo):**
- carregar os 3 arquivos e validar campos obrigatórios de spec por kind
  (`Tracker`: `unit`/`type`/`syntax`/`aggregation` conforme o tipo; `Goal`:
  `target`/`unit`).
- todos os objetos carregam `labels.grupo` consistente com o arquivo.

**Rotinas:**
- as 3 `routine.toml` carregam pelo loader de rotinas existente com
  `coletar="coletar-por-label"`, `label` correto e `ativa=false`.

## Fora de escopo
- Qualquer mudança na interface web ou no `api.py` (sub-projeto 2).
- Endpoint de `apply -f` no servidor (o loader é cliente; usa o `PUT` existente).
- Seletor de labels avançado, novos kinds, AuthN/Z.
- Ativar as rotinas automaticamente (P9 — ação humana via `/ativar`).

## Definição de pronto (DoD)
- `manifests/{academia,saude,produtividade}.yaml` válidos e testados.
- `routines/check-{academia,saude,produtividade}/routine.toml` carregáveis,
  `ativa=false`.
- `src/atlas/apply.py` + subcomando `apply` no `__main__`, com testes verdes.
- `pyproject.toml` com `pyyaml>=6`.
- ADR-0018, `docs/specs/manifestos.md` e nota em `kinds.md` escritos.
- Suíte verde, lint limpo, bot em produção intacto (nada legado tocado).
