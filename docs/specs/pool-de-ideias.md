---
titulo: Spec — Pool de ideias e desenvolvimento
id: SPEC-POOL
status: em-revisao
versao: 0.1
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Spec — Pool de ideias e desenvolvimento

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-06-16 | Tech Lead | Criação (prioridade máxima) | — |

---

> Decisão de origem: [ADR-0014](../arquitetura/adr/ADR-0014-pool-de-ideias-desenvolvimento.md).
> Capturar ideias/tarefas/lições pelo Telegram, com CRUD e prioridade, e alimentar
> a **geração automática** de rotinas (ativação sempre humana).

## Objetivo
Dar ao dono uma "caixa de entrada" de ideias direto no chat — incluindo as
**lições de casa** das próximas sessões — e transformar a fila no motor de
crescimento do sistema.

## Dados — nova tabela `ideas`
| Campo | Tipo | Nota |
|---|---|---|
| `id` | int PK | |
| `tipo` | text | `ideia` \| `tarefa` \| `rotina` (default `ideia`) |
| `titulo` | text | resumo curto (1ª linha do texto) |
| `corpo` | text | descrição completa (opcional) |
| `prioridade` | int | menor = mais urgente (default 100) |
| `estado` | text | `capturada`→`priorizada`→`em_desenvolvimento`→`gerada`→`ativada`; ou `arquivada`/`descartada` |
| `rotina_alvo` | text | nome da rotina gerada (quando `tipo=rotina`) |
| `erro` | text | última falha de geração (se houver) |
| `criado_em` | datetime | |
| `atualizado_em` | datetime | |

Migração: schema idempotente (`CREATE TABLE IF NOT EXISTS`) — ver
[ADR-0014](../arquitetura/adr/ADR-0014-pool-de-ideias-desenvolvimento.md) Pendências.

## Comandos (Telegram, 0 IA)
| Comando | Efeito |
|---|---|
| `/ideia <texto>` | Captura item `tipo=ideia`. |
| `/tarefa <texto>` · `/licao <texto>` | Captura item `tipo=tarefa`. |
| `/rotina_nova <texto>` | Captura item `tipo=rotina` (candidato à geração automática). |
| `/ideias [estado]` | Lista itens (default: ativos, ordenados por prioridade). |
| `/ideia <id>` | Detalhe de um item. |
| `/ideia <id> prio <n>` | Define prioridade. |
| `/ideia <id> editar <texto>` | Edita o corpo. |
| `/ideia <id> feito` · `/ideia <id> arquivar` | Conclui/arquiva. |
| `/ideia <id> remover` | Descarta (soft: `estado=descartada`). |

> Os nomes exatos podem ser consolidados no registro de comandos
> ([interface-config-chat](interface-config-chat.md)); o conjunto acima é o contrato.

## Laço de desenvolvimento (autoimplementação — ativação humana)
1. **Gatilho:** periodicamente (ou ao capturar um item `rotina`), o laço verifica
   se o **agente 2b está livre** (nenhum `run` camada `2b` em andamento).
2. **Seleção:** pega o item `tipo=rotina`, `estado=priorizada`, de menor
   `prioridade`. Marca `em_desenvolvimento` (1 por vez, P5).
3. **Geração:** chama o **meta-loop** fase 2
   ([meta-loop-chat](meta-loop-chat.md)) com o corpo do item como base de `SPEC.md`.
   A rotina nasce **`ativa=false`**.
4. **Resultado:**
   - Sucesso → item `gerada`, `rotina_alvo` preenchido, **notifica**: "rotina
     `<nome>` gerada (inativa). Revise e `/ativar <nome>`."
   - Falha → item volta a `priorizada`, `erro` anexado, notifica.
5. **Ativação:** **sempre humana** (`/ativar`), nunca pelo laço
   ([ADR-0014](../arquitetura/adr/ADR-0014-pool-de-ideias-desenvolvimento.md) §5).

## Lições de casa via Telegram
"Escrever lições de casa pelo celular" = capturar itens `tarefa`/`ideia` no pool.
O documento [`roadmap/licao-de-casa.md`](../roadmap/licao-de-casa.md) continua sendo
o registro curado pelo Tech Lead; o pool é a **entrada rápida** que o alimenta. (Um
exportador pool → markdown da lição de casa é melhoria futura.)

## Casos de erro
| Caso | Resposta |
|---|---|
| `/ideia` sem texto | ajuda; não grava |
| `/ideia <id>` inexistente | "Item #<id> não encontrado. Veja `/ideias`." |
| `prio` com valor não-numérico | erro + exemplo; nada muda |
| Geração falha | item volta a `priorizada` com `erro`; notifica |
| Agente ocupado | laço não inicia outro; espera o próximo ciclo |

## Testes (TDD)
- `/ideia comprar webcam` → 1 linha `ideas` (`tipo=ideia`, `estado=capturada`).
- `/ideias` lista por prioridade ascendente.
- `/ideia 1 prio 5` → prioridade atualizada; reordena.
- `/ideia 1 remover` → `estado=descartada`; some da lista default.
- Laço com agente livre + 1 item `rotina` priorizado → chama meta-loop (fake),
  item vira `gerada`, rotina `ativa=false`, notificação enviada.
- Laço com agente ocupado → nenhum item entra em `em_desenvolvimento`.
- Geração que falha (fake lança) → item volta a `priorizada` com `erro`.

## Pendências
- ADR de modelo de dados para `ideas` (junto da migração — relacionado a D-04).
- Cadência do laço (a cada tick do loop? comando `/desenvolver` manual também?).
- Exportador pool → `licao-de-casa.md`.
- Depende de [executor](executor-e-notificacao.md), [meta-loop](meta-loop-chat.md) e
  do login do `claude -p`.
