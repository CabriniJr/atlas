"""Testes de trackers (E5-04/05, batch): criar, logar por sintaxe, detalhe, rm."""

from __future__ import annotations

from datetime import datetime

from atlas.db import Database
from atlas.handler import responder

_AGORA = datetime(2026, 6, 16, 10, 0, 0)


def _db() -> Database:
    return Database(":memory:")


def test_criar_e_listar():
    db = _db()
    resp = responder("/track new weight kg", db, _AGORA)
    assert "weight" in resp
    assert "weight" in responder("/track", db, _AGORA)


def test_log_por_sintaxe_grava_activity():
    db = _db()
    responder("/track new weight kg", db, _AGORA)
    resp = responder("weight: 82.3", db, _AGORA)
    assert "82.3" in resp and "kg" in resp
    row = db.connection.execute(
        "SELECT json_extract(dados_json,'$.valor') AS v, rotina FROM activities"
    ).fetchone()
    assert row["rotina"] == "tracking"
    assert row["v"] == 82.3


def test_valor_nao_numerico_avisa_e_nao_grava():
    db = _db()
    responder("/track new weight kg", db, _AGORA)
    resp = responder("weight: muito", db, _AGORA)
    assert "number" in resp.lower()
    assert db.connection.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 0


def test_detalhe_mostra_historico_e_stats():
    db = _db()
    responder("/track new weight kg", db, _AGORA)
    responder("weight: 80", db, _AGORA)
    responder("weight: 82", db, _AGORA)
    resp = responder("/track weight", db, _AGORA)
    assert "avg" in resp and "weight" in resp


def test_texto_livre_sem_tracker_cai_no_log_normal():
    db = _db()
    resp = responder("treino de perna", db, _AGORA)
    assert "logged" in resp.lower()
    # virou activity normal, não tracking
    rot = db.connection.execute("SELECT rotina FROM activities").fetchone()[0]
    assert rot == "log"


def test_rm_desativa():
    db = _db()
    responder("/track new weight kg", db, _AGORA)
    responder("/track weight rm", db, _AGORA)
    assert (
        db.connection.execute("SELECT ativo FROM trackers WHERE nome='weight'").fetchone()[0] == 0
    )
    # após rm, a sintaxe não registra mais
    responder("weight: 90", db, _AGORA)
    assert (
        db.connection.execute("SELECT COUNT(*) FROM activities WHERE rotina='tracking'").fetchone()[
            0
        ]
        == 0
    )
