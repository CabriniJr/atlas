"""Auth do servidor MCP (ADR-0053).

v1: **Bearer token** forte (segredo em ``secrets/mcp.env`` → env ``ATLAS_MCP_TOKEN``),
verificado em middleware ASGI. Isolado de propósito para o **OAuth 2.1** (F3) entrar
aqui sem mexer nas ferramentas nem no servidor. Comparação em tempo constante.
"""

from __future__ import annotations

import hmac
import os

from starlette.responses import JSONResponse

TOKEN_ENV = "ATLAS_MCP_TOKEN"
# Caminhos sem auth (metadados/health que o cliente lê antes de ter token).
ISENTOS = ("/health",)


def carregar_token() -> str:
    """Token esperado (env ``ATLAS_MCP_TOKEN``). Vazio ⇒ servidor nega tudo."""
    return os.environ.get(TOKEN_ENV, "")


def token_valido(apresentado: str, esperado: str) -> bool:
    """Compara em tempo constante. Falso se o esperado é vazio (fail-closed)."""
    if not esperado:
        return False
    return hmac.compare_digest(apresentado, esperado)


def _bearer(header_value: str) -> str:
    return header_value[7:] if header_value.lower().startswith("bearer ") else ""


class BearerMiddleware:
    """Middleware ASGI: exige ``Authorization: Bearer <token>`` (menos ``ISENTOS``)."""

    def __init__(self, app, token: str, *, isentos: tuple[str, ...] = ISENTOS) -> None:
        self.app = app
        self.token = token
        self.isentos = isentos

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http" or scope.get("path", "") in self.isentos:
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        apresentado = _bearer(headers.get(b"authorization", b"").decode())
        if not token_valido(apresentado, self.token):
            resp = JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await resp(scope, receive, send)
            return
        await self.app(scope, receive, send)
