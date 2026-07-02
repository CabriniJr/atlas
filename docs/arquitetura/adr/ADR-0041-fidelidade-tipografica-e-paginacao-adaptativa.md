---
titulo: ADR-0041 — Fidelidade tipográfica real + fólio/quebras extraídos do original
id: ADR-0041
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-02
substitui: —
substituido-por: —
---

# ADR-0041 — Fidelidade tipográfica real + fólio/quebras extraídos do original

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-07-02 | Tech Lead | Criação — decisão do PO: motor `editorial_html.py` (ADR-0036) ainda perde informação (fonte genérica, ênfase inline, listas, notas de rodapé nativas) e usa numeração/quebra de página inventadas em vez de extraídas do original | PO/PM |

## Status
`aceito` — decidido pelo PO/PM (2026-07-02). Aprofunda [ADR-0036](ADR-0036-render-editorial-modelo-semantico.md) (não o substitui): mesmo motor (`editorial_html.py` + WeasyPrint), seis frentes de fidelidade.

## Contexto

Run de controle e inspeção do PO no motor do ADR-0036 revelaram perda real de
informação, não só de "polimento":

1. **Fonte não é a original.** O CSS usa famílias genéricas fixas (`Liberation
   Serif`/`Sans`/`Mono`) — o documento final não usa a tipografia do PDF de origem,
   mesmo o `Span.font` já vindo da extração (`extracao.py`) e não sendo usado.
2. **Ênfase só por bloco.** `_estilo()` calcula bold/itálico **dominante do bloco
   inteiro** — uma palavra em negrito no meio de uma frase normal é descartada. O
   contrato render↔tradução (`traducoes: dict[id, str]`) só carrega texto plano por
   bloco, sem marcação de trecho.
3. **Hyperlink força azul.** `a { color: #0645ad; }` no CSS global sobrescreve a cor
   original do span, mesmo quando o PDF de origem tem o link na cor do corpo do
   texto — o "azul de link" é uma invenção do render, não do original.
4. **Listas perdem conteúdo.** `_e_lista()` só reconhece bullets (`•`, `-` etc);
   listas numeradas (`1.`, `a)`) caem como parágrafo comum (perda de estrutura, não
   de texto). Mais grave: em `montar_html`, `texto = traducoes.get(b.id); if texto is
   None: continue` — **qualquer bloco sem tradução no dict desaparece do PDF final
   sem aviso**, sem fallback pro original.
5. **Notas de rodapé nativas do original correm risco de serem descartadas.**
   `_e_folio()` (heurística "é fólio/cabeçalho de margem, exclui do corpo") usa só
   "linha curta perto da margem" como critério — uma nota de rodapé real do PDF
   (curta, perto do fundo da página) cai no mesmo balde e é **excluída do render**
   junto com o fólio de verdade. `notas_rodape` (ADR-0033) cobre só glossário
   (termos mantidos em inglês); notas nativas do PDF não têm papel próprio.
6. **Numeração de página é inventada.** `counter(page)` do CSS conta páginas físicas
   do PDF *remontado*, que não bate com a paginação do original (o texto PT-BR
   cresce ~15–25%). O PO quer o número **literal impresso no original** (`"42"`,
   `"xviii"`) em cada página final, não uma sequência recalculada.
7. **Quebra de página é hardcoded.** `h1 { page-break-before: auto }` não força
   nada — hoje nenhum nível de heading força quebra. O PO quer essa regra **extraída
   do próprio original**: se no PDF de origem um nível de heading consistentemente
   abre página nova (ex.: capítulos), o render deve reproduzir esse padrão; se não
   (ex.: seções), não deve forçar.

## Decisão

Seis mudanças no motor `editorial_html.py` (+ extensão pontual do contrato
extração↔tradução), todas resilientes (ADR-0006: falha em qualquer heurística cai
pro comportamento atual, nunca derruba o render):

### 1. Fonte real embutida
Extrair os arquivos de fonte do PDF (`doc.extract_font(xref)`, via os `xref`s
referenciados pelos spans) e gerar `@font-face` no CSS com o nome real do span
(`Span.font`). O elemento HTML usa `font-family: "<nome-real>", <fallback
genérico atual>` — fallback garante que uma fonte não-extraível (Type3, subset
corrompido) degrada pro comportamento de hoje, nunca quebra o render.

### 2. Ênfase inline (negrito/itálico no meio do bloco)
`extracao.py` marca, dentro do texto do bloco, os limites de trecho em negrito/
itálico com marcadores leves (`**trecho**`, `_trecho_`) só onde o span diverge do
estilo dominante do bloco. O prompt de refino (`traducao_ia.py`) é instruído a
**preservar esses marcadores ao redor da palavra/trecho correspondente**. O render
converte marcador → `<b>`/`<i>` dentro do parágrafo. Degradação: MT bruta (sem
refino, ou tokens esgotados) não segue instrução de formato → marcadores se perdem
→ bloco cai no estilo dominante de hoje (sem regressão, só sem o ganho).

### 3. Cor do link herdada, não forçada
Remove `a { color: #0645ad }`. Link usa a cor do span original (já computada em
`_estilo()`), igual a qualquer outro texto — `a` só adiciona sublinhado sutil se
quiser diferenciação visual, não cor fixa.

### 4. Listas numeradas + zero blocos descartados
`_e_lista` ganha reconhecimento de marcador numérico/alfabético (`^\d+[.)]\s`,
`^[a-z][.)]\s`) além de bullets, preservando o tipo (`<ol>` vs `<ul>`). Em
`montar_html`, bloco sem tradução no dict **nunca** é pulado: cai no texto
original (mesmo padrão de segurança já usado em `traduzir_blocos`/`_render_do_cache`
— nunca perder conteúdo, ADR-0033 "fallback seguro").

### 5. Papel `nota_rodape_original` distinto de fólio
Nova heurística em `extracao.py`: bloco perto da margem inferior é **fólio**
(padrão curto, majoritariamente numérico/label de capítulo — o que `_e_folio` já
pega bem) ou **nota de rodapé** (multi-palavra, muitas vezes com marcador
numérico/superescrito no início, sentado acima da faixa do fólio). Fólio continua
excluído do corpo (item 6). Nota de rodapé ganha papel próprio: renderiza numa
faixa de rodapé com regra fina acima, fonte reduzida — mesmo mecanismo visual já
usado pra `notas_rodape` do glossário (ADR-0033), unificando os dois.

### 6. Fólio dinâmico via `string-set`
Cada página original vira um marcador invisível no início do seu conteúdo:
`<span style="string-set: folio '<valor-literal-extraído>'"></span>` (mesmo
mecanismo já usado pro cabeçalho de capítulo `cap`, ADR-0036/E9-09). O rodapé passa
a usar `content: string(folio)` em vez de `content: counter(page)`. Como o CSS
propaga o último valor definido até o próximo marcador, uma página original que
transborda em N páginas físicas (PT-BR mais longo) mostra o mesmo número original
em todas as N — sem contagem manual de "página de continuação", escala sozinho
com o tamanho que o reflow gerar. Página original sem fólio visível no PDF de
origem (comum em abertura de capítulo) simplesmente não emite marcador — o valor
anterior continua valendo até o próximo marcador real (degradação aceitável:
manual `Editorial` sabe que abertura de capítulo tradicionalmente omite o número
impresso mesmo no original).

### 7. Quebra de página extraída, não assumida
Nova função de análise (`extracao.py` ou `editorial_html.py`) mede, para cada
heading (h1/h2/h3 — classificados por *clustering* dos tamanhos de fonte grandes
do documento, não mais 2 faixas fixas), se ele é o primeiro bloco de conteúdo da
sua página original (perto do topo, após a margem). Agrega a taxa de "abre
página" por nível; nível com taxa ≥ 60% (e amostra ≥ 3 ocorrências, pra não
decidir por 1 caso isolado) recebe `break-before: page` no CSS gerado para esse
nível; abaixo disso, fica `auto`. É uma decisão **por documento**: um livro onde só
"Parte" força quebra sai diferente de um onde every capítulo força.

## Alternativas consideradas

| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| **Extrair fonte/quebra/fólio do original (escolhida)** | fidelidade real, adaptativo por documento, reusa mecanismo `string-set` já validado (E9-09) | mais heurísticas (extração de fonte, clustering de heading, detecção de nota de rodapé) | é o pedido explícito do PO — "extraído do original e preservado" |
| Fólio sequencial + rótulo "(pág. orig. NN)" | simples, sem `string-set` | não é "IGUAL ao original" — o PO foi explícito que não quer isso | rejeitado pelo PO |
| Regra de quebra fixa (h1 sempre força) | zero heurística | ignora documentos onde h1 não abre página (falso padrão universal) | PO pediu extração real, não regra hardcoded |
| Ênfase inline fora de escopo agora | menor risco/escopo | mantém perda de informação que o PO chamou de "primordial" | PO decidiu incluir agora (ver brainstorm) |

## Consequências

- **Positivas:** render deixa de inventar layout/numeração — reproduz padrões do
  próprio documento; ênfase inline, listas numeradas e notas de rodapé nativas
  deixam de ser perdidas; hyperlink para de destoar visualmente sem motivo.
- **Negativas / custos:** contrato extração↔tradução ganha marcadores inline (risco
  de a IA corromper/deslocar um marcador raro — mitigado por fallback ao estilo
  dominante se o parser de marcador falhar); extração de fonte pode falhar em PDFs
  com fontes não-extraíveis (Type3/bitmap) — fallback pro genérico atual, nunca
  quebra; heurística de "abre página"/nota-de-rodapé é estatística, não 100%
  precisa (mitigada por piso de amostra mínima e fallback seguro de conteúdo).
- **Impacto na constituição:** nenhum invariante muda; aprofunda o motor default do
  ADR-0036 (mesmo `render_motor=html`). Sem novo Kind; `BlocoTraducao` ganha campos
  (marcadores inline, papel de rodapé nativo) — retrocompatível (default preserva
  comportamento atual quando ausente).

## Pendências

- Multi-coluna e tabelas ricas seguem fora de escopo (ADR-0033/0036).
- Nota de rodapé nativa que compete por espaço com o corpo em transbordo: reusa o
  mesmo fluxo de reflow do WeasyPrint (nenhuma lógica nova de "empurrar" — o motor
  HTML já lida com isso via fluxo contínuo, diferente do antigo `remontagem.py`
  in-place).
