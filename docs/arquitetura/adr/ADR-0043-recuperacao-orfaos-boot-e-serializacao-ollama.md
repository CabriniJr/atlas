---
titulo: ADR-0043 — Recuperação de jobs órfãos no boot + serialização de chamadas Ollama locais
id: ADR-0043
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-02
substitui: —
substituido-por: —
---

# ADR-0043 — Recuperação de jobs órfãos no boot + serialização de chamadas Ollama locais

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-07-02 | Tech Lead | Proposta + implementação (dois fixes operacionais descobertos em produção) | PO/PM |

---

## Status
`aceito` — implementado; código já referenciava este ADR antes do documento
existir (débito de documentação corrigido nesta versão).

## Contexto

Dois problemas operacionais distintos, ambos ligados ao pipeline de tradução
(épico E9) rodando contra o servidor Ollama local:

1. **Restart mata job em andamento sem checkpoint de pausa.** Um `Traducao`
   preso na fase `traduzindo`/`fila`/`retomando` quando o processo reinicia
   (crash ou deploy via `atlas-deploy.timer`, ADR-0043 nada tem a ver com o
   deploy em si, mas sofre o efeito) fica **preso para sempre**: o guard de
   reinício (`_iniciar_traducao`) recusa religar porque "já está traduzindo",
   e não existe pausa automática (essa só acontece por escassez de quota,
   ADR-0035) para esse caso. O usuário fica sem saída pela UI.
2. **Paralelismo de página (ADR-0039) contra um servidor Ollama que processa
   sequencialmente.** Ao contrário da nuvem Claude (elástica), o servidor
   Ollama da LAN processa uma inferência por vez. Disparar N chamadas HTTP
   concorrentes faz todas além da primeira ficarem na fila do lado do
   servidor — o timeout é contado do lado do cliente, então elas estouram
   antes de serem atendidas, disparando o fallback claude↔ollama (ADR-0040)
   por um falso-positivo de indisponibilidade, não por um problema real.

## Decisão

1. **`retomada.recuperar_orfaos_no_boot(store, agora)`** — roda uma vez no
   boot (`app.run`), antes do primeiro ciclo do scheduler. No boot sabemos com
   certeza que nada estava rodando ainda (acabamos de subir); logo, qualquer
   recurso num Kind com job assíncrono (`_KINDS_COM_JOB_ASSINCRONO`, hoje só
   `Traducao`) numa fase órfã (`_FASES_ORFAS = "traduzindo"/"fila"/"retomando"`)
   é, por definição, órfão de um restart anterior. É recolocado em `pausado`
   com `retoma_em=agora` (retomada imediata) — o ciclo normal de
   `retomar_pausados`, chamado logo em seguida no loop do app, já pega de
   volta no primeiro tick, sem intervenção manual. Nunca propaga exceção
   (ADR-0006): um recurso corrompido não pode impedir o boot nem a recuperação
   dos demais.
2. **`ia._OLLAMA_SEMAFORO`** (`threading.Semaphore`, teto
   `ATLAS_OLLAMA_MAX_CONCURRENT`, default `1`) — serializa `_chamar_ollama` no
   processo inteiro. Bate com a capacidade real de um servidor Ollama local
   (processa sequencialmente); configurável via env se o operador subir o
   servidor com `OLLAMA_NUM_PARALLEL` maior. Não afeta `_chamar_claude` (nuvem
   elástica, sem necessidade de serializar).

## Alternativas consideradas

| Alternativa | Prós | Contras | Veredito |
|---|---|---|---|
| **Recuperação de órfãos só no boot** (não em todo tick) | simples; boot é o único momento em que "nada está rodando" é uma garantia, não uma suposição | não cobre um travamento que não seja causado por restart (não é o caso observado) | **escolhida** |
| Timeout/watchdog periódico que declara um job "travado" após N minutos sem progresso | cobriria mais casos | falso-positivo real (job lento, não travado) exigiria heurística; mais complexo que o problema pedia | adiada (pendência) |
| **Semáforo global por processo** para chamadas Ollama | simples; um parâmetro; corrige o falso-positivo na causa raiz | serializa TODAS as chamadas ollama do processo, não só as de um job (aceitável: já é o gargalo real do servidor) | **escolhida** |
| Reduzir o paralelismo de páginas (ADR-0039) apenas quando o motor é ollama | evita fila do lado do cliente também | duplicaria a decisão de concorrência em dois lugares (pool de réplicas E9-10 + paralelismo de página E9-11); o semáforo resolve no ponto único de chamada (`ia.py`) | rejeitada |

## Consequências

- **Positivas:** um restart não trava mais uma tradução em andamento sem saída
  pela UI; falso-positivo de "ollama indisponível" por fila do lado do
  servidor desaparece — o fallback claude↔ollama (ADR-0040) só dispara para
  indisponibilidade real.
- **Negativas / custos:** com `ATLAS_OLLAMA_MAX_CONCURRENT=1` (default), o
  paralelismo de página (ADR-0039) perde efeito prático quando o motor
  resolvido é ollama — as chamadas viram sequenciais de qualquer forma
  (aceitável: é a capacidade real do servidor, não uma escolha artificial).
- **Impacto na constituição:** estende ADR-0035 (pausa/retomada) para cobrir
  órfãos de restart, além de escassez de quota; estende ADR-0039/0040
  (paralelismo e fallback) com o limite real de concorrência do motor local.
  Nenhuma decisão anterior é revertida.

## Pendências
- Se o operador rodar Ollama com `OLLAMA_NUM_PARALLEL>1`, reavaliar o default
  de `ATLAS_OLLAMA_MAX_CONCURRENT` (hoje fixo em 1 salvo override manual).
- Recuperação de órfãos cobre só `Traducao`; generalizar
  `_KINDS_COM_JOB_ASSINCRONO` se outro Kind ganhar job assíncrono de vida longa.
