---
titulo: ADR-0006 — Tratamento de erro e resiliência
id: ADR-0006
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
substitui: —
substituido-por: —
---

# ADR-0006 — Tratamento de erro e resiliência

## Histórico de revisão
| Versão | Data       | Autor     | Mudança          | Aprovado por |
|--------|------------|-----------|------------------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Aceito (endurecimento B6) | PO/PM |

---

## Status
`aceito`.

## Contexto
Nenhum modo de falha estava especificado: `collect` que lança, `claude -p` que dá
timeout, Telegram fora do ar, notebook fechado no horário do agendamento.

## Decisão
- **Por fase:** cada fase é encapsulada; falha vira run `failed` + saída segura +
  alerta opcional. O sistema nunca trava por uma rotina quebrada.
- **`claude -p`:** timeout da config → mata, registra, retry opcional (1x).
- **Telegram indisponível:** fila de saída com backoff; inbound já é pull
  (long-poll), não perde mensagem recebida.
- **Schedule perdido (notebook off/fechado):** no boot, o agendador detecta runs
  atrasados e decide catch-up por rotina via campo `catch_up`. O resumo diário
  recupera se dentro de uma janela de X horas; senão, pula com registro.

## Alternativas consideradas
| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Falha propaga e derruba o serviço | Simples | Uma rotina quebra tudo | Inaceitável p/ sempre-ligado |
| Catch-up sempre | Não perde nada | Rajada de runs antigos no boot | Ruído; pode estourar orçamento |

## Consequências
- **Positivas:** robustez do serviço sempre-ligado; nenhuma rotina derruba o motor.
- **Negativas:** novo campo `catch_up` na config; lógica de detecção de atraso.
- **Impacto na constituição:** campos da rotina; comportamento do agendador.

## Pendências
Valor da janela de catch-up do resumo diário; política de retry por tipo de falha.
