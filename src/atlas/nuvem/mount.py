"""Ponto de montagem do OneDrive dentro do acervo da loja (ADR-0056).

Dois achados que moldam este módulo (medidos em 2026-10-03):

1. **O mount tem de existir ANTES do container.** Os volumes do Ownfoil são
   ``propagation=rprivate``; um mount criado depois **não** aparece dentro do
   container (ele vê o diretório vazio). Como o ``-v`` é *rbind*, submount que já
   existe no start entra. Daí ``Type=notify``: o systemd só considera a unit
   pronta **depois** do mount, e quem vem ``After=`` enxerga tudo.
2. **O acervo não pode ter ``:Z``.** O relabel recursivo do podman falha no FUSE
   read-only (``lsetxattr: read-only file system``) e o container não sobe. Sem o
   ``:Z``, ninguém rotula: o acervo **local** passa a ser rotulado por nós
   (``rotular_acervo`` → ``container_file_t:s0``, sem categorias MCS), e o mount
   fica ``fusefs_t``, que a política do Fedora já deixa o ``container_t`` ler
   (medido: zero negações AVC com SELinux ``Enforcing``).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field

from atlas.core import unidade

_log = logging.getLogger("atlas.nuvem")

NOME_UNIT = "atlas-nuvem"
REMOTO_DEFAULT = "onedrive:Jogos/Switch"
# Subpasta do acervo que o Ownfoil já serve — a nuvem entra como mais uma pasta.
PONTO_DEFAULT = os.path.expanduser("~/Games/Switch/Nuvem")
# Rótulo de dado compartilhado p/ o acervo LOCAL: qualquer container o lê
# (tipo container_file_t + nível s0 sem categorias MCS). Ver `rotular_acervo`.
CONTEXTO_SELINUX = "system_u:object_r:container_file_t:s0"
# O Ownfoil lê o header de cada NSP/NSZ no scan; sem cache ele rebaixaria da
# nuvem a cada varredura.
VFS_CACHE_MAX = "8G"
DIR_CACHE_TIME = "72h"
_FUSERMOUNT = "/usr/bin/fusermount3"


def rclone_bin() -> str:
    return shutil.which("rclone") or os.path.expanduser("~/bin/rclone")


def disponivel() -> bool:
    """``True`` se há rclone e fuse para montar a nuvem."""
    return os.path.isfile(rclone_bin()) and os.path.exists(_FUSERMOUNT)


def montar_unit_mount(
    *,
    remoto: str,
    ponto: str,
    rclone_bin: str,
    config: str,
    cache_dir: str,
) -> str:
    """Conteúdo da unit do mount (puro).

    ``--config``/``--cache-dir`` são explícitos porque o systemd roda a unit **sem
    HOME nem PATH** — ``~`` não expande (requisito da própria doc do rclone).

    **Nada de ``-o context=``:** medido em 2026-10-03, o rclone **descarta** esse
    flag (não aparece em ``mount``). O mount fica ``fusefs_t`` e funciona porque a
    política do Fedora permite ``container_t`` ler ``fusefs_t`` — verificado com
    zero negações AVC e SELinux ``Enforcing``. Quem precisa de rótulo explícito é
    o acervo **local**: ver ``rotular_acervo``.
    """
    flags = (
        f"--config {config} --cache-dir {cache_dir} "
        f"--read-only --vfs-cache-mode full --vfs-cache-max-size {VFS_CACHE_MAX} "
        f"--dir-cache-time {DIR_CACHE_TIME}"
    )
    return f"""[Unit]
Description=Atlas — OneDrive montado no acervo da loja (rclone)
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
ExecStartPre=/usr/bin/mkdir -p {ponto}
ExecStart={rclone_bin} mount {remoto} {ponto} {flags}
ExecStop={_FUSERMOUNT} -u {ponto}
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
"""


def rotular_acervo(
    acervo: str, *, runner: Callable[..., subprocess.CompletedProcess] = subprocess.run
) -> bool:
    """Garante ``container_file_t:s0`` no acervo local (idempotente).

    O volume do acervo perdeu o ``:Z`` (ADR-0056), então **ninguém** rotula por
    nós. Sem isto o container (``container_t:s0:cX,cY``) é negado:
    - tipo errado → negação de leitura;
    - **categorias MCS** sobrando de um ``:Z`` antigo (ex. ``s0:c30,c41``) →
      negação, porque as categorias do container não casam. ``-l s0`` zera o
      nível e torna o acervo legível por qualquer container.

    Fazer isto em código (e não "lembrar de rodar o chcon") é o que impede a
    regressão silenciosa.
    """
    if not os.path.isdir(acervo):
        return False
    r = runner(
        ["chcon", "-R", "-l", "s0", "-t", "container_file_t", acervo],
        capture_output=True,
        text=True,
    )
    ok = getattr(r, "returncode", 1) == 0
    if not ok:
        _log.warning("chcon no acervo %s falhou: %s", acervo, getattr(r, "stderr", ""))
    return ok


@dataclass
class ClienteNuvem:
    """Garante o OneDrive montado no acervo. ``runner`` é injetável (testes)."""

    remoto: str = REMOTO_DEFAULT
    ponto: str = PONTO_DEFAULT
    config: str = os.path.expanduser("~/.config/rclone/rclone.conf")
    cache_dir: str = os.path.expanduser("~/.cache/rclone")
    unit_dir: str = field(default_factory=unidade.unit_dir_default)
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run

    @property
    def unit(self) -> str:
        return f"{NOME_UNIT}.service"

    def esta_montado(self) -> bool:
        return os.path.ismount(self.ponto)

    def conteudo_unit(self) -> str:
        return montar_unit_mount(
            remoto=self.remoto,
            ponto=self.ponto,
            rclone_bin=rclone_bin(),
            config=self.config,
            cache_dir=self.cache_dir,
        )

    def garantir_montado(self) -> bool:
        """Idempotente: escreve/atualiza a unit e sobe. ``True`` se montado."""
        if self.esta_montado():
            return True
        os.makedirs(self.unit_dir, exist_ok=True)
        caminho = os.path.join(self.unit_dir, self.unit)
        conteudo = self.conteudo_unit()
        atual = ""
        if os.path.isfile(caminho):
            with open(caminho) as f:
                atual = f.read()
        if atual != conteudo:
            with open(caminho, "w") as f:
                f.write(conteudo)
            self.runner(
                [unidade.SYSTEMCTL, "--user", "daemon-reload"], capture_output=True, text=True
            )
        self.runner(
            [unidade.SYSTEMCTL, "--user", "enable", self.unit], capture_output=True, text=True
        )
        self.runner(
            [unidade.SYSTEMCTL, "--user", "start", self.unit], capture_output=True, text=True
        )
        return self.esta_montado()
