---
titulo: Spec — Trackers via chat
id: SPEC-TRACKERS
status: em-revisao
versao: 0.1
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Spec — Trackers via chat

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-06-16 | Tech Lead | Criação (lição de casa, item 5 — prioridade) | — |

---

> Implementa o núcleo do épico **E5**. Cadastrar, configurar e consultar
> **trackers** inteiramente pelo chat, com wizard interativo e **0 IA**.

## Modelo: híbrido (decisão do PO/PM)
Um **tracker é uma entidade no schema** (linha de dados, com CRUD barato via
chat) **mas é descoberto e executado como uma rotina-de-tracking genérica do
core**. Assim:

- O **wizard** (`/tracker novo`) cria/edita **dados**, não escreve código nem sobe
  IA — barato e interativo.
- O **registro** de uma entrada (ex.: `peso: 82.3`) é processado por **uma única
  rotina genérica** (`tracking`) embutida no core, que consulta a definição do
  tracker e grava em `activities`. Preserva P3/P4 ("tudo é rotina"; o motor não
  conhece domínios), com a exceção registrada em
  [ADR-0013](../arquitetura/adr/ADR-0013-barreira-de-entrada.md) (ver Pendências
  sobre o ADR de modelo de dados).

## Dados — nova tabela `trackers`
| Campo | Tipo | Nota |
|---|---|---|
| `id` | int PK | |
| `nome` | text único | identificador (ex.: `peso`, `sono`, `agua`) |
| `dominio` | text | grava em `activities.dominio` |
| `tipo` | text | `numero` \| `duracao` \| `contagem` \| `texto` |
| `unidade` | text | ex.: `kg`, `h`, `páginas`, `copos` |
| `sintaxe` | text | prefixo/gramática de entrada (ex.: `peso:`) |
| `meta_id` | int FK → goals | opcional; liga ao sistema de metas |
| `agregacao` | text | `soma` \| `media` \| `ultimo` \| `contagem` (p/ resumo) |
| `ativo` | bool | liga/desliga sem apagar |
| `criado_em` | datetime | |

Cada **entrada** registrada continua indo para `activities` (log genérico):
`dominio=<tracker.dominio>`, `rotina="tracking"`, `texto_cru=<mensagem>`,
`dados_json={ tracker, valor, unidade }`. Quando há `meta_id`, cria também o
`goal_link` com a `contribuicao` ([modelo-de-dados](../arquitetura/modelo-de-dados.md)).

## A rotina genérica `tracking` (core, built-in)
- **trigger:** a mensagem casa a `sintaxe` de algum tracker ativo (barreira de
  entrada, [ADR-0013](../arquitetura/adr/ADR-0013-barreira-de-entrada.md)).
- **collect:** parseia o valor conforme `tipo`/`unidade`; monta `CollectResult`
  com `store` apontando para `activities` (+ `goal_link` se houver meta).
- **gate/analyze:** ausentes (log puro, 0 IA).
- **deliver:** confirma o registro ("✓ peso 82.3kg registrado · meta 80kg: faltam
  2.3").

## Comandos

| Comando | Efeito |
|---|---|
| `/trackers` | Lista trackers ativos + progresso recente (última entrada / agregação). |
| `/tracker novo` | **Wizard** interativo de cadastro (abaixo). |
| `/tracker <nome>` | Detalhe: definição, histórico recente, meta ligada. |
| `/tracker <nome> editar` | Edita campos (sintaxe, unidade, meta, agregação, ativo). |
| `/tracker <nome> remover` | Desativa (`ativo=false`); dados em `activities` ficam. |

### Wizard `/tracker novo` (passo a passo, 0 IA)
1. **Nome** → valida unicidade.
2. **Domínio** → texto livre (ex.: `saude`).
3. **Tipo** → escolha entre `numero`/`duracao`/`contagem`/`texto`.
4. **Unidade** → ex.: `kg` (pula se `tipo=texto`).
5. **Sintaxe de entrada** → sugere `<nome>:` como default (ex.: `peso:`); valida
   que não conflita com sintaxe/trigger existente (ADR-0008).
6. **Meta?** → opcional: liga a uma `goal` existente ou cria uma rápida (alvo +
   unidade + prazo).
7. **Agregação** → como o resumo/checkup consolida (`soma`/`media`/`ultimo`/`contagem`).
8. **Confirmação** → mostra o resumo; ao confirmar, grava a linha em `trackers`.

A partir daí, `peso: 82.3` já registra — **sem reiniciar o motor**, porque a
rotina `tracking` lê a tabela `trackers` em runtime (diferente do meta-loop, que
gera código e exige recarga).

## Consulta e visualização
- `/tracker peso` → últimas N entradas + agregação do período + progresso da meta.
- Visualização textual (sparkline ASCII / lista); gráfico de imagem fica como
  melhoria futura (Pendências).
- Ligação com o **checkup semanal** de metas (agregação sobre `activities` +
  `goal_links`).

## Casos de erro
| Caso | Resposta |
|---|---|
| Nome de tracker já existe | pede outro nome (não sobrescreve) |
| `sintaxe` conflita com tracker/rotina | avisa o conflito; pede outra |
| Entrada com valor não-parseável (`peso: muito`) | ajuda específica do tracker; não grava |
| `/tracker <nome>` inexistente | "Tracker `<nome>` não existe. Veja `/trackers`." |

## Testes (TDD)
- Wizard completo cria linha em `trackers` com os campos certos.
- `peso: 82.3` após cadastro → 1 `activities` com `dados_json.valor=82.3`,
  `rotina="tracking"`, sem reinício do motor.
- Tracker com meta: entrada cria `goal_link` e atualiza progresso.
- `peso: muito` → ajuda; 0 registro.
- Sintaxe conflitante no wizard → rejeitada.
- `/trackers` mostra a agregação correta de 3 entradas.
- DoD: cadastrar um tracker novo pelo chat e registrar/ver dados nele.

## Pendências
- A nova tabela `trackers` precisa de **ADR de modelo de dados** (estende
  [ADR-0002](../arquitetura/adr/ADR-0002-modelo-de-dados.md)) — abrir junto da
  implementação.
- Gramática da micro-sintaxe (compartilhada, D-03 / ADR-0008).
- Visualização gráfica (imagem) — melhoria futura.
- `tracking` como rotina built-in: confirmar se vive em `routines/` (versionada)
  ou no core (`src/atlas/`).
