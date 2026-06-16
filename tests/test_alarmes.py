"""Testes de alarmes (E5-07, batch): criar, listar, remover, disparar."""

from __future__ import annotations

from datetime import datetime, timedelta

from atlas.alarmes import tick_alarmes
from atlas.db import Database
from atlas.handler import responder

_AGORA = datetime(2026, 6, 16, 20, 0, 0)


def _db() -> Database:
    return Database(":memory:")


def test_criar_e_listar():
    db = _db()
    resp = responder("/alarm 23:00 go to sleep", db, _AGORA)
    assert "#" in resp and "23:00" in resp
    assert "go to sleep" in responder("/alarms", db, _AGORA)


def test_horario_invalido_nao_cria():
    db = _db()
    responder("/alarm 99:99 nope", db, _AGORA)
    assert db.connection.execute("SELECT COUNT(*) FROM alarms").fetchone()[0] == 0


def test_remover():
    db = _db()
    responder("/alarm 07:00 wake up", db, _AGORA)
    i = db.connection.execute("SELECT id FROM alarms").fetchone()[0]
    responder(f"/alarm {i} remove", db, _AGORA)
    assert db.connection.execute("SELECT ativo FROM alarms WHERE id=?", (i,)).fetchone()[0] == 0


def test_tick_diario_dispara_e_reagenda():
    db = _db()
    responder("/alarm 21:00 sleep", db, _AGORA)  # próximo: hoje 21:00
    enviados: list[str] = []
    # ainda não venceu às 20:00
    assert tick_alarmes(_AGORA, db, enviados.append) == 0
    # às 21:00 dispara
    disparo = _AGORA.replace(hour=21, minute=0)
    assert tick_alarmes(disparo, db, enviados.append) == 1
    assert enviados and "sleep" in enviados[0]
    # reagenda p/ amanhã (continua ativo, não redispara no mesmo tick)
    assert tick_alarmes(disparo, db, enviados.append) == 0
    prox = db.connection.execute("SELECT proximo_disparo FROM alarms").fetchone()[0]
    assert datetime.fromisoformat(prox) == disparo + timedelta(days=1)


def test_tick_uma_vez_desativa():
    db = _db()
    responder("/alarm 21:00 once only @once", db, _AGORA)
    disparo = _AGORA.replace(hour=21, minute=0)
    enviados: list[str] = []
    assert tick_alarmes(disparo, db, enviados.append) == 1
    assert db.connection.execute("SELECT ativo FROM alarms").fetchone()[0] == 0
