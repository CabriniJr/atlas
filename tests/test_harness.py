"""TDD — harness de teste de rotina (E1-07 / ADR-0007).

Verifica que o harness injeta contexto e roda collect de forma isolada,
sem IA real, sem Telegram, sem banco em disco permanente.
"""

from __future__ import annotations

from datetime import datetime

import pytest

import atlas.harness as harness
from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.db import Database
from atlas.harness import HarnessResult
from atlas.rotinas import registrar

_AGORA = datetime(2025, 6, 16, 10, 0)


# ── Fixture de rotina sintética ───────────────────────────────────────────────


@registrar("_test_ok")
def _collect_ok(ctx):
    from atlas.executor import CollectResult

    return CollectResult(data={"_saida": f"ok em {ctx.agora.hour}h"})


@registrar("_test_err")
def _collect_err(ctx):
    raise ValueError("collect quebrou")


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def store(tmp_path):
    return ResourceStore(str(tmp_path / "store.db"))


# ── Testes harness.testar_collect ─────────────────────────────────────────────────────


def test_harness_collect_rotina_ok(db):
    res = harness.testar_collect("_test_ok", db=db, agora=_AGORA)
    assert isinstance(res, HarnessResult)
    assert res.erro is None
    assert "ok" in res.saida
    assert "10h" in res.saida


def test_harness_collect_agora_injetado(db):
    agora2 = datetime(2025, 6, 16, 15, 0)
    res = harness.testar_collect("_test_ok", db=db, agora=agora2)
    assert "15h" in res.saida


def test_harness_collect_rotina_nao_existe():
    res = harness.testar_collect("_rotina_que_nao_existe_xyz")
    assert res.erro is not None
    assert "não encontrada" in res.erro


def test_harness_collect_rotina_com_excecao(db):
    res = harness.testar_collect("_test_err", db=db)
    assert res.erro is not None
    assert "ValueError" in res.erro
    assert "collect quebrou" in res.erro


def test_harness_collect_sem_db():
    res = harness.testar_collect("_test_ok", agora=_AGORA)
    assert res.erro is None
    assert "ok" in res.saida


def test_harness_collect_com_store(db, store):
    store.apply(
        Resource(kind="Tracker", name="peso", labels={"active": "true"}, spec={"unit": "kg"}),
        _AGORA,
    )
    res = harness.testar_collect("_test_ok", db=db, store=store, agora=_AGORA)
    assert res.erro is None


# ── Testes harness.testar_gate ────────────────────────────────────────────────────────


def test_harness_gate_true():
    assert harness.testar_gate(lambda data: data.get("_saida") != "", {"_saida": "algo"}) is True


def test_harness_gate_false():
    assert harness.testar_gate(lambda _: False, {}) is False


# ── Testes harness.inspecionar ────────────────────────────────────────────────────────


def test_inspecionar_formata_saida(db):
    saida = harness.inspecionar("_test_ok", db=db, agora=_AGORA)
    assert "🧪" in saida
    assert "_test_ok" in saida
    assert "ok" in saida


def test_inspecionar_rotina_inexistente():
    saida = harness.inspecionar("_xyz_inexistente")
    assert "⚠️" in saida
    assert "_xyz_inexistente" in saida


def test_inspecionar_rotina_com_excecao(db):
    saida = harness.inspecionar("_test_err", db=db)
    assert "⚠️" in saida


# ── Teste de rotinas reais ────────────────────────────────────────────────────


def test_harness_resumo_diario_roda_sem_crash(db):
    """resumo-diario deve funcionar mesmo com DB vazio."""
    import atlas.rotinas.resumo_diario  # noqa: F401 — registra

    res = harness.testar_collect("resumo-diario", db=db, agora=_AGORA)
    assert res.erro is None
    assert "Resumo" in res.saida


def test_harness_checkin_com_store(db, store):
    """checkin deve listar trackers do store."""
    import atlas.rotinas.checkin  # noqa: F401

    store.apply(
        Resource(kind="Tracker", name="peso", labels={"active": "true"}, spec={"unit": "kg"}),
        _AGORA,
    )
    res = harness.testar_collect("checkin", db=db, store=store, agora=_AGORA)
    assert res.erro is None
    assert "peso" in res.saida
