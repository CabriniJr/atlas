---
titulo: ADR-0036 — Render editorial por modelo semântico + re-layout (WeasyPrint)
id: ADR-0036
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-02
substitui: —
substituido-por: —
---

# ADR-0036 — Render editorial por modelo semântico + re-layout (WeasyPrint)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-07-02 | Tech Lead | Criação — decisão do PO: motor editorial de alta fidelidade (modelo semântico + HTML/CSS + WeasyPrint), substituindo o in-place do ADR-0033 como default | PO/PM |

## Status
`aceito` — decidido pelo PO/PM (2026-07-02). Substitui o **motor default** do render
editorial: o in-place do [ADR-0033](ADR-0033-render-editorial-hibrido.md) fica como
fallback (`render_motor="pymupdf"`); o novo default é `render_motor="html"`.

## Contexto

O in-place (ADR-0033/E9-01b) reinsere texto no bbox do bloco. Na prática entregou
qualidade **inaceitável** na run de controle: **sem justificação**, **perda de
bold/itálico** (o bloco era redesenhado numa única fonte fallback), **páginas de 1
linha** (continuação por página) e sem controle tipográfico. O PO definiu o alvo: a
parte editorial é uma **substituição de texto no documento** respeitando estilo,
elementos e normas — como editar um Word, onde o documento **remolda** para acomodar
o texto traduzido (mais longo), preservando design, imagens, código e ênfases.

O PyMuPDF in-place não alcança isso: não faz fluxo contínuo, justificação nem
tipografia rica. Precisamos de um **motor de layout de verdade**.

## Decisão

Motor **por modelo semântico + re-layout**, em `traducao/editorial_html.py`:

1. **Modelo semântico** extraído do PDF: por bloco, o *papel* (título/parágrafo/
   lista/código/legenda) e o *estilo dominante* (bold, itálico, mono, tamanho, cor)
   a partir das flags de span do PyMuPDF; e as **imagens** (bytes preservados).
2. **Reintrodução só do texto bruto traduzido** — código (mono) e imagens seguem o
   original; ênfases (bold/itálico) e hierarquia de fonte são reaplicadas por bloco.
3. **Re-layout** do documento inteiro como fluxo **HTML + CSS** (justificado,
   `hyphens:auto` pt-BR, hierarquia de títulos, `<pre>` p/ código, `<ul>` p/ listas,
   `page-break` controlado) renderizado com **WeasyPrint** → PDF. O `@page` usa o
   tamanho e as margens medianas do original.

**Config:** `spec.render_motor` = `html` (default) | `pymupdf` (fallback). Resiliente:
se o WeasyPrint faltar ou falhar, cai para o in-place (ADR-0006).

**Fidelidade vs. remold:** não se preserva a posição pixel-a-pixel do original (o doc
remolda, como pedido); preservam-se **estilo, elementos, ordem e design**: imagens,
código, ênfases, hierarquia, justificação. Resultado medido na run de controle:
337 págs (vs. 571 do in-place), justificado, código em monospace preservado, imagens
intactas, zero glyphs perdidos.

## Alternativas consideradas

| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| **Modelo semântico + WeasyPrint (escolhida)** | fluxo real, justificação, estilos, tipografia, controle total | re-layout (não pixel-exato); dep WeasyPrint | é o alvo do PO |
| Roundtrip PDF→DOCX→PDF (LibreOffice) | engine Word madura | fidelidade do pdf2docx imprevisível em 2 colunas/tabelas | risco de layout torto |
| Evoluir in-place (ADR-0033) | sem deps novas | teto de qualidade baixo; sem justificação/tipografia | não alcança editorial |

## Consequências

- **Positivas:** PDF final **usável**, nível editorial; estilo/elementos preservados;
  sem páginas ralas; determinístico e barato (re-render do cache sem IA, E9-05).
- **Negativas / custos:** nova dependência (WeasyPrint + libs nativas pango/cairo, já
  presentes); layout não é pixel-exato ao original (esperado — remold); inline
  bold/itálico *dentro* de um parágrafo ainda é aplicado por bloco dominante (refino
  futuro: tradução preservando marcação de run); multi-coluna vira fluxo único (MVP).
- **Impacto na constituição:** nenhum invariante muda; troca o default do render do
  ADR-0033 (que vira fallback). Atualiza índice de ADRs e backlog (E9-01c).
