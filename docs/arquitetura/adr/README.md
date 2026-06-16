---
titulo: Índice de ADRs
id: ADR-INDEX
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Architecture Decision Records (ADRs)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança                              | Aprovado por |
|--------|------------|-----------|--------------------------------------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação + 10 ADRs de endurecimento   | PO/PM        |
| 1.1    | 2026-06-16 | Tech Lead | ADR-0013 (barreira) e ADR-0014 (pool) — aceitos | PO/PM |

---

> Um **ADR** registra uma decisão de arquitetura: contexto, alternativas e
> consequências. ADRs são **imutáveis** depois de aceitos — para mudar uma
> decisão, abra um novo ADR que **substitui** o anterior. Use o
> [template](template-adr.md).

## Como criar um ADR

1. Copie [`template-adr.md`](template-adr.md) para `ADR-NNNN-<slug>.md` (próximo
   número livre).
2. Preencha contexto, decisão, alternativas, consequências. Status `proposto`.
3. PO/PM revisa → aceite → status `aceito`; atualize a [constituição](../constituicao.md)
   e este índice.
4. Se substitui outro ADR, marque ambos (`substitui` / `substituido-por`).

## Índice

| ADR | Título | Status | Origem |
|---|---|---|---|
| [0001](ADR-0001-ia-em-dois-modos.md) | IA em dois modos: análise (2a) vs agente (2b) | aceito | Endurecimento A1 |
| [0002](ADR-0002-modelo-de-dados.md) | Modelo de dados SQLite | aceito | Endurecimento A2 |
| [0003](ADR-0003-seguranca-meta-loop.md) | Modelo de segurança do meta-loop | aceito | Endurecimento A3 |
| [0004](ADR-0004-contrato-collect.md) | Contrato tipado do `collect` | aceito | Endurecimento B4 |
| [0005](ADR-0005-orcamento-reativo.md) | Orçamento de token reativo | aceito | Endurecimento B5 |
| [0006](ADR-0006-erro-e-resiliencia.md) | Tratamento de erro e resiliência | aceito | Endurecimento B6 |
| [0007](ADR-0007-contrato-de-teste.md) | Contrato de teste da rotina | aceito | Endurecimento B7 |
| [0008](ADR-0008-roteamento-e-extracao.md) | Roteamento e extração de parâmetros | aceito | Endurecimento C8 |
| [0009](ADR-0009-handoff-entre-modos.md) | Handoff entre modos via `SPEC.md` | aceito | Endurecimento C9 |
| [0010](ADR-0010-observabilidade-claude-p.md) | Observabilidade via `claude -p` JSON | aceito | Endurecimento C10 |
| [0011](ADR-0011-ci-cd-versionamento.md) | Política de CI/CD e versionamento | aceito | Política de desenvolvimento |
| [0012](ADR-0012-empacotamento-docker.md) | Empacotamento e deploy via Docker | aceito | Sempre-ligado |
| [0013](ADR-0013-barreira-de-entrada.md) | Barreira de entrada (registro só com intenção) | aceito | Lição de casa (item 0) |
| [0014](ADR-0014-pool-de-ideias-desenvolvimento.md) | Pool de ideias → desenvolvimento (autoimplementação, ativação humana) | aceito | Lição de casa (pool, prioridade máxima) |

## Lastro

O design completo que originou estes 10 ADRs está em
[`../../superpowers/specs/2026-06-16-atlas-endurecimento-design.md`](../../superpowers/specs/2026-06-16-atlas-endurecimento-design.md).

## ADRs retroativos a escrever (backlog)

As decisões travadas da [constituição](../constituicao.md) que ainda não têm ADR
próprio (Telegram, Claude Code na assinatura, script-primeiro, pastas plugáveis)
são candidatas a ADRs retroativos. Rastreado no [backlog](../../roadmap/backlog.md).
