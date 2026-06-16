---
titulo: Spec — Scheduler (agendador de rotinas)
id: SPEC-SCHEDULER
status: em-revisao
versao: 0.1
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Spec — Scheduler (agendador de rotinas)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-06-16 | Tech Lead | Criação (lição de casa, item 2) | — |

---

> Implementa **E1-06**. Dispara rotinas por horário/intervalo e recupera runs
> perdidos no boot. Decisões de resiliência:
> [ADR-0006](../arquitetura/adr/ADR-0006-erro-e-resiliencia.md).

## Objetivo
Disparar automaticamente as rotinas cujo campo `agenda` está definido, e fazer
**catch-up** dos disparos perdidos enquanto o motor esteve fora do ar. Cada
execução agendada usa o [executor](executor-e-notificacao.md) e **notifica no
Telegram** quando roda.

## Requisitos
- **R1.** Rotina ativa com `agenda` definida é disparada no horário/intervalo.
- **R2.** Formato de `agenda` suporta, no mínimo: intervalo (`@every 1m`,
  `@every 1h`) e horário diário (`@daily 21:00`). (Sintaxe completa em Pendências.)
- **R3.** No boot, para cada rotina com `catch_up=true`, runs perdidos são
  **recuperados** uma vez; com `catch_up=false`, são **pulados** (grava `skipped`).
- **R4.** O disparo agendado passa pelo executor (ciclo de vida completo) e grava
  `runs`.
- **R5.** Notifica no Telegram o resultado/erro do disparo agendado.
- **R6.** O scheduler não bloqueia o loop de mensagens do bot (concorrência segura
  com o long-poll).
- **R7.** Determinístico e barato: o agendamento em si é 0 IA.

## Arquitetura
Novo módulo `src/atlas/scheduler.py`:

```
proxima_execucao(agenda: str, ultimo: datetime | None, agora: datetime) -> datetime | None
tick(agora, rotinas, db, executar) -> list[RunResult]   # dispara o que está vencido
catch_up(agora, rotinas, db, executar) -> list[RunResult]  # no boot
```

- A "fonte da verdade" do último disparo é `routine_state` (chave `ultimo_run`).
- `tick` é chamado periodicamente pelo loop principal ([`app.py`](../../src/atlas/app.py));
  compara `proxima_execucao` com `agora` e dispara o que venceu.
- Modelo single-process (P7): sem cron externo; o próprio motor faz o tick.

## Catch-up (boot)
- Para cada rotina agendada, calcula quantos disparos foram perdidos desde
  `ultimo_run`.
- `catch_up=true`: executa **um** run de recuperação (não enxurrada) e marca o
  estado como em-dia. `catch_up=false`: marca `skipped` e segue.
- Janela máxima de catch-up: ver Pendências (constituição lista como item em
  aberto para o resumo diário).

## Casos de erro
| Caso | Comportamento |
|---|---|
| `agenda` malformada | rotina não agenda; erro logado (não derruba o boot) |
| Disparo falha no executor | `runs.failed` + notificação; próximo tick segue |
| Relógio mudou (DST/sleep) | usa horário absoluto; recalcula `proxima_execucao` |

## Testes (TDD)
- `@every 1m`: dado `ultimo` há 70s, `tick` dispara 1 run e atualiza `ultimo_run`.
- `@daily 21:00`: dispara uma vez ao cruzar 21:00; não redispara no mesmo dia.
- Boot com 3 disparos perdidos e `catch_up=true`: exatamente 1 run de recuperação.
- Boot com `catch_up=false`: 0 runs, estado marcado em-dia.
- DoD: agendar uma rotina "a cada 1 min" e ver as notificações chegarem.

## Pendências
- Gramática completa de `agenda` (cron-like vs vocabulário `@every`/`@daily`).
- Valor da **janela de catch-up** (item em aberto da
  [constituição](../arquitetura/constituicao.md)).
- Fuso horário: assumir o do host; configurável depois.
