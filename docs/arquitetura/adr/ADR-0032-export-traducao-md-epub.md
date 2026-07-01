---
titulo: ADR-0032 — Export de tradução para Markdown/EPUB via pandoc
id: ADR-0032
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-01
substitui: —
substituido-por: —
---

# ADR-0032 — Export de tradução para Markdown/EPUB via pandoc

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-07-01 | Tech Lead | Criação — decisão do PO: além do PDF, exportar .md e .epub reusando pandoc | PO/PM |

---

## Status
`aceito` — decidido pelo PO/PM (2026-07-01). Acopla-se ao Kind `Traducao`
([ADR-0030](ADR-0030-kind-traducao-pdf.md), [ADR-0031](ADR-0031-traducao-mt-mais-refino.md)).

## Contexto

Todo o texto traduzido já está **serializado** no PDF de saída. O PO pediu formatos
de saída além do PDF — **`.md`** e **`.epub`** (leitura em e-readers) — e foi
explícito: **reusar programas que já fazem isso**, não reimplementar conversão de
documentos.

## Decisão

Novo módulo `atlas/traducao/exportar.py`, **acoplado** à feature de tradução:

1. **Serialização → Markdown:** re-extrai o texto do PDF traduzido com PyMuPDF
   (`page.get_text`), página a página, separadas por `---`. Sem dependência externa.
2. **Markdown → EPUB:** delega ao **`pandoc`** (programa consagrado). Se o `pandoc`
   não está no PATH, o EPUB levanta `PandocAusente` e a API responde `503` com
   instrução — o `.md` continua funcionando (fallback gracioso).

**Superfície:**
- API: `GET /_exportar?label=<Traducao>&fmt=md|epub` — serializa e faz stream do
  arquivo (espelha `/_download`).
- UI: botões **📝 .md** e **📚 .epub** na view (custom render) do Kind `Traducao`.
- Infra: `pandoc` adicionado ao `Dockerfile`; na Rasp, `apt install pandoc`.

## Alternativas consideradas

| Alternativa | Prós | Contras |
|---|---|---|
| **pandoc (escolhida)** | qualidade EPUB alta, formato consagrado, não reimplementa | dependência de binário externo (dev + Rasp + Docker) |
| Puro-Python (ebooklib) | sem binário, só pip | EPUB mais simples; reimplementa parte da conversão |
| Só `.md` | trivial, zero dep | não entrega EPUB pedido |

## Consequências

- **Positivas:** entrega `.md` e `.epub` reusando ferramenta madura; `.md` sem
  dependência; degradação graciosa sem pandoc.
- **Negativas / custos:** nova dependência de sistema (`pandoc`) no dev, na Rasp e
  na imagem Docker; a fidelidade do Markdown depende do texto extraível do PDF.
- **Impacto na constituição:** não muda decisões; adiciona dependência de sistema e
  amplia o Kind `Traducao`. Atualiza o índice de ADRs.
