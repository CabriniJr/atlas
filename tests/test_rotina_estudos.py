"""TDD — E3-02: collect da rotina de estudos."""

from __future__ import annotations

from datetime import datetime

import pytest

from atlas.db import Database
from atlas.executor import ContextoExecucao
from atlas.rotinas import obter
from atlas.routines import Rotina

_AGORA = datetime(2025, 6, 16, 21, 0)
_ROTINA = Rotina(nome="estudos", descricao="Resumo de estudos", agenda="0 21 * * *", modelo="none")


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


def _ctx(db):
    return ContextoExecucao(agora=_AGORA, rotina=_ROTINA, origem="agenda", db=db)


def test_collect_estudos_registrado():
    import atlas.rotinas.estudos  # noqa: F401

    assert obter("estudos") is not None


def test_collect_estudos_vazio(db):
    import atlas.rotinas.estudos  # noqa: F401

    result = obter("estudos")(_ctx(db))
    saida = result.data["_saida"]
    assert "estudo" in saida.lower() or "0" in saida or "nenhum" in saida.lower()


def test_collect_estudos_com_reg_estudo(db):
    import atlas.rotinas.estudos  # noqa: F401

    db.insert(
        "activities",
        ts=_AGORA.isoformat(),
        dominio="estudo",
        rotina="reg",
        texto_cru="capítulo 3 de Python",
    )
    result = obter("estudos")(_ctx(db))
    assert "capítulo 3" in result.data["_saida"]


def test_collect_estudos_com_timer(db):
    import atlas.rotinas.estudos  # noqa: F401

    db.insert(
        "activities",
        ts=_AGORA.isoformat(),
        dominio="geral",
        rotina="timer",
        texto_cru="estudo 45min",
        dados_json={"timer": "estudo", "duration_min": 45},
    )
    result = obter("estudos")(_ctx(db))
    assert "45" in result.data["_saida"]


def test_collect_estudos_ignora_outros_dias(db):
    import atlas.rotinas.estudos  # noqa: F401

    db.insert(
        "activities", ts="2020-01-01T10:00:00", dominio="estudo", rotina="reg", texto_cru="ontem"
    )
    result = obter("estudos")(_ctx(db))
    assert "ontem" not in result.data["_saida"]
