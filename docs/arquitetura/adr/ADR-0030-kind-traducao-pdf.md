---
titulo: ADR-0030 — Kind Traducao (tradutor de PDFs de alta fidelidade)
id: ADR-0030
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-01
substitui: —
substituido-por: —
---

# ADR-0030 — Kind Traducao (tradutor de PDFs de alta fidelidade)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-07-01 | Tech Lead | Criação — desenho aprovado pelo PO ("faça tudo") | PO/PM |

---

## Status
`aceito` — aceito pelo PO/PM (2026-07-01); em implementação ágil.

## Contexto

O PO pediu um **job a mais / script acoplável** para **traduzir PDFs inteiros**
(livros técnicos) **preservando 100% do design** — estrutura, fonte, cores, imagens,
vetores e posição — mudando **apenas o texto**, traduzido por IA com contexto da
tecnicidade do livro; termos técnicos e código permanecem em inglês. O Atlas serve
como **motor** (IA via [`ia.py`](../../../src/atlas/ia.py) — [ADR-0022](ADR-0022-motor-de-ia-plugavel.md))
e **front** (web shell — [ADR-0029](ADR-0029-web-shell-da-api.md)). Requisito de
**alta fidelidade**, não substituição ingênua palavra-a-palavra.

As rotinas atuais são agendadas e produzem saída curta (telegram); não modelam
processamento de arquivo grande, resumível e on-demand. Preservar layout com
fidelidade **exige uma biblioteca de PDF** — colide com a preferência por "zero
dependências" (P7/simplicidade), tensão que este ADR resolve explicitamente.

Design completo em
[`../../superpowers/specs/2026-07-01-traducao-pdf-design.md`](../../superpowers/specs/2026-07-01-traducao-pdf-design.md).

## Decisão

1. **Kind `Traducao`** (primeira classe, schema-driven — [ADR-0017](ADR-0017-gui-por-kind-abstrai-api.md)):
   objeto na API (P11) que representa um pedido de tradução. `spec`: `origem` (caminho
   do PDF), `idioma_origem`/`idioma_destino` (default `en`→`pt-BR`), `motor`
   (`claude` default | `ollama`), `modelo`, `assunto` (contexto de tecnicidade),
   `glossario` (termos que ficam em inglês), `glossario_auto`, `fidelidade`. `status`:
   `fase` (`pendente|traduzindo|pronto|erro`), `paginas_total`, `paginas_prontas`,
   `saida`, `custo_tokens_*`, `erro`.
2. **Collect acoplável `traduzir-pdf`** (`@registrar` — espelha
   [`rotinas/prompt.py`](../../../src/atlas/rotinas/prompt.py)): lê o `Traducao/<label>`,
   roda o pipeline e grava progresso/saída no `status`. **On-demand** (via `/run`/API),
   **não** por cron.
3. **Dependência nova `PyMuPDF` (`fitz`)** — adotada como a forma de preservar o design
   com fidelidade. Abordagem **in-place redaction + reinsert**: extrai spans
   (fonte/cor/bbox), traduz por bloco, remove os glyphs originais (`apply_redactions`,
   que **não** toca imagens/vetores) e reinsere a tradução no mesmo bbox com auto-fit.
4. **IA** via `ia.invocar` ([ADR-0022](ADR-0022-motor-de-ia-plugavel.md)), em batch de
   blocos numerados, com instrução técnica + glossário. **Código/monospace nunca é
   traduzido** (marcado `skip` na extração). **Cache por hash** do bloco evita repagar
   (P1, economia do recurso escasso).

## Alternativas consideradas

| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| **In-place redaction+reinsert (PyMuPDF)** | design idêntico; imagens/vetores intocados; só texto muda | nova dep; auto-fit para absorver diferença de comprimento | **escolhida** |
| Span-a-span posicional | posição exata | estoura em texto mais longo (PT>EN); traduz sem contexto | qualidade e layout ruins |
| PDF → HTML → re-render | reflow rico | re-renderiza → design deriva | viola "estrutura idêntica" |
| Sem lib (stdlib) | zero deps | impossível preservar layout com fidelidade | não atende o requisito |

## Consequências

- **Positivas:** vocabulário coerente (objeto na API, P11); tradução de livros com
  design preservado; motor de IA e front reusados do Atlas; custo mitigado por
  cache/estimativa.
- **Negativas / custos:** **nova dependência externa** (`pymupdf`) — primeira do tipo
  "pesada"; justificada por não haver caminho stdlib para PDF fiel. Custo de IA por
  livro (muitas chamadas) — mitigado por batch, cache e opção Ollama.
- **Impacto na constituição:** introduz Kind novo e uma dependência externa; não muda
  decisões arquiteturais. Atualiza o índice de ADRs e a lista de Kinds.

## Pendências

- ✅ Estimativa de custo/budget ([ADR-0005](ADR-0005-orcamento-reativo.md)) antes de
  rodar — módulo `traducao/estimativa.py` + `GET /_estimar` (grátis, sem IA).
- ✅ View no web shell ([ADR-0029](ADR-0029-web-shell-da-api.md)): Kind `Traducao` no
  `/_schema`, render dedicada (`kinds/traducao.js`) com prévia, disparo (`POST
  /_traduzir`, background) e barra de progresso via polling do status.
- View no web shell — **falta** upload do PDF e download do resultado pela UI (hoje o
  caminho de origem/saída é do filesystem do servidor).
- `glossario_auto` (detecção de termos técnicos pela IA) e cache persistido em disco.
- OCR de PDFs escaneados (fora de escopo inicial).
