---
titulo: ADR-0038 — Pool de execução de traduções (concorrência, fila e escalonamento)
id: ADR-0038
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-02
substitui: —
substituido-por: —
---

# ADR-0038 — Pool de execução de traduções (concorrência, fila e escalonamento)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-07-02 | Tech Lead | Criação — decisão do PO: pool com teto configurável ("réplicas"), fila e visibilidade p/ rodar vários lotes de tradução ao mesmo tempo | PO/PM |

---

## Status
`aceito` — decidido pelo PO/PM (2026-07-02). Sub-projeto de infraestrutura do
épico [E9](../../roadmap/backlog.md#épico-tradutor-editorial) (item **E9-10**);
generaliza para `Traducao` o padrão de concorrência+registro já provado no
[ADR-0028](ADR-0028-endurecimento-agente-code.md) §3/§5 (Agente modo `code`).

## Contexto

Hoje `_iniciar_traducao` (`api.py`) dispara **uma `threading.Thread` daemon sem
teto** por chamada — não há limite de quantas traduções rodam ao mesmo tempo, nem
um registro central de quais estão ativas. Cada `Traducao` só expõe o próprio
`status.fase` (via polling do recurso individual); não existe uma visão agregada
("o que está rodando agora", "o que está na fila").

O PO quer rodar **vários lotes de tradução simultaneamente** e precisa de:

1. **Controle** de quais runs foram invocados.
2. **Ciclo de vida** claro (fila → rodando → pausado/concluído/erro).
3. **Capacidade de escalonamento** — quantas traduções rodam em paralelo, ajustável
   sem reiniciar a instância (analogia explícita do PO a um *replicaset*: um teto de
   "réplicas" que pode subir/descer).
4. **Visibilidade** agregada na **API e na UI** — para verificar de fato que várias
   traduções estão progredindo ao mesmo tempo, não só ver cada `Traducao` isolada.

Sem teto, N traduções concorrentes competem por CPU/IO da Rasp e pela mesma cota de
IA (P1 — recurso escasso) sem coordenação — o mesmo risco que motivou o teto de
concorrência do Agente `code` (ADR-0028 §3), agora do lado da tradução.

## Decisão

**`TraducaoPool`** (`src/atlas/traducao/pool.py`) — registro em memória, thread-safe
(lock), que decide **na hora de iniciar** se uma tradução roda agora ou entra na
**fila FIFO**, e **despacha automaticamente** o próximo da fila quando um slot libera.

### 1. Teto configurável ("réplicas")
- `max_concorrente` (default **2**, env `ATLAS_TRADUCAO_MAX_CONCURRENT` no boot).
- **Escalável em runtime** (sem restart): `POST /_traducao_pool/escalar
  {"max_concorrente": N}`. Se o novo teto é maior, a fila é drenada imediatamente
  (dispara quantas traduções pendentes couberem no novo slot).

### 2. Fila em vez de rejeição
- Diferente do Agente `code` (ADR-0028, que rejeita com 429 — uso interativo), aqui
  **enfileira**: `_iniciar_traducao` acima do teto **não recusa**, marca
  `status.fase = "fila"` e devolve `200 {ok, fase: "fila", posicao}`. Combina com o
  caso de uso de **lote** (disparar N traduções de uma vez e deixar o pool
  escalonar), não o de uma ação pontual que o usuário repete manualmente.

### 3. Ciclo de vida
- Novo valor de `status.fase`: **`fila`** — precede `traduzindo` (ADR-0030) e
  `pausado` (ADR-0035). Transições: `fila → traduzindo → {concluido|erro|pausado}`.
  Ao terminar (sucesso, erro ou pausa por escassez), a thread libera o slot no pool
  (`pool.liberar(label)`), que **despacha o próximo da fila** se houver.
- Cancelar da fila (antes de começar a rodar): `DELETE /_traducao_pool/fila/<label>`
  — remove sem custo de IA (nunca chegou a rodar).

### 4. Visibilidade — API
- `GET /_traducao_pool` → `{max_concorrente, rodando: [label...], fila: [label...]}`.
  Estado só em memória (como o registro de `AgentRun`, ADR-0028 §5) — reflete a
  instância viva, não precisa persistir; o histórico de cada tradução já persiste
  no próprio recurso `Traducao`.

### 5. Visibilidade — UI
- Painel **"Pool de tradução"** no dashboard (`dashboard/kinds/traducao.js`):
  contagem rodando/fila, lista com link pro recurso, e controle de escalonamento
  (campo numérico + botão, chama `POST /_traducao_pool/escalar`). Atualiza por
  polling (mesmo padrão dos demais painéis vivos do Kind `Traducao`; SSE
  dashboard-wide é o item **E8-03**, ainda não geral — fica para quando E8-03 unificar).

### Escopo (explicitamente limitado por agora)
- Só o Kind `Traducao`. O padrão é genérico o bastante para virar capacidade do
  núcleo (como o Pilar 1 do redesenho E9 já apontava para pausa/retomada) — mas o
  PO pediu foco em tradução agora; generalizar fica para um ADR futuro se o padrão
  se repetir em outro Kind.
- Prévia (`_iniciar_previa`) **não** entra no pool — já é explicitamente concorrente
  à tradução (E9), e é barata (não paga IA).

## Alternativas consideradas

| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| **Pool em memória + fila FIFO + escalonamento runtime (escolhida)** | reusa padrão provado (ADR-0028); zero infra nova; escalonável sem restart | estado do pool não sobrevive a restart (mitigado: `Traducao` persiste seu próprio `fase`) | **escolhida** |
| Rejeitar acima do teto (429, como ADR-0028) | mais simples | força o cliente a repetir manualmente; ruim p/ disparar um lote de N de uma vez | rejeitada (não serve o caso de uso de lote) |
| Fila persistida (Kind novo / tabela) | sobrevive a restart | complexidade não justificada — o pool só orquestra threads já daemon; escopo do PO é "ver funcionando agora" | adiada |
| `ThreadPoolExecutor` com `max_workers` fixo | padrão da stdlib | não escalona em runtime sem recriar o executor; menos controle de fila FIFO visível | rejeitada |

## Consequências

- **Positivas:** várias traduções em lote progridem de fato em paralelo até o teto;
  teto ajustável sem restart (escalonamento real); visibilidade agregada (API+UI) do
  que está rodando/na fila; reusa um padrão já validado (ADR-0028), baixo risco.
- **Negativas / custos:** estado do pool é só em memória — um restart no meio de uma
  fila perde a fila (as traduções `fila`/`traduzindo` persistidas ficam com `fase`
  desatualizada até o usuário reiniciar manualmente; mesma limitação que já existe
  hoje para `traduzindo` sem pool). Mais um lifecycle state (`fila`) pra UI tratar.
- **Impacto na constituição:** nenhum invariante muda. Novo módulo
  (`traducao/pool.py`) + 2 endpoints + 1 fase nova no schema de status de
  `Traducao`. Atualiza índice de ADRs e backlog (E9-10).

## Pendências
- Recuperação de fila após restart (hoje: perdida; mitigação é reiniciar
  manualmente as `Traducao` presas em `fila`/`traduzindo`).
- Cancelar uma tradução **já rodando** (não só da fila) — precisa da mesma flag
  cooperativa que a pausa por escassez usa (ADR-0035); fica para quando a UI de
  pausa manual mid-run (pendência do E9-07) for endereçada.
- Generalizar o pool pro núcleo (Kind-agnóstico) se outro Kind precisar do mesmo
  padrão.
