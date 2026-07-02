---
titulo: Spec — Redesenho do Tradutor editorial (guarda-chuva do épico E9)
id: SPEC-TRADUCAO-REDESENHO-E9
status: em-revisao
versao: 0.1
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-01
---

# Spec — Redesenho do Tradutor editorial (guarda-chuva do épico E9)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-07-01 | Tech Lead | Criação — redesenho unificado do E9 a partir do diagnóstico da run de controle (livro *Observability Engineering*) | PO/PM (shape aprovado) |

---

> Spec-guarda-chuva que unifica o épico [E9 — Tradutor editorial](../roadmap/backlog.md#épico-tradutor-editorial).
> Nasce do diagnóstico de uma **run de controle** (o livro *Observability
> Engineering*, 321 págs., 1 PDF in → 1 PDF out) cujo resultado saiu **ilegível**:
> texto colidindo, glyphs perdidos e sem auditoria de fidelidade. Esta spec redefine
> o épico em **4 pilares** e uma **ordem de ataque** que front-loada o que é barato,
> porque **cada run de tradução é cara em tokens**. Decompõe em itens `E9-0x`, cada um
> com ADR + plano próprios. É acoplamento do core (Kind `Traducao`, ADR-0030), não um
> subsistema à parte — usa a API de objetos, o executor e o scheduler do núcleo.

## Objetivo

Produzir, a partir de um PDF, um **arquivo traduzido usável e ipsis-litteris**: só o
texto muda; imagens, charts, apêndices, blocos, fontes, estilo e ordem de leitura são
preservados; a prosa **reflui** e o documento se reorganiza (como "abrir o PDF num
editor e trocar só o texto"). Com **fidelidade auditada** contra o original,
**controle total na UI** (pausar, escolher modelo, configurar tudo) e **automação de
núcleo** que protege runs caras (pausa por escassez de token e retoma sozinha).

## Não-objetivos (deste redesenho)

- Re-layout de tabelas ricas e reflow multi-coluna verdadeiro (encaixam in-place; ADR
  futuro). OCR de PDF-imagem. Tradução de conteúdo dentro de imagens/charts.
- Reescrever o core de objetos/executor/scheduler — apenas **acrescentar** a capacidade
  de job pausável/reagendável e consumi-la na tradução.

## Diagnóstico da run de controle (evidência)

A saída foi gerada **depois** de o render editorial (E9-01) já estar no `main` — logo,
os defeitos são de **execução do E9-01**, não de código faltando. Três falhas
**independentes**:

1. **Sem reflow real entre blocos.** O PDF de saída tem as **mesmas 321 páginas** do
   original ⇒ *nenhuma página de continuação foi criada*. Cada bloco é reinserido na
   posição Y original; quando o PT-BR cresce (quase sempre), ele estoura a própria
   caixa e **colide com o bloco de baixo**. `remontagem.py` só manda o overflow de
   `prosa` pra página de continuação e **não empurra os vizinhos**; e bullets caem como
   `encaixado` (encolhe só até `min_fonte_pct` e depois transborda).
2. **Perda de glyphs.** O render usa Helvetica embutida (`_FONTE_FALLBACK = "helv"`),
   que **não tem** o caractere de bullet `•` nem aspas curvas/travessões ⇒ PyMuPDF
   substitui por `?`. Todo bullet virou `?`.
3. **Fidelidade não auditada.** Comparador (ADR-0034) e agente Editor/judge (E9-03)
   ainda não existem; a tradução é bruta + refino por página, sem auditoria contra o
   original.

## Princípio organizador: separar o CARO do BARATO

**IA = caro e cacheável; render = barato e determinístico.** O cache já guarda MT
**bruta** (namespace `raw:`) e **refinada** por bloco, salvo a cada página; o render
(`remontar_documento`) é determinístico a partir de `render_paginas`. Logo, a tradução
cara do documento, uma vez feita, **está paga** — dá pra re-renderizar de graça.

Para que isso valha na prática, a config é **partida em duas**, e **só a de tradução
entra na chave do cache**:

| Bloco de config | Afeta cache de IA? | Campos (MVP) |
|---|---|---|
| `spec.traducao` | **sim** (mudou ⇒ re-traduz) | `modelo`, `motor`, `refino`, `lote_refino`, `comparador`, `modelo_comparador`, `fidelidade`, modelos por estágio |
| `spec.render` | **não** (mudou ⇒ só re-renderiza) | `min_fonte_pct`, `notas_rodape`, `fonte`, `margens`, `nivel_reflow` |

Consequência: iterar layout **não gasta token**. É a base do "atacar cedo sem repagar".

## Os 4 pilares

### Pilar 1 — Core: job pausável/reagendável por escassez *(genérico)*

Capacidade **do núcleo**, não da tradução; qualquer job longo herda.

- **Comportamento (aprovado):** escassez detectada ⇒ **checkpoint → status `pausado` →
  agenda a própria retomada** para quando a janela de quota resetar (ex.: +5h) ⇒
  **retoma sozinho** de onde parou. Botão **pausar/retomar manual** na UI também.
- **Reuso:** aproveita o resume-por-página que a tradução já tem (ADR-0031) e o
  generaliza no executor/scheduler.
- **Relação com ADR-0005:** o 0005 é disjuntor *pré-run* (não despacha a próxima se o
  acumulado estourou). Este pilar adiciona o **mid-run**: pausar e reagendar a run
  **em curso**. Vira **ADR novo** ("job de vida-longa pausável/reagendável").
- **Contrato:** um job expõe `checkpoint()` idempotente e `retomar()`; o scheduler sabe
  agendar a retomada; o estado `pausado` é de primeira classe no progresso.

### Pilar 2 — Fase 1: serialização + tradução auditada *(fidelidade)*

Fidelidade é o valor primário desta fase.

- Serialização do PDF em blocos (existe: `extracao.py`) → tradução bruta → refino.
- **Comparador de consistência** (ADR-0034): mapa canônico `{variante: canônico}`
  aplicado deterministicamente antes do render.
- **Agente Editor + LLM-as-judge** (E9-03): auditam cada lote **contra o original**.
- **`spec.traducao.fidelidade`** — parâmetro que escala quanto de IA se gasta auditando.
  **Default aprovado: `editorial`** (pipeline completo: bruto → refino → comparador →
  editor → judge). Níveis menores (`rascunho`, `padrao`) desligam estágios caros.
  A economia (princípio #1) é preservada **pela escolha de nível**, não por cortar a
  qualidade do default.

### Pilar 3 — Fase 2: documento editorial *(conserta o "péssimo")*

Corrige os defeitos 1 e 2 do diagnóstico e cumpre a meta editorial.

- **Reflow real:** quando um bloco cresce, **empurra os blocos de fluxo seguintes pra
  baixo** na mesma página; o que transbordar da página vira **página de continuação**
  real (preserva ordem). `imutavel`/`encaixado` não migram. Corrige a colisão.
- **Fonte com glyphs completos:** embutir uma TTF Unicode (ex.: DejaVu/Noto) cobrindo
  `•`, aspas curvas, travessões, símbolos — acaba o `?`. Fallback de normalização de
  caractere quando o glyph faltar.
- **Ação "só-render a partir do cache":** re-gera o PDF (e `.md`/`.epub`) sem repagar
  IA, consumindo apenas `spec.render`. É o que permite iterar o observability de graça.
- **Meta:** "abrir o PDF e trocar só o texto; o resto se reorganiza dinamicamente."

### Pilar 4 — UI de controle da criação

- **Ciclo de vida:** iniciar / **pausar / retomar** / "retomar em 5h".
- **Modelo por estágio** (bruto, refino, comparador, editor, judge) e **todos os
  params** de `spec.traducao` e `spec.render` configuráveis antes e depois da run.
- **Progresso por fase** (serialização → tradução → auditoria → render) e botão de
  **re-render grátis** a partir do cache.
- Segue a GUI-por-Kind (ADR-0017/0020): a view do Kind `Traducao` abstrai a API.

## Ordem de ataque (front-load do barato)

Porque **cada run é cara**, entregamos primeiro o que é grátis e visível:

1. **E9-05 — Split de config + ação "só-render".** Parte `spec` em `traducao`/`render`;
   tira params de render da chave do cache; expõe re-render a partir do cache. Base pra
   iterar sem gastar token.
2. **E9-01b — Render legível (Pilar 3).** Reflow que empurra vizinhos + página de
   continuação real + fonte Unicode embutida. **Re-gera o observability legível sem
   repagar IA** — primeiro resultado visível e barato.
3. **E9-06 — Core pausa/reagenda (Pilar 1).** Protege as runs caras dali pra frente.
4. **E9-02/03 — Fidelidade (Pilar 2).** Comparador + Editor + judge; agora o gasto de
   IA é seguro (pausável) e controlado (`fidelidade`, default `editorial`).
5. **E9-04/07 — UI de controle (Pilar 4).** Amarra pausa, modelos e params.

## ADRs a criar/atualizar

| ADR | Assunto | Pilar |
|---|---|---|
| ADR-0033 (revisar) | Reflow que **empurra vizinhos** (não só overflow de prosa) + fonte Unicode embutida | 3 |
| ADR novo | **Split de config** (`traducao` vs `render`) e chave de cache; ação "só-render" | base/3 |
| ADR novo | **Job de vida-longa pausável/reagendável por escassez** (mid-run; aprofunda ADR-0005) | 1 |
| ADR-0034 (implementar) | Comparador de consistência opt-in | 2 |
| ADR novo | Agente **Editor** + **LLM-as-judge**; níveis de `fidelidade` | 2 |
| ADR novo | GUI de controle da criação (pausa, modelo por estágio, params) | 4 |

## Estratégia de teste (TDD)

- **Render (Pilar 3):** fixture 1–2 págs com prosa longa ⇒ **gera** página de
  continuação (contagem de páginas aumenta) e **não colide** (bboxes não sobrepõem);
  glyphs `•`/aspas/travessão renderizam (sem `?`); figuras intactas (hash inalterado);
  ordem de leitura preservada.
- **Split de config:** mudar `spec.render` **não invalida** o cache (nenhuma chamada de
  IA); mudar `spec.traducao` invalida. Re-render de cache é determinístico.
- **Core pausa (Pilar 1):** simular escassez ⇒ job faz checkpoint, vira `pausado`,
  agenda retomada; retomar continua do checkpoint sem re-trabalho.
- **Fidelidade (Pilar 2):** comparador unifica termos divergentes; judge sinaliza
  desvio do original em fixture controlada; níveis ligam/desligam estágios.

## Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Reflow que empurra vizinhos quebra layout multi-coluna | MVP: multi-coluna/tabela tratados como `encaixado`; ADR futuro |
| TTF embutida aumenta tamanho do PDF | subset de glyphs usados; medir impacto |
| Default `editorial` encarece toda run | protegido pelo Pilar 1 (pausa/reagenda) + níveis menores disponíveis |
| Split de config quebra caches existentes | migração: chave nova ignora campos de render; cache antigo revalida uma vez |
| Mid-run pause conflita com disjuntor pré-run (ADR-0005) | ADR novo define precedência: mid-run pausa e reagenda; pré-run bloqueia despacho |

## Rastreabilidade

- **Aprofunda:** ADR-0030 (Kind Traducao), ADR-0031 (pipeline resumível), ADR-0032
  (export), ADR-0033 (render editorial), ADR-0034 (comparador), ADR-0005 (orçamento).
- **Épico:** [backlog `épico-tradutor-editorial`](../roadmap/backlog.md).
- **Sub-projeto A anterior:** [`traducao-render-editorial.md`](traducao-render-editorial.md)
  (permanece; o Pilar 3 revisa seu motor de reflow e a fonte).
