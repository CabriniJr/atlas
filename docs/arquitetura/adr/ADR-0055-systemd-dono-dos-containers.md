---
titulo: ADR-0055 — systemd é o dono dos containers do Atlas (não o atlas.service)
id: ADR-0055
status: aceito
versao: 0.1
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-10-03
substitui: —
substituido-por: —
---

# ADR-0055 — systemd é o dono dos containers do Atlas

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-10-03 | Tech Lead | Proposta e aceite (PO escolheu "systemd dono, Atlas só dá start") | PO |

---

## Status
`aceito` — revisa o ciclo de vida definido no [ADR-0051](ADR-0051-torrent-client-em-container-podman.md)
(torrent) e no [ADR-0052](ADR-0052-ownfoil-tinfoil-via-funnel.md) (Ownfoil). Não muda
runtime (segue **podman rootless**), nem flags, nem config — só **quem possui** o processo.

## Contexto

Os dois containers (`atlas-qbt`, `atlas-ownfoil`) subiam com `podman run -d`
chamado de dentro do processo do Atlas. Em podman **rootless e daemonless**, o
`conmon` (o supervisor do container) nasce **no cgroup de quem chamou**. Como quem
chama é o `atlas.service`, os containers ficavam dentro do cgroup do serviço.

`systemd` mata o cgroup inteiro no `stop`/`restart` (`KillMode=control-group`, o
default). Consequência medida em 2026-10-03:

```
# conmon ANTES da mudança
atlas-qbt     -> /user.slice/.../app.slice/atlas.service
atlas-ownfoil -> /user.slice/.../app.slice/atlas.service
```

Um `systemctl --user restart atlas` — isto é, **qualquer deploy** — derrubava o
client de torrent. Observado ao vivo: o `atlas-qbt` saiu como `Exited (0)` no
restart, e só voltava na próxima vez que alguém confirmasse um download
(`garantir_no_ar` é lazy). Com download em curso, isso **interrompe um jogo de
25 GB no meio**. O Ownfoil tinha o mesmo defeito, com o agravante de ser
reiniciado a cada restart sem ninguém notar.

O contraste estava na própria máquina: o `buildkit` do podman vive em
`podman-restart.service` e sobrevive a tudo.

## Decisão

**O systemd passa a ser o dono.** Cada container tem uma **unit de usuário**
(`atlas-qbt.service`, `atlas-ownfoil.service`), e o Atlas apenas garante que ela
exista e esteja no ar:

1. `core/unidade.py` (novo, puro/injetável) — `montar_unit` renderiza a unit a
   partir do **mesmo** `montar_run_args` já usado pelo `podman run`, mantendo uma
   única fonte de verdade das flags (`:Z` do SELinux, `--userns=keep-id`, binds).
2. `garantir_no_ar` → `gravar_e_subir`: escreve a unit **só se mudou**,
   `daemon-reload`, `enable` e `start`. Idempotente.
3. A unit roda o podman em **foreground** (sem `-d`): é isso que põe o `conmon`
   no cgroup da unit em vez de perdê-lo como filho.
4. `ExecStop = podman stop -t 30` + `TimeoutStopSec=60` — parada graciosa, para o
   qBittorrent salvar o **resume data** em vez de ser morto.
5. `ExecStart`/`ExecStop` com **caminho absoluto** do binário (o systemd recusa a
   unit sem isso — pego por teste).
6. `WantedBy=default.target` + `enable`: com `Linger=yes`, os containers sobem no
   **boot** sem depender do Atlas. O Atlas deixa de ser o caminho crítico.

**Fallback preservado:** sem `systemd --user` (CI, outra máquina), cai no
`podman run -d` de antes — decidido por `tem_systemd`, injetável.

## Consequências

**Ganhos**
- Download sobrevive a restart e a deploy do Atlas (**verificado ao vivo**: o
  `atlas-qbt` seguiu `Up` contínuo e com WebUI 200 através de um `restart atlas`,
  enquanto o Ownfoil ainda-não-migrado voltou a `Up 3 seconds`).
- Container sobe no boot por si; o Atlas só reconcilia.
- Parada graciosa em vez de morte por cgroup.

**Custos / riscos**
- Passa a existir estado fora do repo (`~/.config/systemd/user/atlas-*.service`).
  Mitigado: a unit é **derivada** do código e reescrita quando divergir, então o
  código segue sendo a fonte de verdade.
- Testes podiam escrever no `~/.config/systemd/user` real — aconteceu durante a
  implementação (unit apontando para `/tmp/pytest-*`). Fixtures agora **fixam**
  `unit_dir` em `tmp_path` e `tem_systemd=False`.

## Alternativas consideradas
- **Quadlet** (`~/.config/containers/systemd/*.container`): mais idiomático, mas
  duplicaria as flags do `montar_run_args` num segundo formato.
- **`--restart=always` + `podman-restart.service`**: resolve o boot, **não**
  resolve o restart do Atlas — o `conmon` continuaria no cgroup errado.
- **`KillMode=process` no `atlas.service`**: pararia de matar os containers, mas
  também deixaria de limpar os outros filhos do Atlas.
