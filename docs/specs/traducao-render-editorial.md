---
titulo: Spec — Render editorial ipsis-litteris (sub-projeto A)
id: SPEC-TRADUCAO-RENDER-EDITORIAL
status: em-revisao
versao: 0.1
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-01
---

# Spec — Render editorial ipsis-litteris (sub-projeto A)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-07-01 | Tech Lead | Criação — primeiro sub-projeto do épico editorial | — |

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

## Estratégia de teste (TDD, mais altos padrões)

- **Unit `layout.py`:** medição de altura; caber vs transbordar; paginação
  determinística; piso de fonte respeitado. Sem PDF real (geometria pura).
- **Unit classificação:** fixtures de blocos → papel esperado; fallback seguro.
- **Integração (PyMuPDF):** PDF-fixture 1–2 páginas com prosa longa → gera página de
  continuação; figura permanece intacta (hash da imagem inalterado); legenda encaixa.
- **Regressão de fidelidade:** contagem de imagens/xrefs de figura idêntica
  antes/depois; ordem de leitura preservada (sequência de blocos).
- **Nota de rodapé:** termo do glossário gera marcador + glosa ao pé.

## Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Classificação erra papel em PDF ruim | fallback `encaixado`; nunca descarta texto |
| Reflow quebra layout multi-coluna | MVP: multi-coluna trata como encaixado; ADR futuro |
| Tabelas ricas | fit-in-place no MVP; ADR futuro para re-layout |
| Página de continuação confunde numeração | marcar "(cont.)" no rodapé da página inserida |
| Custo de re-render | determinístico + checkpoint por página (ADR-0031) |

## Interface com o épico (rastreabilidade)

- **Depende de:** ADR-0030 (Kind Traducao), ADR-0031 (pipeline resumível).
- **Habilita:** sub-projeto B (Agente editor + judge) — que produz `traducao`/`notas`
  de maior qualidade para este render consumir.
- **Épico:** [backlog `épico-tradutor-editorial`](../roadmap/backlog.md).
