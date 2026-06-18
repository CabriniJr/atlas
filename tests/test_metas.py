"""TDD — E3-04: Kind Goal — metas mensuráveis com checkup."""

from __future__ import annotations

from datetime import datetime

import pytest

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.db import Database
from atlas.handler import responder

_AGORA = datetime(2025, 6, 16, 10, 0)


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def store(tmp_path):
    return ResourceStore(str(tmp_path / "test.db"))


# ---------------------------------------------------------------------------
# /goal set — criar/atualizar meta
# ---------------------------------------------------------------------------


def test_goal_set_cria_resource(db, store):
    resp = responder("/goal set peso target=80 unit=kg tracker=peso", db, _AGORA, store=store)
    assert "✅" in resp or "goal" in resp.lower()
    r = store.get("Goal", "peso")
    assert r is not None
    assert r.spec.get("target") == "80"
    assert r.spec.get("unit") == "kg"


def test_goal_set_sem_nome_mostra_usage(db, store):
    resp = responder("/goal set", db, _AGORA, store=store)
    assert "usage" in resp.lower()


# ---------------------------------------------------------------------------
# /goal list / /goals
# ---------------------------------------------------------------------------


def test_goals_lista(db, store):
    store.apply(
        Resource(
            kind="Goal",
            name="peso",
            spec={"target": "80", "unit": "kg", "tracker": "peso"},
            status={"current": "85", "progress": "62%"},
        ),
        _AGORA,
    )
    resp = responder("/goals", db, _AGORA, store=store)
    assert "peso" in resp.lower()


def test_goal_list_vazio(db, store):
    resp = responder("/goals", db, _AGORA, store=store)
    assert "no goal" in resp.lower() or "nenhuma" in resp.lower()


# ---------------------------------------------------------------------------
# /goal status <name>
# ---------------------------------------------------------------------------


def test_goal_status_mostra_progresso(db, store):
    store.apply(
        Resource(
            kind="Goal",
            name="peso",
            spec={"target": "80", "unit": "kg", "tracker": "peso", "direction": "down"},
            status={"current": "85", "progress": "62%"},
        ),
        _AGORA,
    )
    resp = responder("/goal status peso", db, _AGORA, store=store)
    assert "peso" in resp.lower()
    assert "80" in resp or "85" in resp


def test_goal_status_nao_encontrado(db, store):
    resp = responder("/goal status inexistente", db, _AGORA, store=store)
    assert "not found" in resp.lower()


# ---------------------------------------------------------------------------
# /goal check <name> — calcula progresso atual via tracker
# ---------------------------------------------------------------------------


def test_goal_check_atualiza_status(db, store):
    # tracker com último valor
    db.insert(
        "activities",
        ts=_AGORA.isoformat(),
        dominio="fisico",
        rotina="tracking",
        texto_cru="peso: 83",
        dados_json={"tracker": "peso", "valor": 83, "unidade": "kg"},
    )
    store.apply(
        Resource(
            kind="Goal",
            name="peso",
            spec={
                "target": "80",
                "unit": "kg",
                "tracker": "peso",
                "start": "90",
                "direction": "down",
            },
        ),
        _AGORA,
    )
    resp = responder("/goal check peso", db, _AGORA, store=store)
    assert "83" in resp or "%" in resp
    r = store.get("Goal", "peso")
    assert r.status.get("current") is not None
