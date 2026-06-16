---
titulo: Estágios de amadurecimento
id: ROAD-MATURIDADE
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Estágios de amadurecimento

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação | PO/PM        |

---

> O Atlas amadurece em estágios. Cada estágio tem um **objetivo de valor** e uma
> **porta de saída** (o que precisa estar pronto para avançar). Detalhe de itens
> no [backlog](backlog.md); sequência temporal no [planejamento](planejamento.md).

## M0 — Fundação documental ✅ (atual)
**Valor:** a fonte de verdade existe e governa o trabalho.
- Documentação modular, ADRs, diretrizes de agentes, processos.
- **Porta de saída:** doc aprovada pelo PO/PM. *(Estamos aqui.)*

## M1 — Motor mínimo
**Valor:** uma mensagem entra e uma rotina roda de ponta a ponta.
- Carregar rotinas (auto-descoberta), agendador, adapter Telegram, invocador de
  IA (2a/2b), banco SQLite ([modelo-de-dados](../arquitetura/modelo-de-dados.md)).
- Roteador determinístico ([ADR-0008](../arquitetura/adr/ADR-0008-roteamento-e-extracao.md)).
- Harness de teste de rotina ([ADR-0007](../arquitetura/adr/ADR-0007-contrato-de-teste.md)).
- **Porta de saída:** uma rotina de log roda fim-a-fim, com testes e observabilidade.

## M2 — As duas rotinas-âncora
**Valor:** o sistema entrega valor diário e sabe se expandir.
- **Resumo diário** (única rotina que sempre usa IA, modo 2a).
- **Meta-loop** de criação de rotinas (com a segurança do
  [ADR-0003](../arquitetura/adr/ADR-0003-seguranca-meta-loop.md)).
- **Porta de saída:** resumo diário útil + criar uma rotina por conversa funciona.

## M3 — Tracking e metas
**Valor:** os domínios de maior valor estão cobertos.
- Físico, estudos, leitura (Librera), e a camada transversal de metas + checkup
  semanal.
- **Porta de saída:** os quatro domínios rodam; metas consolidam progresso.

## M4+ — Expansão via meta-loop
**Valor:** o sistema cresce sozinho.
- Novas rotinas nascem pelo meta-loop; efeito bola de neve.
- Possíveis adapters novos (ntfy, dashboard web local).
- **Porta de saída:** aberta — guiada por backlog e PO/PM.

## Mapa rápido
```
M0 doc ──► M1 motor ──► M2 âncoras ──► M3 tracking ──► M4+ expansão
 (você     (uma rotina    (resumo +     (físico/estudo  (meta-loop
  está      fim-a-fim)     meta-loop)    /leitura/metas)  livre)
  aqui)
```
