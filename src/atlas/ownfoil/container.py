"""Container único da loja **Ownfoil** via podman rootless (ADR-0052).

Espelha o client de torrent em container (ADR-0051): um **único** container
``a1ex4/ownfoil`` serve o acervo de ``~/Games/Switch`` como loja Tinfoil. A WebUI é
publicada só em ``127.0.0.1:<porta>``; a exposição pública é feita pelo **Tailscale
Funnel** (não pelo container). Auth forte: o admin inicial vem de um **env-file**
(``secrets/ownfoil.env``), nunca inline no ``argv`` (não vaza no ``podman inspect``/
``ps``).

Testável: ``runner`` (subprocess) e ``http_get`` são injetáveis; ``montar_run_args``
e ``contar_jogos`` são **puros**. O ciclo é exercitado sem podman nem imagem.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field

_log = logging.getLogger("atlas.ownfoil")

_RUNTIME = "podman"
IMAGEM_DEFAULT = "docker.io/a1ex4/ownfoil:latest"
NOME_CONTAINER = "atlas-ownfoil"
PORT = 8465
GAMES_CONTAINER = "/games"
CONFIG_HOST_DEFAULT = os.path.expanduser("~/.local/share/atlas-ownfoil/config")
DATA_HOST_DEFAULT = os.path.expanduser("~/.local/share/atlas-ownfoil/data")
ENV_FILE_DEFAULT = os.path.expanduser("~/atlas/secrets/ownfoil.env")
GAMES_HOST_DEFAULT = os.path.expanduser("~/Games/Switch")
# Extensões de jogo do Switch (NSP/NSZ/XCI/XCZ). Usadas só para contar o acervo.
_EXT_JOGO = (".nsp", ".nsz", ".xci", ".xcz")
# A 1ª subida do Ownfoil (init + varredura do acervo) pode levar alguns segundos.
_HTTP_TIMEOUT_S = 60


def disponivel() -> bool:
    """``True`` se o runtime de container (podman) existe nesta máquina."""
    return shutil.which(_RUNTIME) is not None


def contar_jogos(dir_games: str) -> int:
    """Número de arquivos de jogo (extensões do Switch) no acervo, recursivo.

    Puro (só toca o filesystem passado). Diretório ausente → 0.
    """
    total = 0
    for _raiz, _dirs, arquivos in os.walk(dir_games):
        for nome in arquivos:
            if nome.lower().endswith(_EXT_JOGO):
                total += 1
    return total


def montar_run_args(
    *,
    imagem: str,
    nome: str,
    porta: int,
    dir_games: str,
    dir_config: str,
    dir_data: str,
    env_file: str | None,
) -> list[str]:
    """Argumentos do ``podman run`` (puro), afinados para **podman rootless** com
    **SELinux enforcing** (Fedora), como no ADR-0051.

    - **``:Z`` nos volumes** — relabela o SELinux; sem isso o enforcing nega acesso.
    - Acervo montado **``ro``** (a loja só serve, nunca escreve nos jogos).
    - **SEM ``--userns=keep-id``** (ao contrário do torrent/ADR-0051): o entrypoint do
      Ownfoil roda **como root** dentro do container e faz ``chown /app``; com
      ``keep-id`` o processo vira o usuário do host (não-root) e o ``chown`` falha
      (``Operation not permitted`` → cai pra ``sudo`` → sai com erro). No podman
      rootless, o root do container já mapeia para o **usuário do host**, então lê o
      acervo e escreve config/data com o dono certo.
    - **``--env-file``** — admin (``USER_ADMIN_NAME``/``USER_ADMIN_PASSWORD``) fora
      do ``argv``, para não vazar no ``ps``/``inspect``.
    - Publica a WebUI só em ``127.0.0.1`` (o Funnel expõe publicamente).
    """
    args = [
        _RUNTIME, "run", "-d", "--replace", "--name", nome,
        "-p", f"127.0.0.1:{porta}:{porta}",
        "-e", "TZ=Etc/UTC",
    ]
    if env_file:
        args += ["--env-file", env_file]
    args += [
        "-v", f"{dir_games}:{GAMES_CONTAINER}:ro,Z",
        "-v", f"{dir_config}:/app/config:Z",
        "-v", f"{dir_data}:/app/data:Z",
        imagem,
    ]
    return args


def _http_get(url: str) -> str | None:
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=5) as r:  # noqa: S310
            return r.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return None


@dataclass
class ClienteOwnfoil:
    """Gerencia o container único da loja Ownfoil (ADR-0052)."""

    porta: int = PORT
    dir_games: str = field(default_factory=lambda: GAMES_HOST_DEFAULT)
    dir_config: str = CONFIG_HOST_DEFAULT
    dir_data: str = DATA_HOST_DEFAULT
    env_file: str | None = ENV_FILE_DEFAULT
    nome: str = NOME_CONTAINER
    imagem: str = IMAGEM_DEFAULT
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run
    http_get: Callable[[str], str | None] = _http_get

    def run_args(self) -> list[str]:
        # Só passa o env-file se ele existir de fato (evita erro do podman).
        env = self.env_file if (self.env_file and os.path.exists(self.env_file)) else None
        return montar_run_args(
            imagem=self.imagem,
            nome=self.nome,
            porta=self.porta,
            dir_games=self.dir_games,
            dir_config=self.dir_config,
            dir_data=self.dir_data,
            env_file=env,
        )

    def esta_rodando(self) -> bool:
        r = self.runner(
            [_RUNTIME, "ps", "--filter", f"name=^{self.nome}$", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
        )
        return self.nome in (getattr(r, "stdout", "") or "")

    def garantir_no_ar(self) -> bool:
        """Idempotente: se já roda, só espera a WebUI; senão cria os diretórios de
        estado e sobe o container. ``True`` quando a WebUI responde."""
        if self.esta_rodando():
            return self.esperar_http(_HTTP_TIMEOUT_S)
        os.makedirs(self.dir_config, exist_ok=True)
        os.makedirs(self.dir_data, exist_ok=True)
        self.runner(self.run_args())
        return self.esperar_http(_HTTP_TIMEOUT_S)

    def esperar_http(self, timeout_s: int) -> bool:
        alvo = f"http://127.0.0.1:{self.porta}/"
        for _ in range(timeout_s):
            if self.http_get(alvo) is not None:
                return True
            time.sleep(1)
        return False

    def status(self) -> dict:
        """Estado observável da loja (para ``atlas_status`` e Telegram)."""
        return {
            "rodando": self.esta_rodando(),
            "porta": self.porta,
            "jogos": contar_jogos(self.dir_games),
            "acervo": self.dir_games,
            "imagem": self.imagem,
        }

    def encerrar(self) -> None:
        try:
            self.runner([_RUNTIME, "stop", self.nome], capture_output=True, text=True)
        except Exception:  # noqa: BLE001
            pass
