---
titulo: ADR-0037 — Kind DocTraducao + pipeline em 3 estágios (serialização → julgamento → editorial)
id: ADR-0037
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-02
substitui: —
substituido-por: —
---

# ADR-0037 — Kind DocTraducao + pipeline em 3 estágios

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-07-02 | Tech Lead | Criação — decisão do PO: serialização vira objeto (Kind DocTraducao); 3 estágios com slider de fidelidade | PO/PM |

## Status
`aceito` — decidido pelo PO/PM (2026-07-02). Formaliza o fluxo do tradutor em três
estágios de responsabilidade separada, sobre um objeto de primeira classe. Reusa
extração/bruto (ADR-0030/0031), o comparador/judge (ADR-0034 + E9-03) e o render
editorial (ADR-0036).

## Contexto

O PO definiu o fluxo com responsabilidades limpas: **serialização → julgamento →
editorial**. Hoje o texto vive num **cache JSON por hash** — não é objeto, não tem
`id`/`ordem`/`label` explícitos, não é query­ável nem visível. O PO quer **objetos**
("um kind doc"), com o original (en) e a tradução por unidade, e um **slider de
fidelidade** controlando o quão fiel/bruto é o texto que o editorial usa.

## Decisão

**Kind `DocTraducao`** — um recurso por livro (P11), relacionado ao Kind `Traducao`
(o job) por `label`. Guarda a lista **ordenada de unidades** serializadas:

```
DocTraducao/<label>.status.unidades[] = {
  id, ordem, pagina, papel,      # posição e papel (prosa/heading/código/…)
  en,                            # original
  bruto,                         # MT do motor comum (deep-translator)
  final,                         # texto pós-julgamento (fidelidade máx.) | null
  fidelidade                     # score/estimativa do julgamento | null
}
```

**Três estágios, cada um com uma responsabilidade:**

1. **Serialização** — extrai o PDF em unidades (`id`/`ordem`/`pagina`/`papel`/`en`) e
   preenche `bruto` pelo motor comum já usado. Produz/atualiza o `DocTraducao`. Sem
   IA cara. (`traducao/serializacao.py`)
2. **Julgamento** — IA em **batches** compara `bruto` × `en` e reescreve para
   **máxima fidelidade** conforme o **nível de qualidade**; um passe avaliador
   (LLM-as-judge, modelo configurável) controla. Grava `final` + `fidelidade` na
   unidade. É resumível e pausável (ADR-0031/0035). (E9-02/03; `traducao/julgamento.py`)
3. **Editorial** — render (WeasyPrint, ADR-0036) lê as unidades e produz o PDF usando
   `final` ou `bruto` conforme o **slider `spec.fidelidade`** (0 = bruto/rápido …
   1 = mais fiel). O texto entra e o documento **remolda** respeitando a norma/estilo.

**Slider de fidelidade (`spec.fidelidade`, 0..1):** controla (a) o alvo do julgamento
(quão agressiva a reescrita para fidelidade) e (b) a escolha do editorial (abaixo de
um limiar usa `bruto`; acima usa `final`). Configurável na UI.

**Resumibilidade/objeto:** como o estado vive no `DocTraducao`, cada estágio é
retomável por unidade e o objeto é visível/queryável (substitui o cache JSON como
fonte de verdade da tradução; o cache vira detalhe de implementação da serialização).

## Alternativas consideradas

| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| **Kind DocTraducao (1/livro, unidades internas) (escolhida)** | objeto P11 com id/ordem/label; 1 recurso/livro; estágios plugáveis | payload grande por recurso | SQLite aguenta; ganho de clareza |
| 1 recurso por unidade | selector máximo | milhares de recursos/livro; lento | pesa demais |
| Manter cache JSON | mínimo esforço | não é objeto; sem visibilidade | contraria o pedido/P11 |

## Consequências

- **Positivas:** responsabilidades limpas e testáveis isoladamente; estado como objeto
  visível/retomável; slider dá controle real do trade-off fidelidade×custo; editorial
  desacoplado (lê unidades).
- **Negativas / custos:** migração do cache→objeto; payload grande por recurso
  (mitigado: 1/livro, SQLite ok); julgamento é o passe caro de IA (protegido por
  ADR-0035 e pelo slider).
- **Impacto na constituição:** nenhum invariante muda; novo Kind (P11). Atualiza índice
  de ADRs e backlog (E9-08). Implementação incremental: (1) Kind+serialização,
  (2) julgamento, (3) editorial-lê-unidades + slider.
