"""Testes do handler do bot (MVP funcional — Camada 0, zero IA)."""

from __future__ import annotations

from datetime import datetime

from atlas.db import Database
from atlas.handler import responder


def _db() -> Database:
    return Database(":memory:")


def test_ajuda_lista_comandos():
    resposta = responder("/ajuda", _db(), datetime(2026, 6, 16, 10, 0))
    assert "/status" in resposta
    assert "/help" in resposta


def test_start_da_boas_vindas():
    resposta = responder("/start", _db(), datetime(2026, 6, 16, 10, 0))
    assert "Atlas" in resposta


def test_mensagem_livre_registra_atividade():
    db = _db()
    resposta = responder("perna hoje, agachamento 80kg", db, datetime(2026, 6, 16, 21, 0))
    linhas = db.connection.execute("SELECT texto_cru, dominio FROM activities").fetchall()
    assert len(linhas) == 1
    assert linhas[0]["texto_cru"] == "perna hoje, agachamento 80kg"
    assert "✓" in resposta


def test_infere_dominio_fisico():
    db = _db()
    responder("treino de perna", db, datetime(2026, 6, 16, 21, 0))
    dominio = db.connection.execute("SELECT dominio FROM activities").fetchone()["dominio"]
    assert dominio == "fisico"


def test_infere_dominio_estudo():
    db = _db()
    responder("estudei álgebra linear 1h30", db, datetime(2026, 6, 16, 21, 0))
    dominio = db.connection.execute("SELECT dominio FROM activities").fetchone()["dominio"]
    assert dominio == "estudo"


def test_status_conta_registros_do_dia():
    db = _db()
    agora = datetime(2026, 6, 16, 21, 0)
    responder("treino", db, agora)
    responder("estudei", db, agora)
    resposta = responder("/status", db, agora)
    assert "2" in resposta


def test_status_ignora_dias_anteriores():
    db = _db()
    responder("treino ontem", db, datetime(2026, 6, 15, 21, 0))
    resposta = responder("/status", db, datetime(2026, 6, 16, 9, 0))
    assert "0" in resposta
