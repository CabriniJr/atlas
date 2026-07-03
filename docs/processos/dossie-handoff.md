---
titulo: Dossiê de handoff — estado atual e como continuar
id: PROC-HANDOFF
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-03
---

# Dossiê de handoff — estado atual e como continuar

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-26 | Tech Lead | Criação — handoff do trabalho recente (E7-24..44, ADR-0025/0026/0027) p/ outro agente | — |
| 1.1    | 2026-06-26 | Tech Lead | Épico multiusuário (ADR-0027) concluído e mergeado em `main` (Fases 1–5 + UI); estado/branches/testes atualizados | — |
| 1.2    | 2026-06-26 | Tech Lead | E7-28 em curso (ADR-0028): workspace restrito + allow/deny de tools + teto de concorrência + flag de gate | — |
| 1.3    | 2026-07-01 | Tech Lead | Épico E9 (tradutor editorial): fixes de store/resume + export md/epub; ADR-0033 + spec + plano do render editorial; E9-01 tarefas 1–4 feitas | — |
| 1.4    | 2026-07-02 | Tech Lead | E9-01..E9-12 concluídos (render editorial HTML/WeasyPrint, TOC/hyperlinks/folio, fallback claude↔ollama). Nova frente **E9-13** (ADR-0041, fidelidade tipográfica + paginação adaptativa) iniciada — 2/12 tarefas feitas | — |
| 1.5    | 2026-07-02 | Tech Lead | **Agente modo `code` via Ollama nativo** (ADR-0042/E7-45, pedido do PO, prioridade máxima) e **recuperação de órfãos no boot + serialização de chamadas Ollama** (ADR-0043/E9-14) — ambos commitados em `main`; não fazem parte do E9-13 | — |
| 1.6    | 2026-07-02 | Tech Lead | **Qualidade/auto mode do Agente via Ollama** (ADR-0044/E7-46): grep/glob reais, CLAUDE.md injetado, `max_turnos`, `POST /_self_restart`, aba 🤖 Auto. `atlas-builder` passou a usar `provider=ollama-local` (gemma4) | — |
| 1.7    | 2026-07-02 | Tech Lead | Instância caiu (crash-loop, WIP quebrado não commitado — revertido). Achado e corrigido: `ia.invocar` trocava de motor ollama→claude **às escondidas** na tradução, queimando cota do Claude; agora `fallback=False` na tradução (ADR-0045/E9-15). Ollama virou motor padrão; controle real (pausar/recomeçar/re-refinar) na UI de `Traducao` | — |
| 1.8    | 2026-07-03 | Tech Lead | **E9-13 concluído** (12/12 tarefas, ADR-0041). Nova frente **E9-15** (opção prévia bruto/IA na UI) feita. Achado + corrigido via amostragem visual real (Kubernetes/Observability/Prometheus): diagrama vetorial virando parágrafos soltos, prosa classificada como código, marcador `**` vazando em `<pre>`, caixa de destaque perdendo fundo/borda, link vazando pro parágrafo inteiro, **e página em branco espúria antes de quebra forçada de heading** (root-causado via bissecção de HTML real + corrigido) | — |
| 1.9    | 2026-07-03 | Tech Lead | Continuação da auditoria visual (Prometheus amostrado): **3 bugs reais** achados e corrigidos — nota de rodapé cortada ao virar página original (vazava como `<p>` solto), espaço espúrio entre tokens de código com syntax highlighting (`http . server` → `http.server`), marcador `**` vazando dentro de nota de rodapé (mesma causa do bug anterior, função esquecida). Um suspeito de bug (página com "Blackbox Exporter" gigante) investigado e **descartado** — era imagem raster de verdade (screenshot), não texto mal classificado | — |

---

## ⭐ Estado atual (2026-07-03) — E9-13 concluído + auditoria visual (9 bugs corrigidos)

**Contexto:** o PO revisou o render editorial (motor `render_motor=html`,
ADR-0036) e apontou perda de informação real: fonte genérica (não a do PDF),
ênfase inline (negrito/itálico no meio do parágrafo) descartada, cor de link
forçada em azul, listas numeradas perdidas, notas de rodapé nativas do original
em risco de serem descartadas junto com o fólio, numeração de página inventada
(não a do original) e quebra de página sem relação com o padrão do documento
original. Decisão registrada em [ADR-0041](../arquitetura/adr/ADR-0041-fidelidade-tipografica-e-paginacao-adaptativa.md)
+ seção "Fidelidade avançada" da [spec](../specs/traducao-render-editorial.md).
Backlog: [`roadmap/backlog.md` §E9-13](../roadmap/backlog.md#épico-tradutor-editorial).

**E9-01..E9-12 e E9-13 (12/12 tarefas) — feito e commitado em `main`.** O
[plano](../superpowers/plans/2026-07-02-fidelidade-editorial-avancada.md) está
inteiro com checkboxes `[x]`: fonte real embutida (`tipografia.extrair_fontes`
+ `@font-face`), ênfase inline (`**bold**`/`_italic_` → `<b>`/`<i>`), link herda
cor (sem azul forçado), listas `<ol>` + zero bloco descartado, nota de rodapé
nativa distinta do fólio, fólio dinâmico via `string-set` (número igual ao
original, escala sozinho no reflow), quebra de página por nível de heading
**extraída do documento** (clustering + taxa de abertura, não regra fixa).

**E9-15 — feito:** opção de renderizar prévia com MT bruta OU tradução
refinada por IA — dois botões na UI (`Prévia (IA)`/`Prévia (bruto)`),
`traduzir_pdf(..., preferir_bruto=True)`, zero custo de IA (usa só cache).

**Auditoria visual pós-E9-13 (pedido do PO: "compara renderizado com original,
lista os ajustes"; depois "implementa tudo"):** amostrando páginas reais dos 3
livros do PO (Kubernetes in Action, Observability Engineering, Prometheus Up &
Running) contra o render, achei e corrigi 9 bugs reais (2 descartados após
investigação), todos commitados:
1. **Diagrama vetorial virava lista de `<p>` soltos** (figuras com caixas/setas
   desenhadas via `page.get_drawings()`, não `page.get_images()`) —
   `_regioes_diagrama()`/`_renderizar_diagrama()` em `editorial_html.py`
   rasterizam a região inteira como imagem (commit `beb1472`).
2. **Prosa classificada como código** (bug real: `mycompany.com/foo` em fonte
   Courier dentro de um parágrafo de prosa fazia o BLOCO INTEIRO virar `<pre>`
   não traduzido) — `tipografia.bloco_e_mono()` unifica a decisão por MAIORIA
   de caracteres (não 1 span), usada em `extracao.py` E `editorial_html.py`
   (commit `5272e75`); isso também consertou o marcador `**` vazando pra
   dentro de código.
3. **Caixa de destaque (callout/tip) perdia fundo/borda** —
   `_regioes_destaque()` detecta forma com `fill` (preenchimento) que envolve
   prosa (>=6 palavras) e envolve em `<div class="destaque">` (commit
   `ff6d4a0`).
4. **Link vazando pro parágrafo inteiro** (uma URL de 1 linha dentro de um
   parágrafo de 5 linhas fazia o parágrafo inteiro virar `<a>` azul/sublinhado)
   — `_link_do_bloco()` agora exige >=50% de cobertura da área do bloco (commit
   `ff6d4a0`, mesmo commit do item 3).
5. **Investigado e descartado:** o traço "—" antes do fólio que parecia bug de
   classificação de texto é na verdade a régua CSS `border-top` intencional do
   `@bottom-left`/`@bottom-right` (não é bug — confirmado via grep no HTML
   gerado, nenhum `<p>` contém só um traço).

6. **Página quase vazia antes de quebra forçada de heading** — achada e
   **corrigida** (commit `754f8d5`). Root cause isolado bissectando o HTML real
   (sintético não reproduziu): o `<span style="string-set:...">` vazio do
   fólio, quando a página anterior já está 100% cheia, é empurrado sozinho pro
   WeasyPrint numa nova página — e a quebra forçada do heading seguinte
   empurra o conteúdo real por MAIS uma página, deixando uma página fantasma
   entre elas. Fix: `_injetar_string_set()` anexa a declaração `string-set` no
   PRIMEIRO elemento com conteúdo real da página (splice no `style="..."`),
   nunca um `<span>` vazio separado — elemento nunca fica "sozinho". Verificado
   no Observability Engineering completo: de ~12+ páginas quase-vazias
   esperadas caiu pra só 3 remanescentes, todas explicadas (capa + colofão do
   original, não o bug).

**Auditoria visual, rodada 2 (Prometheus Up & Running amostrado):**
7. **Nota de rodapé cortada ao virar página original** — uma nota que estoura
   pro TOPO da página original seguinte (fora da faixa de margem que
   `_e_rodape_nativo` reconhece) vazava como `<p>` solto no meio do corpo,
   cortando a frase ao meio. `_comeca_minuscula()` detecta a continuação
   (primeiro bloco útil da página começando com minúscula, quando a página
   anterior terminou em nota pendente) e gruda no final da nota; notas agora
   são deferidas (`pendente_notas`) e só "fecham" no início da próxima página
   (commit `c2196d7`).
8. **Espaço espúrio entre tokens de código** (`http . server . BaseHTTP...`
   em vez de `http.server.BaseHTTP...`) — código com destaque de sintaxe tem
   cada token/cor como span separado do PyMuPDF; `texto_plano` usava
   `" ".join(...)` cego entre TODOS os spans. `_juntar_spans()` decide por
   geometria (gap de bbox no eixo x, mesma linha) se insere espaço — spans
   tocando ficam colados (commit `1a2525f`).
9. **Marcador `**` vazando dentro de nota de rodapé** — `flush_notas()` usava
   `_e(t)` (escape puro) em vez de `converter_enfase(t, _e)`; mesma função já
   usada em parágrafos normais, só faltava aplicar em notas (commit `892d7f8`).
10. **Investigado e descartado:** uma página com "Blackbox Exporter" em fonte
    gigante + links azuis + tabela parecia texto mal classificado como
    heading — na verdade é uma imagem raster de verdade (screenshot de
    navegador, 106 imagens na página original), preservada corretamente.
    `get_text()` no PDF renderizado confirma: nenhum desses textos existe como
    texto real, só pixels da imagem.

**Como retomar:**
1. Ler [ADR-0041](../arquitetura/adr/ADR-0041-fidelidade-tipografica-e-paginacao-adaptativa.md)
   + seção "Fidelidade avançada" da [spec](../specs/traducao-render-editorial.md).
2. Os 3 livros do PO (Kubernetes in Action, Observability Engineering,
   Prometheus Up & Running) já foram amostrados nesta sessão (várias páginas
   de cada, tipos variados: início de capítulo, foto/diagrama, callout,
   lista, código). Se o PO trouxer mais páginas problemáticas, mesma técnica:
   `somente_render=True` a partir do cache (zero custo de IA), amostrar tipos
   variados, comparar pixmap do render vs. original lado a lado. Técnica de
   bissecção (fatiar `montar_html` de um range de páginas + testar direto no
   WeasyPrint, sem reprocessar o livro inteiro) provou ser essencial pra achar
   bugs de layout que só aparecem com conteúdo real longo — reusar se surgir
   outro caso parecido.
3. Trabalho é **direto em `main`**, sem worktree/branch (convenção deste repo,
   CLAUDE.md §0).
4. `handoff-auto.md` (gerado por `scripts/handoff-snapshot.sh`) traz o snapshot
   mecânico mais recente (commits, testes, checkboxes).

**Trabalho concorrente:** rodar `git status` antes de tocar em
`README.md`/`backlog.md`/qualquer arquivo compartilhado — outros processos
concorrentes (Dev Sonnet em paralelo) podem estar mexendo neles.

**Ambiente:** local via `python -m atlas` (env `ATLAS_DB_PATH=data/atlas.sqlite`,
`ATLAS_API_PORT=8080`) → `http://atlas.local:8080`. **Não reiniciado com o
código desta sessão ainda** — o PO pediu explicitamente pra NÃO reiniciar até
o render ficar bom; reinicie (`systemctl --user restart atlas.service`) só
quando o PO confirmar ou pedir.
**Pendência do PO:** `sudo dnf install -y pandoc` (botão EPUB). Sub-projetos B/C/D
(qualidade AI-augmented, Agente editor + judge, configs de qualidade) = E9-02..04.

---

> **Para quem assume o desenvolvimento.** Este é o ponto de entrada. Leia nesta
> ordem: (1) [`CLAUDE.md`](../../CLAUDE.md), (2) [`docs/visao/principios.md`](../visao/principios.md)
> (em especial **P11**), (3) os ADRs [0024](../arquitetura/adr/ADR-0024-kind-agente.md)/
> [0025](../arquitetura/adr/ADR-0025-agente-modo-code.md)/[0026](../arquitetura/adr/ADR-0026-llm-provider.md)/
> [0027](../arquitetura/adr/ADR-0027-multiusuario-credenciais.md), (4) este dossiê, (5)
> o [backlog](../roadmap/backlog.md) (épico E7 e fases do multiusuário).

## 1. Onde o desenvolvimento está

Trabalho recente (épico E7 — IDE/agente integrado + produção) e o épico
**multiusuário** (ADR-0027). **Tudo em `main`** (o CD da Rasp acompanha `main`):

| Entregue | O quê | ADR |
|---|---|---|
| Agente modo `code` | Claude Code agêntico dentro do app; `POST /_agent_run` + SSE `/_agent_run/{id}/stream`; `ThreadingHTTPServer`; runs em background (multitarefa) | ADR-0025 |
| Agente modo `code` via Ollama | Segundo motor 2b: loop de tool-calling nativo (`agente_ollama.py`) contra `POST /api/chat`; `_run_agent_bg` despacha por motor resolvido, fallback pro claude se o endpoint cair antes do 1º turno; erro de tool vira `warning` não-fatal; custo 0 | ADR-0042 |
| Agente segue a API | system-prompt injeta o schema vivo + seção de relações (P11); o agente cria recursos **pela API** | ADR-0025 |
| LLMProvider | Kind de config de IA; `Agente.provider` dita o modelo; `_resolve_engine` | ADR-0026 |
| Análise de repo por Agente | `Repo.spec.analyze_agente` (default `repo-analyzer`); insight manual + automático no sync | ADR-0024 §2 |
| Multirepo `RepoGroup` | dash manager: Visão \| 🎯 Objetivos (Goals×Trackers, barras) \| 🔍 Análises \| Config; "🔔 Sync diário" | — |
| Serialização snapshot | `/repo snapshot` serializa a árvore inteira → Doc; aba 📁 Files | — |
| Landing Hub | Home (Construir com IA + rastreio + quadro branco); Explorer/Graph/Status no menu ☰ Mais | — |
| Render de Job + aba Jobs no Repo | vínculo por **label** (`spec.label`), não por nome | — |
| Fix sync por label | `_resolve_repo_sync_job`; `POST /_run {repo}`; Jobs do store rodam (`_rotina_from_job`) | — |
| Tracking de gasto de IA | acumula `custo_total_usd`/`runs` no status do Agente quando evocado | — |
| CD na Rasp | `scripts/atlas-deploy.{sh,service,timer}` — pull main + restart a cada 5 min | — |
| Job schema unificado | `schedule`/`model`/`active` (era `agenda`/`modelo`/`ativa`) | — |
| **Multiusuário (completo)** | ADR-0027 — cofre cifrado, User/Credential, GitHub device flow, auth/sessão, isolamento por dono + UI de login | ADR-0027 |

**Sem branches de feature abertas** do multiusuário — Fases 1–5 + UI mergeadas em
`main` (PR #4 das Fases 1–2 + rebase das Fases 3–5/UI). O ADR-0027 está **aceito**.

## 2. Como rodar, testar e fazer deploy

**Dois ambientes** (ver [`RASP.md`](../../RASP.md)): local dev (`python -m atlas`,
`http://atlas.local:8080`) e Rasp pseudo-prod (`atlas.service` systemd user,
`http://atlas:8080`, DB em `data/atlas.sqlite`).

**Servidor local roda como serviço systemd** — após mudar código:
```bash
systemctl --user restart atlas.service
journalctl --user -u atlas -f
```

**Testes (gotcha resolvido):** a suíte roda com **qualquer Python** — `python -m
pytest` (sistema) **ou** `.venv/bin/pytest` (venv). O fixture `free_tcp_port` agora
é definido em [`tests/conftest.py`](../../tests/conftest.py) (não depende mais do
plugin do `anyio` no Python do sistema), e `pythonpath=["src","."]` no
`pyproject.toml` faz o `pytest` puro do CI achar `tests.repohelpers`.

```bash
.venv/bin/pytest -q                 # 526 testes, devem passar (igual ao CI)
.venv/bin/ruff check .              # repo inteiro, deve passar limpo
.venv/bin/ruff format --check .     # idem (CI também checa)
```

**CD (Rasp):** o timer `atlas-deploy.timer` puxa `main` e reinicia sozinho. Para
ir a produção: merge em `main` (o CD aplica em ≤5 min). Instalação do CD: ver RASP.md.

## 3. Arquitetura essencial (o que você precisa saber)

- **Tudo é objeto (P11).** API REST estilo K8s: `GET/PUT/DELETE /apis/atlas/v1/<Kind>/<name>`.
  Recursos se relacionam **por labels/selectors**, nunca por convenção de nome. Novo
  tipo de coisa = **novo Kind**. A fonte da verdade do store é o SQLite via `ResourceStore`.
- **Kinds atuais:** Tracker, Goal, Alarm, Job (ex-Routine), RepoGroup, Repo, Branch,
  Commit, Diff, Idea, Task, Doc, RoutineRequest, Timer, Prompt, LLMProvider, Agente.
  Schema (forms/ações) em [`src/atlas/api_schema.py`](../../src/atlas/api_schema.py).
- **Renders especializados** ("quadro branco", ADR-0020): `src/atlas/dashboard/kinds/*.js`
  registram via `registerRender('Kind', fn)`. Hoje: repo, repogroup, agente, job.
  O resto cai no editor genérico. Front é cliente da API (ADR-0019).
- **Motor de IA (ADR-0001/0022):** `claude` CLI via `src/atlas/ia.py`
  (`invocar`/`invocar_ollama`). 2a = análise single-turn; 2b = agente com tools
  (modo `code`, só Agentes marcados). `_resolve_engine(spec, store)` resolve
  motor/modelo/endpoint a partir do `LLMProvider` (ou campos do Agente).
- **Endpoints especiais** (em `api.py`, `do_POST`/`do_GET`): `/_run`, `/_cmd`,
  `/_chat`, `/_insight`, `/_agent_run` (+ `/stream`), `/_status`, `/_schema`, `/_complete`,
  `/_self_restart` (admin-only, ADR-0044 — reinício destacado do processo local),
  `/_traduzir_pausar`/`_recomecar`/`_rerefinar` (ADR-0045 — controle real do job
  de tradução em andamento).

## 4. O agente que constrói (atlas-builder)

`Agente/atlas-builder` (modo `code`, provider `claude-default`) é o "Claude Code"
dentro do app. Fluxo: `POST /_agent_run {agente, mensagem}` → roda
`claude -p --output-format stream-json --verbose --dangerously-skip-permissions
--add-dir <projeto> --append-system-prompt <prompt+contexto>` em background; eventos
via SSE. O system-prompt inclui `_agent_api_context(store)` (schema vivo + como criar
recursos via API + relações por label). **Risco de segurança:** escrita livre sob a
raiz do projeto — endurecer é E7-28 (workspace restrito, gate de curadoria).

## 5. Multiusuário — épico concluído (ADR-0027, aceito)

Decisões do PO: **isolamento total** por usuário; **Claude compartilhado** (host)
com custo por usuário; **GitHub via device flow**; **credenciais cifradas**. Todas as
fases + a UI estão em `main`.

| Fase | O quê | Estado |
|---|---|---|
| 1 | Cofre cifrado `secrets_store` (Fernet) | **feito** (em `main`) |
| 2 | Kinds `User` + `Credential` (metadados; segredo no cofre) | **feito** (em `main`) |
| 3 | GitHub device flow (start/poll → Credential cifrada + git helper escopado; fallback PAT) | **feito** (em `main`) |
| 4 | Auth/sessão (login por senha local + login via GitHub; cookie httpOnly; admin via token/loopback) | **feito** (em `main`) |
| 5 | Isolamento por `labels.owner` no store/API + migração | **feito** (em `main`) |
| 6 | UI multiusuário no front (login + Conectar GitHub + logout) | **feito** (em `main`) |

**Fase 1 entregue:** [`src/atlas/secrets_store.py`](../../src/atlas/secrets_store.py) —
`encrypt/decrypt`, `put/get/delete_secret`. Chave em `ATLAS_SECRET_KEY` ou
`secrets/secret.key` (0600). Segredo **nunca** no spec nem no front. Dep nova:
`cryptography` (no `pyproject.toml`). Testes: `tests/test_secrets_store.py`.

**Fase 3 entregue** (em `main`):
[`src/atlas/github_auth.py`](../../src/atlas/github_auth.py) — device flow
(`start_device_flow`/`poll_access_token`/`complete_device_login`), fallback PAT
(`connect_via_pat`), resolução de token (`token_for_owner`) e git helper escopado
(`git_auth_args` → `gitcmd.git(..., auth_args=...)`, sem persistir o token no
`.git/config`). Endpoints: `POST /_github/device/start`, `/_github/device/poll`,
`/_github/pat`. O repo-sync resolve o token do dono (`labels.owner`) e autentica
clone/fetch (`_auth_args_for_repo`). Config: `ATLAS_GITHUB_CLIENT_ID` (OAuth App);
sem ele, só o fallback de PAT funciona. HTTP é stdlib (`urllib`), injetável em teste.

**Fase 4 entregue** (em `main`):
[`users.py`](../../src/atlas/users.py) (senha local: PBKDF2 cifrado no cofre,
`create_user`/`verify_password`), [`sessions.py`](../../src/atlas/sessions.py)
(sessão em memória, token opaco + TTL) e a auth da API: `_identity()` resolve
`(user, role)` de **admin** (token/loopback) **ou** sessão (cookie `atlas_session`
httpOnly); `_auth()` exige um dos dois. Endpoints **públicos** (pré-gate):
`POST /_auth/login` (senha), `/_auth/logout`, `/_auth/github/start|poll` (login via
device flow — cria o `User`, salva a credencial e abre sessão), `GET /_auth/me`, e
`POST /_auth/users` (**admin** cria usuário + define senha — bootstrap do sistema).

**Fase 5 entregue** (em `main`):
[`scoping.py`](../../src/atlas/scoping.py) (políticas puras `can_see`/`can_write`/
`stamp_owner`/`visible` + `migrate_unowned`). A API escopa **list/get/put/delete**
pelo dono da sessão: o admin vê/altera tudo; o member só os seus recursos (recurso
alheio ⇒ **404**, não revela existência); `labels.scope=system` é global (read-only a
não-admin); no create, o dono é **carimbado** (member não escolhe). Migração no boot
([`app.py`](../../src/atlas/app.py)): recursos antigos sem dono vão para `ATLAS_DEFAULT_OWNER`
(default `admin`), idempotente. **Importante:** o isolamento roda na camada **HTTP**;
usos internos do store (sync, rotinas, scheduler) **não** são escopados.

**UI multiusuário no front (feito).** Tela de login ([index.html](../../src/atlas/dashboard/index.html)
+ [main.js](../../src/atlas/dashboard/main.js)): senha local, **Conectar com GitHub**
(device flow), e token de API como opção avançada (admin/script); chip de usuário +
logout no titlebar; botão **🔗 Conectar GitHub** (credencial p/ repo-sync do usuário
logado). `init()` checa `GET /_auth/me` e abre o login no 401. Local (loopback) segue
admin sem tela de login.

**Pendências do épico (não-bloqueantes, viram backlog):** ~~persistência de sessões~~
(feito, item 1.2); rotação/backup da chave mestra do cofre. Ver ADR-0027 §Pendências.

## 6. Convenções de trabalho (não-negociáveis)

- **Doc é o contrato.** Código que diverge da doc exige ADR (regra de ouro do CLAUDE.md).
- **Branch + PR + Conventional Commits.** Commits terminam com
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- **TDD ao implementar.** Atualize a doc junto com o código.
- **Toda decisão de arquitetura vira ADR** antes de virar código; atualize o
  [índice de ADRs](../arquitetura/adr/README.md) e o [backlog](../roadmap/backlog.md).
- **Nunca commitar segredos.** Tokens vão cifrados no cofre / `secrets/` (gitignored).

## 7. Pendências/known issues abertas

- **E7-28** — endurecer o modo `code`. **Feito** (ADR-0028, branch
  `feat/hardening-agente-code`): **workspace restrito**
  (`resolve_workspace` confina cwd/`--add-dir`, recusa traversal/symlink),
  **allow/deny de tools** (`build_tool_args` → `--allowedTools`/`--disallowedTools`,
  campos `allowed_tools`/`denied_tools` no schema), **teto de concorrência**
  (`active_runs_count` + `ATLAS_AGENT_MAX_CONCURRENT`, default 3 → 429), **gate**
  (`spec.gate`, carimbada no `init`), **persistência de runs**
  (`persist_agent_run` → Kind `AgentRun` escopado por `labels.owner`) e **UI de
  curadoria** ([curadoria.py](../../src/atlas/curadoria.py) + aba 🔍 Curadoria no
  Agente: diff → aprovar em branch `agent/<id>` / descartar; endpoints
  `GET/POST /_agent_run/{id}/diff|discard|approve` escopados por dono).
  **Limitações documentadas** (SPEC-CURADORIA): working tree compartilhada; `approve`
  no repo vivo da Rasp é dev-time.
- ~~**Sessões em memória**~~ — **resolvido** (item 1.2): `sessions.py` persiste em
  `sessions.json` (só o hash sha256 do token; escrita atômica; degrade em IO/arquivo
  corrompido) → sobrevivem a restart. Path: `ATLAS_SESSIONS_PATH` ou `<dir do DB>/sessions.json`.
- ~~**Chave mestra do cofre** — sem rotação/backup~~ — **resolvido** (item 1.4):
  `secrets_store.rotate_key()` + `scripts/rotate_secret_key.py` (re-cifra tudo,
  backup automático da chave antiga).
- ~~**UX de cadastro de usuários**~~ — **resolvido** (item 1.4b): **auto-registro com
  código** (`ATLAS_SIGNUP_CODE` habilita "criar conta" na tela de login;
  `POST /_auth/register`; papel sempre `member`). Convite individual por link e
  rate-limit de brute-force ficam em backlog (SPEC-AUTO-REGISTRO).

> Os **próximos passos priorizáveis** estão consolidados em
> [`docs/roadmap/proximos-passos.md`](../roadmap/proximos-passos.md).
