---
titulo: Planejamento de marcos
id: ROAD-PLANO
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Planejamento de marcos

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação | PO/PM        |

---

> A sequência de construção e como os marcos ([amadurecimento](amadurecimento.md))
> se encadeiam. Sem datas fixas — o projeto é guiado por portas de saída, não por
> calendário. O PO/PM ajusta prioridade; o Tech Lead despacha conforme o
> [fluxo](../processos/fluxo-de-desenvolvimento.md).

## Ordem de construção

1. **M0 — Fundação documental** ✅ — a doc que governa tudo (este conjunto).
2. **M1 — Motor mínimo** — épico [E1](backlog.md#épico-e1--motor-mínimo-m1). Começa
   por E1-02 (banco) e E1-01 (carga de rotinas), depois adapter e roteador, e por
   fim invocador/agendador/observabilidade.
3. **M2 — Rotinas-âncora** — épico [E2](backlog.md#épico-e2--rotinas-âncora-m2).
   Resumo diário primeiro (valor imediato), meta-loop em seguida.
4. **M3 — Tracking e metas** — épico [E3](backlog.md#épico-e3--tracking-e-metas-m3).
5. **M4+ — Expansão via meta-loop** — daqui em diante, novas rotinas nascem pelo
   próprio sistema.

## Dependências críticas
- M1 depende do schema ([ADR-0002](../arquitetura/adr/ADR-0002-modelo-de-dados.md))
  estar fixado — **está**.
- M2 (meta-loop) depende do invocador agente (2b) e da segurança
  ([ADR-0003](../arquitetura/adr/ADR-0003-seguranca-meta-loop.md)).
- E3-03 (leitura/Librera) está **bloqueado** até definir o formato de sync.

## Critérios de avanço entre marcos
Avança-se de um marco para o próximo somente quando a **porta de saída** do marco
(definida em [amadurecimento](amadurecimento.md)) está satisfeita e aceita pelo
PO/PM.

## Riscos acompanhados
| Risco | Mitigação | Onde |
|---|---|---|
| Estouro do limite da assinatura Pro | Orçamento reativo + modelos baratos | [ADR-0005](../arquitetura/adr/ADR-0005-orcamento-reativo.md) |
| Código gerado inseguro | Inativo por padrão + revisão humana | [ADR-0003](../arquitetura/adr/ADR-0003-seguranca-meta-loop.md) |
| Formato do `claude -p` divergir do esperado | Verificação empírica antes do E1-08 | [ADR-0010](../arquitetura/adr/ADR-0010-observabilidade-claude-p.md) |
| Notebook indisponível em horários-chave | Catch-up no boot | [ADR-0006](../arquitetura/adr/ADR-0006-erro-e-resiliencia.md) |
