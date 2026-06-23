---
titulo: ADR-0024 — Kind Agente (analisador configurável)
id: ADR-0024
status: proposto
versao: 0.1
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-23
substitui: —
substituido-por: —
---

# ADR-0024 — Kind Agente (analisador configurável)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-06-23 | Tech Lead | Proposta (brainstorm Repo, carro-chefe) | — |

---

## Status
`proposto` — aguardando aceite do PO/PM.

## Contexto

A análise de IA do `repo-sync` é hoje **hardcoded** na rotina: modelo fixo, nível de
contexto fixo, prompt embutido ([repo_sync.py](../../../src/atlas/rotinas/repo_sync.py)).
No brainstorm do Repo o PO pediu um **analisador configurável e reutilizável** — não
só do Repo, mas de qualquer Kind: motor + nível de contexto + prompt/personalidade +
política. Por ser transversal, foi **promovido a ADR próprio** (em vez de embutido no
ADR-0023).

Ele se apoia em dois ADRs: [0016](ADR-0016-ia-plugavel-kind-prompt.md) (prompt
plugável via Kind `Prompt`) e [0022](ADR-0022-motor-de-ia-plugavel.md) (motor
selecionável). O `Agente` é a peça que **amarra** prompt + motor + contexto + política
num objeto configurável.

## Decisão

1. **Kind `Agente`** (primeira classe, schema-driven — [ADR-0017](ADR-0017-gui-por-kind-abstrai-api.md)).
   `spec`:
   - `motor` — referência/seleção de motor (ADR-0022) + `modelo`.
   - `nivel_contexto` — `none | resumo | completo` (regula custo×qualidade).
   - `prompt` — referência a um Kind `Prompt` (ADR-0016) ou template inline.
   - `politica` — limites/regras (timeout, budget, escopo).
2. **Consumido por referência.** `Repo.spec.analyze.agente` (ADR-0023) aponta para um
   `Agente`; qualquer rotina/Kind que faça análise pode reusar o mesmo objeto.
3. **Nível de contexto regulável** — o quanto de contexto do projeto entra no prompt
   (nada / resumo represado / corpus completo), modulando gasto.
4. **Execução:** o motor (ADR-0022) roda o prompt (ADR-0016) com o contexto no nível
   pedido, em **modo análise 2a single-turn, sem tools**
   ([ADR-0001](ADR-0001-ia-em-dois-modos.md), [seguranca](../seguranca.md)). O
   `Agente` **não** é o "agente 2b" com ferramentas do meta-loop.
5. **Agente Builder (evolução futura — backlog E7-24):** dado um prompt em linguagem
   natural, configura o Kind pedido **nos conformes do projeto** (schema/regras) e
   passa por **curadoria** ([ADR-0013](ADR-0013-barreira-de-entrada.md),
   [revisor-curador](../../agentes/revisor-curador.md)) antes de ativar. Não faz parte
   do escopo mínimo deste ADR.

## Alternativas consideradas

| Alternativa | Prós | Contras | Veredito |
|---|---|---|---|
| **Kind `Agente` (motor + contexto + prompt + política), reutilizável** | configurável e reusável por qualquer Kind; custo sob controle; base do Agente Builder | +1 Kind; schema/validação; acopla 0016/0022 | **escolhida** |
| Parâmetros soltos na rotina (status quo) | nada a criar | não reutiliza; volta ao hardcode | não atende |
| Estender só o Kind `Prompt` | reusa ADR-0016 | cobre prompt, não motor/contexto/política | insuficiente |
| Agente com tools (estilo 2b) | mais poderoso | risco de segurança (meta-loop, [ADR-0003](ADR-0003-seguranca-meta-loop.md)) | fora de escopo (é análise 2a) |

## Consequências

- **Positivas:** análise configurável e reutilizável por todo o sistema; nível de
  contexto controla custo; centraliza motor+prompt+política num objeto; abre caminho
  para o Agente Builder.
- **Negativas / custos:** +1 Kind a manter (schema, ações, validação); acoplamento com
  ADR-0016 (Prompt) e ADR-0022 (motor); risco de confundir `Agente` (análise 2a) com o
  agente 2b do meta-loop — mitigado pela regra 4.
- **Impacto na constituição:** estende ADR-0016/0017; reforça "agnóstico e plugável" e
  "economia do recurso escasso". Nenhuma decisão anterior muda.

## Pendências

- Schema exato do `Agente` e seus defaults (motor `claude`, `nivel_contexto=resumo`?).
- Relação fina com o Kind `Prompt` (referência vs. inline) e com a `analyze_policy` do Repo.
- Escopo, gate de curadoria e segurança do **Agente Builder** (item de backlog separado).
- Validação empírica dos níveis de contexto em custo×qualidade.
