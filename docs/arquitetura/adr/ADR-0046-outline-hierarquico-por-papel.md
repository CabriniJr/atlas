---
titulo: ADR-0046 — Outline hierárquico do PDF por papel estrutural (Parte > Capítulo > Seção)
id: ADR-0046
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-06
substitui: —
substituido-por: —
---

# ADR-0046 — Outline hierárquico do PDF por papel estrutural

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-07-06 | Tech Lead | `bookmark-level` por papel (parte/capítulo/seção) desacoplado do tamanho de fonte; supressão do rótulo de parte solto | PO/PM |

---

## Status
`aceito` — implementado (`editorial_html._atribuir_niveis_outline`).

## Contexto

O WeasyPrint gera o **outline/marcadores do PDF** (a árvore de tópicos que os
leitores mostram na barra lateral) diretamente das tags `h1`/`h2`/`h3`: nível 1,
2 e 3, respectivamente. No motor editorial (ADR-0036/ADR-0041), o nível do
heading é escolhido por **tamanho de fonte** (`clusters_titulo` →
`nivel_titulo`). Isso é suficiente para o *visual*, mas produz um outline plano
ou torto — reclamação direta do usuário ("os tópicos do lado esquerdo estão
todos bagunçados… provavelmente o problema no sumário seja a hierarquia de
h1/h2"). Auditando os três livros (dump de `doc.get_toc()` do PDF gerado):

- **Prometheus (O'Reilly):** "Parte I. Introdução" e "Capítulo 1." são **ambos
  h1** (mesmo corpo de fonte, distintos só pela palavra "Parte"/"Capítulo") →
  caíam **os dois no nível 1**, lado a lado, sem o capítulo aninhar sob a parte.
- **Observability (O'Reilly):** a parte é composta de **duas linhas** — um
  rótulo pequeno "PART I" (h3, ao lado) e o título grande "The Path to
  Observability" (h1). O título já entrava como nível 1 (ok), mas o rótulo solto
  entrava como nível 2/3 órfão, poluindo o outline com uma entrada "parte i"
  sem sentido no meio do prefácio.
- **Kubernetes (Manning):** os divisores de parte são **páginas rasterizadas**
  (imagem full-page, ADR-0041) e as seções não têm tamanho de fonte distinto do
  corpo — não há heading de parte/seção extraível. O outline vira uma lista
  chapada de capítulos.

A raiz é a mesma: **o tamanho da fonte não codifica o papel estrutural**. Parte,
capítulo, seção e subseção precisam de uma profundidade de outline própria,
independente de quão grande cada um é desenhado.

## Decisão

Um passe pós-render (`_atribuir_niveis_outline`, aplicado sobre a lista de
fragmentos HTML antes do join) reatribui a propriedade CSS **`bookmark-level`**
de cada heading por **papel estrutural**, que o WeasyPrint honra para montar o
outline — desacoplando a navegação do tamanho visual (a tag/tamanho/quebra do
heading não muda; só o metadado de bookmark).

1. **Classificação de papel por texto** (regex sobre o texto plano do heading):
   - `parte` — `^(PARTE|PART)\s+([IVXLCDM]+|\d+)\b` (ex.: "Parte I", "Part 2").
     O `\b` após o numeral evita falso positivo com prosa ("Parte **da**
     configuração" não casa: "da" não é numeral romano completo).
   - `cap` — `^(CAP[IÍ]TULO|CHAPTER|AP[EÊ]NDICE|APPENDIX)\b`.
   - `secao` — qualquer outro heading (mapeado por tamanho, ver item 4).
2. **Gate de segurança:** se **nenhum** heading é `parte`, o passe é **no-op** —
   mantém o comportamento padrão do WeasyPrint (tag→nível). Assim, livro cujas
   partes não são extraíveis como heading (Kubernetes) **não regride**.
3. **Rótulo de parte solto → funde no título** (caso Observability): um heading
   `parte` que é só o rótulo (`^(PARTE|PART)\s+…$`, sem título) e é **seguido**
   por um heading maior (rank de tag menor) tem seu bookmark **suprimido**
   (`bookmark-level: none`) e o título seguinte é promovido a `parte`. Assim a
   Parte aparece uma vez só, com o nome bom.
4. **Atribuição de nível:** `parte → 1`, `cap → 2`; os headings sem papel
   (seções) são ordenados pelos **tiers de tamanho** que ocorrem entre eles — o
   maior vira `3`, o próximo `4`, etc. (`2 + índice_do_tier`). Isso resolve as
   duas formas de O'Reilly com a mesma regra:
   - **Prometheus** (parte/capítulo rotulados em h1; seção h2; subseção h3) →
     Parte 1 · Capítulo 2 · Seção 3 · Subseção 4.
   - **Observability** (parte = título h1; capítulo h2 **sem** rótulo; seção h3)
     → Parte 1 · Capítulo 2 · Seção 3.
5. O WeasyPrint **normaliza níveis órfãos**: um bookmark nível 2/3 sem pai nível
   1 (o front-matter — "Elogios", "Índice", "Prefácio" — que precede a primeira
   parte) é promovido a nível 1 no PDF final. É o comportamento desejado (o
   front-matter fica no topo do outline, como no livro original).

## Alternativas consideradas

| Alternativa | Prós | Contras | Veredito |
|---|---|---|---|
| Reclusterizar tamanhos para inferir mais tiers | reusaria a maquinaria existente | tamanho não separa parte de capítulo (mesmo corpo no O'Reilly); nem recupera parte rasterizada (Kubernetes) | rejeitada |
| Trocar a tag do heading (`h1`→`h4` etc.) para forçar o nível | direto | acopla de novo visual e navegação — mudaria fonte/quebra do heading, quebrando o layout já validado (ADR-0041) | rejeitada — `bookmark-level` separa as duas coisas |
| Reconstruir a árvore de partes a partir do outline nativo do PDF-fonte | fiel à intenção do autor | o outline do PDF-fonte usa paginação/âncoras do original (invalidadas pela repaginação, ADR-0041) e muitos livros não têm outline embutido | rejeitada |

## Consequências

- **Positivas:** o outline dos dois livros O'Reilly passa a aninhar de verdade
  (Parte > Capítulo > Seção > Subseção), batendo com a estrutura do livro; o
  rótulo de parte solto some do outline; a mudança é só de metadado (zero risco
  ao layout/visual já aprovado).
- **Negativas / custos:** livro sem parte detectável (Kubernetes) continua com
  outline chapado de capítulos — limitação de **extração** (divisor de parte
  rasterizado, seções sem tamanho distinto), não deste passe; documentada em
  Pendências. Classificação por regex é PT/EN — outro idioma precisaria estender
  os padrões.
- **Impacto na constituição:** estende ADR-0036/ADR-0041 (motor editorial) — o
  render passa a emitir metadado de navegação estruturado, não só visual.

## Pendências
- **Kubernetes in Action:** partes (divisores rasterizados) e seções (sem tamanho
  distinto do corpo) não viram heading → não entram no outline. Recuperá-las
  exige trabalho de **extração** (detectar o divisor de parte na página-imagem;
  reclusterizar seção por cor/peso de fonte, não só tamanho), fora do escopo
  deste ADR.
- Front-matter ("Elogios", "Índice", "Prefácio") aparece no nível 1 do outline
  antes da primeira parte — correto para front-matter, mas depende da
  normalização de órfãos do WeasyPrint (não é um nível explícito nosso).
- Classificação de parte/capítulo é PT/EN (regex) — internacionalização futura.
