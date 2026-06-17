"""Testes — rotina checkup-semanal (E3-04)."""
from __future__ import annotations

from datetime import datetime

import pytest

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.db import Database
from atlas.executor import ContextoExecucao
from atlas.routines import Rotina

_AGORA = datetime(2026, 6, 16, 10, 0)


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / "test.db"))
    # Uma entrada de tracker para a goal de peso
    d.insert(
        "activities",
        ts=_AGORA.isoformat(),
        dominio="fisico",
        rotina="tracking",
        texto_cru="peso: 83.5",
        dados_json={"tracker": "peso", "valor": 83.5, "unidade": "kg"},
    )
    return d


@pytest.fixture
def store(tmp_path):
    s = ResourceStore(str(tmp_path / "test.db"))
    s.apply(Resource(
        kind="Goal", name="emagrecimento",
        labels={"state": "active"},
        spec={"target": "80", "unit": "kg", "tracker": "peso",
              "start": "90", "direction": "down"},
        status={"current": "90", "progress": "0%"},
    ), _AGORA)
    s.apply(Resource(
        kind="Goal", name="sem-tracker",
        labels={"state": "active"},
        spec={"target": "10", "unit": "km"},
        status={},
    ), _AGORA)
    s.apply(Resource(
        kind="Goal", name="concluida",
        labels={"state": "done"},
        spec={"target": "5", "unit": "km", "tracker": "corrida"},
        status={"progress": "100%"},
    ), _AGORA)
    return s


def _ctx(db, store):
    rot = Rotina(
        nome="checkup-semanal",
        descricao="", agenda="0 10 * * 1",
        modelo="none", saida="telegram", ativa=True,
    )
    return ContextoExecucao(agora=_AGORA, rotina=rot, origem="agenda", db=db, store=store)


def test_collect_retorna_saida(db, store):
    import atlas.rotinas.checkup_semanal  # noqa: F401
    from atlas.rotinas import obter
    collect = obter("checkup-semanal")
    assert collect is not None
    result = collect(_ctx(db, store))
    assert result is not None
    saida = result.data.get("_saida", "")
    assert "emagrecimento" in saida


def test_collect_inclui_progresso(db, store):
    from atlas.rotinas import obter
    collect = obter("checkup-semanal")
    result = collect(_ctx(db, store))
    saida = result.data["_saida"]
    # deve ter calculado progresso do goal com tracker
    assert "%" in saida


def test_collect_ignora_goals_concluidas(db, store):
    from atlas.rotinas import obter
    collect = obter("checkup-semanal")
    result = collect(_ctx(db, store))
    saida = result.data["_saida"]
    # goal "concluida" tem state=done → deve aparecer apenas como concluída
    # mas não como item ativo
    assert saida.count("concluida") == 0 or "✅" in saida


def test_collect_sem_goals(tmp_path):
    import atlas.rotinas.checkup_semanal  # noqa: F401
    from atlas.rotinas import obter
    db2 = Database(str(tmp_path / "empty.db"))
    s2 = ResourceStore(str(tmp_path / "empty.db"))
    collect = obter("checkup-semanal")
    result = collect(_ctx(db2, s2))
    saida = result.data["_saida"]
    assert "goal" in saida.lower() or "meta" in saida.lower()
