"""E0-04 — Tracker + Alarm kinds no ResourceStore (TDD)."""

from __future__ import annotations

from datetime import datetime

from atlas.core.store import ResourceStore
from atlas.db import Database
from atlas.handler import responder

T0 = datetime(2026, 6, 16, 10, 0)


def _env() -> tuple[Database, ResourceStore]:
    return Database(":memory:"), ResourceStore(":memory:")


# --- Tracker -----------------------------------------------------------------


def test_track_new_vai_pro_store():
    db, store = _env()
    responder("/track new weight kg", db, T0, store=store)
    recursos = store.list("Tracker")
    assert len(recursos) == 1
    r = recursos[0]
    assert r.name == "weight"
    assert r.spec.get("unit") == "kg"
    assert r.spec.get("syntax") == "weight:"


def test_track_new_sem_unit_vai_pro_store():
    db, store = _env()
    responder("/track new steps", db, T0, store=store)
    r = store.get("Tracker", "steps")
    assert r is not None
    assert r.spec.get("unit") == ""


def test_list_tracker_via_verbo():
    db, store = _env()
    responder("/track new weight kg", db, T0, store=store)
    responder("/track new sleep h", db, T0, store=store)
    resposta = responder("/list Tracker", db, T0, store=store)
    assert "weight" in resposta
    assert "sleep" in resposta


def test_describe_tracker_via_verbo():
    db, store = _env()
    responder("/track new weight kg", db, T0, store=store)
    resposta = responder("/describe Tracker weight", db, T0, store=store)
    assert "weight" in resposta
    assert "kg" in resposta


# --- Alarm -------------------------------------------------------------------


def test_alarm_vai_pro_store():
    db, store = _env()
    responder("/alarm 08:00 acordar", db, T0, store=store)
    recursos = store.list("Alarm")
    assert len(recursos) == 1
    r = recursos[0]
    assert r.spec.get("time") == "08:00"
    assert r.spec.get("message") == "acordar"
    assert r.spec.get("mode") == "daily"


def test_alarm_once_vai_pro_store():
    db, store = _env()
    responder("/alarm 15:30 reuniao @once", db, T0, store=store)
    recursos = store.list("Alarm")
    assert len(recursos) == 1
    assert recursos[0].spec.get("mode") == "once"


def test_list_alarm_via_verbo():
    db, store = _env()
    responder("/alarm 07:00 gym", db, T0, store=store)
    resposta = responder("/list Alarm", db, T0, store=store)
    assert "alarm-" in resposta or "gym" in resposta or "07:00" in resposta


def test_resources_mostra_tracker_e_alarm():
    db, store = _env()
    responder("/track new weight kg", db, T0, store=store)
    responder("/alarm 08:00 wake up", db, T0, store=store)
    resposta = responder("/resources", db, T0, store=store)
    assert "Tracker" in resposta
    assert "Alarm" in resposta
