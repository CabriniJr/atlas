"""Subir o jogo baixado pro OneDrive e liberar o disco (ADR-0056, fase 2).

O fluxo "Nuvem" do PO: ao concluir o download, o jogo vai para
``onedrive:Jogos/Switch/<nome>`` e **sai do disco local**. A loja continua
servindo-o porque esse mesmo caminho está montado dentro do acervo (ver
``mount``) — do ponto de vista do Switch, nada muda.

**Por que ``rclone move`` e não ``copy`` + ``rm``:** o ``move`` confere cada
arquivo no destino antes de remover a origem. Um ``rm`` cego depois de um upload
truncado apagaria o jogo. Na prática: só apaga o que chegou.
"""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from atlas.nuvem.mount import REMOTO_DEFAULT, rclone_bin

_log = logging.getLogger("atlas.nuvem")

CONFIG_DEFAULT = os.path.expanduser("~/.config/rclone/rclone.conf")


@dataclass
class ResultadoEnvio:
    ok: bool
    mensagem: str
    destino_remoto: str = ""


def montar_args_subir(
    *,
    alvo: str,
    nome: str,
    remoto: str,
    rclone_bin: str,
    config: str = CONFIG_DEFAULT,
) -> list[str]:
    """Argumentos do ``rclone move`` (puro)."""
    return [
        rclone_bin,
        "move",
        alvo,
        f"{remoto}/{nome}",
        "--config",
        config,
        "--delete-empty-src-dirs",
        "--stats-one-line",
        "--stats",
        "30s",
    ]


def subir(
    alvo: str,
    nome: str,
    *,
    remoto: str = REMOTO_DEFAULT,
    config: str = CONFIG_DEFAULT,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> ResultadoEnvio:
    """Sobe ``alvo`` para a nuvem e remove o local **só do que chegou**.

    Nunca levanta: devolve ``ok=False`` com a mensagem do rclone (ADR-0006).
    """
    destino = f"{remoto}/{nome}"
    if not os.path.exists(alvo):
        return ResultadoEnvio(False, f"não encontrei o conteúdo em disco: {alvo}")
    args = montar_args_subir(
        alvo=alvo, nome=nome, remoto=remoto, rclone_bin=rclone_bin(), config=config
    )
    try:
        r = runner(args, capture_output=True, text=True)
    except Exception as e:  # noqa: BLE001
        _log.exception("rclone move falhou para %s", nome)
        return ResultadoEnvio(False, f"falha ao subir {nome}: {e}")
    if getattr(r, "returncode", 1) != 0:
        erro = (getattr(r, "stderr", "") or getattr(r, "stdout", "") or "?").strip()
        return ResultadoEnvio(False, f"falha ao subir {nome}: {erro}", destino)
    _remover_se_vazio(alvo)
    return ResultadoEnvio(True, f"☁️ {nome} está na nuvem (local liberado)", destino)


def _remover_se_vazio(alvo: str) -> None:
    """Remove a raiz da origem **somente** se ficou vazia.

    O ``--delete-empty-src-dirs`` do rclone não apaga a raiz (medido em
    2026-10-03). A sobra não é cosmética: ``servico.arquivar_ausentes`` olha
    ``os.path.exists``, então uma pasta vazia faria o jogo parecer ainda local
    depois de ter ido pra nuvem.

    ``os.rmdir`` é o primitivo seguro: falha se houver qualquer coisa dentro —
    então um upload parcial **nunca** perde arquivo.
    """
    if not os.path.isdir(alvo):
        return
    for raiz, dirs, arquivos in os.walk(alvo, topdown=False):
        if arquivos:
            return  # sobrou conteúdo: a origem fica
        for d in dirs:
            try:
                os.rmdir(os.path.join(raiz, d))
            except OSError:
                return
    try:
        os.rmdir(alvo)
    except OSError:
        _log.info("origem %s não estava vazia; mantida", alvo)
