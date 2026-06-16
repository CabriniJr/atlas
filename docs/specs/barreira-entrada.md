---
titulo: Spec — Barreira de entrada
id: SPEC-BARREIRA
status: em-revisao
versao: 0.1
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Spec — Barreira de entrada

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-06-16 | Tech Lead | Criação (lição de casa, item 0) | — |

---

> Decisão de origem: [ADR-0013](../arquitetura/adr/ADR-0013-barreira-de-entrada.md).
> Esta spec detalha **como** o handler decide registrar ou ajudar, sem IA.

## Objetivo
Substituir o `_registrar` automático do
[`handler.py`](../../src/atlas/handler.py) por uma **barreira**: só grava em
`activities` quando há intenção explícita. Caso contrário, responde com ajuda.

## Requisitos
- **R1.** Mensagem que não casa trigger, micro-sintaxe nem `/reg` **não** grava
  nada e devolve a resposta de ajuda.
- **R2.** Trigger de rotina ativa → roteia para a rotina (registro pela rotina).
- **R3.** Micro-sintaxe de tracker → registro estruturado (ver
  [trackers-via-chat](trackers-via-chat.md)).
- **R4.** `/reg <texto>` → grava nota livre, domínio `geral`, `rotina="reg"`.
- **R5.** Zero IA em todo o caminho (P1). O fallback Haiku, se acionado, só
  desambigua roteamento — nunca cria registro de texto sem intenção.
- **R6.** Resposta de ajuda é determinística e curta; não persiste nada.

## Fluxo de decisão (determinístico)

```
mensagem
  ├─ começa com "/" ?
  │     ├─ /reg <texto>  → grava nota livre (R4)
  │     └─ outro comando → handler de comandos (interface-config-chat)
  └─ texto livre
        ├─ casa micro-sintaxe de tracker?  → registro estruturado (R3)
        ├─ casa trigger de rotina ativa?   → roteia p/ rotina (R2)
        │     └─ múltiplos candidatos?     → regra de conflito (ADR-0008);
        │                                     empate → pergunta (não grava)
        └─ não casa nada                   → resposta de ajuda (R1); 0 registro
```

## Contrato

`responder(texto, db, agora)` passa a retornar **sem efeito colateral de gravação**
salvo nos caminhos R2/R3/R4. A inferência de domínio por palavra-chave
(`_inferir_dominio`) **deixa de existir como gatilho de gravação** — palavra-chave
solta não é mais intenção suficiente; só `triggers` declarados de rotina contam.

### `/reg` — nota livre
- Sintaxe mínima: `/reg <texto>` → `activities(dominio="geral", rotina="reg",
  texto_cru=<texto>)`.
- Sintaxe com domínio opcional: `/reg #<dominio> <texto>` → grava com aquele
  `dominio` (ex.: `/reg #sono fui dormir 23h`). Domínio inválido/ausente → `geral`.
- `/reg` sem texto → ajuda (não grava).

## Mensagem de ajuda (texto-base)
> "🤔 Não entendi como registrar isso.
> • Use a sintaxe de um tracker (ex.: `treino: agachamento 80kg 4x10`).
> • Ou `/reg <texto>` para uma nota livre.
> • `/trackers` lista o que dá pra registrar · `/ajuda` mostra os comandos."

## Casos de erro
| Caso | Comportamento |
|---|---|
| Texto vazio / só espaços | Ajuda; não grava. |
| `/reg` sem texto | Ajuda; não grava. |
| Trigger casa 2+ rotinas, sem desempate | Pergunta qual (ADR-0008); não grava até a resposta. |
| Micro-sintaxe malformada (`treino:` sem corpo) | Ajuda específica do tracker; não grava. |

## Testes (TDD — antes do código)
- "oi" → resposta de ajuda; `SELECT COUNT(*) FROM activities` inalterado.
- "treino: agachamento 80kg" → 1 registro estruturado no tracker/rotina.
- `/reg fui dormir 23h` → 1 registro `geral`/`reg` com `texto_cru` correto.
- `/reg #sono fui dormir 23h` → 1 registro `dominio="sono"`.
- `/reg` (vazio) → ajuda; 0 registro.
- Mensagem ambígua entre duas rotinas → pergunta; 0 registro.

## Pendências
- Gramática da micro-sintaxe comum (D-03) — ver [ADR-0008](../arquitetura/adr/ADR-0008-roteamento-e-extracao.md).
- Lista de domínios válidos para `/reg #<dominio>` (fixa vs derivada dos trackers).
