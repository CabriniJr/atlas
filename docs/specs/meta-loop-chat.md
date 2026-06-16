---
titulo: Spec — Meta-loop via chat (criar rotinas conversando)
id: SPEC-META-LOOP
status: em-revisao
versao: 0.1
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Spec — Meta-loop via chat

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-06-16 | Tech Lead | Criação (lição de casa, item 3) | — |

---

> Implementa o épico **E2** (fases 1–2 + ativação). Criar uma rotina **conversando**
> pelo Telegram: planejar → gerar com Claude Code (modo 2b) → revisar → ativar.
> Segurança: [ADR-0003](../arquitetura/adr/ADR-0003-seguranca-meta-loop.md);
> handoff por arquivo: [ADR-0009](../arquitetura/adr/ADR-0009-handoff-entre-modos.md).

## Objetivo
Permitir que o dono descreva uma rotina nova em linguagem natural e o sistema
gere a pasta da rotina seguindo os contratos do projeto, **sem ativar nada
automaticamente**. É o único fluxo que usa o **agente (modo 2b)**.

## Distinção importante (vs. trackers)
- **Tracker** = dado + rotina genérica `tracking`; **não gera código**, aplica em
  runtime ([trackers-via-chat](trackers-via-chat.md)).
- **Meta-loop** = **gera código** (uma pasta `routines/<nome>/` com `collect`,
  `prompt`, etc.) quando o que se quer não cabe num tracker (ex.: integrar uma API,
  lógica de `gate`, análise com IA). Exige recarga/reinício do motor para aparecer.

## Fases

### Fase 1 — Planejar (`/nova`) — 0 IA ou IA leve
1. `/nova` inicia um fluxo conversacional de planejamento.
2. O bot guia perguntas (o que dispara? o que coletar? precisa de análise? com que
   frequência?) e monta um **`SPEC.md`** da rotina.
3. Salvo em `routines/<nome>/SPEC.md` ([ADR-0009](../arquitetura/adr/ADR-0009-handoff-entre-modos.md)).
   O template do `SPEC.md` é a dívida D-02 do backlog.
4. Nada de código ainda; nada ativo.

> Nota: a fase 1 pode ser 100% determinística (formulário guiado) ou usar IA leve
> para redigir o `SPEC.md`. Default: **guiado, 0 IA**; IA aqui é opcional.

### Fase 2 — Gerar (`/gerar <nome>`) — IA modo 2b
1. Invoca `claude -p` em **modo agente (2b)** com o `SPEC.md` como entrada e os
   **contratos do projeto** como guarda ([ciclo-de-vida-rotina](../arquitetura/ciclo-de-vida-rotina.md),
   [ADR-0004](../arquitetura/adr/ADR-0004-contrato-collect.md),
   [ADR-0007](../arquitetura/adr/ADR-0007-contrato-de-teste.md)).
2. O agente cria `routine.toml`, `collect.*`, `prompt.*` e testes na pasta.
3. A rotina nasce **`ativa=false`** (invariante da
   [constituição](../arquitetura/constituicao.md) #11 / P9).
4. O bot mostra **progresso** durante a geração e um resumo do que foi criado.

### Fase 3 — Revisar e ativar (`/ativar <nome>`) — humano no loop
1. O dono revisa o diff (a pasta gerada) — fluxo de revisão humana
   ([ADR-0003](../arquitetura/adr/ADR-0003-seguranca-meta-loop.md)).
2. `/ativar <nome>` seta `ativa=true` e commita a rotina
   ([politica-de-desenvolvimento](../processos/politica-de-desenvolvimento.md)).
3. Recarregar o motor → a rotina **aparece como disponível** em `/rotinas`.

## Segurança (não-negociável)
- Código gerado **nunca** auto-executa (constituição #4/#11).
- O agente 2b roda na sessão de **desenvolvimento**, separada da operação (P5);
  comunicação por arquivo (`SPEC.md`, pasta), não por estado de runtime.
- Orçamento/timeout do 2b respeitam [ADR-0005](../arquitetura/adr/ADR-0005-orcamento-reativo.md).

## Casos de erro
| Caso | Comportamento |
|---|---|
| `/gerar` sem `SPEC.md` | pede rodar `/nova` antes |
| Agente 2b falha/timeout | run `failed`; pasta parcial sinalizada; nada ativado |
| `/ativar` em rotina que não passa nos testes | bloqueia ativação; mostra falhas |
| `claude -p` não logado no host | erro claro (pendência de login do container) |

## Testes (TDD)
- `/nova` guiado produz `SPEC.md` válido na pasta.
- `/gerar` (com fake do agente 2b) cria a pasta com `ativa=false`.
- `/ativar` só liga se os testes da rotina passam.
- Rotina recém-ativada aparece em `/rotinas`.
- DoD: criar uma rotina simples 100% pelo chat e vê-la rodar.

## Pendências
- **Login do `claude -p` dentro do container** (credencial da assinatura no host) —
  pendência técnica da lição de casa; bloqueia a fase 2 em produção containerizada.
- Template de `SPEC.md` (D-02).
- Recarregar rotina sem downtime vs. reiniciar o container — decisão de operação.
- Integração com a **fila de insights** (direção futura): um insight priorizado
  poderia disparar `/nova`+`/gerar` automaticamente. Fora do escopo agora.
