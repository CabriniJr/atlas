---
titulo: ADR-0035 — Job de vida-longa pausável e reagendável por escassez (mid-run)
id: ADR-0035
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-01
substitui: —
substituido-por: —
---

# ADR-0035 — Job de vida-longa pausável e reagendável por escassez (mid-run)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-07-01 | Tech Lead | Criação — decisão do PO: parar por escassez de token e **retomar sozinho** daqui X horas; capacidade genérica do núcleo | PO/PM |

---

## Status
`aceito` — decidido pelo PO/PM (2026-07-01). É o **Pilar 1** do redesenho do
tradutor ([spec E9](../../specs/traducao-redesenho-e9.md), item E9-06), mas a
capacidade é **do núcleo** (qualquer job longo herda). Aprofunda o
[ADR-0005](ADR-0005-orcamento-reativo.md) (que só age **pré-run**) adicionando o
comportamento **mid-run**.

## Contexto

Uma run de tradução é **cara e longa**; quando os tokens acabam no meio, hoje ela
termina `parcial` e **espera um re-disparo manual** (ADR-0031). O PO quer o
comportamento autônomo: **detectou escassez → checkpoint → se pausa → agenda a
própria retomada (ex.: +5h, quando a janela de quota reseta) → volta sozinha e
continua de onde parou**. E isso "tudo precisa ter aplicação" — não pode ser
específico de tradução.

Restrições do que já existe:
- O checkpoint já existe: o pipeline é **resumível por página** (cache salvo a cada
  página, ADR-0031). Retomar = re-disparar; o cache pula o que já foi feito.
- A tradução é despachada em **thread de background pela API** (`_run` em `api.py`),
  **fora** do executor/scheduler. Logo o mecanismo não pode depender do caminho do
  `executar()`/`tick()` do cron.
- O `ResourceStore` sabe **enumerar** recursos (`kinds()` + `list()`) e cada recurso
  tem um `status` (dict) que a UI já faz polling. O motor **não conhece domínios**
  (P3): o mecanismo tem de ser **Kind-agnóstico**.

## Decisão

Uma capacidade genérica **baseada no `status` do recurso**, varrida pelo loop do app.

1. **Contrato de pausa (genérico).** Qualquer `collect` que pare por escassez marca,
   no `status` do seu recurso, três campos:
   - `fase = "pausado"`,
   - `retoma_em` = timestamp ISO de quando retomar,
   - `retoma_collect` = nome do `collect` que retoma o job.
   Um helper (`atlas/retomada.py::campos_pausa(agora, segundos, collect)`) devolve
   esses campos para o `collect` mesclar no seu patch de status. Nenhum conteúdo é
   perdido: o parcial já deixou o trabalho feito no checkpoint.

2. **Scanner de retomada (genérico, no loop do app).**
   `retomada.retomar_pausados(store, agora, disparar)` percorre `store.kinds()` /
   `store.list(kind)`, seleciona os recursos com `fase == "pausado"` e
   `retoma_em <= agora`, **limpa o marcador antes** (evita disparo duplo) e chama
   `disparar(kind, name, retoma_collect)`. Roda a cada tick do loop, ao lado do
   `scheduler.tick`.

3. **Disparo em background.** O `disparar` do app reconstrói
   `Rotina(nome=name, label=name, coletar=retoma_collect)` e roda o `collect` numa
   **thread daemon** (o mesmo padrão do `_run` da API) — não bloqueia o loop. Ao
   rodar, o `collect` volta a marcar `fase="traduzindo"/…`; se a escassez persistir,
   ele **se pausa de novo** com uma nova janela (auto-reentrante, sem hot-loop porque
   a janela é de horas).

4. **Consumidor #1 — tradução.** Quando `prog.parcial`, o collect `traduzir-pdf`
   grava `campos_pausa(agora, janela, "traduzir-pdf")`. A janela vem de
   `spec.janela_retomada_seg` (default **18000 s = 5 h**). A UI mostra "pausado —
   retoma às HH:MM".

5. **Relação com ADR-0005.** Ortogonais e complementares: ADR-0005 é **disjuntor
   pré-run** (o scheduler não despacha a próxima se o acumulado estourou); este ADR é
   **mid-run** (a run em curso se pausa e se reagenda). Um não substitui o outro.

## Alternativas consideradas

| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| **Status do recurso + scanner no loop (escolhida)** | funciona no path de background da tradução; Kind-agnóstico; UI já lê status | varre recursos a cada tick | varredura é barata (poucos recursos) |
| `routine_state` + `tick` do cron | reusa o scheduler | tradução **não** passa pelo cron; ctx da API não tem `db` | não cobre o caminho real |
| Reagendar via `agenda`/cron da rotina | nativo do scheduler | one-shot "+5h" não é cron; bloquearia o loop se síncrono | não encaixa |

## Consequências

- **Positivas:** qualquer job longo herda pausa+retomada autônoma; a tradução
  termina sozinha após a janela de quota; protege o gasto de IA (habilita o default
  `editorial` da fidelidade, [spec E9](../../specs/traducao-redesenho-e9.md)).
- **Negativas / custos:** o loop faz uma varredura de recursos por tick (barata); um
  job que falha sempre se reagenda indefinidamente (mitigável com contador de
  tentativas — fora do MVP); pausa manual pela UI fica para o Pilar 4 (o mecanismo já
  suporta: basta a UI gravar `retoma_em`).
- **Impacto na constituição:** nenhum invariante muda; aprofunda ADR-0005 e ADR-0031.
  Atualiza índice de ADRs e backlog (E9-06).
