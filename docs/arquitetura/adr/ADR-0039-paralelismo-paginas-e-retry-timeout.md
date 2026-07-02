---
titulo: ADR-0039 — Paralelismo de páginas entre réplicas + retry curto antes de escassez
id: ADR-0039
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-02
substitui: —
substituido-por: —
---

# ADR-0039 — Paralelismo de páginas entre réplicas + retry curto antes de escassez

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-07-02 | Tech Lead | Criação — decisão do PO: distribuir páginas entre réplicas + retry curto persistido antes do pause longo | PO/PM |

---

## Status
`aceito` — decidido pelo PO/PM (2026-07-02). Estende o [ADR-0038](ADR-0038-pool-execucao-traducao.md)
(pool entre jobs) e o [ADR-0035](ADR-0035-job-pausavel-reagendavel.md) (pause/retomada).

## Contexto

Depois do [ADR-0038](ADR-0038-pool-execucao-traducao.md) (pool entre **jobs**), o PO
escalou o pool pra 4 réplicas e observou que uma tradução **em curso** continuava
processando página a página, sequencialmente — o pool só distribui jobs diferentes,
não acelera as páginas **restantes de um mesmo job**. Pedido: "réplicas" devem valer
também dentro de um job.

Segundo problema, observado ao vivo: uma única chamada de IA que **timeout** (60s)
é tratada como "tokens esgotados" — o restante do documento cai pro bruto e o job
pausa por **5 horas** (ADR-0035). Um timeout isolado nem sempre é escassez de cota;
pode ser uma chamada lenta pontual. O PO quer distinguir os dois casos:

- **Timeout** (transitório, possivelmente pontual): retry **curto** — pausa 5 min,
  retoma sozinho, até **5 tentativas**. Precisa **persistir** a contagem de
  tentativas (sobrevive a restart) — sem isso, um retry "in-process" com sleep
  bloquearia a thread e se perderia num restart.
- **Escassez confirmada**: erro não-timeout (ex.: rate-limit explícito), OU 5
  tentativas curtas seguidas sem sucesso ⇒ aí sim é "garantido" que é limite de
  cota — cai pro bruto e pausa **5 horas** (comportamento atual do ADR-0035), e
  zera a contagem de tentativas pro próximo ciclo.

## Decisão

### 1. Paralelismo de páginas dentro de um job (`traduzir_pdf(..., paralelismo=N)`)

`pipeline.traduzir_pdf` ganha o parâmetro `paralelismo` (default 1 = comportamento
sequencial atual, intocado). Quando `> 1`, as páginas são processadas por um
`ThreadPoolExecutor(max_workers=paralelismo)` em vez do loop sequencial — cada
página é independente (extração + bruto + refino), então paraleliza sem mudar a
semântica. **N vem do pool global** (`atlas.traducao.pool.pool_global.max_concorrente`,
o mesmo dial de "réplicas" do ADR-0038) — escalar o pool acelera tanto "quantos jobs
rodam ao mesmo tempo" quanto "quantas páginas de UM job rodam ao mesmo tempo". É a
mesma unidade mental de "réplicas" pro PO, sem precisar de dois controles.

**Seções críticas:** um lock protege (a) o checkpoint do cache em disco
(`cache.salvar`) — evita corromper o JSON com escritas concorrentes — e (b) a
chamada de `on_progress`/atualização de `paginas_prontas`/`esgotado` — evita
lost-update no status. A tradução em si (chamada de IA, cara) roda **fora** do
lock, só a contabilidade é serializada.

**Propagação de esgotamento:** um `threading.Event` compartilhado sinaliza
"parar de chamar IA" pras próximas páginas a começar (as já em voo terminam
naturalmente). Não cancela subprocessos em curso — não há como interromper o
`claude -p` no meio de forma limpa; deixa terminar (sucesso ou timeout).

### 2. Classificação do erro (`timeout` vs outro)

`refinar_blocos` passa a devolver `(resultado, esgotou, motivo)` — `motivo` é
`"timeout"` (mensagem contém "timeout", vem de `atlas.ia.invocar`'s
`subprocess.TimeoutExpired`) ou `"erro"` (qualquer outra falha — ex.: rate-limit
explícito do CLI, binário ausente). Só timeout é elegível pro retry curto.

### 3. Retry curto persistido (`Traducao.status.tentativas_timeout`)

Novo campo de status (persistido no recurso, sobrevive a restart) +
`ConfigTraducao.max_tentativas_timeout` (default **5**) e
`ConfigTraducao.janela_retry_timeout_seg` (default **300** = 5 min).

Em `rotinas/traduzir_pdf.py` (collect), ao terminar um run parcial:

- `motivo_pausa == "timeout"` **e** `tentativas_timeout < max_tentativas_timeout`:
  incrementa `tentativas_timeout`, pausa com a janela **curta** (5 min) — reusa o
  mecanismo de pause/retomada existente (`campos_pausa`, ADR-0035), só que com
  `janela` pequena em vez do padrão de 5h.
- Senão (erro não-timeout, ou já esgotou as tentativas curtas): trata como
  escassez confirmada — pausa com a janela **longa** (`spec.janela_retomada_seg`,
  default 5h) e **zera** `tentativas_timeout` (novo ciclo).
- Run que **não** é parcial (sucesso total): zera `tentativas_timeout` — um
  sucesso prova que a capacidade voltou.

Isso reusa 100% da infraestrutura de pause/retomada já existente (o scanner do
loop principal, `retomar_pausados`) — só varia a janela e o que decide qual
janela usar. Nenhum `sleep()` novo; nenhum estado só-em-memória: tudo sobrevive a
restart porque vive no `status` do recurso.

## Alternativas consideradas

| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| **Pause curto reusando ADR-0035 + threading.Event pro paralelismo (escolhida)** | reusa infra existente; persistente por natureza; sem sleep bloqueante | mais um campo de status; lock serializa parte da contabilidade | **escolhida** |
| `time.sleep()` in-process pros retries curtos | simples de escrever | bloqueia a thread até 25min; estado perdido num restart — viola o pedido de persistência | rejeitada |
| Fila de páginas compartilhada entre jobs (work-stealing global) | paralelismo ótimo entre jobs+páginas | reescreve o pool inteiro; risco alto pra entregar hoje | adiada — ver Pendências |
| Cancelar subprocess em voo ao detectar esgotamento | pararia mais rápido | não há como interromper `claude -p` limpo; complexidade não compensa | rejeitada |

## Consequências

- **Positivas:** escalar o pool agora acelera tanto jobs concorrentes quanto
  páginas de um job só; timeouts pontuais não jogam fora 5h de espera à toa;
  contagem de tentativas sobrevive a restart (persistência real).
- **Negativas / custos:** mais um campo de status (`tentativas_timeout`); o
  paralelismo por página exige cuidado de concorrência (mitigado: lock em volta
  de cache.salvar + progresso; cache em si é seguro por chave sob o GIL do
  CPython — escritas em chaves diferentes não corrompem).
- **Impacto na constituição:** nenhum invariante muda. Estende `ConfigTraducao`,
  `ProgressoTraducao` e o status de `Traducao`. Atualiza índice de ADRs e backlog.

## Pendências
- Fila de páginas **compartilhada entre jobs** (não só dentro de um job) — hoje
  cada job usa até `max_concorrente` workers **próprios**; se dois jobs rodam ao
  mesmo tempo, cada um tenta usar o teto inteiro (não há partilha justa do dial
  entre jobs simultâneos). Fica pro próximo ADR se isso virar gargalo real.
- Classificação de erro por string ("timeout" na mensagem) é frágil se
  `atlas.ia.invocar` mudar o texto — considerar um tipo de exceção dedicado
  (`TimeoutInvocarErro`) numa próxima limpeza.
