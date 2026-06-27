"""TDD — login/sessão na API (ADR-0027, Fase 4).

Testa as funções de handler module-level (sem subir o servidor). Senha local e
login via GitHub (device flow), ambos criando sessão.
"""

from __future__ import annotations

import pytest

import atlas.secrets_store as sec
from atlas import api, sessions, users
from atlas import credentials as cred
from atlas import github_auth as gh
from atlas.core.store import ResourceStore


@pytest.fixture(autouse=True)
def _vault(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_SECRETS_DIR", str(tmp_path / "secrets"))
    monkeypatch.setenv("ATLAS_SESSIONS_PATH", str(tmp_path / "sessions.json"))
    monkeypatch.delenv("ATLAS_SECRET_KEY", raising=False)
    sec.reset_cache()
    sessions.reset()
    yield
    sec.reset_cache()
    sessions.reset()


@pytest.fixture
def store(tmp_path):
    return ResourceStore(str(tmp_path / "t.db"))


# ── login por senha ──────────────────────────────────────────────────────────


def test_login_senha_correta_cria_sessao(store):
    users.create_user(store, "luigi", role="admin", password="boa-senha")
    body, token = api._auth_login(store, "luigi", "boa-senha")
    assert body["ok"] is True
    assert body["role"] == "admin"
    assert token and sessions.resolve_session(token)["user"] == "luigi"


def test_login_senha_errada_falha_sem_sessao(store):
    users.create_user(store, "luigi", password="boa-senha")
    body, token = api._auth_login(store, "luigi", "errada")
    assert body["ok"] is False
    assert token is None


def test_login_usuario_inexistente_falha(store):
    body, token = api._auth_login(store, "ninguem", "x")
    assert body["ok"] is False
    assert token is None


# ── login via GitHub (device flow) ───────────────────────────────────────────


def test_github_login_conecta_cria_user_credencial_e_sessao(store, monkeypatch):
    monkeypatch.setattr(
        gh,
        "poll_access_token",
        lambda dc, **kw: {"status": "connected", "access_token": "gho_X", "scope": "repo"},
    )
    monkeypatch.setattr(gh, "fetch_github_login", lambda tok, **kw: "CabriniJr")

    body, token = api._github_login_poll(store, device_code="DEV")
    assert body["status"] == "connected"
    assert body["user"] == "cabrinijr"
    # User criado, credencial salva (repo-sync passa a funcionar), sessão ativa
    assert store.get("User", "cabrinijr") is not None
    assert cred.get_secret(cred.credential_id("github", "cabrinijr")) == "gho_X"
    assert sessions.resolve_session(token)["user"] == "cabrinijr"


def test_github_login_pendente_nao_cria_sessao(store, monkeypatch):
    monkeypatch.setattr(
        gh,
        "poll_access_token",
        lambda dc, **kw: {"status": "pending", "error": "authorization_pending"},
    )
    body, token = api._github_login_poll(store, device_code="DEV")
    assert body["status"] == "pending"
    assert token is None


# ── integração HTTP: cookie de sessão de ponta a ponta ───────────────────────


@pytest.fixture
def server_token(store, free_tcp_port, monkeypatch):
    """Servidor com ATLAS_API_TOKEN setado: loopback NÃO é admin → testa sessão."""
    import threading
    from http.server import HTTPServer

    import atlas.api as api_mod
    from atlas.api import _Handler

    api_mod._store = store
    monkeypatch.setattr(api_mod, "_TOKEN", "secret-token")
    srv = HTTPServer(("127.0.0.1", free_tcp_port), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield store, free_tcp_port
    srv.shutdown()


def _req(port, method, path, *, body=None, cookie=None, bearer=None):
    from http.client import HTTPConnection

    headers = {}
    data = None
    if body is not None:
        import json as _j

        data = _j.dumps(body).encode()
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = str(len(data))
    if cookie:
        headers["Cookie"] = cookie
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    conn = HTTPConnection("127.0.0.1", port)
    conn.request(method, path, body=data, headers=headers)
    resp = conn.getresponse()
    raw = resp.read()
    set_cookie = resp.getheader("Set-Cookie")
    conn.close()
    import json as _j

    return resp.status, (_j.loads(raw) if raw else {}), set_cookie


def test_fluxo_http_login_cookie_me_logout(server_token):
    store, port = server_token
    users.create_user(store, "luigi", role="admin", password="boa-senha")
    pref = "/apis/atlas/v1"

    # sem credencial → protegido dá 401
    st, _, _ = _req(port, "GET", pref)
    assert st == 401

    # login errado → 401, sem cookie
    st, _, sc = _req(port, "POST", pref + "/_auth/login", body={"user": "luigi", "password": "x"})
    assert st == 401 and sc is None

    # login certo → 200 + Set-Cookie httpOnly
    st, out, sc = _req(
        port, "POST", pref + "/_auth/login", body={"user": "luigi", "password": "boa-senha"}
    )
    assert st == 200 and out["ok"] is True
    assert sc and "atlas_session=" in sc and "HttpOnly" in sc
    cookie = sc.split(";")[0]

    # /_auth/me reflete a identidade
    st, me, _ = _req(port, "GET", pref + "/_auth/me", cookie=cookie)
    assert me == {"authenticated": True, "user": "luigi", "role": "admin"}

    # protegido agora acessível com a sessão
    st, _, _ = _req(port, "GET", pref, cookie=cookie)
    assert st == 200

    # logout → sessão morre
    st, _, _ = _req(port, "POST", pref + "/_auth/logout", cookie=cookie)
    assert st == 200
    st, me, _ = _req(port, "GET", pref + "/_auth/me", cookie=cookie)
    assert me["authenticated"] is False


def test_admin_cria_usuario_e_member_nao(server_token):
    store, port = server_token
    # admin (Bearer token) cria um usuário com senha
    st, out, _ = _req(
        port,
        "POST",
        "/apis/atlas/v1/_auth/users",
        body={"user": "novo", "password": "p", "role": "member"},
        bearer="secret-token",
    )
    assert st == 200 and out["ok"] is True
    assert store.get("User", "novo") is not None
    assert users.verify_password("novo", "p") is True

    # sem admin → 403
    st, _, _ = _req(port, "POST", "/apis/atlas/v1/_auth/users", body={"user": "x", "password": "p"})
    assert st == 403
