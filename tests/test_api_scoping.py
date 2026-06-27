"""TDD — isolamento por dono na API HTTP (ADR-0027, Fase 5).

Sobe o servidor com ``ATLAS_API_TOKEN`` setado (loopback ≠ admin) e exercita o
escopo: um member só vê/altera os seus recursos; o admin vê tudo.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from http.client import HTTPConnection
from http.server import HTTPServer

import pytest

import atlas.secrets_store as sec
from atlas import sessions, users
from atlas.core.resource import Resource
from atlas.core.store import ResourceStore

_AGORA = datetime(2026, 6, 26, 12, 0)


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
def server(tmp_path, free_tcp_port, monkeypatch):
    import atlas.api as api_mod
    from atlas.api import _Handler

    store = ResourceStore(str(tmp_path / "t.db"))
    # recursos de dois donos + um global
    store.apply(Resource(kind="Task", name="da-ana", labels={"owner": "ana"}, spec={}), _AGORA)
    store.apply(Resource(kind="Task", name="do-bob", labels={"owner": "bob"}, spec={}), _AGORA)
    store.apply(Resource(kind="Task", name="global", labels={"scope": "system"}, spec={}), _AGORA)
    users.create_user(store, "ana", role="member", password="x")

    api_mod._store = store
    monkeypatch.setattr(api_mod, "_TOKEN", "secret-token")
    srv = HTTPServer(("127.0.0.1", free_tcp_port), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield store, free_tcp_port
    srv.shutdown()


def _req(port, method, path, *, body=None, cookie=None, bearer=None):
    headers = {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
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
    sc = resp.getheader("Set-Cookie")
    conn.close()
    return resp.status, (json.loads(raw) if raw else {}), sc


def _login(port, user, password):
    _st, _out, sc = _req(
        port, "POST", "/apis/atlas/v1/_auth/login", body={"user": user, "password": password}
    )
    return sc.split(";")[0]


PREF = "/apis/atlas/v1"


def test_member_lista_so_os_seus_mais_system(server):
    _store, port = server
    cookie = _login(port, "ana", "x")
    st, lst, _ = _req(port, "GET", PREF + "/Task", cookie=cookie)
    assert st == 200
    nomes = {r["name"] for r in lst}
    assert nomes == {"da-ana", "global"}


def test_admin_lista_tudo(server):
    _store, port = server
    st, lst, _ = _req(port, "GET", PREF + "/Task", bearer="secret-token")
    nomes = {r["name"] for r in lst}
    assert nomes == {"da-ana", "do-bob", "global"}


def test_member_nao_ve_recurso_alheio(server):
    _store, port = server
    cookie = _login(port, "ana", "x")
    st, _, _ = _req(port, "GET", PREF + "/Task/do-bob", cookie=cookie)
    assert st == 404  # invisível ⇒ 404 (não revela existência)


def test_member_nao_apaga_alheio(server):
    store, port = server
    cookie = _login(port, "ana", "x")
    st, _, _ = _req(port, "DELETE", PREF + "/Task/do-bob", cookie=cookie)
    assert st in (403, 404)
    assert store.get("Task", "do-bob") is not None  # continua lá


def test_create_de_member_estampa_dono(server):
    store, port = server
    cookie = _login(port, "ana", "x")
    st, out, _ = _req(port, "PUT", PREF + "/Task/nova", body={"spec": {"x": 1}}, cookie=cookie)
    assert st == 200
    assert store.get("Task", "nova").labels["owner"] == "ana"


def test_member_nao_altera_system(server):
    store, port = server
    cookie = _login(port, "ana", "x")
    st, _, _ = _req(port, "PUT", PREF + "/Task/global", body={"spec": {"x": 9}}, cookie=cookie)
    assert st == 403
