"""Testes do executor do ciclo de vida da rotina (E1-10 — TDD).

Cobre os casos da spec docs/specs/executor-e-notificacao.md: orquestração das
fases trigger→collect→gate→analyze→deliver, gravação em `runs` e notificação.
Cada fase é injetada (testável isoladamente); o invocador de IA é um fake
(a CI nunca chama `claude -p` real).
"""

from __future__ import annotations

from datetime import datetime

from atlas.db import Database
from atlas.executor import (
    CollectResult,
    ContextoExecucao,
    StoreOp,
    executar,
)
from atlas.routines import Rotina

_AGORA = datetime(2026, 6, 16, 10, 0, 0)


def _db() -> Database:
    return Database(":memory:")


def _ctx(rotina: Rotina, origem: str = "manual", payload: str | None = None) -> ContextoExecucao:
    return ContextoExecucao(agora=_AGORA, rotina=rotina, origem=origem, payload=payload)


def _coletor() -> list[str]:
    return []


# ---------------------------------------------------------------------------
# Rotina log-puro (sem collect, sem IA)
# ---------------------------------------------------------------------------


def test_log_puro_notifica_confirmacao_e_grava_run_ok():
    db = _db()
    rotina = Rotina(nome="treino", descricao="registra treino", modelo="none")
    enviados: list[str] = []
    res = executar(_ctx(rotina), db, enviados.append)

    assert res.status == "ok"
    assert res.camada == "0"
    assert enviados and "treino" in enviados[0]

    run = db.connection.execute("SELECT rotina, status, camada FROM runs").fetchone()
    assert run["rotina"] == "treino"
    assert run["status"] == "ok"
    assert run["camada"] == "0"


# ---------------------------------------------------------------------------
# collect persiste o que `store` declara
# ---------------------------------------------------------------------------


def test_collect_persiste_store_em_activities():
    db = _db()
    rotina = Rotina(nome="treino", descricao="d", modelo="none", store="activities")

    def collect(ctx):
        return CollectResult(
            data={},
            store=[
                StoreOp(
                    entity="activities",
                    fields={
                        "ts": ctx.agora.isoformat(),
                        "dominio": "fisico",
                        "rotina": "treino",
                        "texto_cru": "agachamento 80kg",
                    },
                )
            ],
        )

    res = executar(_ctx(rotina), db, _coletor().append, collect=collect)
    assert res.status == "ok"
    n = db.connection.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
    assert n == 1


# ---------------------------------------------------------------------------
# gate / analyze (modo 2a com invocador fake)
# ---------------------------------------------------------------------------


def test_gate_falha_nao_chama_ia_e_run_skipped():
    db = _db()
    rotina = Rotina(nome="resumo", descricao="d", modelo="sonnet")
    chamou_ia: list[str] = []

    res = executar(
        _ctx(rotina),
        db,
        _coletor().append,
        collect=lambda ctx: CollectResult(data={"x": 1}, store=[]),
        gate=lambda data: False,
        render_prompt=lambda data: "prompt",
        invocar_ia=lambda prompt, modelo: chamou_ia.append(prompt) or "nunca",
    )

    assert res.status == "skipped"
    assert res.gate_passou is False
    assert chamou_ia == []  # IA não foi chamada
    run = db.connection.execute("SELECT status FROM runs").fetchone()
    assert run["status"] == "skipped"


def test_analyze_roda_quando_gate_passa_e_notifica_resultado():
    db = _db()
    rotina = Rotina(nome="resumo", descricao="d", modelo="sonnet")
    enviados: list[str] = []

    res = executar(
        _ctx(rotina),
        db,
        enviados.append,
        collect=lambda ctx: CollectResult(data={"n": 3}, store=[]),
        gate=lambda data: True,
        render_prompt=lambda data: f"resuma {data['n']}",
        invocar_ia=lambda prompt, modelo: f"[{modelo}] análise de '{prompt}'",
    )

    assert res.status == "ok"
    assert res.camada == "2a"
    assert res.gate_passou is True
    assert enviados and "análise de 'resuma 3'" in enviados[0]
    run = db.connection.execute("SELECT status, camada FROM runs").fetchone()
    assert run["status"] == "ok"
    assert run["camada"] == "2a"


# ---------------------------------------------------------------------------
# Resiliência: erro numa fase não derruba o motor (ADR-0006)
# ---------------------------------------------------------------------------


def test_collect_que_lanca_marca_failed_e_notifica_erro():
    db = _db()
    rotina = Rotina(nome="quebrada", descricao="d", modelo="none")
    enviados: list[str] = []

    def collect(ctx):
        raise RuntimeError("boom")

    res = executar(_ctx(rotina), db, enviados.append, collect=collect)

    assert res.status == "failed"
    assert res.erro is not None
    assert enviados and ("falh" in enviados[0].lower() or "erro" in enviados[0].lower())
    run = db.connection.execute("SELECT status FROM runs").fetchone()
    assert run["status"] == "failed"
