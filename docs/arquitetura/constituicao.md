---
titulo: Constituição — o núcleo invariante
id: ARQ-CONSTITUICAO
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Constituição — o núcleo invariante

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação | PO/PM        |
| 1.1    | 2026-06-16 | Tech Lead | Decisões #13 (barreira de entrada) e #14 (pool de desenvolvimento) | PO/PM |

---

> Este documento lista o que **não muda sem um ADR que o substitua**. É o contrato
> mais forte do projeto. Qualquer agente que precise contrariar algo daqui **deve
> abrir um ADR** e obter aceite do PO/PM antes de codificar.

## Decisões travadas

| # | Tema | Decisão | ADR |
|---|---|---|---|
| 0 | Core | O backend é uma **API de objetos (estilo Kubernetes)**: tudo é `Resource` (kind+spec+status), com **verbos uniformes** (get/describe/apply/delete). Interfaces (Telegram, web) são **adapters** do core. | [0015](adr/ADR-0015-core-api-de-objetos.md) |
| 1 | Interface | Bot do **Telegram** (long-poll, sem domínio) **+ web app (Vercel)**, ambos adapters da API central. | [0015](adr/ADR-0015-core-api-de-objetos.md) |
| 2 | Motor de IA | **Claude Code local** na assinatura, dividido em **análise single-turn (2a)** e **agente (2b, só meta-loop)** — sem billing por token de API. | [0001](adr/ADR-0001-ia-em-dois-modos.md) |
| 3 | Padrão de rotina | **Script-primeiro, agente só quando precisa** (ciclo de vida). | — |
| 4 | Rotinas | **Pastas plugáveis** auto-descobertas; o repositório é o estado. | — |
| 5 | Modos | **Operação** e **desenvolvimento** em sessões separadas; handoff por arquivo. | [0009](adr/ADR-0009-handoff-entre-modos.md) |
| 6 | Hospedagem | **Notebook Linux**, sempre ligado. Empacotamento preferido **Docker** (`restart: always`); systemd permanece válido. Mesma imagem migra para host always-on. | [0012](adr/ADR-0012-empacotamento-docker.md) |
| 7 | Resumo diário | Rotina built-in, **única que sempre usa IA** (Sonnet, modo 2a). | [0001](adr/ADR-0001-ia-em-dois-modos.md) |
| 8 | Criação de rotina | **Meta-loop:** descrição no Telegram → geração via Claude Code. | [0003](adr/ADR-0003-seguranca-meta-loop.md) |
| 9 | Contrato do `collect` | Retorno **tipado** `CollectResult { data, store }`. | [0004](adr/ADR-0004-contrato-collect.md) |
| 10 | Orçamento de token | **Reativo** (pós-chamada) + teto global pré-despacho. | [0005](adr/ADR-0005-orcamento-reativo.md) |
| 11 | Segurança do meta-loop | Código gerado nasce **inativo**; ativação exige revisão humana. | [0003](adr/ADR-0003-seguranca-meta-loop.md) |
| 12 | CI/CD e versionamento | **Híbrido** (GitHub p/ PR+CI, deploy local pull), **trunk-based + tags**, **Conventional Commits + SemVer auto**, sem QA. | [0011](adr/ADR-0011-ci-cd-versionamento.md) |
| 13 | Barreira de entrada | Atividade só é registrada com **intenção explícita** (trigger declarado, micro-sintaxe de tracker ou `/reg`); não-match vira ajuda, **não** registro. | [0013](adr/ADR-0013-barreira-de-entrada.md) |
| 14 | Pool de desenvolvimento | O pool prioriza itens e **auto-gera** rotinas (meta-loop); a **ativação é sempre humana** — reforça #4 e #11, não os revoga. | [0014](adr/ADR-0014-pool-de-ideias-desenvolvimento.md) |

## Invariantes de comportamento

1. **A documentação é a fonte de verdade.** Código diverge → ADR ou correção.
2. **Zero IA é o caminho padrão.** IA só na análise/geração genuína.
3. **O motor é agnóstico.** Nenhum domínio vira código do core.
4. **Nada de auto-execução de código gerado.** Meta-loop → revisão humana → ativa.
5. **Segredos nunca no versionamento.**
6. **Monousuário.** O bot só responde ao ID do dono.

## Como alterar a constituição

1. Abra um **ADR** propondo a mudança (contexto, alternativas, consequências).
2. Status `proposto` → discussão com o PO/PM.
3. Aceite do PO/PM → status `aceito`; o ADR atualiza esta tabela e marca o ADR
   anterior (se houver) como `substituído por`.
4. Só então o código pode mudar.

## Itens em aberto (a decidir)

Rastreados no [backlog](../roadmap/backlog.md) e na seção de pendências dos ADRs:
- Teto de uso da assinatura Pro para rotinas pesadas (e se vale fallback).
- Formato exato do sync do Librera no setup do dono.
- Quais rotinas entram como built-in além de resumo diário e meta-loop.
- Política de retenção/limpeza do histórico de runs.
- Valor da janela de catch-up do resumo diário.
