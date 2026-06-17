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


def test_texto_livre_nao_registra_e_retorna_ajuda():
    """E1-11: barreira — texto sem intenção não grava nada."""
    db = _db()
    resposta = responder("perna hoje, agachamento 80kg", db, datetime(2026, 6, 16, 21, 0))
    n = db.connection.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
    assert n == 0
    assert "/reg" in resposta or "help" in resposta.lower()


def test_reg_grava_atividade():
    db = _db()
    resposta = responder("/reg treino de perna", db, datetime(2026, 6, 16, 21, 0))
    linhas = db.connection.execute("SELECT texto_cru, dominio FROM activities").fetchall()
    assert len(linhas) == 1
    assert "perna" in linhas[0]["texto_cru"]
    assert linhas[0]["dominio"] == "geral"
    assert "📝" in resposta


def test_status_conta_registros_do_dia():
    db = _db()
    agora = datetime(2026, 6, 16, 21, 0)
    responder("/reg treino", db, agora)
    responder("/reg estudei", db, agora)
    resposta = responder("/status", db, agora)
    assert "2" in resposta


def test_status_ignora_dias_anteriores():
    db = _db()
    responder("/reg treino ontem", db, datetime(2026, 6, 15, 21, 0))
    resposta = responder("/status", db, datetime(2026, 6, 16, 9, 0))
    assert "0" in resposta
