---
titulo: Spec — Render editorial ipsis-litteris (sub-projeto A)
id: SPEC-TRADUCAO-RENDER-EDITORIAL
status: em-revisao
versao: 0.2
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-02
---

# Spec — Render editorial ipsis-litteris (sub-projeto A)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-07-01 | Tech Lead | Criação — primeiro sub-projeto do épico editorial | — |
| 0.2    | 2026-07-02 | Tech Lead | +fonte real embutida, ênfase inline, cor de link herdada, listas numeradas, notas de rodapé nativas, fólio dinâmico (`string-set`), quebra de página extraída por nível de heading (ADR-0041) | PO/PM |

---

> Motor de remontagem que produz um PDF traduzido **ipsis litteris** ao original — só
> o texto muda — em **nível editorial**. Implementa a decisão do
> [ADR-0033](../arquitetura/adr/ADR-0033-render-editorial-hibrido.md), aprofundando o
> [ADR-0030](../arquitetura/adr/ADR-0030-kind-traducao-pdf.md). É o **sub-projeto A**
> do épico *tradutor AI-augmented + render editorial* (rastreabilidade:
> [backlog](../roadmap/backlog.md#épico-tradutor-editorial)).

## Objetivo e não-objetivos

**Objetivo:** dado o PDF original + os blocos traduzidos (com metadados), gerar um PDF
onde texto está traduzido e **imagens, charts, fontes, estilo e ordem** são
preservados; a prosa **reflui** quando cresce, gerando **página de continuação** se
transbordar; termos sem tradução ganham **nota de rodapé** opcional.

**Não-objetivos (MVP):** re-layout de tabelas ricas e reflow multi-coluna (encaixam
in-place; ADR futuro); OCR de PDF-imagem (fora de escopo); edição tipográfica além do
necessário para caber/refluir.

## Contrato com o sub-projeto B (qualidade AI-augmented)

O render **não traduz**. Recebe, por página, blocos já traduzidos:

```
BlocoRenderizavel:
  id: int
  papel: "prosa" | "encaixado" | "imutavel"   # classificado em extracao
  bbox: (x0, y0, x1, y1)
  spans: [Span]          # fonte, tamanho, cor, estilo do original (p/ herdar)
  origem: str            # texto original (p/ nota de rodapé/diagnóstico)
  traducao: str          # texto final (vindo do cache/pipeline)
  notas: [ {termo, glosa} ]   # opcional: termos mantidos em outro idioma
```

`papel` vem da extração (heurística) e pode ser sobrescrito por metadados do bloco.
Fallback seguro: papel desconhecido ⇒ trata como `encaixado` (nunca perde conteúdo).

## Classificação de papel (em `extracao`)

| Papel | Heurística (MVP) | Render |
|---|---|---|
| `imutavel` | bloco sem texto tradutível (imagem/chart), código monoespaçado, fórmula | não toca; redação só em spans de texto |
| `encaixado` | legenda/label curto próximo a figura/tabela; célula de tabela; cabeçalho/rodapé | fit-in-place (auto-fit no bbox, ADR-0030) |
| `prosa` | parágrafo de corpo (largura ≈ coluna, múltiplas linhas) | reflow + página de continuação |

A heurística vive em `extracao.py` (classificação) e é **testável isoladamente** com
PDFs-fixture. Erros de classificação nunca descartam texto.

## Motor de reflow da prosa

1. **Medição:** com a fonte/tamanho herdados do bloco, medir a altura que a `traducao`
   ocupa na **largura do bbox** (word-wrap por largura, via PyMuPDF `TextWriter`/
   `insert_textbox` em modo de medição).
2. **Crescimento no fluxo:** se a altura ≤ espaço disponível até o próximo bloco de
   fluxo, insere no lugar (pode reduzir levemente o tamanho, dentro de um mínimo
   legível — ex.: ≥ 90% do original). Caso contrário, o bloco **empurra** os blocos de
   fluxo seguintes para baixo.
3. **Transbordo → página de continuação:** o texto que não cabe na página é
   **paginado** em uma nova página inserida **imediatamente após** a de origem, com as
   mesmas margens/geometria. A ordem de leitura é preservada. Blocos `imutavel`/
   `encaixado` **não** migram — só a prosa transborda.
4. **Idempotência:** a paginação é função pura de (bbox, fonte, texto) ⇒ re-render de
   uma página já pronta é determinístico (compatível com o checkpoint do ADR-0031).

### Limite de legibilidade
Nunca encolher a fonte abaixo de um piso configurável (`min_fonte_pct`, default 90%).
Preferir sempre refluir/paginar a espremer.

## Notas de rodapé (opt-in)

Quando um bloco carrega `notas` (termos mantidos no idioma de origem, vindos do
glossário), o render:
- marca a 1ª ocorrência do termo com um índice sobrescrito (¹, ²…);
- acumula as glosas no **pé da página** correspondente, em fonte menor, acima da
  margem inferior;
- se o rodapé competir por espaço, ele participa do cálculo de transbordo (empurra
  prosa para a continuação).

Controlado por `spec.notas_rodape` (default `false`).

## Superfície (código)

- `traducao/extracao.py` — **+classificação de papel** (`papel` no `BlocoTraducao`).
- `traducao/layout.py` (**novo**) — medição, reflow, paginação (motor puro, sem IO).
- `traducao/remontagem.py` — orquestra: redação + fit-in-place + chama `layout` para
  prosa + rodapés; insere páginas de continuação.
- `traducao/pipeline.py` — passa os blocos+papel ao render; inalterado no fluxo de
  tradução.
- `Traducao.spec`: `+min_fonte_pct` (default 90), `+notas_rodape` (default false).
- `traducao/extracao.py` (ADR-0041) — **+marcadores de ênfase inline** no
  `BlocoTraducao.texto`; **+papel `nota_rodape_original`** distinto de fólio.
- `traducao/traducao_ia.py` (ADR-0041) — `montar_prompt_refino` ganha regra de
  preservar marcador de ênfase.
- `traducao/editorial_html.py` (ADR-0041) — fonte real embutida (`@font-face`);
  parse de marcador de ênfase → `<b>`/`<i>` inline; cor de link herdada (remove
  `a{color}` fixo); `<ol>` p/ lista numerada; render de nota de rodapé nativa;
  fólio via `string-set` (não mais `counter(page)`); clustering de heading (h1/h2/h3)
  + `break-before: page` por nível, calculado por documento.

## Estratégia de teste (TDD, mais altos padrões)

- **Unit `layout.py`:** medição de altura; caber vs transbordar; paginação
  determinística; piso de fonte respeitado. Sem PDF real (geometria pura).
- **Unit classificação:** fixtures de blocos → papel esperado; fallback seguro.
- **Integração (PyMuPDF):** PDF-fixture 1–2 páginas com prosa longa → gera página de
  continuação; figura permanece intacta (hash da imagem inalterado); legenda encaixa.
- **Regressão de fidelidade:** contagem de imagens/xrefs de figura idêntica
  antes/depois; ordem de leitura preservada (sequência de blocos).
- **Nota de rodapé:** termo do glossário gera marcador + glosa ao pé.
- **Fonte real (ADR-0041):** PDF-fixture com fonte embutida → `@font-face` gerado
  com o nome do span; PDF com fonte não extraível → cai no fallback genérico, sem
  exceção.
- **Ênfase inline (ADR-0041):** bloco com marcador `**x**`/`_x_` no meio do texto →
  `<b>`/`<i>` só no trecho; texto sem marcador → comportamento atual (estilo
  dominante).
- **Listas (ADR-0041):** marcador numérico → `<ol>`; bloco sem tradução no dict →
  cai no original (nunca `continue` silencioso).
- **Fólio dinâmico (ADR-0041):** página original que transborda em N páginas
  físicas → todas as N mostram o mesmo `string(folio)`; página original sem fólio
  extraído → não emite marcador, herda o valor anterior.
- **Quebra por nível (ADR-0041):** fixture com heading que sempre abre página →
  nível recebe `break-before: page`; amostra < 3 ocorrências → fica `auto`.

## Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Classificação erra papel em PDF ruim | fallback `encaixado`; nunca descarta texto |
| Reflow quebra layout multi-coluna | MVP: multi-coluna trata como encaixado; ADR futuro |
| Tabelas ricas | fit-in-place no MVP; ADR futuro para re-layout |
| Página de continuação confunde numeração (motor `pymupdf`, fallback) | marcar "(cont.)" no rodapé da página inserida |
| Página original transborda em N páginas (motor `html`, default — ADR-0041) | fólio via `string-set` propaga o mesmo número original nas N páginas, sem contagem manual |
| Custo de re-render | determinístico + checkpoint por página (ADR-0031) |
| Marcador de ênfase corrompido/deslocado pela IA (ADR-0041) | parser tolerante: marcador que não fecha ou não bate com texto final é ignorado (cai no estilo dominante do bloco) |
| Extração de fonte falha (Type3/subset) (ADR-0041) | fallback pro CSS genérico atual, nunca derruba o render |

## Fidelidade avançada (ADR-0041)

Seis frentes que aprofundam o motor `render_motor=html` (ADR-0036), todas
resilientes: falha de qualquer heurística abaixo cai pro comportamento anterior
descrito nas seções acima, nunca derruba o render (ADR-0006).

### Fonte real embutida
`_estilo()`/`Span.font` já carregam o nome da fonte de cada span. `montar_html`
passa a extrair, uma vez por documento, os arquivos de fonte referenciados
(`doc.extract_font(xref)`) e gerar `@font-face { font-family: "<nome>"; src:
url(data:...) }` para cada família encontrada. Cada elemento usa
`font-family: "<nome-real>", <fallback genérico atual>` — fonte não extraível
(Type3/subset corrompido) cai no fallback, sem quebrar.

### Ênfase inline (negrito/itálico no meio do bloco)
`extrair_pagina` (`extracao.py`) monta `BlocoTraducao.texto` marcando, span a
span, os trechos que divergem do estilo dominante do bloco com marcadores leves
(`**negrito**`, `_itálico_`) — não é markdown geral, só esses dois marcadores,
escapados se aparecerem literalmente no texto original. `montar_prompt_refino`
(`traducao_ia.py`) ganha uma frase de regra: preservar os marcadores ao redor da
palavra/trecho equivalente na tradução. O render (`_elemento`) faz o parse dos
marcadores dentro do texto final e emite `<b>`/`<i>` no meio do parágrafo, além
do estilo dominante do bloco (que continua valendo pro resto do texto).
Degradação: MT bruta (sem refino) ou blocos que esgotaram o refino não seguem a
instrução de formato → marcadores ausentes → bloco renderiza no estilo dominante
de hoje (sem perda, só sem o ganho pontual).

### Cor do link herdada
Remove a regra global `a { color: #0645ad }`. `<a>` não seta cor própria — herda a
`color` já aplicada ao elemento pai (computada de `_estilo(b)["color"]`, o span
original). Sublinhado sutil (`text-decoration: underline`) substitui a cor como
diferenciador visual do link.

### Listas numeradas + zero perda por bloco sem tradução
`_e_lista` reconhece, além dos bullets atuais, marcador numérico/alfabético
(`^\d+[.)]\s`, `^[a-z][.)]\s`) — gera `<ol>` em vez de `<ul>` quando o marcador é
numérico. Em `montar_html`, remove o `continue` silencioso quando
`traducoes.get(b.id)` é `None`: cai no `b.texto` (original) — mesmo padrão de
"nunca perder conteúdo" já usado em `traduzir_blocos`/`_render_do_cache`.

### Papel `nota_rodape_original`
`extracao.py` distingue, entre os blocos perto da margem inferior, **fólio**
(curto, majoritariamente numérico/label — critério atual de `_e_folio`) de
**nota de rodapé nativa** (multi-palavra, muitas vezes iniciando com
marcador numérico/superescrito, posicionado acima da faixa do fólio). Nota de
rodapé nativa ganha o mesmo tratamento visual das notas de glossário
(ADR-0033): faixa de rodapé com regra fina acima, fonte reduzida — os dois tipos
de nota (glossário + nativa) compartilham o mesmo elemento de render.

### Fólio dinâmico (número igual ao original)
Cada página original emite, antes do seu primeiro item de conteúdo, um marcador
invisível `<span style="string-set: folio '<valor-literal>'"></span>` com o
valor de fólio extraído do bloco identificado por `_e_folio` (mesmo mecanismo já
usado pro cabeçalho de capítulo `cap`, E9-09). O `@page` passa a usar
`content: string(folio)` no lugar de `content: counter(page)`. Página original
sem fólio visível (comum em abertura de capítulo) não emite marcador — o valor
anterior permanece até o próximo marcador real. Como o texto PT-BR é mais longo,
uma página original pode transbordar em N páginas físicas; todas as N herdam o
mesmo `string(folio)` até o marcador da próxima página original — dinâmico por
construção, sem contagem manual de página de continuação.

### Quebra de página extraída por nível de heading
Classificação de heading deixa de ser 2 faixas fixas (`sz≥1.6×`/`sz≥1.18×` do
corpo) e passa a *clustering* dos tamanhos de fonte grandes do documento em até 3
níveis (h1/h2/h3), do maior pro menor. Para cada heading classificado, mede-se
se ele é o primeiro bloco de conteúdo (não-fólio) da sua página original — perto
do topo, logo após a margem. Agregando por nível: taxa de "abre página" ≥ 60% E
amostra ≥ 3 ocorrências ⇒ esse nível recebe `break-before: page` no CSS gerado
(por documento, não um valor fixo no template); abaixo disso, `auto`
(comportamento atual). Documentos onde só um nível específico (ex.: "Parte", não
"Capítulo") abre página tratam esse nível corretamente sem regra hardcoded.

## Interface com o épico (rastreabilidade)

- **Depende de:** ADR-0030 (Kind Traducao), ADR-0031 (pipeline resumível).
- **Habilita:** sub-projeto B (Agente editor + judge) — que produz `traducao`/`notas`
  de maior qualidade para este render consumir.
- **Épico:** [backlog `épico-tradutor-editorial`](../roadmap/backlog.md).
