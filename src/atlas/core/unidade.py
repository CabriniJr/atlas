"""Unit de usuário que **possui** um container do Atlas (ADR-0051, revisto 2026-10-03).

O ``conmon`` nasce no cgroup de quem chamou o ``podman run``. Quando isso é o
``atlas.service``, reiniciar o Atlas mata o container — medido em 2026-10-03:
``atlas-qbt`` e ``atlas-ownfoil`` caíam a cada restart, interrompendo download em
curso. Com a unit, o dono é o **systemd**: o container sobrevive a restart/deploy
do Atlas e sobe no boot sem depender dele (``Linger=yes``).

As funções são puras/injetáveis — exercitadas sem systemd nem podman.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable

SYSTEMCTL = "systemctl"
# Parada graciosa: o qBittorrent precisa salvar o resume data dos torrents.
STOP_TIMEOUT_S = 30


def tem_systemd_no_ar() -> bool:
    """``True`` se há um ``systemd --user`` para possuir o container."""
    return shutil.which(SYSTEMCTL) is not None and bool(os.environ.get("XDG_RUNTIME_DIR"))


def montar_unit(
    *,
    nome: str,
    run_args: list[str],
    runtime_bin: str | None = None,
    runtime: str = "podman",
) -> str:
    """Conteúdo da unit (puro).

    Roda o podman em **foreground** (sem ``-d``) — é assim que o systemd
    supervisiona o processo em vez de perder o filho. ``ExecStart``/``ExecStop``
    usam **caminho absoluto**, que o systemd exige.
    """
    binario = runtime_bin or shutil.which(runtime) or f"/usr/bin/{runtime}"
    args = [binario] + [a for a in run_args[1:] if a != "-d"]
    return f"""[Unit]
Description=Atlas — container {nome} (dono: systemd, não o atlas.service)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={" ".join(args)}
ExecStop={binario} stop -t {STOP_TIMEOUT_S} {nome}
TimeoutStopSec={STOP_TIMEOUT_S + 30}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""


def unit_dir_default() -> str:
    return os.path.expanduser("~/.config/systemd/user")


def gravar_e_subir(
    *,
    nome: str,
    run_args: list[str],
    unit_dir: str,
    runner: Callable[..., object],
    runtime: str = "podman",
) -> str:
    """Escreve/atualiza a unit, recarrega, habilita e dá ``start``. Devolve o caminho.

    Só reescreve e recarrega quando o conteúdo mudou (idempotente).
    """
    os.makedirs(unit_dir, exist_ok=True)
    unit = f"{nome}.service"
    caminho = os.path.join(unit_dir, unit)
    conteudo = montar_unit(nome=nome, run_args=run_args, runtime=runtime)
    atual = ""
    if os.path.isfile(caminho):
        with open(caminho) as f:
            atual = f.read()
    if atual != conteudo:
        with open(caminho, "w") as f:
            f.write(conteudo)
        runner([SYSTEMCTL, "--user", "daemon-reload"], capture_output=True, text=True)
    # `enable` deixa o container subir no boot sem depender do Atlas.
    runner([SYSTEMCTL, "--user", "enable", unit], capture_output=True, text=True)
    runner([SYSTEMCTL, "--user", "start", unit], capture_output=True, text=True)
    return caminho
