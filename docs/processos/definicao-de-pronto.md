---
titulo: Definição de Pronto (DoR / DoD)
id: PROC-DOD
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Definição de Pronto (DoR / DoD)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação | PO/PM        |

---

## Definition of Ready (DoR) — uma tarefa pode ser despachada quando…
- [ ] Tem objetivo claro e ligado a um item de [backlog](../roadmap/backlog.md).
- [ ] O **contrato** está definido (entradas, saídas, interface).
- [ ] As decisões de arquitetura necessárias já têm [ADR](../arquitetura/adr/README.md)
      aceito (ou a tarefa é "abrir o ADR").
- [ ] Os critérios de aceite (DoD) estão escritos.
- [ ] Dependências e isolamento estão claros (não colide com tarefa paralela).

## Definition of Done (DoD) — uma tarefa está pronta quando…
- [ ] **Testes escritos primeiro (TDD)** e **passando**, com evidência (saída do
      comando).
- [ ] O contrato da spec é satisfeito.
- [ ] Segue a [constituição](../arquitetura/constituicao.md), os ADRs e os
      [princípios](../visao/principios.md).
- [ ] **Doc atualizada junto com o código** (header + histórico de revisão).
- [ ] Sem segredos commitados; sem código de meta-loop auto-ativado.
- [ ] Para rotinas: `collect`/`gate` testados isoladamente; `analyze` com IA
      mockada ([ADR-0007](../arquitetura/adr/ADR-0007-contrato-de-teste.md)).
- [ ] Passou pela curadoria best-of-two e pelo aceite de alto nível do PO/PM.

## Evidência antes de afirmação
Nenhum agente afirma "pronto", "corrigido" ou "passando" sem ter rodado o comando
de verificação e observado a saída. Evidência sempre antes da afirmação.
