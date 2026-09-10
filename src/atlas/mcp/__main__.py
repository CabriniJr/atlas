"""Entrypoint do servidor MCP: ``python -m atlas.mcp`` (ADR-0053).

Sobe o Streamable HTTP (uvicorn) em 127.0.0.1:<porta>; o Tailscale Funnel publica
em :8443. Lê o token de ``ATLAS_MCP_TOKEN`` (secrets/mcp.env).
"""

from __future__ import annotations

import logging
import os

import uvicorn

from atlas.mcp import auth
from atlas.mcp.server import app

_log = logging.getLogger("atlas.mcp")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    token = auth.carregar_token()
    if not token:
        _log.warning(
            "ATLAS_MCP_TOKEN vazio — o servidor vai NEGAR tudo (fail-closed). "
            "Defina o token em secrets/mcp.env."
        )
    host = os.environ.get("ATLAS_MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("ATLAS_MCP_PORT", "8787"))
    _log.info("MCP do Atlas em http://%s:%d/mcp", host, port)
    uvicorn.run(app(token), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
