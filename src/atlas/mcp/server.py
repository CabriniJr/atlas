"""Servidor MCP do Atlas (ADR-0053) — Streamable HTTP via FastMCP.

Expõe as ferramentas de ``tools.py`` como tools MCP. Roda como processo separado
(``python -m atlas.mcp``), abrindo o mesmo SQLite do Atlas (WAL permite concorrência
com o processo principal). Auth por Bearer (``auth.BearerMiddleware``) envolvendo o
app ASGI do FastMCP.
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from atlas.core.store import ResourceStore
from atlas.mcp import auth, tools
from atlas.torrent import container

_INSTRUCOES = (
    "Interface do Atlas (motor de rotinas pessoais). Use atlas_status para um "
    "panorama, enfileirar_torrent para baixar por magnet, push_nuvem para o backup "
    "no OneDrive. instalar_jogo ainda é stub (frente D)."
)


def _db_path() -> str:
    return os.environ.get(
        "ATLAS_DB_PATH", os.path.expanduser("~/atlas/data/atlas.sqlite")
    )


def _abrir_store() -> ResourceStore:
    return ResourceStore(_db_path())


def _cliente_torrent():
    """Reusa o client de torrent em container quando há podman (ADR-0051)."""
    if not container.disponivel():
        return None
    return container.ClienteContainer(
        dir_downloads=os.path.expanduser("~/Documents/torrent")
    )


def build_server(*, host: str = "127.0.0.1", port: int = 8787) -> FastMCP:
    """Monta o FastMCP com as 4 ferramentas ligadas ao store/torrent."""
    mcp = FastMCP(
        "Atlas",
        instructions=_INSTRUCOES,
        host=host,
        port=port,
        stateless_http=True,
    )
    store = _abrir_store()
    cliente = _cliente_torrent()

    @mcp.tool(description="Panorama do Atlas: jobs, torrents, loja Ownfoil e disco.")
    def atlas_status() -> dict:
        return tools.status(store)

    @mcp.tool(
        description="Enfileira um download por magnet ou URL de .torrent na fila do qBittorrent."
    )
    def enfileirar_torrent(link: str) -> dict:
        return tools.enfileirar_torrent(cliente, link)

    @mcp.tool(description="Dispara o backup (não-destrutivo) das pastas para o OneDrive.")
    def push_nuvem() -> dict:
        return tools.push_nuvem()

    @mcp.tool(
        description="(stub, frente D) Instala um jogo local ou na nuvem. Ainda não implementado."
    )
    def instalar_jogo(nome: str, destino: str = "local") -> dict:
        return tools.instalar_jogo(nome, destino)

    return mcp


def app(token: str | None = None):
    """App ASGI (Streamable HTTP) já envolvido pela auth Bearer."""
    token = token if token is not None else auth.carregar_token()
    asgi = build_server().streamable_http_app()
    return auth.BearerMiddleware(asgi, token)
