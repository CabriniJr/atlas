"""Client único de torrent num container Linux via **podman rootless** (ADR-0051).

Substitui o modelo de 1 ``qbittorrent-nox`` por download (ADR-0049): um **único**
container ``linuxserver/qbittorrent`` roda o client com a **fila nativa** do
qBittorrent. O Atlas fala com a WebUI (publicada só em ``127.0.0.1``) e um monitor
único (``torrent/monitor.py``) dirige progresso/conclusão de todos os recursos.

Testável: ``runner`` (subprocess) e os ``http_*`` são injetáveis; os construtores
``montar_conf``/``montar_run_args`` são **puros**. Assim o ciclo é exercitado sem
podman nem imagem.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from atlas.torrent.download import Progresso, _esta_completo, _velocidade_humana

_log = logging.getLogger("atlas.torrent")

_RUNTIME = "podman"
IMAGEM_DEFAULT = "docker.io/linuxserver/qbittorrent:latest"
NOME_CONTAINER = "atlas-qbt"
# Fora da faixa do fallback nox (``alocar_porta`` varre 8099..8118), p/ conviverem
# durante a transição: downloads antigos terminam no nox, novos vão pro container.
WEBUI_PORT = 8190
DESTINO_CONTAINER = "/downloads"
CONFIG_HOST_DEFAULT = os.path.expanduser("~/.local/share/atlas-torrent/cliente")
# A 1ª subida do linuxserver (init s6, permissões, config) pode passar de 40s.
_WEBUI_TIMEOUT_S = 75


def disponivel() -> bool:
    """``True`` se o runtime de container (podman) existe nesta máquina."""
    return shutil.which(_RUNTIME) is not None


def montar_conf(*, porta: int, max_ativos: int, semear: bool) -> str:
    """Config do qBittorrent (pura) — fila nativa + segurança + WebUI passwordless.

    A WebUI escuta em ``*`` DENTRO do container (o host publica só em
    ``127.0.0.1:<porta>``); o whitelist ``0.0.0.0/0`` dispensa senha porque o único
    caminho de rede é o bind local. Fila nativa: até ``max_ativos`` baixam juntos,
    o resto fica ``queuedDL`` (substitui o ``TorrentPool``). Sem semear por default.

    ``Session\\Encryption=0`` = **preferir** encriptação (não exigir): usa sempre que
    o peer suporta, mas não descarta os que não suportam. Era ``1`` (exigir), herdado
    do ``torrent-safe``, e isso cortava o pool de peers em torrents com pouco seed
    (decisão do PO, 2026-10-03).
    """
    if semear:
        seed_min, seed_en = -1, "false"
    else:
        seed_min, seed_en = 0, "true"
    return f"""[Application]
FileLogger\\Enabled=false

[BitTorrent]
Session\\DefaultSavePath={DESTINO_CONTAINER}
Session\\TempPath={DESTINO_CONTAINER}/.incompleto
Session\\TempPathEnabled=true
Session\\Encryption=0
Session\\AnonymousModeEnabled=true
Session\\QueueingSystemEnabled=true
Session\\MaxActiveDownloads={max_ativos}
Session\\MaxActiveUploads={max_ativos}
Session\\MaxActiveTorrents={max_ativos}
Session\\IgnoreSlowTorrentsForQueueing=true
Session\\GlobalMaxSeedingMinutes={seed_min}
Session\\GlobalMaxSeedingMinutesEnabled={seed_en}
Session\\MaxRatioAction=0
Session\\PortForwardingEnabled=false
Session\\UseRandomPort=true

[LegalNotice]
Accepted=true

[Preferences]
Connection\\UPnP=false
General\\ExitConfirm=false
WebUI\\Enabled=true
WebUI\\Address=*
WebUI\\Port={porta}
WebUI\\LocalHostAuth=false
WebUI\\AuthSubnetWhitelistEnabled=true
WebUI\\AuthSubnetWhitelist=0.0.0.0/0
WebUI\\CSRFProtection=false
WebUI\\HostHeaderValidation=false
"""


def montar_run_args(
    *,
    imagem: str,
    nome: str,
    porta: int,
    dir_downloads: str,
    dir_config: str,
) -> list[str]:
    """Argumentos do ``podman run`` (puro), afinados para **podman rootless** com
    **SELinux enforcing** (Fedora).

    Dois detalhes que, sem eles, dão ``Permission denied`` no ``/config`` (o
    container nem sobe):
    - **``:Z`` nos volumes** — relabela o SELinux; sem isso o enforcing nega TODO
      acesso do container ao diretório montado, independente de uid.
    - **``--userns=keep-id:uid=911,gid=911``** — o usuário ``abc`` (911) do
      linuxserver mapeia para o **uid do host**, então ele escreve no ``/config`` e
      os arquivos baixados saem com o **dono do host** (o Atlas lê p/ auto-enviar).
    Publica a WebUI só em ``127.0.0.1``. Volumes: config (sessão) e downloads (dados)."""
    return [
        _RUNTIME, "run", "-d", "--replace", "--name", nome,
        "--userns=keep-id:uid=911,gid=911",
        "-p", f"127.0.0.1:{porta}:{porta}",
        "-e", f"WEBUI_PORT={porta}",
        "-e", "TZ=Etc/UTC",
        "-v", f"{dir_config}:/config:Z",
        "-v", f"{dir_downloads}:{DESTINO_CONTAINER}:Z",
        imagem,
    ]


# -- HTTP mínimo (stdlib), injetável nos testes --------------------------------


def _http_get(url: str) -> str | None:
    try:
        with urllib.request.urlopen(url, timeout=5) as r:  # noqa: S310
            return r.read().decode("utf-8")
    except Exception:  # noqa: BLE001
        return None


def _http_post(url: str, corpo: bytes, headers: dict[str, str]) -> str | None:
    try:
        req = urllib.request.Request(url, data=corpo, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
            return r.read().decode("utf-8")
    except Exception:  # noqa: BLE001
        return None


def montar_multipart_add(
    torrent_bytes: bytes, nome: str, savepath: str, fronteira: str
) -> bytes:
    """Corpo multipart do ``/torrents/add`` (puro): o ``.torrent`` por bytes (sem
    mapear path pro container) + ``savepath`` e ``paused=false``."""
    b = fronteira.encode()
    partes: list[bytes] = []

    def campo(nome_campo: str, valor: str) -> None:
        partes.append(b"--" + b)
        partes.append(
            f'\r\nContent-Disposition: form-data; name="{nome_campo}"\r\n\r\n'.encode()
        )
        partes.append(valor.encode() + b"\r\n")

    partes.append(b"--" + b)
    partes.append(
        f'\r\nContent-Disposition: form-data; name="torrents"; '
        f'filename="{nome}"\r\n'.encode()
    )
    partes.append(b"Content-Type: application/x-bittorrent\r\n\r\n")
    partes.append(torrent_bytes + b"\r\n")
    campo("savepath", savepath)
    campo("paused", "false")
    partes.append(b"--" + b + b"--\r\n")
    return b"".join(partes)


@dataclass
class ClienteContainer:
    """Gerencia o container único e fala com a WebUI do qBittorrent (ADR-0051)."""

    porta: int = WEBUI_PORT
    dir_downloads: str = field(
        default_factory=lambda: os.path.expanduser("~/Documents/torrent")
    )
    dir_config: str = CONFIG_HOST_DEFAULT
    nome: str = NOME_CONTAINER
    imagem: str = IMAGEM_DEFAULT
    max_ativos: int = 3
    semear: bool = False
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run
    http_get: Callable[[str], str | None] = _http_get
    http_post: Callable[[str, bytes, dict[str, str]], str | None] = _http_post

    @property
    def _api(self) -> str:
        return f"http://127.0.0.1:{self.porta}/api/v2"

    def run_args(self) -> list[str]:
        return montar_run_args(
            imagem=self.imagem,
            nome=self.nome,
            porta=self.porta,
            dir_downloads=self.dir_downloads,
            dir_config=self.dir_config,
        )

    def esta_rodando(self) -> bool:
        r = self.runner(
            [_RUNTIME, "ps", "--filter", f"name=^{self.nome}$", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
        )
        return self.nome in (getattr(r, "stdout", "") or "")

    def _gravar_conf(self) -> None:
        cfg_dir = os.path.join(self.dir_config, "qBittorrent")
        os.makedirs(cfg_dir, exist_ok=True)
        os.makedirs(self.dir_downloads, exist_ok=True)
        with open(os.path.join(cfg_dir, "qBittorrent.conf"), "w") as f:
            f.write(
                montar_conf(
                    porta=self.porta, max_ativos=self.max_ativos, semear=self.semear
                )
            )

    def garantir_no_ar(self) -> bool:
        """Idempotente: se o container já roda, só espera a WebUI; senão grava a
        config e sobe o container. ``True`` quando a WebUI responde."""
        if self.esta_rodando():
            return self.esperar_webui(_WEBUI_TIMEOUT_S)
        self._gravar_conf()
        self.runner(self.run_args())
        return self.esperar_webui(_WEBUI_TIMEOUT_S)

    def esperar_webui(self, timeout_s: int) -> bool:
        for _ in range(timeout_s):
            if self.http_get(self._api + "/app/version") is not None:
                return True
            time.sleep(1)
        return False

    def adicionar(self, torrent_bytes: bytes, nome: str) -> bool:
        fronteira = f"----atlas{uuid.uuid4().hex}"
        corpo = montar_multipart_add(
            torrent_bytes, nome, DESTINO_CONTAINER, fronteira
        )
        headers = {"Content-Type": f"multipart/form-data; boundary={fronteira}"}
        resp = self.http_post(self._api + "/torrents/add", corpo, headers)
        return resp is not None

    def adicionar_url(self, url: str) -> bool:
        """Adiciona por **magnet** ou URL http(s) do ``.torrent`` (campo ``urls`` da
        WebUI). Usado pelo ``enfileirar_torrent`` do MCP (ADR-0053)."""
        import urllib.parse

        corpo = urllib.parse.urlencode({"urls": url, "savepath": DESTINO_CONTAINER}).encode()
        resp = self.http_post(
            self._api + "/torrents/add",
            corpo,
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
        return resp is not None

    def listar(self) -> list[dict]:
        raw = self.http_get(self._api + "/torrents/info")
        if raw is None:
            return []
        try:
            arr = json.loads(raw)
        except Exception:  # noqa: BLE001
            return []
        return arr if isinstance(arr, list) else []

    def progresso_de(self, infohash: str, arr: list[dict] | None = None) -> Progresso | None:
        """``Progresso`` do torrent (por infohash) a partir de uma listagem. ``None``
        se o cliente ainda não conhece o torrent. Reusa ``_esta_completo`` (espera
        sair de ``moving``/``checkingUP`` — fix do ADR-0049)."""
        arr = self.listar() if arr is None else arr
        want = infohash.lower()
        t = next((x for x in arr if str(x.get("hash", "")).lower() == want), None)
        if t is None:
            return None
        pct = float(t.get("progress", 0.0))
        estado = str(t.get("state", "?"))
        return Progresso(
            pct=pct * 100,
            estado=estado,
            velocidade=_velocidade_humana(float(t.get("dlspeed", 0.0))),
            seeds=int(t.get("num_seeds", 0)),
            concluido=_esta_completo(pct, estado),
        )

    def parar_p2p(self, infohash: str) -> None:
        self._post_form("/torrents/stop", {"hashes": infohash})
        self._post_form("/torrents/pause", {"hashes": infohash})  # nome antigo

    def remover(self, infohash: str, apagar_dados: bool = False) -> None:
        self._post_form(
            "/torrents/delete",
            {"hashes": infohash, "deleteFiles": "true" if apagar_dados else "false"},
        )

    def encerrar(self) -> None:
        try:
            self.runner([_RUNTIME, "stop", self.nome], capture_output=True, text=True)
        except Exception:  # noqa: BLE001
            pass

    def _post_form(self, rota: str, campos: dict[str, str]) -> None:
        corpo = "&".join(f"{k}={v}" for k, v in campos.items()).encode()
        self.http_post(
            self._api + rota,
            corpo,
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
