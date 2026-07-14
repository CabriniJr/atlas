# Design — Client de torrent em container (Podman) + auto-envio

- **Data:** 2026-07-14
- **Autor:** Claude (Opus) — PO: humano
- **ADR:** ADR-0051
- **Status:** aprovado (arquitetura decidida pelo PO), em implementação

## Problema

O PO quer o **download e o client de torrent rodando num container Linux** e que,
**ao terminar, o Atlas pegue o arquivo e mande pra ele** (Telegram). Hoje o Atlas
sobe **um `qbittorrent-nox` por download** (profile + porta por infohash, pool em
memória) — modelo que gera o bug do socket de instância única
(`listen on local socket failed, error 17`) e é o refactor de cliente único que
estava **diferido** no ADR-0050.

Restrições reais da máquina (verificadas):
- `docker` **não** está instalado; instalar exige `sudo`/daemon root (indisponível).
- `podman 5.8.2` **está** instalado, rootless pronto (`subuid`/`subgid`). Podman é
  compatível com Docker e roda a mesma imagem **sem daemon e sem root**.

**Decisão do PO:** runtime = **podman rootless**; escopo = **um container único**
que substitui o `qbittorrent-nox` (fila nativa do qBittorrent).

## Arquitetura

### Um container compartilhado (`linuxserver/qbittorrent`)

Um **único** container Linux roda o qBittorrent com **fila nativa**. Some o modelo
de 1 daemon/porta/profile por download e o `TorrentPool` em memória — "baixando vs
fila" passa a derivar do **estado do qBittorrent** (`downloading/stalledDL` vs
`queuedDL`).

- **Volumes:** `<destino>` → `/downloads` (dados caem direto no host, sem cópia);
  `~/.local/share/atlas-torrent/cliente` → `/config` (config/sessão persistem;
  retoma parciais após restart).
- **Rede:** WebUI publicada só em `127.0.0.1:<porta>` do host. Segurança preservada
  (encriptação forçada, modo anônimo, sem port-forward, sem semear por default).
- **Fila nativa:** `QueueingSystemEnabled=true`, `MaxActiveDownloads=N`,
  `MaxActiveTorrents=N` (N do `ATLAS_TORRENT_MAX_CONCURRENT`, default 3).
- **Auth:** WebUI só alcançável pela porta local mapeada → passwordless no client
  (`LocalHostAuth=false`, `AuthSubnetWhitelistEnabled=true`,
  `AuthSubnetWhitelist=0.0.0.0/0`). O limite de rede é o bind em `127.0.0.1`.

### Módulos

- **`torrent/container.py` — `ClienteContainer`** (novo). Gerencia o container e
  fala com a WebUI. Injetáveis nos testes: `runner` (subprocess) e `http` (get/post).
  - `disponivel()` — `shutil.which("podman")`.
  - `montar_conf(cfg, max_ativos)` / `montar_run_args(...)` — **puros** (testáveis).
  - `garantir_no_ar()` — idempotente: se o container já roda, no-op; senão grava a
    config no volume, `podman run -d --replace ...`, espera a WebUI.
  - `adicionar(torrent_bytes, nome)` — `POST /torrents/add` (multipart, savepath
    `/downloads`). Enfileira nativamente; o .torrent vai por bytes (sem mapear path).
  - `listar()` → `/torrents/info` (todos). `progresso_de(infohash)` → `Progresso`
    (reusa `_esta_completo`, já corrigido: espera sair de `moving/checkingUP`).
  - `parar_p2p(infohash)`, `remover(infohash)`, `encerrar()` (`podman stop`).

- **`torrent/monitor.py` — monitor único** (novo). Uma thread no boot poll-a o
  container e dirige **todos** os recursos `Torrent`:
  - `tick(store, cliente, notificar, enviar)` — uma varredura (pura o suficiente p/
    testar com fakes): casa cada `Torrent` em `baixando/fila` por infohash, atualiza
    `status` (progresso/velocidade/seeds/estado/fase), dispara marcos (10/50/90%) e,
    **ao concluir**: integridade (magic + tamanho) → `remover` do client → e o
    **auto-envio** (feature pedida).
  - `monitorar(...)` — loop que chama `tick` a cada `intervalo_s` numa thread daemon.

- **`torrent/servico.py`** — ganha o caminho container: `confirmar` adiciona ao
  `ClienteContainer` e marca `baixando` (ou `fila`, derivado do estado); o pool sai
  do caminho container. `retomar_no_boot` re-adiciona os pendentes ao container
  (retomam do parcial no volume). O caminho `qbittorrent-nox` fica como **fallback**
  quando `podman` não está disponível (Rasp sem podman segue funcionando).

- **`app.py`** — no boot: sobe o `ClienteContainer` (lazy) + inicia o monitor único;
  injeta `enviar` = `enviar_documento`/notificação. `confirmar` usa o container.

### Auto-envio ao concluir (a feature)

No `tick`, quando um `Torrent` conclui (`_esta_completo` e integridade rodada):
- **arquivo único ≤ 49 MB** → `enviar_documento(chat, arquivo, legenda="✅ baixado: …")`.
- **pasta / múltiplos arquivos / > 49 MB** (o caso comum de jogo/ISO) → mensagem
  com o **caminho local** e o resumo de integridade (limite do bot ~50 MB). Reusa
  `conversa.acoes.preparar_envio`. Honesto: torrent grande não cabe no Telegram; o
  Atlas avisa que terminou e onde está, em vez de falhar o envio.

## Testes (TDD)

- `container`: `montar_conf` tem queueing/segurança/auth; `montar_run_args` mapeia
  volumes + publica `127.0.0.1:porta`; `garantir_no_ar` idempotente (não sobe 2x);
  `adicionar` monta multipart; `progresso_de` casa por infohash e usa `_esta_completo`.
- `monitor.tick`: atualiza N recursos por uma listagem; conclui só quem passou de
  `moving`; ao concluir chama integridade + `enviar` + `remover`; marco dispara 1x.
- `servico`: `confirmar` adiciona ao client e deriva `baixando`/`fila`; fallback p/
  nox quando `podman` ausente. `retomar_no_boot` re-adiciona pendentes.
- Auto-envio: arquivo pequeno → documento; pasta/grande → caminho (mock do envio).

## Smoke test (real, com podman — de-risca o item que estava diferido)

**Feito (2026-07-14):** `podman pull linuxserver/qbittorrent`, `garantir_no_ar`,
WebUI passwordless (qBittorrent v5.2.3), `adicionar` do Debian netinst `.torrent`,
progresso real a ~4.8 MB/s / 39 seeds, dados no host com dono correto (`1000:1000`).

**Achados que viraram fix no `montar_run_args`** (sem eles o container nem sobe):
- **SELinux enforcing (Fedora):** volume sem label → `Permission denied` no
  `/config`. Fix: **`:Z`** nos volumes.
- **Mapeamento de uid rootless:** o user `abc` (911) do linuxserver precisa mapear
  para o uid do host. Fix: **`--userns=keep-id:uid=911,gid=911`** (downloads saem
  com o dono do host; o Atlas lê p/ auto-enviar).
- **Colisão de porta:** o fallback nox usa 8099+; o container foi p/ **8190**.

## Fora de escopo (backlog)

- Dividir/compactar torrent grande p/ caber no Telegram (por ora: caminho local).
- Kill-switch de VPN dentro do container (rede do container ≠ iface do host) — por
  ora o gate de VPN roda no host antes de adicionar; revisar em incremento próprio.
- Migrar downloads em andamento do modelo nox → container (por ora: novos vão pro
  container; os do nox terminam no nox).
