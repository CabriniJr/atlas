---
titulo: ADR-0042 — Agente modo `code` via Ollama nativo (segundo motor 2b)
id: ADR-0042
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-02
substitui: —
substituido-por: —
---

# ADR-0042 — Agente modo `code` via Ollama nativo (segundo motor 2b)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-07-02 | Tech Lead | Proposta + implementação (pedido do PO, prioridade máxima) | PO/PM |

---

## Status
`aceito` — implementado em ritmo ágil (pedido do PO, prioridade máxima).

## Contexto

Com o Ollama da LAN (`192.168.86.38:11434`) já servindo como motor de tradução
(ADR-0040), o PO pediu explicitamente um segundo salto: "ele [Ollama] vai ser
o motor de desenvolvimento, você vai ser o agente editor e orquestrador...
preciso essa capacidade e visibilidade de desenvolvimento e chat com a API
ollama no front, exatamente como um Claude Code mas como render do Kind
Agente, para eu conseguir desenvolver e administrar a plataforma via ela
mesma e com o ollama" — e, em seguida, "o mais importante do agente modo code
é o auto mode e UI rica na API para erros simples não me travarem".

O [ADR-0025](ADR-0025-agente-modo-code.md) já criou o modo `code` do Kind
`Agente` (2b — tools, edição de arquivo), mas **hardcoded pro `claude -p`
CLI** (`api._run_agent_bg`, linha "modo code roda sempre via claude CLI").
Isso é, por definição, um **segundo consumidor da camada 2b** além do
adapter claude — mesma natureza de decisão do ADR-0025 em relação ao
meta-loop original ([ADR-0001](ADR-0001-ia-em-dois-modos.md)/[ADR-0003](ADR-0003-seguranca-meta-loop.md)),
logo, novo ADR (regra de ouro do CLAUDE.md).

Diferença chave em relação ao claude: o Ollama **não tem um "Claude Code"
pronto** — só a API `/api/chat` com function-calling nativo (`tools`/
`tool_calls`, suportado por modelos com capability `tools`: `llama3.1`,
`qwen3.6`, testados no servidor do PO). É preciso **implementar o loop
agêntico** (enviar tools → executar tool_call → devolver resultado → repetir),
não só trocar o binário chamado.

## Decisão

1. **Módulo `atlas/agente_ollama.py`** — loop de tool-calling nativo contra
   `POST /api/chat`. Catálogo próprio de tools (equivalente ao Read/Write/
   Edit/Bash do Claude Code): `read_file`, `write_file`, `edit_file`,
   `list_dir`, `run_command`. Cada tool roda confinada ao workspace resolvido
   (reusa `api.resolve_workspace`, ADR-0028 §1). `filtrar_ferramentas()`
   aplica o mesmo allow/deny CSV do Agente (`spec.allowed_tools`/
   `denied_tools`, ADR-0028 §2), só que em processo, não via flag de CLI.

2. **`api._run_agent_bg` despacha por motor resolvido** (`_resolve_engine`,
   ADR-0026): `motor=claude` → `_run_agent_bg_claude` (comportamento do
   ADR-0025/0028, inalterado); `motor=ollama` **e** endpoint saudável
   (`agente_ollama.ollama_disponivel`, probe `GET /api/tags`) →
   `_run_agent_bg_ollama` (novo). Setup compartilhado (resolver workspace,
   montar system prompt com contexto da API, calcular `gated`) foi
   extraído pro corpo comum de `_run_agent_bg` — cada caminho só faz a
   parte específica do motor.

3. **Fallback pro claude também no modo code** (estende ADR-0040 pro 2b):
   se `motor=ollama` mas o endpoint está fora do ar, emite um evento
   `warning` e roda o run inteiro via claude (não dá pra trocar de motor
   NO MEIO de uma conversa de tool-calling — os dois protocolos são
   incompatíveis — então a decisão é tomada **antes do primeiro turno**).

4. **Eventos compatíveis com o dashboard existente, sem mudar o contrato.**
   `agente_ollama.rodar_loop` emite `assistant` (texto + blocos `tool_use`) e
   `done` no MESMO formato que `dashboard/kinds/agente.js` já sabe renderizar
   (herdado do `stream-json` do claude) — o *render* pedido pelo PO ("como
   render do Kind Agente") vem de graça, zero mudança de UI para o que já
   existia. Único evento novo: **`warning`** — erro de UMA tool (arquivo
   ausente, comando com erro, JSON malformado) ou motor trocado no meio do
   caminho. Ao contrário de `error`, `warning` **não termina o run**: o
   modelo recebe o erro como resultado da tool e decide como prosseguir.
   Isso concretiza o pedido do PO ("erro simples não me trava") — só falha
   de rede/endpoint em si (`OllamaIndisponivel`) é fatal.
5. **Custo sempre 0** (`_registrar_gasto_agente(store, agente, 0.0, modelo)`)
   — Ollama é local, sem billing por token (mesmo princípio do ADR-0022/0040).
6. **Tools mapeadas visualmente 1:1 com as do claude** no dashboard
   (`_TOOL_ICONS`/detalhe em `agente.js`): `read_file`↔Read, `write_file`↔
   Write, `edit_file`↔Edit, `run_command`↔Bash, `list_dir`↔Glob/Grep — mesmo
   ícone e extração de detalhe (caminho/comando), visual idêntico entre motores.

## Alternativas consideradas

| Alternativa | Prós | Contras | Veredito |
|---|---|---|---|
| **Loop de tool-calling nativo próprio (`agente_ollama.py`)** | controle total; sem dependência externa; reusa toda a infra de run/SSE/gate/curadoria já existente; erro de tool é não-fatal por design | precisa implementar o loop (não é "trocar um binário") | **escolhida** |
| Rodar um CLI agêntico de terceiros (ex.: "openclaw"/Open Interpreter) apontado pro Ollama | menos código próprio | dependência externa não avaliada (segurança, formato de evento, manutenção); não teria o mesmo formato de evento pro dashboard sem um adapter de qualquer forma — o esforço de integração seria parecido ao de escrever o loop nativo | rejeitada por ora (fica como nota — dá pra reavaliar se o loop nativo mostrar limitação real) |
| Ollama só no modo `chat` (2a), modo `code` continua exclusivo do claude | menor superfície de risco | não atende o pedido explícito do PO ("ele vai ser o motor de desenvolvimento") | rejeitada |
| Erro de tool sempre fatal (como o claude CLI faz ao sair com código ≠ 0) | mais simples | contraria pedido explícito do PO ("erro simples não me trava") | rejeitada |

## Consequências

- **Positivas:** o Atlas ganha um segundo motor de desenvolvimento agêntico,
  gratuito e local, com a MESMA UI/UX já validada (curadoria por diff, config,
  chat); resiliente a erro pontual de tool; fallback automático pro claude se
  o Ollama cair antes de começar o run.
- **Negativas / custos:** abre um **terceiro ponto agêntico 2b** (meta-loop,
  claude modo=code, agora ollama modo=code) — mesma superfície de risco do
  ADR-0025/0028 (workspace confinado + gate mitigam, mas `run_command` ainda
  é shell livre dentro do workspace). Catálogo de tools próprio (não os
  Read/Write/Edit/Bash "de verdade" do Claude Code) — mais simples, mas
  também menos capaz (sem Glob/Grep de verdade, sem Task/sub-agentes). Se o
  Ollama cair NO MEIO de um run (não antes), o run termina com `error` — não
  há troca de motor a meio de conversa (limitação aceita, ver decisão 3).
- **Impacto na constituição:** estende ADR-0001 (2b ganha um 3º consumidor),
  ADR-0025 (modo `code` deixa de ser exclusivo do claude) e ADR-0028
  (allow/deny e workspace confinado agora se aplicam a dois motores). Nenhuma
  decisão anterior é revertida.

## Pendências
- Tools mais ricas (busca por padrão tipo Grep real, não só listagem) se o
  catálogo atual se mostrar limitante na prática.
- Persistir métricas de uso (turnos, tool calls, taxa de erro) por motor no
  status do Agente, hoje só `custo_total_usd`/`runs` genéricos.
- Reavaliar troca de motor **a meio** de um run (hoje: decisão só no início).
