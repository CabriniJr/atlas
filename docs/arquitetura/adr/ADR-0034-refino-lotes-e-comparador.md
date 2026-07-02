---
titulo: ADR-0034 — Refino em lotes maiores + comparador de consistência opt-in
id: ADR-0034
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-01
substitui: —
substituido-por: —
---

# ADR-0034 — Refino em lotes maiores + comparador de consistência opt-in

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-07-01 | Tech Lead | Criação — decisão do PO: lotes maiores + comparador geral opt-in (Opus) | PO/PM |

---

## Status
`aceito` — decidido pelo PO/PM (2026-07-01). Sub-projeto **B** (E9-02) do épico
tradutor editorial; aprofunda o refino do [ADR-0031](ADR-0031-traducao-mt-mais-refino.md)
e alimenta o render do [ADR-0033](ADR-0033-render-editorial-hibrido.md).

## Contexto

O PO pediu: **tradução bruta → refino em lotes maiores → um comparador geral mais
potente** para consistência do documento inteiro. O refino do ADR-0031 processa por
página com `lote_refino=20`; termos e tom podem divergir entre páginas (ex.: um termo
traduzido de dois jeitos). IA é o **recurso escasso** (princípio #1), então o passe
mais caro (Opus) deve ser **opcional**.

## Decisão

1. **Lotes maiores:** `ConfigTraducao.lote_refino` default **20 → 60**. Mantém o
   **checkpoint por página** (ADR-0031 intacto): só aumenta o nº de blocos por chamada
   de refino, dando mais contexto ao LLM e menos chamadas.
2. **Comparador de consistência (opt-in):** `spec.comparador` (default `false`).
   Quando ligado e a tradução **conclui** (não parcial), um modelo **mais potente**
   (Opus; `spec.modelo_comparador`, senão o default forte) recebe os termos/nomes
   traduzidos do documento e devolve um **mapa de unificação** `{variante: canônico}`.
   O mapa é aplicado **deterministicamente** às traduções (substituição) **antes do
   render** — barato, mecânico, sem reescrever prosa. Foco: consistência de
   terminologia/nomes.
3. **Modularidade (quanto/qual IA):** `spec.refino` (liga/desliga refino),
   `spec.lote_refino`, `spec.comparador`, `spec.modelo_comparador`, `spec.modelo`/
   `spec.motor`. (Os níveis nomeados — rascunho/padrão/editorial — ficam para o
   [E9-04].)

## Alternativas consideradas

| Alternativa | Prós | Contras |
|---|---|---|
| **Mapa de unificação + aplicar (escolhida)** | barato, determinístico, consistência global | não reescreve prosa (só termos/nomes) |
| Reescrita global em lotes (Opus no doc todo) | qualidade máxima | custo alto de IA (fere princípio #1) |
| Só relatório (sem auto-aplicar) | mais barato | não melhora o PDF sozinho |

## Consequências

- **Positivas:** consistência de termos/nomes no documento; opt-in respeita a economia
  de IA; render editorial (ADR-0033) recebe traduções já unificadas.
- **Negativas / custos:** o comparador só unifica termos (não reescreve tom/coesão —
  isso é o Agente editor, [E9-03]); lote maior aumenta o custo por chamada e o risco
  de timeout (mitigado: default 60, configurável; resume por página preservado).
- **Impacto na constituição:** nenhum; aprofunda ADR-0031 e conecta ao ADR-0033.
  Atualiza índice de ADRs e backlog (E9-02).
