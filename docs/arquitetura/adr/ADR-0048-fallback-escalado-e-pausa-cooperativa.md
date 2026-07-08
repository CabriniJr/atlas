---
titulo: ADR-0048 — Fallback escalado e visível (Ollama→Claude) e pausa cooperativa nos dois loops
id: ADR-0048
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-08
substitui: —
substituido-por: —
---

# ADR-0048 — Fallback escalado e visível (Ollama→Claude) e pausa cooperativa nos dois loops

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-07-08 | Tech Lead | Pausa cooperativa no loop paralelo + escalada de motor no nível do job (Ollama→Claude), visível | PO/PM |

---

## Status
`aceito` — implementado (E9-16).

## Contexto

O ADR-0045 desligou o fallback bidirecional de `atlas.ia.invocar()` na tradução
(`_invocar_sem_fallback_de_motor`, `fallback=False`): num livro inteiro, trocar de
motor por chamada às escondidas mistura tom entre blocos e queima cota do Claude
numa tarefa que o usuário configurou para rodar local. Correto — mas deixou a
tradução **sem nenhuma** rede quando o endpoint Ollama local está simplesmente
**fora do ar**: o job pausava por "escassez" e reagendava para daqui 5h (ADR-0035),
como se fosse cota — mas esperar não ressuscita um servidor local desligado.

O PO pediu, explicitamente: *"garantir que vai tentar rodar pelo ollama a tradução
e fallback para claude se precisar"*. Ou seja: Ollama continua o padrão/prioridade,
mas quando ele não dá conta (endpoint fora), o job precisa **cair para o Claude** —
sem, contudo, reintroduzir o switch silencioso por chamada que o 0045 removeu.

Em paralelo, apareceu um bug de controle: a pausa manual cooperativa do ADR-0045
(`checar_pausa` no pipeline) só era honrada no loop **sequencial**. A rotina roda em
`paralelismo=pool_global.max_concorrente` (ADR-0039), então com concorrência > 1 o
botão ⏸ era **silenciosamente ignorado**.

## Decisão

1. **Pausa cooperativa honrada nos dois loops.** `_processar_paginas_paralelo` passa a
   receber e honrar `checar_pausa`: cada worker, **antes** de pegar a próxima página,
   checa o pedido de pausa; se setado, um `threading.Event` compartilhado é acionado,
   `motivo_pausa="manual"` é registrado (sob lock) e as páginas ainda não iniciadas são
   puladas. Páginas em voo terminam (o checkpoint por página garante o progresso). A
   pausa **nunca** mata uma chamada de IA em andamento (não corrompe o checkpoint).

2. **Escalada de motor no nível do job — determinística e visível.** O
   `_invocar_sem_fallback_de_motor` do 0045 é substituído por `montar_invocar_escalavel`,
   um wrapper de `ia.invocar` que:
   - usa o motor pedido (`cfg.motor`, default `ollama`) à risca enquanto funciona;
   - numa falha classificada como **conexão** (endpoint fora — `_classificar_erro`
     ganha a classe `"conexao"`), tenta rápido até `cfg.escalonar_apos_falhas` vezes
     (default 3) — *connection refused* é imediato/determinístico contra um servidor
     local, então isso não introduz latência relevante;
   - esgotadas as tentativas, **muta `cfg.motor` para `cfg.escalonar_para`** (Claude) e
     **retenta a chamada** no novo motor com `modelo=None` (nunca herda o modelo do
     Ollama). `cfg.motor` é a **fonte única** do motor atual, relida pelo pipeline a
     cada lote — então a escalada vale para **todo o restante** do job. A parte já
     traduzida em Ollama fica no cache (a chave de cache independe do motor), sem
     re-tradução;
   - a escalada é **idempotente sob concorrência**: a mutação de `cfg` + o callback
     `on_escala` ficam sob lock com guarda `if cfg.motor == "ollama"`, então só o
     primeiro worker a cruzar o limiar escala (e emite o evento) uma única vez;
   - **timeout/erro não escalam**: propagam direto e caem no retry/pausa do ADR-0039
     (Ollama ocupado ≠ Ollama fora; cota do Claude recupera com o tempo).

3. **Visibilidade.** `on_escala` grava em `Traducao.status`: `motor_efetivo` (motor
   realmente em uso), `escalonado_em`, `escalonado_motivo`, e uma linha de log. A UI
   mostra um badge `ollama → claude ⚡` com tooltip do motivo quando `motor_efetivo`
   difere de `spec.motor`.

4. **Leitura atômica do motor no pipeline.** Como a escalada muta `cfg` em tempo de
   execução com workers concorrentes, o call site do pipeline lê `cfg.motor` **uma
   vez** por lote (`motor_lote`) e o usa tanto para `modelo_padrao(...)` quanto para o
   `motor=` — evitando um *torn read* em que um worker computaria o modelo do Ollama e
   chamaria o Claude com ele.

## Alternativas consideradas
| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Reativar `fallback=True` do `ia.invocar` na tradução | Trivial | Reintroduz o switch **silencioso por chamada** (mistura de tom, cota escondida) | É exatamente o que o ADR-0045 removeu de propósito |
| Contador cross-batch de falhas consecutivas (com reset por lote OK) | Tolera "flap" intermitente do endpoint | Mais estado (campo em `status`), mais complexo; um endpoint local que "flapa" é raro e escalar pro Claude continua a escolha segura | A escalada por **retry rápido por chamada** é mais simples e, contra um endpoint determinísticamente fora, escala já no 1º lote em vez de esperar 3 lotes distintos |
| Escalar re-traduzindo tudo num motor só | Um motor só no doc inteiro | Desperdiça o cache já pago em Ollama | O ganho de consistência não paga o custo; cada trecho (pré/pós escalada) já é internamente consistente |

## Consequências
- **Positivas:** o pedido do PO é atendido (Ollama-first com queda pro Claude quando
  o local está fora); o ⏸ funciona de verdade em qualquer concorrência; a escalada é
  auditável (status + badge); o já-pago em Ollama é reaproveitado.
- **Negativas / custos:** a escalada é **por run** — em resume/restart o job re-tenta
  Ollama, refalha por conexão e re-escala (o badge pode "piscar" `ollama`→`claude` de
  novo). Aceitável: é auto-curativo e não paga IA duas vezes (cache). Contra um
  endpoint que "flapa" (raro), 3 retries sem backoff não toleram o blip — mas escalar
  pro Claude é seguro.
- **Impacto na constituição:** **supersede a postura de fallback** do ADR-0045 (mantém
  "Ollama padrão" e os controles reais pausar/recomeçar/re-refinar). Refina o ADR-0040
  (o fallback bidirecional de `ia.invocar` continua existindo para outros usos — ex.:
  dev-agent — mas a tradução usa a política de **escalada de job**, não o switch por
  chamada) e o ADR-0039 (timeout/erro seguem o retry/pausa; conexão vira escalada).

## Pendências
- Persistir a escalada no `spec` (não só no `cfg` em memória) para o resume não
  re-tentar Ollama — só se o "piscar" do badge incomodar na prática.
- Pausa cooperativa que **cancela** uma chamada de IA em voo (cancelamento hard) —
  fora de escopo; hoje a pausa é entre páginas.
