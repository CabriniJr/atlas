---
titulo: Mapa da documentação
id: DOC-INDEX
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Documentação do Atlas — fonte de verdade

Esta pasta é a **fonte de verdade** do projeto. Código, decisões e planejamento
derivam daqui. Todo documento segue o [padrão de documento](#padrão-de-documento)
(header + histórico de revisão).

## Mapa

### 📐 Visão — *por que existimos*
- [`visao/visao-produto.md`](visao/visao-produto.md) — problema, dores, north star, não-objetivos.
- [`visao/principios.md`](visao/principios.md) — princípios de produto e engenharia.
- [`visao/personas-e-uso.md`](visao/personas-e-uso.md) — quem usa e como.

### 🏛️ Arquitetura — *como é construído*
- [`arquitetura/visao-geral.md`](arquitetura/visao-geral.md) — a arquitetura geral.
- [`arquitetura/constituicao.md`](arquitetura/constituicao.md) — o núcleo invariante.
- [`arquitetura/modelo-de-dados.md`](arquitetura/modelo-de-dados.md) — schema SQLite.
- [`arquitetura/ciclo-de-vida-rotina.md`](arquitetura/ciclo-de-vida-rotina.md) — o contrato da rotina.
- [`arquitetura/motor-de-ia.md`](arquitetura/motor-de-ia.md) — análise (2a) vs agente (2b).
- [`arquitetura/seguranca.md`](arquitetura/seguranca.md) — modelo de ameaça e meta-loop.
- [`arquitetura/adr/`](arquitetura/adr/README.md) — registros de decisão de arquitetura.

### 🗺️ Roadmap — *o que vamos fazer e quando*
- [`roadmap/amadurecimento.md`](roadmap/amadurecimento.md) — estágios de maturidade (M0→M3).
- [`roadmap/backlog.md`](roadmap/backlog.md) — épicos e histórias priorizadas.
- [`roadmap/planejamento.md`](roadmap/planejamento.md) — marcos e releases.

### 🤖 Agentes — *quem constrói*
- [`agentes/README.md`](agentes/README.md) — catálogo de agentes especializados.
- [`agentes/diretrizes-gerais.md`](agentes/diretrizes-gerais.md) — regras p/ todo agente.
- [`agentes/tech-lead.md`](agentes/tech-lead.md) — o orquestrador/curador.
- [`agentes/dev.md`](agentes/dev.md) — o agente de desenvolvimento.
- [`agentes/revisor-curador.md`](agentes/revisor-curador.md) — critérios de curadoria.

### ⚙️ Processos — *como trabalhamos*
- [`processos/ciclo-ideias-para-implementacao.md`](processos/ciclo-ideias-para-implementacao.md) — **LER PRIMEIRO:** o fluxo padrão: ideia → doc → implementação.
- [`processos/fluxo-de-desenvolvimento.md`](processos/fluxo-de-desenvolvimento.md) — o fluxo background + curadoria.
- [`processos/politica-de-desenvolvimento.md`](processos/politica-de-desenvolvimento.md) — commits, branches, PR, CI/CD, deploy.
- [`processos/definicao-de-pronto.md`](processos/definicao-de-pronto.md) — DoR / DoD.
- [`processos/revisao-e-curadoria.md`](processos/revisao-e-curadoria.md) — best-of-two na prática.

### 📝 Specs — *como cada feature funciona em detalhe*
Specs detalhadas que guiam a implementação (requisitos, fluxo, dados, erros, testes).
- [`specs/barreira-entrada.md`](specs/barreira-entrada.md) — registro só com intenção (item 0).
- [`specs/executor-e-notificacao.md`](specs/executor-e-notificacao.md) — ciclo de vida + notificação (item 1).
- [`specs/scheduler.md`](specs/scheduler.md) — agendador + catch-up (item 2).
- [`specs/meta-loop-chat.md`](specs/meta-loop-chat.md) — criar rotinas conversando (item 3).
- [`specs/interface-config-chat.md`](specs/interface-config-chat.md) — comandos de config (item 4).
- [`specs/trackers-via-chat.md`](specs/trackers-via-chat.md) — trackers pelo chat (item 5).
- [`specs/pool-de-ideias.md`](specs/pool-de-ideias.md) — captura de ideias/lições + autoimplementação (prioridade máxima).
- [`specs/alarmes.md`](specs/alarmes.md) — alarmes e lembretes pelo chat.

### 📖 Apoio
- [`glossario.md`](glossario.md) — vocabulário do projeto.
- [`superpowers/specs/`](superpowers/specs/) — specs de design (lastro histórico das decisões).

## Padrão de documento

Todo documento `.md` começa com um header em YAML e, logo abaixo do título, uma
tabela de histórico de revisão:

```markdown
---
titulo: <título legível>
id: <ID curto, ex. ARQ-DADOS>
status: rascunho | em-revisao | aprovado | obsoleto
versao: <semver simples, ex. 1.2>
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: AAAA-MM-DD
---

# Título

## Histórico de revisão
| Versão | Data       | Autor     | Mudança   | Aprovado por |
|--------|------------|-----------|-----------|--------------|
| 1.0    | AAAA-MM-DD | Tech Lead | Criação   | PO/PM        |
```

**Status:** `rascunho` (em escrita) → `em-revisao` (aguardando PO/PM) →
`aprovado` (vigente) → `obsoleto` (substituído; aponta o sucessor).

## Convenções

- **Idioma:** PT-BR; termos técnicos consagrados em inglês (ADR, backlog, gate).
- **Um arquivo = um assunto.** Documento que cresce demais é dividido.
- **Links relativos** entre documentos (navegável no Git e em IDE).
- **Nada é apagado:** documento superado vira `obsoleto` com link para o sucessor.
