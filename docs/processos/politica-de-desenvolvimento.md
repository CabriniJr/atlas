---
titulo: Política de desenvolvimento (commits, branches, CI/CD)
id: PROC-CICD
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Política de desenvolvimento (commits, branches, CI/CD)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação | PO/PM        |

---

> Como o código nasce, é validado e chega em produção. Complementa o
> [fluxo de desenvolvimento](fluxo-de-desenvolvimento.md) (que trata da *autoria*
> best-of-two); aqui tratamos de **commits, branches, PR, pipeline e deploy**.
> Decisão de base: [ADR-0011](../arquitetura/adr/ADR-0011-ci-cd-versionamento.md).

## ⚡ Exceção MVP — branch única (economia de tokens)

> **Diretriz do PO/PM (2026-06-16):** enquanto estamos no **MVP**, o
> desenvolvimento segue numa **única branch** (sem `feat/<slug>` por tarefa, sem
> PR por história) para economizar tokens e overhead. Commits continuam em
> **Conventional Commits** para preservar o histórico e o SemVer futuro. Quando o
> MVP amadurecer, voltamos ao fluxo branch→PR→CI descrito abaixo (que permanece a
> regra-alvo). O best-of-two/curadoria também fica **opcional** nesta fase.

## Modelo: híbrido + trunk-based

- **GitHub** hospeda o repositório, os **PRs** e a **CI** (testes/checks).
- **CD é local e pull-based:** o notebook puxa do GitHub e faz deploy nos bots —
  nenhum segredo sai da máquina, alinhado com a filosofia long-poll do Atlas.
- **Trunk único:** a branch `main` é sempre verde e sempre liberável.
- **Privacidade:** vai pro GitHub o **código**, nunca o banco/dados (SQLite e
  `.env` ficam no `.gitignore`).

## Os dois ambientes (dois bots)

| Bot | Serviço systemd | Roda | Propósito |
|---|---|---|---|
| **dev** | `atlas-dev` | branch `main` (HEAD) | dogfooding de features recém-mergeadas |
| **prod** | `atlas-prod` | última **tag** `vX.Y.Z` | uso diário, estável |

## Ciclo de uma feature

```
 main ──┬───────────────────────────────────────────► (sempre verde)
        │                                         ▲
   feat/<slug>  ──commits──►  PR ──CI verde──► merge (squash)
        │                      │                  │
   best-of-two curado     testes + lint      deploy → atlas-dev
                                                   │
                              release (SemVer auto) → tag vX.Y.Z
                                                   │
                                          deploy → atlas-prod
```

1. **Branch:** sai de `main`, nome `feat/<slug>` ou `fix/<slug>` (curta, uma feature).
2. **Commits:** [Conventional Commits](#conventional-commits) ao longo do trabalho.
   A solução curada do best-of-two é commitada aqui.
3. **PR para `main`:** abre PR no GitHub. A **CI roda** (lint, commit-lint, testes).
4. **Revisão (sem QA):** a qualidade é garantida por **(a)** checks da CI verdes +
   **(b)** o registro de curadoria do Tech Lead ([revisao-e-curadoria](revisao-e-curadoria.md)).
   Não há etapa de QA separada nem revisor humano de código.
5. **Merge (squash) em `main`:** dispara CI em `main` → **deploy no `atlas-dev`**.
6. **Release:** o versionamento automático (SemVer a partir dos commits) abre/atualiza
   uma *release PR*; ao mergeá-la, cria a **tag `vX.Y.Z`** + CHANGELOG.
7. **Promoção a prod:** a tag dispara o **deploy no `atlas-prod`**. O PO/PM dá o
   **aceite de alto nível** para promover.

## Conventional Commits

Formato: `tipo(escopo): assunto`

| Tipo | Efeito no SemVer | Uso |
|---|---|---|
| `feat` | **minor** | nova capacidade |
| `fix` | **patch** | correção |
| `docs`, `test`, `refactor`, `chore`, `ci`, `build`, `perf` | nenhum | mudanças sem release |
| qualquer com `!` ou rodapé `BREAKING CHANGE:` | **major** | quebra de compatibilidade |

Regras:
- Assunto no imperativo, ≤ 72 chars, sem ponto final.
- Todo commit termina com o rodapé `Co-Authored-By: Claude ...`.
- A CI **valida o formato** (commit-lint) nos commits do PR; um hook local
  `commit-msg` valida na máquina antes do commit.

## Versionamento (SemVer automático)

- A versão sai dos commits via *release automation* ([release-please](../arquitetura/adr/ADR-0011-ci-cd-versionamento.md)).
- `main` acumula `feat`/`fix`; a release PR consolida e gera a tag + `CHANGELOG.md`.
- `prod` **só roda tags** — nunca um commit solto de `main`.

## A pipeline (estágios da CI)

Roda em **PR para `main`** e em **push para `main`**:

1. **commit-lint** — valida Conventional Commits (só em PR).
2. **lint + format** — `ruff check` + `ruff format --check`.
3. **tipos** (opcional) — `mypy`.
4. **testes** — `pytest`: unitários + harness de rotina
   ([ADR-0007](../arquitetura/adr/ADR-0007-contrato-de-teste.md)). `collect`/`gate`
   puros; `analyze` com **IA mockada** — a CI **nunca chama `claude -p` real**
   (custo e não-determinismo, P1).
5. **cobertura** (opcional) — limiar mínimo.

Todos os checks **verdes** são pré-condição de merge. `main` tem *branch
protection*: exige PR + checks verdes.

## CD — deploy pull-based

- **Mecanismo:** um *poller* local (timer systemd) verifica o GitHub; ao ver
  `main` novo ou tag nova, roda `scripts/deploy.sh <env>`:
  - `deploy.sh dev` → `git fetch`/checkout `main` → instala deps → smoke test →
    `systemctl restart atlas-dev`.
  - `deploy.sh prod` → checkout da última tag → smoke test → `systemctl restart
    atlas-prod`.
- **Rollback:** prod roda tags imutáveis; reverter = apontar o serviço para a tag
  anterior.
- Os units systemd e o poller são tarefas de infra ([backlog E4](../roadmap/backlog.md)).

## .gitignore (essencial)

`*.sqlite`/`*.db`, `.env`, segredos, `__pycache__/`, artefatos de build — **dados e
segredos nunca versionados** ([seguranca](../arquitetura/seguranca.md)).

## Pré-requisitos para ativar (tarefa de infra)

1. Criar o repositório no GitHub e adicionar o remote.
2. Instalar e autenticar o `gh` na máquina.
3. Renomear o trunk `master` → `main` e configurar branch protection.
4. Instalar o hook local `commit-msg`.

Enquanto não ativado, os workflows em `.github/workflows/` ficam prontos e
no-op-safe (passam mesmo sem código/teste ainda).
