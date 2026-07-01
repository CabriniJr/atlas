---
titulo: Spec de design — Tradutor de PDFs de alta fidelidade (Kind Traducao)
id: SPEC-TRADUCAO-PDF
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-01
---

# Spec de design — Tradutor de PDFs de alta fidelidade

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-07-01 | Tech Lead | Criação — desenho aprovado pelo PO ("faça tudo") | PO/PM |

---

> Novo **job acoplável** do Atlas: traduzir PDFs inteiros (livros técnicos)
> **preservando 100% do design** — estrutura, fonte, cores, imagens, vetores e
> posição — **mudando apenas o texto**, traduzido por IA com contexto da tecnicidade
> do livro. Termos técnicos permanecem em inglês. O Atlas serve como **motor** (IA via
> [`ia.py`](../../../src/atlas/ia.py)) e **front** (web shell — [ADR-0029](../../arquitetura/adr/ADR-0029-web-shell-da-api.md)).
> A ferramenta precisa ser de **alta fidelidade / sofisticada**, não substituição
> ingênua palavra-a-palavra.

## Problema

Não existe forma no Atlas de traduzir um documento inteiro preservando layout. As
rotinas atuais são agendadas e produzem saída curta (telegram); não modelam
processamento de arquivo grande, resumível, on-demand. Traduzir um livro técnico
exige: (1) fidelidade visual absoluta — só o texto muda; (2) tradução com contexto
técnico — termos de arte permanecem em inglês, código não é traduzido; (3) controle
de custo — livros = muitas chamadas de IA (P1, economia do recurso escasso).

## Decisão de arquitetura (resumo — detalhe no ADR-0030)

Modelado como **objeto na API** (P11) + **script acoplável** (P2), espelhando o
padrão do collect [`prompt.py`](../../../src/atlas/rotinas/prompt.py):

- **Kind novo `Traducao`** — recurso que representa um pedido de tradução.
- **Collect acoplável `traduzir-pdf`** (`@registrar("traduzir-pdf")`) — executa o
  pipeline e atualiza `status` no store. On-demand (via `/run`, API ou botão no web
  shell), **não** por cron.
- **Dependência nova `PyMuPDF` (`fitz`)** — única forma de preservar design com
  fidelidade; registrada e justificada no ADR-0030 (colide com "zero deps", mas PDF
  fiel a exige).

> **Precede o código:** este spec + **ADR-0030** (Kind Traducao + PyMuPDF) são o
> contrato. O ADR é criado como primeiro passo do plano de implementação.

## O Kind `Traducao`

```yaml
Kind: Traducao
metadata:
  nome: livro-x
  labels: { projeto: estudos }
spec:
  origem: "data/pdfs/livro-x.pdf"      # caminho do PDF de entrada (upload no front grava aqui)
  idioma_origem: en
  idioma_destino: pt-BR                 # default do produto
  motor: claude                         # claude (default) | ollama
  modelo: null                          # opcional; default do motor
  assunto: "Kubernetes / engenharia de plataforma"   # contexto de tecnicidade p/ o prompt
  glossario: [Kubernetes, pod, deployment, buffer, thread]  # termos que ficam em inglês
  glossario_auto: true                  # IA também detecta termos técnicos a preservar
  fidelidade: alta                      # alta (claude) | rascunho (ollama)
status:
  fase: pendente|extraindo|traduzindo|remontando|pronto|erro
  paginas_total: 0
  paginas_prontas: 0
  saida: null                           # "data/pdfs/livro-x.pt-BR.pdf" quando pronto
  custo_tokens_estimado: 0
  custo_tokens_real: 0
  erro: null
```

Schema-driven (ADR-0017): a view especializada no shell é derivada do schema do Kind.

## Abordagem de fidelidade — *in-place redaction + reinsert* (PyMuPDF)

Comparação (o requisito "estrutura idêntica, só texto muda" é o filtro):

| Abordagem | Fidelidade de design | Qualidade de tradução | Veredito |
|---|---|---|---|
| **A. Bloco in-place (`fitz`)** — extrai spans (fonte/cor/bbox), traduz por bloco, redaction do original, reinsere no bbox com auto-fit | **Idêntica** (imagens/vetores/fundo intocados) | Alta (bloco com contexto) | **escolhida** |
| B. Span-a-span posicional | Boa posição, estoura em texto longo | Baixa (sem contexto) | rejeitada |
| C. PDF→HTML→re-render | Reflui/re-renderiza → design deriva | Alta | rejeitada (viola requisito) |

Só a **A** garante que apenas o texto muda: imagens, vetores e fundo nunca são
tocados (redaction remove só os glyphs de texto).

## Pipeline (4 estágios, resumível por página)

### 1. Extrair
- `page.get_text("dict")` → blocos → linhas → spans; cada span com
  `text, bbox, font, size, color, flags`.
- Agrupa spans em **unidades de tradução por bloco** (parágrafo), respeitando ordem
  de leitura e colunas.
- **Não-tradutível:** spans em **fonte monospace** (código) e blocos numéricos/símbolos
  são marcados `skip` e passam intactos.

### 2. Traduzir (IA)
- Envia o bloco ao [`invocar()`](../../../src/atlas/ia.py) com: instrução de tradução
  técnica, `assunto`, glossário ("manter em inglês"), e **contexto de vizinhança**
  (blocos adjacentes) para coerência.
- **Batch** de blocos por chamada para reduzir número de invocações (P1).
- **Cache por hash do bloco** (texto normalizado) → reprocessar o livro não repaga
  blocos idênticos; blocos repetidos (cabeçalhos/rodapés) traduzem uma vez.
- Saída da IA é **estruturada** (bloco→tradução) para reancorar sem ambiguidade.

### 3. Remontar
- `page.add_redact_annot(bbox)` + `apply_redactions()` remove o texto original
  (preserva imagens/vetores).
- Reinsere a tradução via `page.insert_textbox(bbox, texto, fontname, fontsize, color)`
  com **auto-fit**: reduz `fontsize` em passos até caber; permite reflow **dentro** do
  bloco. Absorve a diferença de comprimento EN↔PT (PT ~15-30% mais longo).
- **Cobertura de glyphs:** se a fonte embutida não tiver acentos (á, ç, ã), usa fonte
  de fallback com cobertura latina; caso contrário mantém a fonte original.

### 4. Checkpoint
- Grava resultado **página a página** no PDF de saída; `status.paginas_prontas` e
  `custo_tokens_real` atualizados incrementalmente.
- **Retomável:** se cair, recomeça da primeira página não concluída (cache cobre o já
  traduzido).

## Terminologia técnica (o "contexto da tecnicidade")

- **Prompt de sistema** por `Traducao`: "tradução técnica de livro sobre {assunto};
  preserve termos técnicos em inglês; não traduza nomes de APIs/comandos/código;
  mantenha tom técnico".
- **Glossário** manual (`spec.glossario`) reforça termos fixos; `glossario_auto`
  deixa a IA detectar termos de arte adicionais numa passada inicial de amostragem.
- **Código / monospace** nunca é traduzido (marcado `skip` na extração).

## Front (web shell — ADR-0029)

- View do Kind `Traducao`: seleção/upload do PDF, **estimativa de custo antes de
  rodar**, barra de progresso (lê `status.fase`/`paginas_prontas`), download do
  resultado quando `fase=pronto`.
- Ação "traduzir" dispara o collect via API (mesmo caminho de `/run`).

## Controle de custo (P1)

- **Estimativa** de tokens antes de rodar (contagem de caracteres tradutíveis).
- `fidelidade: rascunho` usa **Ollama** (custo zero de assinatura).
- **Cache de blocos** evita repagar reprocessamentos e repetições.
- `spec.politica` de limite (budget de tokens) aborta com `status.fase=erro` se
  estourar — alinhado a ADR-0005 (orçamento reativo).

## Testes (TDD)

Fixtures de PDFs pequenos gerados em teste (via `fitz`), sem depender de arquivos
externos: 1 coluna, 2 colunas, com imagem, com bloco de código (monospace), com
acento no destino.

Asserções:
- Imagens/vetores **intactos** (hash do stream de imagem inalterado).
- Bbox dos blocos preservado (posição não muda).
- Texto **traduzido** (mock do `invocar()` retorna tradução determinística).
- Termo do **glossário mantido em inglês** no PDF de saída.
- Bloco **monospace não traduzido**.
- **Glyph de acento** renderiza (extração do PDF de saída contém "ç/ã").
- `invocar()` é **mockado** (nenhuma IA real gasta em teste).
- Retomada: matar no meio e recomeçar produz o mesmo PDF, sem repagar (cache hit).

## Fora de escopo (YAGNI, propor no backlog)

- OCR de PDFs escaneados (sem camada de texto).
- Tradução de texto **dentro de imagens**.
- Edição manual/revisão inline da tradução no front.
- Outros formatos (EPUB, DOCX).

## Riscos

- **Layouts complexos** (tabelas densas, múltiplas colunas justapostas) podem reflow
  imperfeito no auto-fit → mitigado por passo de fidelidade e testes de fixture.
- **Fontes sem glyphs** de acento → fallback latino.
- **Custo de livro inteiro** → estimativa + cache + opção Ollama.
