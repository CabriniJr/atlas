---
titulo: ADR-0044 — Qualidade e auto mode do Agente modo `code` via Ollama
id: ADR-0044
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-02
substitui: —
substituido-por: —
---

# ADR-0044 — Qualidade e auto mode do Agente modo `code` via Ollama

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-07-02 | Tech Lead | Proposta + implementação (pedido do PO — fechar as pendências do ADR-0042) | PO/PM |
| 1.1    | 2026-07-02 | Tech Lead | Correção de rumo: dispatch do modo code vai no **terminal global existente** (`/code`), não numa aba nova do Kind Agente — ver decisão 6 | PO/PM |

---

## Status
`aceito` — implementado.

## Contexto

O ADR-0042 entregou o motor de desenvolvimento via Ollama, mas com pendências
explícitas: catálogo de tools mais pobre que o Claude Code (sem busca real) e
sem as diretrizes do projeto (CLAUDE.md) no system prompt — o `claude` CLI as
lê sozinho por rodar na raiz do repo; o loop nativo (`agente_ollama.py`) não. O
PO pediu explicitamente: "preciso conseguir despachar os devs e editar com
qualidade como fazemos em sessões claude code, mas full ollama para o
desenvolvimento não parar quando o seu [Claude] limite acabar" — e reforçou:
"auto mode também é super importante" (o run não pode travar/parar sozinho) e
"tem que ter [a] capacidade de commitar, reiniciar a instância pra ir se
atualizando".

Considerou-se integrar um CLI agêntico de terceiros ("openclaw") — avaliado e
**rejeitado**: é um assistente pessoal multi-canal (WhatsApp/Telegram/Discord/
etc.), não uma ferramenta de código; tools são browser/cron/mensageria, não
read/write/edit/grep; suporte a tool-calling nativo do Ollama não é claro.
Traria uma superfície enorme e não relacionada só pra emprestar um loop de
agente não comprovado contra Ollama — mantém-se o loop nativo do ADR-0042.

## Decisão

1. **Busca real no workspace** — `search_text` (regex linha-a-linha,
   equivalente ao Grep) e `find_files` (glob de nome, equivalente ao Glob),
   ambos ignorando `.git`/`.venv`/`__pycache__`/etc., truncados em 200
   resultados. Fecha a pendência "tools mais ricas" do ADR-0042.
2. **Diretrizes do projeto injetadas** — `api._claude_md_context()` lê
   `CLAUDE.md` da raiz (cacheado por mtime — não relê a cada run) e é
   concatenado ao system prompt de **todo** run modo=code (claude e ollama),
   antes do `_agent_api_context`. Antes só o claude CLI via essas regras
   (por rodar dentro do repo); agora os dois motores seguem TDD/conventional
   commits/ADR-first igualmente.
3. **Teto de turnos configurável** — `Agente.spec.max_turnos` (schema, default
   40 = `agente_ollama.TURNOS_MAX_PADRAO`) evita que uma tarefa mais longa seja
   cortada prematuramente; auto mode = o run não para sozinho antes da hora.
   Continua **não-fatal**: ao esgotar o teto, emite `warning` + `done` (nunca
   `error`) — mesma filosofia do ADR-0042.
4. **`POST /_self_restart`** (admin-only) — permite o próprio ciclo de
   desenvolvimento (commit → reiniciar → validar) sem depender de um humano
   rodando `systemctl` manualmente. Deliberadamente **via API** (P11 — "use a
   API pra tudo", não abre uma exceção de shell direto pro agente): o agente
   comita com `run_command` (`git commit`/`git push`, já coberto pelas
   diretrizes do CLAUDE.md) e chama esse endpoint pra recarregar o código
   novo. Dispara `systemctl --user restart <serviço>` **destacado**
   (`start_new_session=True`) via `threading.Timer` (default 0.3s) — tempo
   pra resposta HTTP sair antes do processo atual morrer. Isso substitui, só
   pro processo **local** (dev, sem CD/timer), o texto antigo de `debug.py`
   ("lifecycle fica host-side, o bot não gerencia o próprio container") — a
   premissa de container não se aplica aqui (é `systemd --user`, não docker);
   a Rasp continua servida pelo `atlas-deploy.timer` (ADR não numerado, E7-43),
   que já resolve o mesmo problema puxando `main` via git.
5. **UI: aba 🤖 Auto** no Kind `Agente` (dashboard) — visibilidade pedida no
   ADR-0042 ("UI rica... erros simples não me travarem"): mostra motor real
   resolvido, modelo, teto de turnos, gate de curadoria, workspace confinado,
   tools permitidas/negadas e confirma que as diretrizes do CLAUDE.md estão
   injetadas — sem precisar abrir o Config genérico ou inspecionar a API.
6. **Dispatch pelo terminal global existente, não numa aba nova** (correção
   de rumo pedida pelo PO: "a CLI não é tab, a UI da API já tem um terminal, é
   nele que vai rodar esse builder e a UX precisa ser o mais semelhante
   possível com o Claude Code CLI"). O terminal (`#cli-bar`/`#cli-output`,
   `main.js`) ganha um modo: `/code [agente]` (default `atlas-builder`) entra
   em modo dev — o prompt vira `🤖<agente>$`, e daí em diante **texto livre
   sem `/`** é enviado direto pro agente via `POST /_agent_run`, com o stream
   de eventos renderizado inline reusando `_appendCodeEventToEl`/
   `_appendCodeLog` (mesmas funções/classes CSS da aba Chat do Kind Agente —
   zero duplicação de lógica de render). `/exit` volta ao modo comando normal.
   **Fila client-side:** tarefas digitadas com um run já em andamento entram
   numa fila FIFO (`_cliCode.queue`) em vez de serem recusadas — drena
   automaticamente a cada run concluído. Concorrência real (várias tarefas
   *em paralelo*, não só enfileiradas) é responsabilidade do servidor (teto
   `ATLAS_AGENT_MAX_CONCURRENT`, ADR-0028 §3) — pendência do PO ("vou
   preparar [o server] para tratar em paralelo").

## Alternativas consideradas

| Alternativa | Prós | Contras | Veredito |
|---|---|---|---|
| **Integrar CLI de terceiros ("openclaw")** | tools potencialmente mais ricas de fábrica | não é ferramenta de código (é assistente multi-canal); compatibilidade Ollama não comprovada; superfície de risco enorme (browser/cron/mensageria) só pra emprestar um loop | rejeitada |
| **`run_command` chamando `systemctl` direto** (sem endpoint dedicado) | zero código novo | contraria P11 (usar a API pra ações, não shell solto); sem controle central de quem pode disparar restart | rejeitada |
| **Self-restart via endpoint dedicado admin-only** | centraliza e audita a ação mais destrutiva do sistema; reusa o padrão de auth já existente | ainda mata o processo (aceito — é o próprio pedido) | **escolhida** |
| CLAUDE.md relido a cada run (sem cache) | mais simples | reabre o arquivo em disco em todo turno; a diretriz de "cache" do PO pede o oposto | rejeitada |

## Consequências

- **Positivas:** loop via Ollama fica funcionalmente mais próximo de uma
  sessão Claude Code real (busca, diretrizes, teto de turnos configurável);
  ciclo commit→restart→validar não depende mais de um humano no terminal;
  visibilidade operacional (aba Auto) sem precisar ler a API/config crua.
- **Negativas / custos:** `/_self_restart` é destrutivo por natureza — mata o
  processo que atende a própria request (mitigado: admin-only + delay pra
  resposta sair). Catálogo de tools ainda não tem subagentes/Task nem Grep com
  todos os flags do real (fica pendência, ver abaixo).
- **Impacto na constituição:** estende ADR-0042 (fecha pendências), ADR-0028
  (mesmo padrão admin-only de endpoints sensíveis) e P11 (ação de lifecycle
  também vira endpoint da API, não shell ad-hoc). Nenhuma decisão anterior é
  revertida; o texto de `debug.py` sobre "não gerenciar o próprio container"
  é superado só para o caso systemd local — mantém-se correto para deploy
  containerizado, se algum dia usado.

## Pendências
- Subagentes/Task no loop nativo (delegação recursiva) — ainda não existe.
- `/_self_restart` na Rasp: hoje só faz sentido local (a Rasp já se atualiza
  sozinha via `atlas-deploy.timer`); reavaliar se um dia o CD virar API-driven.
- `search_text`/`find_files` são full-scan (sem índice) — se o repo crescer
  muito, considerar um índice incremental.
- Fila do `/code` no terminal é FIFO client-side (uma tarefa por vez visível);
  concorrência real de runs no servidor é trabalho do PO (`ATLAS_AGENT_MAX_CONCURRENT`,
  ADR-0028 §3) — reavaliar a UX de fila quando o server tratar runs em paralelo.
- Sem cancelamento/interrupção de um run em andamento a partir do terminal
  (equivalente a Ctrl+C no Claude Code CLI) — não implementado ainda.
