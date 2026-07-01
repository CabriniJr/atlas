---
titulo: ADR-0033 — Motor de render editorial ipsis-litteris (híbrido por papel de bloco)
id: ADR-0033
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-01
substitui: —
substituido-por: —
---

# ADR-0033 — Motor de render editorial ipsis-litteris (híbrido por papel de bloco)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-07-01 | Tech Lead | Criação — decisão do PO: render editorial, híbrido por papel de bloco | PO/PM |

---

## Status
`aceito` — decidido pelo PO/PM (2026-07-01). Aprofunda o estágio de remontagem do
[ADR-0030](ADR-0030-kind-traducao-pdf.md). Primeiro sub-projeto do épico
**tradutor AI-augmented + render PDF ipsis-litteris** (ver
[`specs/traducao-render-editorial.md`](../../specs/traducao-render-editorial.md)).

## Contexto

O norte do produto (democratizar acesso a artigos acadêmicos) exige que o PDF final
seja **ipsis litteris** ao original — só o texto traduzido — preservando **fotos,
charts, fontes, estilo, ordem e termos técnicos**. A remontagem atual (ADR-0030) é
*in-place*: apaga o texto original e reinsere a tradução no **mesmo bbox** com
auto-fit. Como a tradução PT-BR costuma ser **mais longa** que o inglês, o texto ou
**encolhe a fonte** (ilegível) ou **corta**. Isso quebra o nível editorial exigido.

O PO definiu o princípio: **legibilidade e fidelidade convivem via adaptação** —
texto pode refluir e até gerar **página a mais**, sem nunca mexer em imagens/charts.

## Decisão

**Render híbrido, decidido pelo _papel_ de cada bloco** (classificação em
`extracao`):

1. **Prosa** (parágrafos de corpo) → **reflow**: o bloco cresce conforme o texto
   traduzido; o conteúdo seguinte é empurrado no fluxo da página; ao transbordar, o
   excedente vai para uma **página de continuação** inserida logo após a página de
   origem (preserva a ordem de leitura).
2. **Encaixados** (legendas de figura, labels, células de tabela, cabeçalhos) →
   **fit-in-place**: mantêm o bbox original com auto-fit (comportamento ADR-0030).
   Preservam a fidelidade posicional onde ela importa.
3. **Imutáveis** (imagens, charts, fórmulas, blocos de código) → **intocados**: a
   redação só cobre spans de **texto tradutível**; o resto do conteúdo do PDF nunca é
   alterado.

**Notas de rodapé (opt-in):** termos mantidos no idioma de origem (glossário) podem
receber uma **nota de rodapé** com glosa curta, coletadas ao pé da página. Preserva o
aprendizado sem poluir o corpo.

**Contrato com o sub-projeto B (qualidade AI-augmented):** o render recebe **blocos
traduzidos ordenados + metadados de papel**; não conhece _como_ a tradução foi feita.
Isso mantém A e B plugáveis (P3/P11) e testáveis isoladamente.

**Resumível:** a render é **determinística** a partir do cache (ADR-0031); o
checkpoint por página é preservado — re-render de páginas prontas é barato.

## Alternativas consideradas

| Alternativa | Prós | Contras |
|---|---|---|
| **Híbrido por papel (escolhida)** | editorial de verdade; imagens/charts intactos; posição preservada onde importa | motor mais complexo; classifica papel por bloco |
| In-place puro (ADR-0030 v1) | simples; posição idêntica | fonte encolhe/corta; não é nível editorial |
| Re-layout total (rebuild do doc) | máxima liberdade tipográfica | perde ipsis-litteris em layouts complexos; altíssimo risco |

## Consequências

- **Positivas:** PDF em nível editorial, legível, fiel; base plugável para o Agente
  editor/judge (sub-projeto B); notas de rodapé preservam termos técnicos.
- **Negativas / custos:** motor de reflow + paginação é complexo; layouts
  multi-coluna e tabelas ricas ficam **fora do MVP** (encaixam in-place; ADR futuro
  para tabelas/colunas). Classificação de papel pode errar em PDFs ruins (fallback:
  tratar como encaixado, nunca perder conteúdo).
- **Impacto na constituição:** não muda invariantes; aprofunda o render do ADR-0030.
  Atualiza o índice de ADRs e o backlog do épico.
