---
titulo: ADR-0051 — Client de torrent em container (Podman) com fila nativa e auto-envio
id: ADR-0051
status: aceito
versao: 0.1
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-14
substitui: —
substituido-por: —
---

# ADR-0051 — Client de torrent em container (Podman) com fila nativa e auto-envio

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-07-14 | Tech Lead | Proposta e aceite (PO decidiu runtime e escopo) | PO |

---

## Status
`aceito` — resolve o item **diferido** do ADR-0050 (torrent cliente-único).

## Contexto

O PO quer o client de torrent num **container Linux** e que o Atlas **envie o
arquivo ao concluir**. O modelo atual (ADR-0049) sobe **um `qbittorrent-nox` por
download** (profile/porta por infohash + `TorrentPool`), o que gera o bug do socket
de instância única e era o refactor de cliente único **diferido** no ADR-0050.

Restrições verificadas na máquina: `docker` **ausente** (instalar exige sudo/daemon
root, indisponível); `podman 5.8.2` **presente**, rootless pronto. Decisões do PO:
runtime = **podman rootless**; escopo = **um container único** substituindo o nox.

Design detalhado: `docs/superpowers/specs/2026-07-14-torrent-container-podman.md`.

## Decisão

1. **Um container `linuxserver/qbittorrent`** (podman rootless) é o client único.
   Volumes: `<destino>`→`/downloads`, `~/.local/share/atlas-torrent/cliente`→
   `/config`. WebUI publicada só em `127.0.0.1:<porta>`.
2. **Fila nativa** do qBittorrent (`QueueingSystemEnabled=true`,
   `MaxActiveDownloads=N`) substitui o `TorrentPool` em memória. "Baixando vs fila"
   deriva do estado do qBittorrent.
3. **Monitor único** (uma thread) poll-a `/torrents/info`, atualiza cada `Torrent`,
   dispara marcos e, ao concluir, roda integridade (magic + tamanho, `_esta_completo`
   já corrigido) e **auto-envia** o resultado ao dono.
4. **Auto-envio:** arquivo único ≤ 49 MB → documento no Telegram; pasta/múltiplos/
   > 49 MB (jogo/ISO típico) → mensagem com o caminho local (limite do bot ~50 MB).
5. **Fallback:** sem `podman`, o caminho `qbittorrent-nox` (ADR-0049) segue válido.
6. Segurança preservada: encriptação forçada, modo anônimo, sem port-forward, sem
   semear por default; WebUI só no bind local.

## Alternativas consideradas
| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Instalar Docker | É o que o PO pediu ao pé da letra | Precisa sudo + daemon root (indisponível) | Podman roda a mesma imagem, rootless, sem daemon |
| Manter N `qbittorrent-nox` | Já funciona | N processos/portas; bug do socket único | Container único + fila nativa resolve os dois |
| Um container por download | Isola cada download | N containers/portas; mesma complexidade de hoje | Fila nativa num client só é mais simples |

## Consequências
- **Positivas:** um processo (container) em vez de N daemons; some o bug do socket;
  fila nativa; entrega o auto-envio pedido; reusa integridade/marcos/estado no
  recurso. Resolve o diferido do ADR-0050.
- **Negativas / custos:** dependência de `podman` (com fallback p/ nox); torrent
  grande não cabe no Telegram (envia caminho); kill-switch de VPN dentro do
  container fica p/ incremento (gate de VPN roda no host antes de adicionar).
- **Impacto na constituição:** reforça P5 (simplicidade) e P4 (estado no repo — a
  fase segue no recurso). Revisa parte do ADR-0049 (pool/nox → container/fila nativa).

## Notas de implementação (rootless + SELinux)
No smoke test real (Fedora, SELinux enforcing) o container só sobe com **`:Z`** nos
volumes (relabel SELinux — sem isso, `Permission denied` no `/config` e o container
nem inicia) e **`--userns=keep-id:uid=911,gid=911`** (o user `abc`=911 do linuxserver
mapeia para o uid do host, então escreve no `/config` e os downloads saem com o dono
do host — o Atlas os lê para auto-enviar). Ver `torrent/container.py::montar_run_args`.

## Pendências
- ✅ **Smoke test de download real com podman feito (2026-07-14):** container sobe
  passwordless (qBittorrent v5.2.3), `add` via multipart, download real do Debian
  netinst a ~4.8 MB/s / 39 seeds, dados no host com dono correto.
- Kill-switch de VPN dentro do container (backlog).
- Migração de downloads nox em andamento → container (por ora: novos vão pro
  container; os do nox terminam no nox).
