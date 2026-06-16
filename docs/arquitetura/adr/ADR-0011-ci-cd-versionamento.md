---
titulo: ADR-0011 — Política de CI/CD e versionamento
id: ADR-0011
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
substitui: —
substituido-por: —
---

# ADR-0011 — Política de CI/CD e versionamento

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Aceito  | PO/PM        |

---

## Status
`aceito`.

## Contexto
O projeto precisava de uma política de desenvolvimento: commits padronizados,
branches, PRs, pipeline automatizada com testes, versionamento, e deploy para dois
ambientes (bots **dev** e **prod**), **sem etapa de QA**. Havia tensão entre PRs +
CI (que pedem um host Git) e a filosofia local/privada do Atlas.

## Decisão
- **Híbrido:** GitHub hospeda repositório, PRs e CI (testes/checks); **CD é local
  e pull-based** (o notebook puxa do GitHub e faz deploy). Só o **código** vai pro
  GitHub — dados e segredos nunca.
- **Trunk-based + tags:** trunk único `main` (sempre verde); features em branches
  curtas via PR. Bot **dev** roda `main`; bot **prod** roda a última **tag SemVer**.
- **Conventional Commits + SemVer automático:** a versão e o CHANGELOG saem dos
  commits (via release automation, ex.: release-please).
- **Qualidade sem QA:** os gates são a **CI verde** + o **registro de curadoria**
  do best-of-two + o **aceite de alto nível** do PO/PM para promover a prod.
- **IA fora da CI:** a pipeline nunca chama `claude -p` real; `analyze` é testado
  com mock (P1, [ADR-0007](ADR-0007-contrato-de-teste.md)).

Detalhe operacional em [`../../processos/politica-de-desenvolvimento.md`](../../processos/politica-de-desenvolvimento.md).

## Alternativas consideradas
| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| 100% local (hooks/scripts) | Nada sai da máquina | PR sem UI; sem CI hospedada | PRs/CI ficam pobres |
| 100% GitHub (inclui CD) | Tudo num lugar | Deploy puxaria credenciais/segredos pra nuvem | Fere privacidade local |
| Git-flow completo | Estrutura forte | Cerimônia demais p/ monousuário | Fere P7 |
| SemVer manual | Controle | Trabalho repetitivo, sujeito a erro | Pior p/ fluxo de agentes |

## Consequências
- **Positivas:** PRs e CI de verdade; versionamento e CHANGELOG automáticos; prod
  estável em tags imutáveis (rollback fácil); deploy sem expor segredos.
- **Negativas:** o código passa a residir no GitHub; requer setup inicial (repo,
  `gh`, rename de branch, branch protection).
- **Impacto na constituição:** nova decisão travada de processo; afeta backlog
  (infra) e o fluxo de desenvolvimento.

## Pendências
- Escolha final da ferramenta de release automation (release-please vs alternativa).
- Units systemd `atlas-dev`/`atlas-prod` e o poller de deploy (backlog E4).
- Limiar de cobertura de teste (se houver).
