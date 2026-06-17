"""E2-01 — collect da rotina resumo-diario (TDD)."""

from __future__ import annotations

from datetime import datetime

import atlas.rotinas.resumo_diario  # noqa: F401 — registra

from atlas.db import Database
from atlas.executor import ContextoExecucao
from atlas.rotinas import obter
from atlas.routines import Rotina

T0 = datetime(2026, 6, 16, 21, 0)
_ROT = Rotina(nome="resumo-diario", descricao="Resumo", modelo="none")


def _ctx(db: Database) -> ContextoExecucao:
    return ContextoExecucao(agora=T0, rotina=_ROT, db=db)


def test_collect_registrado():
    assert obter("resumo-diario") is not None


def test_collect_vazio_retorna_resumo():
    db = Database(":memory:")
    coletar = obter("resumo-diario")
    resultado = coletar(_ctx(db))
    saida = resultado.data.get("_saida", "")
    assert "Resumo" in saida or "16/06" in saida


def test_collect_com_atividade():
    db = Database(":memory:")
    db.insert(
        "activities",
        ts=T0.isoformat(),
        dominio="geral",
        rotina="reg",
        texto_cru="estudei python",
    )
    coletar = obter("resumo-diario")
    resultado = coletar(_ctx(db))
    saida = resultado.data["_saida"]
    assert "estudei python" in saida


def test_collect_com_pool_aberto():
    db = Database(":memory:")
    db.insert(
        "ideas",
        tipo="ideia",
        titulo="fazer UI web",
        corpo="fazer UI web do Atlas",
        prioridade=10,
        estado="capturada",
        criado_em=T0.isoformat(),
        atualizado_em=T0.isoformat(),
    )
    coletar = obter("resumo-diario")
    resultado = coletar(_ctx(db))
    saida = resultado.data["_saida"]
    assert "fazer UI web" in saida


def test_collect_sem_db_nao_explode():
    ctx = ContextoExecucao(agora=T0, rotina=_ROT, db=None)
    coletar = obter("resumo-diario")
    resultado = coletar(ctx)
    assert "_saida" in resultado.data
