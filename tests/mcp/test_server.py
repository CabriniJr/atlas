"""TDD — auth Bearer e montagem do servidor MCP (ADR-0053)."""

from __future__ import annotations

import asyncio

from atlas.mcp import auth, server


# ── token ────────────────────────────────────────────────────────────────────


def test_token_valido_compara_e_fail_closed():
    assert auth.token_valido("abc", "abc") is True
    assert auth.token_valido("abc", "xyz") is False
    assert auth.token_valido("abc", "") is False  # esperado vazio ⇒ nega
    assert auth.token_valido("", "") is False


# ── middleware ASGI ──────────────────────────────────────────────────────────


def _rodar_middleware(mw, path="/mcp", authorization=None):
    headers = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode()))
    scope = {"type": "http", "path": path, "headers": headers}
    enviados: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        enviados.append(msg)

    async def app_interna(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mw_inst = auth.BearerMiddleware(app_interna, token="segredo")
    # substitui o app interno para o teste isolar a decisão do middleware
    mw_inst.app = app_interna
    asyncio.run(mw_inst(scope, receive, send))
    return enviados


def test_middleware_nega_sem_token():
    enviados = _rodar_middleware(None)
    assert enviados[0]["status"] == 401


def test_middleware_nega_token_errado():
    enviados = _rodar_middleware(None, authorization="Bearer errado")
    assert enviados[0]["status"] == 401


def test_middleware_aceita_token_certo():
    enviados = _rodar_middleware(None, authorization="Bearer segredo")
    assert enviados[0]["status"] == 200


def test_middleware_isenta_health():
    enviados = _rodar_middleware(None, path="/health")  # sem token
    assert enviados[0]["status"] == 200


# ── montagem do servidor ─────────────────────────────────────────────────────


def test_build_server_registra_as_quatro_ferramentas(monkeypatch, tmp_path):
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "t.db"))
    mcp = server.build_server()
    ferramentas = {t.name for t in asyncio.run(mcp.list_tools())}
    assert ferramentas == {"atlas_status", "enfileirar_torrent", "push_nuvem", "instalar_jogo"}


def test_app_asgi_monta_com_auth(monkeypatch, tmp_path):
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "t.db"))
    a = server.app(token="segredo")
    assert isinstance(a, auth.BearerMiddleware)
    assert a.token == "segredo"
