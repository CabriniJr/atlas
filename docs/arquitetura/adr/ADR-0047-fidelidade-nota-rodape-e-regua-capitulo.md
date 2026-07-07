---
titulo: ADR-0047 — Fidelidade de conteúdo/gráfica: sobrescrito de nota de rodapé e régua do abre-capítulo
id: ADR-0047
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-07
substitui: —
substituido-por: —
---

# ADR-0047 — Sobrescrito de nota de rodapé + régua do abre-capítulo

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-07-07 | Tech Lead | Marcador de nota de rodapé re-elevado a sobrescrito Unicode; régua (border-bottom) do abre-capítulo O'Reilly detectada do original | PO/PM |

---

## Status
`aceito` — implementado (`editorial_html._aplicar_sobrescritos`, `_regua_sob_titulo`).

## Contexto

Auditoria visual (sample→avalia→melhora→aplica) dos três livros re-renderizados,
com foco pedido pelo PO em **"fidelidade gráfica e de conteúdo"**. Dois defeitos
recorrentes apareceram, ambos no Prometheus (template O'Reilly), comparando
página a página com o original:

1. **Marcador de nota de rodapé virava número solto na prosa.** No original, a
   referência é um span **sobrescrito** (flag bit0 do fitz, cor vinho): "the
   second member¹". Na extração, o texto dos spans é concatenado num bloco só e
   traduzido como unidade — o "1" sobrescrito desce pra linha de base e a MT
   ainda insere um espaço: "o segundo membro **1** da CNCF". Some no meio da
   frase como um número perdido (visto em "scripts. **4** O ano de 1997",
   "texto simples **2** faz…", etc.) — parece erro de digitação.
2. **Abre-capítulo sem a régua.** O template O'Reilly desenha uma **linha
   horizontal fina** logo abaixo do título de capítulo ("Chapter 1. What Is
   Prometheus?" com o traço embaixo). O render editorial não a reproduzia — o
   corpo começava colado no título.

Restrição-chave: o cache de tradução é keyado pelo texto do bloco (ADR-0031);
qualquer correção que **mude o texto do bloco** invalida o cache e força
re-tradução. As duas correções aqui são feitas **no render**, sem tocar no texto
que vai pro cache — zero re-tradução.

## Decisão

1. **Re-elevar o marcador de nota (`_aplicar_sobrescritos`).** No render, com os
   spans do bloco em mãos, identifica os que são **sobrescrito** (`flags & 1`) e
   **só dígitos** (1–3 chars) — os marcadores de nota. Na prosa **já traduzida**,
   troca a **1ª ocorrência isolada** de cada marcador (lookarounds `(?<!\d)…(?!\d)`
   pra não pegar o "1" dentro de "2016") pelo **glifo sobrescrito Unicode**
   (`0-9` → `⁰¹²³⁴⁵⁶⁷⁸⁹`), comendo um espaço antes: "membro 1 da" → "membro¹ da".
   Sem markup (`<sup>`) e sem re-tradução — o glifo já é sobrescrito e sobrevive
   como texto puro. Aplicado só na prosa (nunca em `<pre>`/código).
2. **Reproduzir a régua (`_regua_sob_titulo`).** Detecção **fiel** (não inventa o
   traço): acha o maior span de texto da página (o título, ≥ 20pt) e exige um
   traço horizontal **largo** (> 50% da largura) e **fino** (< 3pt) numa faixa
   curta (≤ 24pt) logo abaixo da base dele. Quando existe, injeta
   `border-bottom` no heading. Verificado: `True` só no abre-capítulo do
   Prometheus; `False` em corpo de Prometheus, abre-capítulo do Observability
   (que usa rótulo "CAPÍTULO N" sem régua) e do Kubernetes (numeral decorativo,
   ADR-0041) — zero falso-positivo.

## Alternativas consideradas

| Alternativa | Prós | Contras | Veredito |
|---|---|---|---|
| Sobrescrito via `<sup>` reconstruindo o span na posição | semântico | posição do span se perde na tradução/refluxo; teria que re-casar texto→span | rejeitada — glifo Unicode não precisa de markup |
| Converter o marcador a Unicode na **extração** (antes de traduzir) | marcador não polui a MT | muda o texto do bloco → invalida o cache → re-traduz o livro todo; risco da LLM "normalizar" o glifo | rejeitada — correção no render, sem re-tradução |
| Régua fixa (border-bottom em todo heading que casa "Capítulo N") | trivial | põe régua onde o original não tem (apêndice Manning, capítulo Observability) | rejeitada — detecção do traço real no original |

## Consequências

- **Positivas:** notas de rodapé deixam de aparecer como números soltos na prosa
  (fidelidade de conteúdo); abre-capítulo O'Reilly ganha a régua do original
  (fidelidade gráfica). Ambas sem re-tradução (render-only), então re-renderizam
  de graça do cache.
- **Negativas / custos:** a troca do marcador é heurística — se um número igual
  ao marcador aparecer isolado **antes** da posição da nota no mesmo bloco (ex.:
  "seção 2 … como visto²"), pode elevar o número errado. Raro (o marcador quase
  sempre é o único dígito isolado do bloco) e de baixo dano (elevar um número é
  raramente pior que um número solto na linha de base). A régua depende de o
  traço do original ser um drawing vetorial detectável (é, no O'Reilly).
- **Impacto na constituição:** estende ADR-0041/ADR-0036 (motor editorial ganha
  mais dois reparos de fidelidade render-time, sem re-tradução — ADR-0031).

## Pendências
- Nota de rodapé multi-dígito não-sequencial em bloco com outro número isolado
  igual: possível troca no lugar errado (heurística de 1ª ocorrência).
- Régua só reproduzida quando é drawing vetorial no original (não cobre régua
  embutida em imagem de fundo).
