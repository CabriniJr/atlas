---
titulo: Spec — Executor de rotinas e notificação
id: SPEC-EXECUTOR
status: em-revisao
versao: 0.1
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Spec — Executor de rotinas e notificação

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-06-16 | Tech Lead | Criação (lição de casa, item 1) | — |

---

> Completa o épico **E1**. Implementa o
> [ciclo de vida da rotina](../arquitetura/ciclo-de-vida-rotina.md) de ponta a
> ponta e faz a fase `deliver` **notificar no Telegram**.

## Objetivo
Hoje as rotinas são **carregadas** ([`routines.py`](../../src/atlas/routines.py))
mas **não são executadas**. Esta spec define o **executor**: a peça que roda uma
rotina pelas fases `trigger → collect → gate → analyze → deliver`, grava o run em
`runs` e avisa o usuário no Telegram.

## Requisitos
- **R1.** Executar uma `Rotina` carregada pelas fases, respeitando que **cada fase
  é opcional** (log puro usa só registro; análise usa todas).
- **R2.** `collect` roda script Python da pasta (`collect.*`), recebe o contexto e
  devolve `CollectResult` ([ADR-0004](../arquitetura/adr/ADR-0004-contrato-collect.md)).
- **R3.** `gate` decide se sobe IA; se falhar, encerra com saída padrão (run
  `skipped`).
- **R4.** `analyze` só roda se o gate passar; usa **modo 2a**
  ([ADR-0001](../arquitetura/adr/ADR-0001-ia-em-dois-modos.md)) com o `modelo` da
  config.
- **R5.** `deliver` formata e **envia pelo Telegram** + persiste o resultado e o
  que `store` declarar.
- **R6.** Toda execução grava uma linha em `runs` (observabilidade): início/fim,
  status (`ok`/`failed`/`skipped`), camada, `gate_passou`, tokens/custo nocional,
  `ref_saida`.
- **R7.** Execução manual via `/rodar <nome>` (ver
  [interface-config-chat](interface-config-chat.md)); o resultado é notificado.
- **R8.** Erro em qualquer fase não derruba o motor
  ([ADR-0006](../arquitetura/adr/ADR-0006-erro-e-resiliencia.md)); grava `failed` e
  notifica o erro de forma legível.

## Arquitetura

Novo módulo `src/atlas/executor.py`, com uma função pública:

```
executar(rotina: Rotina, ctx: ContextoExecucao, db, notificar) -> RunResult
```

- `ContextoExecucao`: data/hora, config da rotina, dados do **último run**
  (de `routine_state`), origem (`manual` | `agenda` | `mensagem`), e o payload da
  mensagem quando disparada por texto.
- `notificar`: callback de saída (injeta o adapter Telegram; testável com um fake).
- `RunResult`: status, camada, ponteiro de saída, erro (se houver).

### Fases (orquestração)
| Fase | Entrada | Saída | Custo |
|---|---|---|---|
| trigger | já resolvido pelo roteador/scheduler | rotina + payload | 0 |
| collect | `ContextoExecucao` | `CollectResult{data, store}` | 0 |
| gate | `CollectResult.data` + config `gate` | bool | 0 |
| analyze | prompt renderizado + `data` | texto da análise | IA (2a) |
| deliver | resultado | mensagem enviada + persistência | 0 |

Rotina **sem** `collect`/`prompt` (log puro, como `treino`) pula direto para a
persistência de `store` + `deliver` de confirmação.

## Notificação (`deliver`)
- Canal padrão: `saida = "telegram"` → usa o adapter
  ([`telegram.py`](../../src/atlas/telegram.py)).
- Conteúdo: resultado da análise (se houve) **ou** confirmação curta do registro.
- Em erro: mensagem clara ("⚠️ rotina `<nome>` falhou: <motivo curto>"), sem stack
  trace cru para o usuário (o detalhe vai para o log/`runs`).

## Persistência
- `runs`: uma linha por execução (R6).
- `routine_state`: atualizar "último run" e checkpoints que a rotina declarar.
- `activities`/entidades: conforme `CollectResult.store` (mapeamento explícito).

## Casos de erro
| Caso | `runs.status` | Notificação |
|---|---|---|
| `collect` lança exceção | `failed` | erro legível |
| `gate` falha (sem progresso) | `skipped` | saída padrão (ou silêncio, se configurado) |
| `analyze` estoura `timeout`/`budget_tokens` | `failed` | aviso de orçamento ([ADR-0005](../arquitetura/adr/ADR-0005-orcamento-reativo.md)) |
| `deliver` falha no envio | `failed` | re-tentativa conforme [ADR-0006](../arquitetura/adr/ADR-0006-erro-e-resiliencia.md) |

## Testes (TDD)
- Rotina log-puro (`treino`) via `/rodar treino`: grava `activities`, `runs.ok`,
  notifica confirmação.
- Rotina com gate que falha: `runs.skipped`, sem chamar análise.
- Rotina com análise (fake do invocador 2a): `runs.ok`, camada `2a`, tokens
  gravados, notificação com o texto.
- `collect` que lança: `runs.failed`, notificação de erro, motor segue vivo.

## Pendências
- Invocador de IA real (E1-05) — esta spec usa a **interface** do invocador;
  a integração com `claude -p` é tarefa separada.
- DoD: rodar `/rodar <nome>` e receber a notificação no Telegram.
