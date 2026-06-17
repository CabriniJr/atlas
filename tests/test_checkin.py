"""TDD — rotina CheckIn: pergunta periódica para registrar trackers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from atlas.core.store import ResourceStore
from atlas.core.resource import Resource
from atlas.db import Database
from atlas.executor import ContextoExecucao
from atlas.rotinas import obter
from atlas.routines import Rotina

_AGORA = datetime(2025, 6, 16, 9, 0)
_ROTINA = Rotina(nome="checkin", descricao="Check-in periódico", agenda="0 9 * * *", modelo="none")


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def store(tmp_path):
    s = ResourceStore(str(tmp_path / "test.db"))
    s.apply(Resource(kind="Tracker", name="peso", labels={"active": "true"},
                     spec={"unit": "kg", "syntax": "peso:", "active": True}), _AGORA)
    s.apply(Resource(kind="Tracker", name="sono", labels={"active": "true"},
                     spec={"unit": "h", "syntax": "sono:", "active": True}), _AGORA)
    return s


def _ctx(db, store):
    ctx = ContextoExecucao(agora=_AGORA, rotina=_ROTINA, origem="agenda", db=db)
    ctx.store = store
    return ctx


def test_checkin_registrado(db):
    import atlas.rotinas.checkin  # noqa: F401
    fn = obter("checkin")
    assert fn is not None


def test_checkin_pergunta_trackers(db, store):
    import atlas.rotinas.checkin  # noqa: F401
    fn = obter("checkin")
    result = fn(_ctx(db, store))
    saida = result.data["_saida"]
    assert "peso" in saida.lower() or "sono" in saida.lower()


def test_checkin_sem_trackers_mostra_mensagem(db):
    import atlas.rotinas.checkin  # noqa: F401
    fn = obter("checkin")
    ctx = ContextoExecucao(agora=_AGORA, rotina=_ROTINA, origem="agenda", db=db)
    ctx.store = ResourceStore(":memory:")
    result = fn(ctx)
    saida = result.data["_saida"]
    assert saida  # não falha vazio


def test_checkin_inclui_instrucoes_de_registro(db, store):
    import atlas.rotinas.checkin  # noqa: F401
    fn = obter("checkin")
    result = fn(_ctx(db, store))
    saida = result.data["_saida"]
    # deve mostrar sintaxe de como registrar
    assert ":" in saida
