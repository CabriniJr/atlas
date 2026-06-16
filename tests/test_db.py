"""Testes da camada de dados (ADR-0002 — modelo de dados SQLite)."""

import pytest

from atlas.db import Database


def _tables(db: Database) -> set[str]:
    rows = db.connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


def test_schema_cria_as_seis_tabelas_do_adr0002():
    db = Database(":memory:")
    assert _tables(db) == {
        "activities",
        "goals",
        "goal_links",
        "books",
        "runs",
        "routine_state",
    }


def test_insert_devolve_id_e_persiste_a_linha():
    db = Database(":memory:")
    rid = db.insert(
        "activities",
        ts="2026-06-16T21:00:00",
        dominio="fisico",
        rotina="treino",
        texto_cru="perna hoje",
    )
    assert rid == 1
    row = db.get("activities", rid)
    assert row["dominio"] == "fisico"
    assert row["texto_cru"] == "perna hoje"


def test_dados_json_faz_round_trip_como_dict():
    db = Database(":memory:")
    rid = db.insert(
        "activities",
        ts="2026-06-16T21:00:00",
        dominio="fisico",
        rotina="treino",
        dados_json={"exercicio": "agachamento", "carga": 80, "series": "4x10"},
    )
    row = db.get("activities", rid)
    assert row["dados_json"] == {"exercicio": "agachamento", "carga": 80, "series": "4x10"}


def test_foreign_key_impede_goal_link_orfao():
    import sqlite3

    db = Database(":memory:")
    with pytest.raises(sqlite3.IntegrityError):
        db.insert("goal_links", activity_id=999, goal_id=999, contribuicao=1.0)
