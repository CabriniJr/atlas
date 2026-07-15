"""Camada de ferramentas do MCP (ADR-0053) — wrappers finos sobre o Atlas.

Funções **puras/injetáveis** (recebem store, cliente, runner) para serem testadas
sem HTTP nem o SDK MCP. O servidor (``server.py``) só as expõe como tools. Zero
lógica de negócio nova: cada uma reusa algo que já existe.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from typing import Any

from atlas.core.store import ResourceStore
from atlas.ownfoil import servico as ownfoil_servico

PUSH_SCRIPT_DEFAULT = os.path.expanduser("~/bin/onedrive-push.sh")


def status(
    store: ResourceStore,
    *,
    home: str | None = None,
    disk_usage: Callable[[str], Any] = shutil.disk_usage,
) -> dict[str, Any]:
    """Panorama do Atlas: jobs, torrents, loja Ownfoil e disco."""
    home = home or os.path.expanduser("~")
    du = disk_usage(home)
    torrents = [
        {"nome": t.spec.get("nome", t.name), "fase": t.status.get("fase")}
        for t in store.list("Torrent")
    ]
    return {
        "jobs": len(store.list("Job")),
        "torrents": torrents,
        "ownfoil": ownfoil_servico.status_atual(store),
        "disco_livre_gb": round(du.free / 1e9, 1),
        "disco_total_gb": round(du.total / 1e9, 1),
    }


def status_texto(store: ResourceStore, **kw: Any) -> str:
    """Versão humana do ``status`` (para caber numa resposta de chat)."""
    st = status(store, **kw)
    linhas = [
        "📊 Atlas",
        f"• Jobs/rotinas: {st['jobs']}",
        f"• Torrents: {len(st['torrents'])}"
        + (
            " — " + ", ".join(f"{t['nome']}({t['fase']})" for t in st["torrents"])
            if st["torrents"]
            else ""
        ),
        "• " + ownfoil_servico.resumo(store).splitlines()[0],
        f"• Disco: {st['disco_livre_gb']} GB livres de {st['disco_total_gb']} GB",
    ]
    return "\n".join(linhas)


def enfileirar_torrent(cliente: Any, link: str) -> dict[str, Any]:
    """Adiciona um magnet/URL de ``.torrent`` à fila do qBittorrent em container."""
    if cliente is None:
        return {"ok": False, "erro": "torrent indisponível (sem podman nesta máquina)"}
    link = (link or "").strip()
    if not (link.startswith("magnet:") or link.startswith("http")):
        return {"ok": False, "erro": "link inválido (use magnet: ou http(s) de um .torrent)"}
    if not cliente.garantir_no_ar():
        return {"ok": False, "erro": "container do torrent não subiu"}
    ok = cliente.adicionar_url(link)
    return {
        "ok": ok,
        "mensagem": "enfileirado na fila nativa do qBittorrent" if ok else "falha ao adicionar",
    }


def push_nuvem(
    *,
    script: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict[str, Any]:
    """Dispara o ``onedrive-push.sh`` (backup não-destrutivo pro OneDrive)."""
    script = script or PUSH_SCRIPT_DEFAULT
    if not os.path.exists(script):
        return {"ok": False, "erro": f"script não encontrado: {script}"}
    r = runner([script], capture_output=True, text=True)
    rc = getattr(r, "returncode", 1)
    saida = (getattr(r, "stdout", "") or "")[-1500:]
    erro = (getattr(r, "stderr", "") or "")[-500:]
    return {"ok": rc == 0, "saida": saida, "erro": None if rc == 0 else (erro or "falhou")}


def instalar_jogo(nome: str, destino: str = "local") -> dict[str, Any]:
    """STUB (frente D): a instalação Local/Nuvem depende da Inbox mágica, parada."""
    return {
        "ok": False,
        "pendente": "frente D",
        "mensagem": (
            f"instalar_jogo({nome!r}, {destino!r}) ainda não implementado — depende do "
            "roteador Local/Nuvem da Inbox mágica (frente D, fora de escopo por ora)."
        ),
    }
