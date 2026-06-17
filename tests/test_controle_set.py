"""TDD — E5-03: /routine <name> set <field> <value>."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from atlas.controle import aplicar_overrides, responder_controle
from atlas.db import Database
from atlas.routines import carregar_rotinas

_AGORA = datetime(2025, 6, 16, 10, 0)


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


def _rot(db):
    """Retorna rotina 'treino' carregada com overrides aplicados."""
    carga = carregar_rotinas(Path("routines"))
    aplicar_overrides(db, carga.rotinas)
    return next((r for r in carga.rotinas if r.nome == "treino"), None)


# ---------------------------------------------------------------------------
# Agenda
# ---------------------------------------------------------------------------


def test_set_agenda_salva_override(db):
    resp = responder_controle("/routine treino set agenda 0 20 * * *", db, _AGORA)
    assert "✅" in resp

    row = db.connection.execute(
        "SELECT valor FROM routine_state WHERE rotina='treino' AND chave='agenda'"
    ).fetchone()
    assert row is not None
    assert row[0] == "0 20 * * *"


def test_set_agenda_override_aplicado_na_carga(db):
    responder_controle("/routine treino set agenda 0 7 * * *", db, _AGORA)
    rot = _rot(db)
    assert rot is not None
    assert rot.agenda == "0 7 * * *"


def test_set_agenda_cron_invalido_rejeita(db):
    resp = responder_controle("/routine treino set agenda nao-e-cron", db, _AGORA)
    assert "⚠️" in resp or "inválido" in resp.lower() or "invalid" in resp.lower()


def test_set_agenda_cron_com_menos_de_5_partes_rejeita(db):
    resp = responder_controle("/routine treino set agenda 0 20 *", db, _AGORA)
    assert "⚠️" in resp or "invalid" in resp.lower()


def test_set_agenda_substitui_override_anterior(db):
    responder_controle("/routine treino set agenda 0 20 * * *", db, _AGORA)
    responder_controle("/routine treino set agenda 0 7 * * 1", db, _AGORA)
    row = db.connection.execute(
        "SELECT valor FROM routine_state WHERE rotina='treino' AND chave='agenda'"
    ).fetchone()
    assert row["valor"] == "0 7 * * 1"


# ---------------------------------------------------------------------------
# Campo desconhecido / rotina não encontrada
# ---------------------------------------------------------------------------


def test_set_campo_desconhecido_rejeita(db):
    resp = responder_controle("/routine treino set modelo opus", db, _AGORA)
    assert "⚠️" in resp or "unknown" in resp.lower()


def test_set_rotina_nao_encontrada(db):
    resp = responder_controle("/routine nope set agenda 0 20 * * *", db, _AGORA)
    assert "not found" in resp.lower()


def test_set_sem_valor_mostra_usage(db):
    resp = responder_controle("/routine treino set agenda", db, _AGORA)
    assert "usage" in resp.lower() or "⚠️" in resp


def test_set_sem_campo_mostra_detalhe(db):
    resp = responder_controle("/routine treino set", db, _AGORA)
    assert "usage" in resp.lower() or "⚠️" in resp
