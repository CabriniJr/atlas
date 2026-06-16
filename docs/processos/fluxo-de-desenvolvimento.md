---
titulo: Fluxo de desenvolvimento
id: PROC-FLUXO
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Fluxo de desenvolvimento

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação | PO/PM        |

---

> Como uma ideia vira código no Atlas. É **regra do projeto**, não convenção.

## O modelo em uma figura

```
VOCÊ (PO/PM)  ──certifica visão, dores, prioridade, aceite──┐
                                                            ▼
TECH LEAD (Opus) ── traduz visão em ADR/backlog/spec; define a tarefa; orquestra
       │
       ├─►  DEV-A (Sonnet, background)  ─┐
       │                                 ├─► duas soluções da MESMA tarefa,
       └─►  DEV-B (Sonnet, background)  ─┘   visões diferentes
                          │
                          ▼
       CURADORIA (Opus): melhor das duas → funde → melhora → valida contra a doc
                          │
                          ▼
       VOCÊ aprova em alto nível  →  commit + doc/ADR atualizados
```

## Etapas

### 1. Entrada (PO/PM)
O PO/PM traz uma dor, objetivo ou prioridade — em alto nível. Não especifica
implementação.

### 2. Tradução (Tech Lead)
O Tech Lead transforma isso em:
- um item de [backlog](../roadmap/backlog.md) (ou vários);
- se houver decisão de arquitetura, um [ADR](../arquitetura/adr/README.md) proposto;
- uma **spec de tarefa** (objetivo, contrato, DoD) por unidade de trabalho.

### 3. Despacho paralelo (Tech Lead → Devs)
O Tech Lead despacha **N Devs (geralmente 2)** para a **mesma** tarefa, em
**background**, instruindo abordagens/visões diferentes. Cada Dev faz TDD e entrega
solução + resumo de abordagem.

### 4. Curadoria best-of-two (Tech Lead/Curador)
O Curador compara as soluções contra a régua
([revisao-e-curadoria](revisao-e-curadoria.md)), funde o melhor das duas, melhora,
e valida contra a doc: **atende a dor? segue a arquitetura? está no escopo?**

### 5. Aceite (PO/PM)
O Tech Lead leva ao PO/PM a solução curada e os trade-offs, em alto nível. O PO/PM
certifica. Só então a solução entra no fluxo de
[branch → PR → CI → merge → release](politica-de-desenvolvimento.md), com doc e
ADRs atualizados junto. A **curadoria é a revisão de código** (não há QA separado).

## Por que best-of-two
Duas visões independentes da mesma tarefa expõem trade-offs que uma só esconde. A
curadoria por Opus extrai o melhor das duas e produz algo superior a qualquer uma
isolada — ao custo de rodar a tarefa em dobro (aceitável: Devs são Sonnet, em
background).

## Princípios que este fluxo materializa
P8 (doc é fonte de verdade), P9 (rastreável/reversível), P10 (construído por
agentes, curado com rigor).

## Isolamento de trabalho
Tarefas paralelas independentes não compartilham estado. Quando houver risco de
colisão, o Tech Lead serializa ou isola (ex.: worktrees git) — ver
[Definição de Pronto](definicao-de-pronto.md).
