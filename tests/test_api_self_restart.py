"""TDD — auto-reinício do processo local via API (ADR-0044)."""

from __future__ import annotations

import json
import threading
import time
from http.client import HTTPConnection
from http.server import HTTPServer

import pytest

from atlas.core.store import ResourceStore


@pytest.fixture
def store(tmp_path):
    return ResourceStore(str(tmp_path / "t.db"))


@pytest.fixture
def api_server(store, free_tcp_port, monkeypatch):
    import atlas.api as api_mod
    from atlas.api import _Handler

    api_mod._store = store
    api_mod._TOKEN = ""  # sem token → loopback vira admin
    monkeypatch.setattr(api_mod, "_SELF_RESTART_DELAY_S", 0.01)

    server = HTTPServer(("127.0.0.1", free_tcp_port), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield free_tcp_port
    server.shutdown()


def _post(port, path, body=None):
    conn = HTTPConnection("127.0.0.1", port)
    data = json.dumps(body or {}).encode()
    conn.request("POST", path, data, {"Content-Type": "application/json"})
    resp = conn.getresponse()
    out = resp.read()
    conn.close()
    return resp.status, (json.loads(out) if out else {})


def test_self_restart_admin_agenda_restart_e_devolve_202(api_server, monkeypatch):
    import atlas.api as api_mod

    chamadas = []
    monkeypatch.setattr(api_mod, "_agendar_self_restart", lambda servico: chamadas.append(servico))
    monkeypatch.setenv("ATLAS_SYSTEMD_SERVICE", "atlas.service")

    status, body = _post(api_server, "/apis/atlas/v1/_self_restart")

    assert status == 202
    assert body["ok"] is True
    assert body["servico"] == "atlas.service"
    time.sleep(0.05)
    assert chamadas == ["atlas.service"]


def test_self_restart_nao_admin_recusa(api_server, monkeypatch):
    import atlas.api as api_mod

    monkeypatch.setattr(api_mod._Handler, "_identity", lambda self: ("bob", "member"))
    status, body = _post(api_server, "/apis/atlas/v1/_self_restart")

    assert status == 403
    assert "admin" in body["error"]
