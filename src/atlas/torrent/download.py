"""Download headless de torrents via ``qbittorrent-nox`` (ADR-0049).

Porta a lógica do ``~/bin/torrent-safe`` do PO trocando ``flatpak run`` (que abre
a GUI) por ``qbittorrent-nox`` — **sem janela**. Preserva a config de segurança
(encriptação forçada, modo anônimo, sem port-forward, sem semear por default,
kill-switch de VPN quando uma iface é exigida) e o loop de progresso via WebUI
API, já usado pelo script.

O orquestrador ``baixar`` é **agnóstico ao cliente**: recebe um ``ClienteTorrent``
(protocolo). ``QBittorrentNox`` é a implementação real; nos testes injeta-se um
fake. Assim o loop de progresso/kill-switch/conclusão é testável sem o binário.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

_log = logging.getLogger("atlas.torrent")

WEBUI_PORT = 8099
_WEBUI_TIMEOUT_S = 30
_NOX_BIN = "qbittorrent-nox"


@dataclass
class Progresso:
    pct: float = 0.0  # 0..100
    estado: str = "iniciando"
    velocidade: str = "0.0 B/s"
    seeds: int = 0
    concluido: bool = False


@dataclass
class ConfigDownload:
    destino: str = "~/Documents/torrent"
    vpn: str = ""  # iface exigida; vazio = sem kill-switch
    permitir_sem_vpn: bool = True
    semear: bool = False
    porta_webui: int = WEBUI_PORT

    def destino_expandido(self) -> str:
        return os.path.expanduser(self.destino)


@dataclass
class ResultadoDownload:
    ok: bool
    concluido: bool = False
    destino: str = ""
    motivo: str = ""  # em caso de falha/aborto


class ClienteTorrent(Protocol):
    """Contrato mínimo que o loop ``baixar`` consome (permite fake nos testes)."""

    def iniciar(self, torrent_path: str, cfg: ConfigDownload, infohash: str) -> None: ...
    def esperar_webui(self, timeout_s: int) -> bool: ...
    def progresso(self, infohash: str) -> Progresso: ...
    def parar_p2p(self) -> None: ...
    def encerrar(self) -> None: ...


def iface_ativa(iface: str) -> bool:
    """``True`` se a interface de rede existe agora (kill-switch de VPN)."""
    if not iface:
        return False
    return subprocess.run(  # noqa: S603,S607
        ["ip", "link", "show", "dev", iface],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def motor_disponivel() -> bool:
    return shutil.which(_NOX_BIN) is not None


def baixar(
    torrent_path: str,
    infohash: str,
    cfg: ConfigDownload,
    cliente: ClienteTorrent,
    *,
    on_progress: Callable[[Progresso], None] | None = None,
    checar_cancel: Callable[[], bool] | None = None,
    iface_ativa_fn: Callable[[str], bool] = iface_ativa,
    intervalo_s: float = 2.0,
) -> ResultadoDownload:
    """Roda o download até 100%, cancelamento ou kill-switch.

    - ``on_progress`` é chamado a cada tick (persiste no ``status`` do recurso).
    - ``checar_cancel`` (opcional): se devolver ``True``, aborta e encerra o cliente.
    - kill-switch: se ``cfg.vpn`` está setado e a iface cair no meio, aborta.
    Ao concluir sem semear, para o P2P e encerra o cliente (nada em background).
    """
    destino = cfg.destino_expandido()
    Path(destino).mkdir(parents=True, exist_ok=True)

    # Gate de VPN antes de iniciar (espelha o torrent-safe).
    if cfg.vpn:
        if not iface_ativa_fn(cfg.vpn):
            return ResultadoDownload(False, motivo=f"VPN '{cfg.vpn}' não está ativa")
    elif not cfg.permitir_sem_vpn:
        return ResultadoDownload(False, motivo="sem VPN e permitir_sem_vpn=false")

    cliente.iniciar(torrent_path, cfg, infohash)
    try:
        if not cliente.esperar_webui(_WEBUI_TIMEOUT_S):
            cliente.encerrar()
            return ResultadoDownload(False, motivo="WebUI do motor não respondeu")

        while True:
            if checar_cancel is not None and checar_cancel():
                cliente.encerrar()
                return ResultadoDownload(False, motivo="cancelado")
            if cfg.vpn and not iface_ativa_fn(cfg.vpn):
                cliente.encerrar()
                return ResultadoDownload(False, motivo=f"kill-switch: VPN '{cfg.vpn}' caiu")

            p = cliente.progresso(infohash)
            if on_progress is not None:
                on_progress(p)
            if p.concluido:
                break
            time.sleep(intervalo_s)
    except Exception as exc:  # noqa: BLE001
        _log.exception("download %s falhou", infohash)
        cliente.encerrar()
        return ResultadoDownload(False, motivo=str(exc))

    if not cfg.semear:
        cliente.parar_p2p()
        cliente.encerrar()
    return ResultadoDownload(True, concluido=True, destino=destino)


# ---------------------------------------------------------------------------
# Implementação real: qbittorrent-nox + WebUI API.
# ---------------------------------------------------------------------------


def _config_conf(cfg: ConfigDownload) -> str:
    destino = cfg.destino_expandido()
    if cfg.semear:
        seed_min, seed_en = -1, "false"
    else:
        seed_min, seed_en = 0, "true"
    iface_lines = ""
    if cfg.vpn:
        iface_lines = f"Session\\Interface={cfg.vpn}\nSession\\InterfaceName={cfg.vpn}\n"
    return f"""[Application]
FileLogger\\Enabled=false

[BitTorrent]
Session\\DefaultSavePath={destino}
Session\\TempPath={destino}/.incompleto
Session\\TempPathEnabled=true
Session\\Encryption=1
Session\\AnonymousModeEnabled=true
Session\\QueueingSystemEnabled=false
Session\\GlobalMaxSeedingMinutes={seed_min}
Session\\GlobalMaxSeedingMinutesEnabled={seed_en}
Session\\MaxRatioAction=0
Session\\PortForwardingEnabled=false
Session\\UseRandomPort=true
{iface_lines}
[LegalNotice]
Accepted=true

[Preferences]
Connection\\UPnP=false
General\\ExitConfirm=false
WebUI\\Enabled=true
WebUI\\Address=127.0.0.1
WebUI\\Port={cfg.porta_webui}
WebUI\\LocalHostAuth=false
WebUI\\CSRFProtection=false
WebUI\\HostHeaderValidation=false
"""


@dataclass
class QBittorrentNox:
    """Cliente real: escreve a config, lança o daemon headless e fala com a WebUI.

    ``profile`` isola o perfil (config/dados) para não pisar num qBittorrent do
    usuário. Default: perfil dedicado do Atlas.
    """

    profile: str = field(default_factory=lambda: os.path.expanduser("~/.local/share/atlas-torrent"))
    _proc: subprocess.Popen | None = None

    @property
    def _api(self) -> str:
        return f"http://127.0.0.1:{WEBUI_PORT}/api/v2"

    def _config_dir(self) -> str:
        return os.path.join(self.profile, "config", "qBittorrent")

    def iniciar(self, torrent_path: str, cfg: ConfigDownload, infohash: str) -> None:
        cfg_dir = self._config_dir()
        os.makedirs(cfg_dir, exist_ok=True)
        with open(os.path.join(cfg_dir, "qBittorrent.conf"), "w") as f:
            f.write(_config_conf(cfg))
        # --profile isola tudo; passamos o .torrent como argumento posicional.
        self._proc = subprocess.Popen(  # noqa: S603
            [_NOX_BIN, f"--profile={self.profile}", torrent_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def esperar_webui(self, timeout_s: int) -> bool:
        for _ in range(timeout_s):
            if self._get("/app/version") is not None:
                return True
            time.sleep(1)
        return False

    def progresso(self, infohash: str) -> Progresso:
        import json

        raw = self._get("/torrents/info")
        if raw is None:
            return Progresso()
        try:
            arr = json.loads(raw)
        except Exception:  # noqa: BLE001
            return Progresso()
        want = infohash.lower()
        t = next((x for x in arr if x.get("hash", "").lower() == want), None)
        if t is None and arr:
            t = arr[0]
        if not t:
            return Progresso()
        pct = float(t.get("progress", 0.0))
        d = float(t.get("dlspeed", 0.0))
        spd = _velocidade_humana(d)
        return Progresso(
            pct=pct * 100,
            estado=str(t.get("state", "?")),
            velocidade=spd,
            seeds=int(t.get("num_seeds", 0)),
            concluido=pct >= 0.999,
        )

    def parar_p2p(self) -> None:
        self._post("/torrents/stop", b"hashes=all")
        self._post("/torrents/pause", b"hashes=all")  # nome antigo da API

    def encerrar(self) -> None:
        self._get("/app/shutdown")
        time.sleep(1)
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                self._proc.kill()
            self._proc = None

    # -- HTTP mínimo (stdlib) --
    def _get(self, rota: str) -> str | None:
        try:
            with urllib.request.urlopen(self._api + rota, timeout=5) as r:  # noqa: S310
                return r.read().decode("utf-8")
        except Exception:  # noqa: BLE001
            return None

    def _post(self, rota: str, dados: bytes) -> None:
        try:
            urllib.request.urlopen(  # noqa: S310
                urllib.request.Request(self._api + rota, data=dados), timeout=5
            ).read()
        except Exception:  # noqa: BLE001
            pass


def _velocidade_humana(d: float) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if d < 1024 or u == "GB":
            return f"{d:.1f} {u}/s"
        d /= 1024
    return f"{d:.1f} GB/s"
