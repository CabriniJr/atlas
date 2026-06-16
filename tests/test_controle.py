"""Testes do controle de rotinas por chat (E5-02, batch).

Usa o ATLAS_ROUTINES_DIR apontando para a pasta real do repo (tem a rotina
'treino'). Cobre listar, detalhe, run e activate/deactivate (override no DB).
"""

from __future__ import annotations

import os
from datetime import datetime

from atlas.controle import responder_controle
from atlas.db import Database
from atlas.handler import responder

_AGORA = datetime(2026, 6, 16, 10, 0, 0)


def _db() -> Database:
    return Database(":memory:")


def _setup_routines_dir():
    # aponta para routines/ do repo (tem 'treino')
    os.environ["ATLAS_ROUTINES_DIR"] = "routines"


def test_routines_lista_treino():
    _setup_routines_dir()
    resp = responder("/routines", _db(), _AGORA)
    assert "treino" in resp


def test_routine_detalhe_e_inexistente():
    _setup_routines_dir()
    db = _db()
    assert "treino" in responder("/routine treino", db, _AGORA)
    assert "not found" in responder("/routine zzz", db, _AGORA).lower()


def test_run_executa_e_grava_run():
    _setup_routines_dir()
    db = _db()
    resp = responder("/run treino", db, _AGORA)
    assert "treino" in resp
    assert db.connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1


def test_activate_deactivate_persiste_override_no_db():
    _setup_routines_dir()
    db = _db()
    responder("/deactivate treino", db, _AGORA)
    val = db.connection.execute(
        "SELECT valor FROM routine_state WHERE rotina='treino' AND chave='ativa'"
    ).fetchone()[0]
    assert val == "false"
    # reflete na listagem
    assert "treino [off]" in responder_controle("/routines", db, _AGORA)
    responder("/activate treino", db, _AGORA)
    assert "treino [on]" in responder_controle("/routines", db, _AGORA)
