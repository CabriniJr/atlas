---
titulo: ADR-0013 — Barreira de entrada (registro só com intenção explícita)
id: ADR-0013
status: aceito            # proposto | aceito | substituído | obsoleto
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
substitui: —
substituido-por: —
---

# ADR-0013 — Barreira de entrada (registro só com intenção explícita)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-06-16 | Tech Lead | Proposta (lição de casa, item 0) | — |
| 1.0    | 2026-06-16 | Tech Lead | Aceito | PO/PM |

---

## Status
`aceito`.

## Contexto
O handler MVP ([`src/atlas/handler.py`](../../../src/atlas/handler.py), função
`_registrar`) grava **qualquer** mensagem que não comece com `/` como uma
atividade, inferindo o domínio por palavra-chave e caindo em `geral` quando nada
casa. Resultado: mandar "oi", "vou ali" ou um desabafo cria registro de atividade.
O sistema "registra tudo".

Isso conflita com dois compromissos do projeto:

1. **Qualidade do dado.** `activities` é a base do resumo diário, das metas e dos
   trackers. Lixo de entrada polui agregações e o futuro score do dia.
2. **A promessa do roteador.** O [ADR-0008](ADR-0008-roteamento-e-extracao.md)
   prevê micro-sintaxe determinística + fallback Haiku, mas **não definiu** que
   acontece com texto que não expressa intenção de registro. Na prática virou
   "grava como `geral`".

Há tensão com P1 (zero IA por padrão): não se pode subir IA para decidir se cada
mensagem "é um registro". A barreira precisa ser **barata e determinística**.

## Decisão
**Não registrar por padrão.** Uma atividade só é criada quando há **intenção
explícita**, detectada sem IA por um destes caminhos:

1. **Trigger declarado de rotina** — a mensagem casa um `trigger` de uma rotina
   ativa (regras de conflito do [ADR-0008](ADR-0008-roteamento-e-extracao.md)).
2. **Micro-sintaxe de tracker** — a mensagem casa o prefixo/gramática declarado
   por um tracker (ex.: `treino: agachamento 80kg 4x10`), ver
   [trackers-via-chat](../../specs/trackers-via-chat.md).
3. **Comando de registro explícito** — `/reg <texto>` força o registro de uma nota
   livre quando o usuário quer mesmo gravar algo sem rotina.

Mensagem que **não casa** nenhum dos três **não vira registro**. Ela recebe uma
resposta de ajuda/sugestão, sem persistir em `activities`:

> "Não entendi como registrar isso. Use a sintaxe de um tracker, `/reg <texto>`
> para uma nota livre, ou `/ajuda`."

**Efeito sobre o ADR-0008:** o fallback de texto livre é **estreitado**. O Haiku
(Camada 1) deixa de ser um caminho de *gravação automática* de texto não
reconhecido; quando usado, é só para **desambiguar roteamento** entre rotinas
candidatas — nunca para inventar um registro a partir de texto sem intenção. Na
dúvida, o sistema **pergunta ou ajuda**, não grava.

**DoD da decisão:** mandar "oi" **não** cria registro; `treino: agachamento 80kg`
(ou `/reg fui dormir 23h`) **cria**.

## Alternativas consideradas
| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Manter "registra tudo" como `geral` | Nada a fazer | Polui o dado; quebra metas/score | É o bug que motivou este ADR |
| IA decide se cada mensagem é registro | Robusto a linguagem natural | Custa IA em **toda** entrada | Fere P1 (zero IA por padrão) |
| Exigir sempre `/reg` (sem triggers) | Simplíssimo, 100% explícito | Perde a UX de "treino de perna" direto | Atrito alto; triggers já são determinísticos |
| Heurística de "parece registro?" sem lista | Sem declarar nada | Não-determinístico, falsos positivos | Imprevisível; volta ao problema |

## Consequências
- **Positivas:** `activities` só recebe dado intencional; resumo/metas/score
  confiáveis; comportamento previsível e 0 IA no caminho comum.
- **Negativas / custos:** o usuário precisa usar trigger, micro-sintaxe ou `/reg`
  — uma curva de aprendizado pequena, mitigada pela resposta de ajuda. Exige
  **reescrever `handler.py`** (remover `_registrar` automático).
- **Impacto na constituição:** ajusta o comportamento do roteador descrito no
  [ADR-0008](ADR-0008-roteamento-e-extracao.md) (fallback estreitado). Não altera
  itens da tabela travada; quando aceito, este ADR é referenciado na seção de
  roteamento da [visão geral de arquitetura](../visao-geral.md).

## Pendências
- Gramática exata da micro-sintaxe de tracker (compartilhada com
  [ADR-0008](ADR-0008-roteamento-e-extracao.md), pendência D-03 do backlog).
- Se `/reg` aceita domínio explícito (`/reg #sono fui dormir 23h`) ou sempre grava
  como `geral`/nota — detalhar em [barreira-entrada](../../specs/barreira-entrada.md).
- Se a resposta de ajuda deve sugerir o tracker mais próximo (fuzzy) — melhoria
  futura, não bloqueia o MVP.
