---
titulo: ADR-0025 — Agente modo code (Claude Code agêntico no workspace)
id: ADR-0025
status: proposto
versao: 0.1
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-23
substitui: —
substituido-por: —
---

# ADR-0025 — Agente modo `code` (Claude Code agêntico no workspace)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-06-23 | Tech Lead | Proposta — modo `code` no Kind Agente (go-horse, doc segue código) | — |

---

## Status
`proposto` — implementado em ritmo ágil; aguarda aceite do PO/PM. Justifica uma
divergência consciente da regra 4 do [ADR-0024](ADR-0024-kind-agente.md).

## Contexto

O [ADR-0024](ADR-0024-kind-agente.md) criou o Kind `Agente` e, na **regra 4**,
restringiu-o ao **modo análise 2a** (single-turn, sem tools, sem filesystem) —
explicitamente "**não** é o agente 2b com ferramentas do meta-loop". A render do
Agente (E7-25) entregou um chat 2a funcional.

O PO/PM, porém, pediu um agente com **poder de Claude Code dentro da aplicação**:
> "preciso que ele tenha poder de editar o projeto que nem você tem, seja um claude
> code" / "não quero criar os jobs na mão e sim ter um agente que cria os jobs".

Isso é, por definição, a **Camada 2b** do [ADR-0001](ADR-0001-ia-em-dois-modos.md):
Claude Code completo, com tools e escrita de arquivo. O ADR-0001 reservava a 2b a
**um único consumidor: o meta-loop**. Atender o pedido exige abrir um segundo
consumidor da 2b — uma decisão de arquitetura, logo, este ADR (regra de ouro do
[CLAUDE.md](../../../CLAUDE.md): código que diverge da doc exige ADR, nunca silêncio).

## Decisão

1. **Campo `modo` no Kind `Agente`** — `chat` (default, = análise 2a do ADR-0024) ou
   `code` (= agente 2b do ADR-0001). O modo `chat` permanece **exatamente** como o
   ADR-0024 definiu; só o `code` é novidade.
2. **Modo `code` = Claude Code agêntico** via subprocess `claude -p`, com:
   `--output-format stream-json --verbose` (eventos em tempo real),
   `--dangerously-skip-permissions` (sem prompts interativos — não há TTY no servidor),
   `--add-dir <workspace>` e `--append-system-prompt <Agente.spec.prompt>`. O `cwd` é a
   **raiz do projeto** (`ATLAS_PROJECT_DIR`, default = raiz do repo Atlas).
3. **Execução assíncrona com streaming.** A API não bloqueia: `POST /_agent_run` cria um
   *run* em background (thread daemon) e devolve `{run_id}`; `GET /_agent_run/{id}/stream`
   é um **SSE** que faz *replay* dos eventos acumulados e segue ao vivo. Isso permite
   **multitarefa**: o usuário navega por outras abas/recursos enquanto o agente trabalha
   e reconecta ao mesmo run depois. Runs ficam em memória (máx. 30, LRU por `started_at`).
4. **Servidor concorrente.** O HTTP passa de `HTTPServer` para `ThreadingHTTPServer`,
   para que um run agêntico (longo) não trave as demais requisições da API.
5. **Distinção explícita preservada.** `modo=chat` continua tool-less e barato (regra 4
   do ADR-0024 intacta para ele). `modo=code` é o caminho caro/poderoso e fica **opt-in
   por recurso** — só Agentes marcados `code` têm tools.

## Alternativas consideradas

| Alternativa | Prós | Contras | Veredito |
|---|---|---|---|
| **Campo `modo` (chat\|code) no Agente; 2b via `claude -p` streaming assíncrono** | atende o pedido; reusa o Kind; 2a intacto; multitarefa | abre 2º consumidor da 2b; superfície agêntica na app | **escolhida** |
| Detectar `/apply` na resposta 2a e executar via `/_cmd` (E7-24 builder) | sem tools; barato; já existia | o agente não *age* (só sugere comandos do store); não edita código | insuficiente p/ "ser um Claude Code" |
| Anthropic SDK Python com loop de tools próprio | controle fino | reintroduz billing por token (viola assinatura, ADR-0001); reescreve o que o CLI já faz | rejeitada |
| Restringir 2b ao meta-loop (status quo ADR-0024 regra 4) | mais seguro | não atende o pedido do PO | rejeitada (com este ADR) |

## Consequências

- **Positivas:** o Atlas ganha um agente que se expande sozinho (cria Jobs/recursos,
  edita código) pela própria UI; multitarefa real via runs assíncronos + SSE; API não
  bloqueia; base para o loop de dev autônomo ([[autonomous-dev-loop]]).
- **Negativas / custos:** abre um **segundo ponto agêntico 2b** além do meta-loop —
  superfície de risco que o [ADR-0003](ADR-0003-seguranca-meta-loop.md) tratava como
  exclusiva do meta-loop. `--dangerously-skip-permissions` dá ao agente escrita livre
  sob o `cwd`. Runs em memória se perdem no restart. Custo de IA real por run (2b é caro).
- **Impacto na constituição / ADRs:** **estende** o ADR-0001 (2b deixa de ter consumidor
  único) e cria uma **exceção documentada** à regra 4 do ADR-0024. Reforça o pedido do
  PO de "aplicação construída 100% por agentes".

## Pendências (segurança — abrir antes do aceite final)

- **Workspace restrito.** Hoje o `cwd` é a raiz do repo e o bypass de permissão é total.
  O endurecimento ([spec de endurecimento §2](../../superpowers/specs/2026-06-16-atlas-endurecimento-design.md))
  prevê que o 2b só escreva sob um workspace restrito — aplicar ao modo `code`.
- **Gate de curadoria.** Alinhar com [ADR-0013](ADR-0013-barreira-de-entrada.md) /
  [ADR-0003](ADR-0003-seguranca-meta-loop.md): o que o agente gera deve passar por
  revisão humana antes de virar produção (CLAUDE.md: "nunca auto-executar código gerado
  pelo meta-loop sem revisão").
- **Auth.** `/_agent_run` herda a auth da API (token/loopback); validar que não há
  exposição agêntica sem token na Rasp/Tailnet.
- **Persistência de runs** (sobreviver a restart) e limite de concorrência simultânea.
- **Allow/deny de tools** por Agente (ex.: `code` sem `Bash`, só `Read/Edit/Write`).
