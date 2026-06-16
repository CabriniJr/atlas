---
titulo: Lição de casa — próxima sessão (interface de configuração total via chat)
id: ROAD-LICAO
status: rascunho
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Lição de casa — próxima sessão

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Captura de ideias (sessão sem tokens) | PO/PM |

---

> Ideias capturadas para executar na próxima sessão. **Visão:** o bot é a
> **interface de configuração total da aplicação** — configurar rotinas, código,
> trackers e schedule pelo chat. Cada item vira tarefa de backlog + (quando muda
> arquitetura) ADR. Ordem sugerida abaixo.

> **Status de formalização (2026-06-16):** itens **0–5** formalizados. Itens maiores
> (agnosticismo de provider, app autônomo, loja, Rust) ficam como **direção futura**
> no [backlog](backlog.md). Pool de ideias = épico **E6** (prioridade máxima).
>
> | Item | Documento(s) |
> |---|---|
> | 0 — barreira | [ADR-0013](../arquitetura/adr/ADR-0013-barreira-de-entrada.md) · [spec](../specs/barreira-entrada.md) |
> | 1 — executor + notificação | [spec](../specs/executor-e-notificacao.md) |
> | 2 — scheduler | [spec](../specs/scheduler.md) |
> | 3 — meta-loop por chat | [spec](../specs/meta-loop-chat.md) |
> | 4 — comandos de config | [spec](../specs/interface-config-chat.md) |
> | 5 — trackers por chat | [spec](../specs/trackers-via-chat.md) |
> | + pool de ideias | [ADR-0014](../arquitetura/adr/ADR-0014-pool-de-ideias-desenvolvimento.md) · [spec](../specs/pool-de-ideias.md) |
> | + alarmes | [spec](../specs/alarmes.md) |

## 0. Bug atual a corrigir primeiro — "registra tudo"
Hoje **qualquer** mensagem livre vira atividade (handler MVP). Precisa de uma
**barreira de entrada**: só registrar quando houver intenção clara.
- **Proposta:** registro **só** via gatilho explícito de tracker (micro-sintaxe /
  trigger declarado) ou comando (`/reg ...`). Mensagem que não casa **não é
  gravada** — vira ajuda/sugestão ("não entendi; use /ajuda ou /reg").
- Liga em [ADR-0008](../arquitetura/adr/ADR-0008-roteamento-e-extracao.md)
  (roteamento determinístico + fallback). Reescreve `handler.py`.
- DoD: mandar "oi" **não** cria registro; "treino: agachamento 80kg" cria.

## 1. Executor de rotinas + notificação ("avise quando executar")
- Implementar o **ciclo de vida** real (`trigger → collect → gate → analyze →
  deliver`) no executor; `deliver` **notifica no Telegram** quando a rotina roda.
- Registrar cada execução em `runs` (observabilidade) e avisar resultado/erro.
- Backlog: completa E1 (executor) + usa [ciclo-de-vida](../arquitetura/ciclo-de-vida-rotina.md).
- DoD: rodar uma rotina manual (`/rodar <nome>`) e receber a notificação.

## 2. Scheduler (E1-06)
- Agendador por horário/intervalo (`agenda` da config) disparando rotinas.
- Catch-up de runs perdidos no boot ([ADR-0006](../arquitetura/adr/ADR-0006-erro-e-resiliencia.md)).
- Avisar no Telegram quando uma rotina agendada executa.
- DoD: agendar uma rotina "a cada 1 min" e ver as notificações chegarem.

## 3. Meta-loop por chat (configurar rotinas/código pelo Telegram) — E2
O coração do pedido: **criar rotina conversando**, salvar, executar com Claude
headless, aplicar e ela aparecer como disponível.
- **Planejar:** `/nova` inicia conversa → o bot ajuda a escrever um **plano/prompt**
  da rotina → salva como `routines/<nome>/SPEC.md` ([ADR-0009](../arquitetura/adr/ADR-0009-handoff-entre-modos.md)).
- **Gerar:** `/gerar <nome>` invoca `claude -p` (headless, modo agente 2b) que cria
  a pasta da rotina seguindo os contratos ([ADR-0003](../arquitetura/adr/ADR-0003-seguranca-meta-loop.md)).
- **Aplicar:** nasce `ativa=false`; `/ativar <nome>` liga; reiniciar o motor
  recarrega e ela **aparece como disponível**.
- DoD: criar uma rotina simples 100% pelo chat e vê-la rodar.
- **Nota de execução:** o `claude -p` precisa estar logado no host (no container,
  resolver login/credencial — tarefa à parte).

## 4. Comandos de configuração e listagem (a "interface total")
Conjunto de comandos previstos (revisar/expandir na execução):
- `/rotinas` — lista rotinas (ativa/inativa, modelo, agenda).
- `/rotina <nome>` — detalhe; `/ativar <nome>` · `/desativar <nome>`.
- `/nova` · `/gerar <nome>` · `/rodar <nome>` (execução manual).
- `/uso` — consumo de IA (já previsto na §13).
- `/status` — resumo do dia (já existe, evoluir).
- `/ajuda` — lista dinâmica de comandos disponíveis.
- Edição de config pelo chat (agenda, modelo, triggers) — interativo.

## 5. Trackers — cadastrar, configurar e ver pelo chat
Trackers são rotinas de tracking; precisam de UX fácil e interativa.
- `/trackers` — lista os trackers e o progresso recente.
- `/tracker novo` — wizard interativo para cadastrar (nome, domínio, micro-sintaxe
  de entrada, meta associada).
- `/tracker <nome>` — ver histórico/gráfico; configurar (editar campos).
- Ligar com **metas** (§12) e o **checkup semanal**.
- DoD: cadastrar um tracker novo pelo chat e registrar/ver dados nele.

## Sequência recomendada
0 (barreira) → 1 (executor+notificação) → 2 (scheduler) → 4 (comandos base) →
5 (trackers) → 3 (meta-loop). *(O meta-loop por último porque depende do executor,
do scheduler e da resolução do login do `claude -p` no container.)*

## Pendências técnicas a resolver junto
- **Login do `claude -p` dentro do container** (credencial da assinatura no host).
- **Barreira de entrada** vira possivelmente um ADR (decisão de roteamento).
- Recarregar rotinas sem downtime vs. reiniciar o container (definir).
