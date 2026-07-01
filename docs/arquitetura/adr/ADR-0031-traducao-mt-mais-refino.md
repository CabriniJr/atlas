---
titulo: ADR-0031 — Tradução em dois estágios (MT bruta + refino por LLM), modular e resumível
id: ADR-0031
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-01
substitui: —
substituido-por: —
---

# ADR-0031 — Tradução em dois estágios (MT bruta + refino por LLM)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-07-01 | Tech Lead | Criação — decisão do PO: MT online + refino Haiku, modular e resumível | PO/PM |

---

## Status
`aceito` — decidido pelo PO/PM (2026-07-01). Refina o estágio 2 do [ADR-0030](ADR-0030-kind-traducao-pdf.md).

## Contexto

O estágio 2 do [ADR-0030](ADR-0030-kind-traducao-pdf.md) traduzia **cada bloco do
zero pelo LLM**. Em livros grandes isso: (a) **estoura timeout** e **esgota os tokens
da assinatura no meio**; (b) exige um modelo forte para não perder informação. O PO
pediu três coisas:

1. **Agente de tradução modular** — poder trocar o modelo; um **Haiku já basta**.
2. **Dois estágios**: um **tradutor real** produz a tradução **bruta**; o LLM apenas
   **compara origem × bruto** e **melhora o bruto** (post-edit), sem perda de informação.
3. **Persistência/resume** — pode parar no meio (tokens acabam) e **continuar de onde parou**.

## Decisão

**Estágio 2 vira dois passos:**

1. **Tradução bruta (MT real)** — via `deep-translator` (GoogleTranslator). Nova
   dependência externa + rede, aceita pelo PO em troca de qualidade do bruto e custo
   zero de IA neste passo. Cobre 100% do texto (nunca há perda: o bruto já é uma
   tradução completa).
2. **Refino por LLM** — o modelo recebe **origem + bruto** por bloco e devolve uma
   versão **polida** que respeita glossário/termos técnicos e o tom. Modelo/motor/
   timeout **configuráveis** no `spec` do `Traducao`; **default Haiku**
   (`claude-haiku-4-5-20251001`). Trabalho por chamada é menor ⇒ menos timeout.

**Modularidade:** `spec.motor`, `spec.modelo`, `spec.timeout`, `spec.refino`
(liga/desliga o passo 2 → tradução puramente MT).

**Resumível (P4 — repositório é o estado):**
- O **cache** (`data/pdfs/<origem>.<dst>.cache.json`) guarda só a tradução **refinada**
  por bloco. É salvo **a cada página** (checkpoint).
- Bloco com refino **falho** (timeout/tokens) **não é cacheado**: entra no PDF com o
  **bruto** (tradução completa, sem perda) e é **refinado no próximo run**.
- Ao bater no muro de tokens, o run **para de chamar o LLM**, **conclui o PDF com o
  bruto** e marca `status.fase = "parcial"` (resumível). Re-disparar refina o restante.

## Alternativas consideradas

| Alternativa | Prós | Contras |
|---|---|---|
| LLM traduz tudo do zero (ADR-0030 v1) | 1 passo | timeout, gasto alto, exige modelo forte |
| MT offline (argos-translate) | offline, grátis, determinístico | dep pesada + baixar pacotes (centenas de MB) |
| Só MT, sem refino | rápido, grátis | qualidade "bruta"; perde tom técnico |

## Consequências

- **Positivas:** cabe em **Haiku**; menos timeout; custo de IA menor; **sem perda** (o
  bruto é completo); **resumível** de verdade quando os tokens acabam.
- **Negativas / custos:** **nova dependência** (`deep-translator`) e **rede externa**
  no estágio 1 (tensão com "agnóstico/local", aceita pelo PO); qualidade do bruto
  depende do serviço de MT.
- **Impacto na constituição:** não muda decisões; adiciona dependência e refina o
  pipeline do ADR-0030. Atualiza o índice de ADRs.
