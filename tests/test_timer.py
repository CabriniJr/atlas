"""TDD — kind Timer: /timer start <name> / /timer finish <name>."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from atlas.core.store import ResourceStore
from atlas.db import Database
from atlas.handler import responder

_AGORA = datetime(2025, 6, 16, 10, 0, 0)


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def store(tmp_path):
    return ResourceStore(str(tmp_path / "test.db"))


# ---------------------------------------------------------------------------
# /timer start
# ---------------------------------------------------------------------------


def test_timer_start_cria_resource(db, store):
    resp = responder("/timer start estudo", db, _AGORA, store=store)
    assert "⏱" in resp or "started" in resp.lower()
    r = store.get("Timer", "estudo")
    assert r is not None
    assert r.status.get("state") == "running"
    assert r.status.get("started_at") == _AGORA.isoformat()


def test_timer_start_duplicado_rejeita(db, store):
    responder("/timer start estudo", db, _AGORA, store=store)
    resp = responder("/timer start estudo", db, _AGORA + timedelta(minutes=5), store=store)
    assert "já em andamento" in resp.lower() or "already" in resp.lower()


def test_timer_start_sem_nome_mostra_usage(db, store):
    resp = responder("/timer start", db, _AGORA, store=store)
    assert "usage" in resp.lower()


# ---------------------------------------------------------------------------
# /timer finish
# ---------------------------------------------------------------------------


def test_timer_finish_registra_duracao(db, store):
    responder("/timer start estudo", db, _AGORA, store=store)
    fim = _AGORA + timedelta(minutes=47)
    resp = responder("/timer finish estudo", db, fim, store=store)
    assert "47" in resp
    assert "estudo" in resp.lower()


def test_timer_finish_grava_activity(db, store):
    responder("/timer start estudo", db, _AGORA, store=store)
    fim = _AGORA + timedelta(minutes=30)
    responder("/timer finish estudo", db, fim, store=store)
    row = db.connection.execute(
        "SELECT * FROM activities WHERE rotina='timer' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    assert "estudo" in row["texto_cru"]


def test_timer_finish_muda_estado_para_done(db, store):
    responder("/timer start estudo", db, _AGORA, store=store)
    fim = _AGORA + timedelta(hours=1)
    responder("/timer finish estudo", db, fim, store=store)
    r = store.get("Timer", "estudo")
    assert r.status.get("state") == "done"


def test_timer_finish_sem_timer_ativo_retorna_erro(db, store):
    resp = responder("/timer finish estudo", db, _AGORA, store=store)
    assert "not found" in resp.lower() or "não encontrado" in resp.lower()


# ---------------------------------------------------------------------------
# /timer status / /timers
# ---------------------------------------------------------------------------


def test_timer_status_mostra_em_andamento(db, store):
    responder("/timer start foco", db, _AGORA, store=store)
    resp = responder("/timer status foco", db, _AGORA + timedelta(minutes=10), store=store)
    assert "foco" in resp.lower()
    assert "10" in resp or "running" in resp.lower()


def test_timers_lista_ativos(db, store):
    responder("/timer start estudo", db, _AGORA, store=store)
    responder("/timer start leitura", db, _AGORA, store=store)
    resp = responder("/timers", db, _AGORA + timedelta(minutes=5), store=store)
    assert "estudo" in resp.lower()
    assert "leitura" in resp.lower()
