"""Keep-awake: impede a máquina de suspender enquanto o Atlas roda (ADR-0050).

Segura um inibidor ``systemd-inhibit`` de ``sleep``/``idle``/fechar-tampa como um
subprocesso, encerrado no shutdown. Best-effort: sem ``systemd-inhibit`` (ou fora
de um sistema systemd), loga e segue — nunca derruba o boot (ADR-0006). NÃO
bloqueia desligar de propósito, só a suspensão automática.
"""

from __future__ import annotations

import logging
import shutil
import subprocess

_log = logging.getLogger("atlas.keepawake")

_BIN = "systemd-inhibit"
_WHAT = "sleep:idle:handle-lid-switch"


def comando() -> list[str]:
    """O comando do inibidor (função pura, testável)."""
    return [
        _BIN,
        f"--what={_WHAT}",
        "--who=Atlas",
        "--why=jobs Atlas (tradução/torrent) em andamento",
        "--mode=block",
        "sleep",
        "infinity",
    ]


def iniciar() -> subprocess.Popen | None:
    """Sobe o inibidor. Devolve o ``Popen`` (guarde p/ ``parar``) ou ``None`` se
    ``systemd-inhibit`` não existe."""
    if shutil.which(_BIN) is None:
        _log.info("keep-awake: %s indisponível — a máquina pode suspender.", _BIN)
        return None
    try:
        proc = subprocess.Popen(  # noqa: S603
            comando(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        _log.info("keep-awake: suspensão inibida enquanto o Atlas roda (pid %s).", proc.pid)
        return proc
    except Exception as exc:  # noqa: BLE001 — best-effort
        _log.warning("keep-awake: não consegui inibir a suspensão: %s", exc)
        return None


def parar(proc: subprocess.Popen | None) -> None:
    """Libera o inibidor (encerra o subprocesso)."""
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:  # noqa: BLE001
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass
