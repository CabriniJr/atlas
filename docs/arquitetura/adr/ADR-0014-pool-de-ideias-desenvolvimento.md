---
titulo: ADR-0014 — Pool de ideias → desenvolvimento (autoimplementação com ativação humana)
id: ADR-0014
status: aceito            # proposto | aceito | substituído | obsoleto
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
substitui: —
substituido-por: —
---

# ADR-0014 — Pool de ideias → desenvolvimento (autoimplementação com ativação humana)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-06-16 | Tech Lead | Proposta (lição de casa: pool de ideias, prioridade máxima) | — |
| 1.0    | 2026-06-16 | Tech Lead | Aceito | PO/PM |

---

## Status
`aceito`.

## Contexto
O PO/PM quer registrar ideias, tarefas e "lições de casa" **pelo Telegram**, fazer
CRUD e priorização, e que o sistema **comece a se autoimplementar** a partir dessa
fila: quando o agente estiver livre, ele pega o item de maior prioridade e gera a
rotina correspondente.

Isso esbarra na **invariante #4 da [constituição](../constituicao.md)**: *"Nada de
auto-execução de código gerado. Meta-loop → revisão humana → ativa."* e na #11
(código gerado nasce inativo). A pergunta-chave: a autoimplementação ativa código
sozinha?

Decisão do PO/PM: **não**. O sistema **auto-gera**, mas a **ativação continua
humana**.

## Decisão
Criar um **pool** (fila priorizada) de itens capturados, e um laço de
desenvolvimento que **gera** rotinas automaticamente — preservando a ativação
humana.

1. **Captura pelo Telegram (0 IA):** comandos para registrar itens (`/ideia`,
   `/licao`/`/tarefa`), listar, ver, repriorizar, editar e remover. Itens vivem na
   tabela `ideas` (CRUD barato, determinístico).
2. **Tipos de item:** `ideia` (insight), `tarefa`/`licao` (trabalho a fazer),
   `rotina` (pedido explícito de gerar uma rotina).
3. **Ciclo de vida do item:**
   `capturada → priorizada → em_desenvolvimento → gerada → ativada` (ou
   `arquivada`/`descartada`). A transição `gerada → ativada` é **sempre humana**.
4. **Laço de desenvolvimento:** quando o agente (modo 2b) está **livre** e há item
   `rotina` priorizado, o pool dispara o **meta-loop**
   ([meta-loop-chat](../../specs/meta-loop-chat.md)) para **gerar** a rotina. A
   rotina nasce **`ativa=false`** (invariante #11). O pool marca o item como
   `gerada` e **notifica o dono** para revisar e `/ativar`.
5. **Fronteira de segurança (não-negociável):** o laço **nunca** ativa nem executa
   código gerado. Geração automática ✅; ativação automática ❌. Mantém #4 e #11
   intactos — **este ADR não revoga a constituição**, opera dentro dela.
6. **Concorrência:** um item em `em_desenvolvimento` por vez (o agente 2b é único e
   serial, P5). Falha de geração volta o item para `priorizada` com o erro anexado.

## Alternativas consideradas
| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Auto-gera **e** auto-ativa | "Mágico", zero fricção | Revoga invariante #4; código não revisado em produção | PO/PM recusou o risco |
| Só gera sob comando (`/desenvolver <id>`) | Controle total | Não é "autoimplementar"; perde o valor pedido | Aquém do pedido |
| Pool como arquivos no repo (sem tabela) | Versionado | CRUD/priorização por chat fica ruim; conflito com edição | Atrito alto para o uso diário |

## Consequências
- **Positivas:** captura de ideias sem fricção; o sistema cresce sozinho **até** o
  ponto de revisão; rastreabilidade (item → rotina gerada → ativação).
- **Negativas / custos:** nova tabela `ideas` (precisa de migração de schema, hoje
  inexistente — ver Pendências); o laço de desenvolvimento depende do **meta-loop**
  e do **login do `claude -p`** no host.
- **Impacto na constituição:** **nenhuma revogação.** Reforça #4 e #11; quando
  aceito, adiciona uma linha na tabela (item: "Pool de desenvolvimento — gera auto,
  ativa humano") apontando para este ADR.

## Pendências
- **Migração de schema** para a tabela `ideas` (a estratégia de migração é item em
  aberto do [modelo-de-dados](../modelo-de-dados.md); o MVP usa
  `CREATE TABLE IF NOT EXISTS` idempotente).
- Definição de "agente livre" (sem run 2b em andamento; checar `runs`).
- Política de retry/limite de tentativas de geração por item.
- Integração com observabilidade (cada geração é um `run` camada 2b).
- Login do `claude -p` no container (bloqueia o laço em produção; geração fica
  stubada/manual até resolver).
