"""E1-11 — Barreira de entrada (TDD).

Texto livre sem intenção explícita NÃO grava nada. Só grava via:
  - micro-sintaxe de tracker (ex.: 'weight: 82.3')
  - /reg <texto> (nota livre com domínio opcional)
  - comandos dedicados (/track, /alarm, /idea …)
"""

from __future__ import annotations

from datetime import datetime

from atlas.db import Database
from atlas.handler import responder

T0 = datetime(2026, 6, 16, 21, 0)


def _db() -> Database:
    return Database(":memory:")


def _n_activities(db: Database) -> int:
    return db.connection.execute("SELECT COUNT(*) FROM activities").fetchone()[0]


# --- texto livre sem intenção → ajuda, 0 registro ----------------------------


def test_texto_livre_nao_registra():
    db = _db()
    responder("oi", db, T0)
    assert _n_activities(db) == 0


def test_texto_livre_dominio_retorna_ajuda():
    db = _db()
    resposta = responder("treino de perna hoje", db, T0)
    assert _n_activities(db) == 0
    assert "help" in resposta.lower() or "/reg" in resposta or "ajuda" in resposta.lower()


def test_texto_vazio_retorna_ajuda():
    db = _db()
    responder("   ", db, T0)
    assert _n_activities(db) == 0


# --- /reg — nota livre com intenção explícita --------------------------------


def test_reg_grava_nota_geral():
    db = _db()
    resposta = responder("/reg fui dormir 23h", db, T0)
    assert _n_activities(db) == 1
    row = db.connection.execute("SELECT dominio, rotina, texto_cru FROM activities").fetchone()
    assert row["dominio"] == "geral"
    assert row["rotina"] == "reg"
    assert "23h" in row["texto_cru"]
    assert "📝" in resposta or "logged" in resposta.lower()


def test_reg_com_dominio_hash():
    db = _db()
    responder("/reg #sono fui dormir 23h", db, T0)
    row = db.connection.execute("SELECT dominio, texto_cru FROM activities").fetchone()
    assert row["dominio"] == "sono"
    assert "23h" in row["texto_cru"]


def test_reg_vazio_nao_grava():
    db = _db()
    resposta = responder("/reg", db, T0)
    assert _n_activities(db) == 0
    assert "usage" in resposta.lower() or "/reg" in resposta


def test_reg_so_espacos_nao_grava():
    db = _db()
    responder("/reg   ", db, T0)
    assert _n_activities(db) == 0


def test_reg_dominio_invalido_cai_em_geral():
    db = _db()
    responder("/reg #   texto qualquer", db, T0)
    row = db.connection.execute("SELECT dominio FROM activities").fetchone()
    assert row["dominio"] == "geral"


# --- micro-sintaxe de tracker continua funcionando --------------------------


def test_microsintaxe_tracker_ainda_registra():
    db = _db()
    # cria tracker 'weight' primeiro
    db.insert(
        "trackers",
        nome="weight",
        dominio="saude",
        tipo="numero",
        unidade="kg",
        sintaxe="weight:",
        ativo=1,
        criado_em=T0.isoformat(),
    )
    resposta = responder("weight: 82.3", db, T0)
    assert _n_activities(db) == 1
    assert "82.3" in resposta or "weight" in resposta.lower()


# --- /note legado ainda funciona (compatibilidade) ---------------------------


def test_note_legado_ainda_funciona():
    db = _db()
    resposta = responder("/note lembrar de algo", db, T0)
    assert _n_activities(db) == 1
    assert "📝" in resposta or "note" in resposta.lower()
