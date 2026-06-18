"""TDD — API HTTP do Atlas (E0-02 / ADR-0015)."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from http.client import HTTPConnection

import pytest

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore

_AGORA = datetime(2025, 6, 16, 10, 0)


@pytest.fixture
def store(tmp_path):
    s = ResourceStore(str(tmp_path / "test.db"))
    s.apply(
        Resource(
            kind="Tracker",
            name="peso",
            labels={"active": "true", "domain": "fisico"},
            spec={"unit": "kg"},
            status={"last_value": "82.3"},
        ),
        _AGORA,
    )
    s.apply(
        Resource(
            kind="Goal",
            name="emagrecimento",
            labels={"state": "active"},
            spec={"target": 80, "unit": "kg"},
            status={"current": "85", "progress": "25%"},
        ),
        _AGORA,
    )
    return s


@pytest.fixture
def api_server(store, free_tcp_port):
    """Sobe o servidor em porta aleatória para cada teste."""
    import atlas.api as api_mod

    api_mod._store = store
    api_mod._TOKEN = ""  # sem token → aceita qualquer origem nos testes
    from http.server import HTTPServer

    from atlas.api import _Handler

    server = HTTPServer(("127.0.0.1", free_tcp_port), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield free_tcp_port
    server.shutdown()


def _get(port, path):
    conn = HTTPConnection("127.0.0.1", port)
    conn.request("GET", path)
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp.status, json.loads(body)


def _delete(port, path):
    conn = HTTPConnection("127.0.0.1", port)
    conn.request("DELETE", path)
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp.status, json.loads(body)


def _put(port, path, body):
    data = json.dumps(body).encode()
    conn = HTTPConnection("127.0.0.1", port)
    conn.request(
        "PUT",
        path,
        body=data,
        headers={"Content-Type": "application/json", "Content-Length": str(len(data))},
    )
    resp = conn.getresponse()
    out = resp.read()
    conn.close()
    return resp.status, json.loads(out)


# ── GET /health ───────────────────────────────────────────────────────────────


def test_health(api_server):
    status, body = _get(api_server, "/health")
    assert status == 200
    assert body["status"] == "ok"


# ── GET /apis/atlas/v1/ ───────────────────────────────────────────────────────


def test_list_kinds(api_server):
    status, body = _get(api_server, "/apis/atlas/v1/")
    assert status == 200
    assert "Tracker" in body
    assert "Goal" in body
    assert body["Tracker"] >= 1


# ── GET /apis/atlas/v1/<kind> ─────────────────────────────────────────────────


def test_list_resources(api_server):
    status, body = _get(api_server, "/apis/atlas/v1/Tracker")
    assert status == 200
    assert isinstance(body, list)
    names = [r["name"] for r in body]
    assert "peso" in names


def test_list_kind_vazio(api_server):
    status, body = _get(api_server, "/apis/atlas/v1/KindInexistente")
    assert status == 200
    assert body == []


# ── GET /apis/atlas/v1/<kind>/<name> ─────────────────────────────────────────


def test_get_resource(api_server):
    status, body = _get(api_server, "/apis/atlas/v1/Tracker/peso")
    assert status == 200
    assert body["name"] == "peso"
    assert body["kind"] == "Tracker"
    assert body["labels"]["active"] == "true"
    assert body["spec"]["unit"] == "kg"
    assert body["status"]["last_value"] == "82.3"


def test_get_resource_nao_existe(api_server):
    status, body = _get(api_server, "/apis/atlas/v1/Tracker/inexistente")
    assert status == 404
    assert "not found" in body["error"]


# ── PUT /apis/atlas/v1/<kind>/<name> ─────────────────────────────────────────


def test_put_cria_recurso(api_server):
    status, body = _put(
        api_server,
        "/apis/atlas/v1/Tracker/novo",
        {"spec": {"unit": "cm"}, "labels": {"active": "true"}},
    )
    assert status == 200
    assert body["name"] == "novo"
    # verifica que ficou no store
    s2, b2 = _get(api_server, "/apis/atlas/v1/Tracker/novo")
    assert s2 == 200
    assert b2["spec"]["unit"] == "cm"


def test_put_atualiza_recurso(api_server):
    status, body = _put(api_server, "/apis/atlas/v1/Tracker/peso", {"spec": {"unit": "lbs"}})
    assert status == 200
    assert body["spec"]["unit"] == "lbs"


# ── DELETE /apis/atlas/v1/<kind>/<name> ──────────────────────────────────────


def test_delete_recurso(api_server):
    status, body = _delete(api_server, "/apis/atlas/v1/Tracker/peso")
    assert status == 200
    assert "deleted" in body
    # confirma que sumiu
    s2, _ = _get(api_server, "/apis/atlas/v1/Tracker/peso")
    assert s2 == 404


def test_delete_nao_existe(api_server):
    status, body = _delete(api_server, "/apis/atlas/v1/Tracker/fantasma")
    assert status == 404


def test_schema_endpoint(api_server):
    status, body = _get(api_server, "/apis/atlas/v1/_schema")
    assert status == 200
    assert "kinds" in body
    assert "Tracker" in body["kinds"]
    assert body["kinds"]["Timer"]["actions"]


# ── GET / (landing mínima) ───────────────────────────────────────────────────


def test_root_landing_minima(api_server):
    import http.client

    conn = http.client.HTTPConnection("127.0.0.1", api_server)
    conn.request("GET", "/")
    resp = conn.getresponse()
    body = resp.read().decode()
    conn.close()
    assert resp.status == 200
    # landing mínima, não o dashboard antigo
    assert "renderTree" not in body
    assert "_KIND_SCHEMA" not in body
    assert "Atlas API" in body
