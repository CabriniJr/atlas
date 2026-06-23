---
titulo: ADR-0020 — Views especializadas por Kind (o "quadro branco")
id: ADR-0020
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-23
substitui: —
substituido-por: —
---

# ADR-0020 — Views especializadas por Kind (o "quadro branco")

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-06-23 | Tech Lead | Proposta (brainstorm Repo, carro-chefe) | — |

---

## Status
`aceito` — aceito pelo PO/PM (2026-06-23); em implementação ágil.

## Contexto

O [ADR-0017](ADR-0017-gui-por-kind-abstrai-api.md) deu a todo Kind uma GUI
schema-driven (form tipado + ações que chamam a API). Mas essa GUI é **genérica**:
um card/formulário de manifesto e botões. O PO quer um degrau a mais — cada Kind com
uma **renderização especializada**: um relógio para `Timer`, um editor para `Doc`,
dashboards + git-graph para `Repo`. A metáfora é um **quadro branco**: uma superfície
única onde cada Kind "desenha" sua própria visão.

Dois fatos do brainstorm do Repo tornam isso urgente: (1) o Repo
([ADR-0023](ADR-0023-especializacao-kind-repo.md)) precisa de uma render rica
(git-graph, progresso) que não cabe no card genérico; (2) os Kinds auxiliares
`Branch`/`Commit`/`Diff` precisam existir na API mas **não poluir** o explorer ao
lado de Kinds rotineiros. É preciso um **mecanismo genérico** — não dialog hardcoded
por Kind — coerente com "o front é abstração da API, não fonte de verdade".

## Decisão

1. **Superfície "quadro branco".** Uma aba/seção do dashboard onde cada Kind pluga um
   **componente de render especializado**. É um *slot* por Kind, não uma tela por
   Kind hardcoded.
2. **Registro de renders por Kind** (render registry) no front: `kind → componente`.
   Quem não registra cai no **render genérico** atual (card + form de manifesto) — o
   Kind continua 100% funcional sem render própria.
3. **Atributo de visibilidade no schema.** O `_KIND_SCHEMA`/`GET /_schema` ganha
   `hidden` (e, quando aninhado, `parent`). Kinds ocultos somem do explorer principal
   e aparecem **aninhados** dentro da render do seu agregado (ex.: `Branch`/`Commit`/
   `Diff` dentro do `Repo`).
4. **Zero lógica de negócio no front** (reforça [ADR-0017](ADR-0017-gui-por-kind-abstrai-api.md)):
   a render só **lê dados da API** e **chama verbos** (`/_cmd`, `/_run`, `PUT`).
   Nenhuma regra de domínio migra para o cliente.
5. **Front modularizado por Kind.** O dashboard embutido (hoje monolítico em
   [api.py](../../../src/atlas/api.py)) é quebrado em módulos por responsabilidade —
   ex.: `dashboard/kinds/<kind>/*` — ainda servido pela API enquanto o SPA não tem
   paridade ([ADR-0019](ADR-0019-interfaces-clientes-da-api.md)).
6. **Repo é a render-referência** (carro-chefe, ADR-0023). `Timer`→relógio e
   `Doc`→editor são os próximos candidatos.

**Regra de extensão:** adicionar uma render = registrar o componente (+ opcionalmente
marcar visibilidade no schema). Sem isso, o Kind usa o render genérico — nunca quebra.

## Alternativas consideradas

| Alternativa | Prós | Contras | Veredito |
|---|---|---|---|
| **Slot de render por Kind + registry + visibilidade no schema** | genérico; reusa o schema; front fino; novos Kinds plugam sem mexer no core | manter registry + componentes + atributo de visibilidade | **escolhida** |
| Dialogs/telas hardcoded por Kind no front | controle fino | duplica regras; front vira fonte de verdade | viola abstração da API |
| Só o form genérico do ADR-0017 | já existe | não entrega "render especializada" | não atende a diretriz |
| Migrar já para o SPA dedicado (`web/`) | separação limpa | sem paridade hoje | adiado pelo ADR-0019 |

## Consequências

- **Positivas:** experiência rica e específica por Kind; reuso do schema; front
  permanece fino e plugável; Kinds ocultos organizam o explorer; destrava a render do
  Repo (ADR-0023).
- **Negativas / custos:** manter o registry e os componentes de render; novo atributo
  de visibilidade no schema/core; risco de lógica vazar para o front (mitigado pela
  regra 4 e revisão).
- **Impacto na constituição:** estende o ADR-0017; reforça "agnóstico e plugável" e "o
  repositório é o estado". Nenhuma decisão anterior muda.

## Pendências

- Contrato exato do componente de render (props, ciclo de dados, como declara as ações).
- Ordem dos próximos Kinds a ganhar render (Timer, Doc) após o Repo.
- Quando e como migrar as renders para o SPA dedicado (ADR-0019), evitando retrabalho.
- Semântica de `parent`/aninhamento para Kinds ocultos multinível.
