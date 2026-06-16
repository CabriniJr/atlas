---
titulo: Spec — Alarmes e lembretes
id: SPEC-ALARMES
status: em-revisao
versao: 0.1
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Spec — Alarmes e lembretes

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-06-16 | Tech Lead | Criação (lição de casa: alarmes) | — |

---

> Configurar alarmes/lembretes pelo chat ("me avise às 23h para dormir"). Construído
> sobre o [scheduler](scheduler.md) e a notificação do [executor](executor-e-notificacao.md).

## Modelo (híbrido, como trackers)
Um alarme é **dado** (linha na tabela `alarms`), disparado por uma **rotina
genérica `alarme`** do core que o scheduler agenda. Sem IA; o wizard mexe em dados
e o alarme passa a valer **em runtime** (sem reiniciar o motor).

## Dados — nova tabela `alarms`
| Campo | Tipo | Nota |
|---|---|---|
| `id` | int PK | |
| `horario` | text | `HH:MM` (hora local) |
| `mensagem` | text | o que notificar |
| `recorrencia` | text | `diario` \| `uma_vez` \| `dias:seg,qua,sex` |
| `proximo_disparo` | datetime | calculado; base do scheduler |
| `ativo` | bool | liga/desliga |
| `criado_em` | datetime | |

## Comandos (Telegram, 0 IA)
| Comando | Efeito |
|---|---|
| `/alarme HH:MM <mensagem>` | Cria alarme diário (default). Ex.: `/alarme 23:00 hora de dormir`. |
| `/alarme HH:MM <mensagem> @uma_vez` | Dispara uma vez no próximo HH:MM. |
| `/alarmes` | Lista alarmes ativos + próximo disparo. |
| `/alarme <id> remover` | Desativa. |
| `/alarme <id> editar ...` | Edita horário/mensagem/recorrência. |

## Disparo (rotina `alarme` + scheduler)
- O [scheduler](scheduler.md) consulta `alarms` ativos e dispara quando
  `proximo_disparo <= agora`.
- A rotina `alarme` (log puro, 0 IA) faz `deliver`: envia a `mensagem` pelo
  Telegram e recalcula `proximo_disparo` conforme `recorrencia`.
- Cada disparo grava um `run` (observabilidade).

## Relação com a "lição de casa" de dormir
"Me avise para mandar a hora que fui dormir" = alarme `23:00 "registre que horas
foi dormir: /reg #sono ..."`. O registro em si usa a [barreira](barreira-entrada.md)
(`/reg`) ou um tracker `sono` ([trackers](trackers-via-chat.md)).

## Casos de erro
| Caso | Resposta |
|---|---|
| `/alarme` com horário inválido | erro + formato `HH:MM`; não grava |
| `/alarme <id>` inexistente | "Alarme #<id> não existe. Veja `/alarmes`." |
| Disparo falha no envio | retry conforme [ADR-0006](../arquitetura/adr/ADR-0006-erro-e-resiliencia.md) |

## Testes (TDD)
- `/alarme 23:00 dormir` → 1 linha `alarms`, `proximo_disparo` = próximo 23:00.
- Scheduler em 23:00 → dispara, notifica, recalcula para o dia seguinte (diário).
- `@uma_vez` → após disparar, fica `ativo=false`.
- `/alarmes` lista próximos disparos corretos.
- `/alarme 9999 dormir` → erro; 0 gravação.

## Pendências
- Tabela `alarms` entra junto da migração de schema (relacionado a D-04).
- Fuso horário (assume o do host; configurável depois) — ver [scheduler](scheduler.md).
- Reuso possível: alarme é caso particular de "rotina agendada que só notifica";
  avaliar se vira config de rotina em vez de tabela própria (decidir na execução).
