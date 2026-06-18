"""TDD — E3-01: collect da rotina de treino."""

from __future__ import annotations

from datetime import datetime

import pytest

from atlas.db import Database
from atlas.executor import ContextoExecucao
from atlas.rotinas import obter
from atlas.routines import Rotina

_AGORA = datetime(2025, 6, 16, 20, 0)
_ROTINA = Rotina(nome="treino", descricao="Treino físico", agenda="0 20 * * *", modelo="none")


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


def _ctx(db):
    return ContextoExecucao(agora=_AGORA, rotina=_ROTINA, origem="agenda", db=db)


def test_collect_treino_registrado(db):
    """Deve retornar collect registrado no registry."""
    import atlas.rotinas.treino  # noqa: F401

    fn = obter("treino")
    assert fn is not None


def test_collect_treino_sem_atividades_hoje(db):
    import atlas.rotinas.treino  # noqa: F401

    fn = obter("treino")
    result = fn(_ctx(db))
    saida = result.data["_saida"]
    assert "treino" in saida.lower() or "nenhum" in saida.lower() or "0" in saida


def test_collect_treino_com_registro_fisico(db):
    import atlas.rotinas.treino  # noqa: F401

    db.insert(
        "activities",
        ts=_AGORA.isoformat(),
        dominio="fisico",
        rotina="reg",
        texto_cru="peito e costas 45min",
    )
    fn = obter("treino")
    result = fn(_ctx(db))
    saida = result.data["_saida"]
    assert "peito e costas 45min" in saida or "1" in saida


def test_collect_treino_com_tracker_fisico(db):
    import atlas.rotinas.treino  # noqa: F401

    db.insert(
        "activities",
        ts=_AGORA.isoformat(),
        dominio="fisico",
        rotina="tracking",
        texto_cru="treino: 45",
        dados_json={"tracker": "treino", "valor": 45, "unidade": "min"},
    )
    fn = obter("treino")
    result = fn(_ctx(db))
    saida = result.data["_saida"]
    assert "treino" in saida.lower()
    assert "45" in saida


def test_collect_treino_ignora_atividades_de_outros_dias(db):
    import atlas.rotinas.treino  # noqa: F401

    db.insert(
        "activities",
        ts="2020-01-01T10:00:00",
        dominio="fisico",
        rotina="reg",
        texto_cru="ontem",
    )
    fn = obter("treino")
    result = fn(_ctx(db))
    saida = result.data["_saida"]
    assert "ontem" not in saida
