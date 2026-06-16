"""Testes do scheduler (E1-06 — TDD).

Cobre docs/specs/scheduler.md: cálculo do próximo disparo, tick que dispara o
que venceu, e catch-up no boot (1 run de recuperação, não enxurrada).
O disparo é injetado (fake) — o scheduler não conhece o executor.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from atlas.db import Database
from atlas.routines import Rotina
from atlas.scheduler import catch_up, proxima_execucao, tick

_AGORA = datetime(2026, 6, 16, 21, 0, 0)


def _db() -> Database:
    return Database(":memory:")


# ---------------------------------------------------------------------------
# proxima_execucao
# ---------------------------------------------------------------------------


def test_every_nunca_rodou_vence_agora():
    assert proxima_execucao("@every 1m", None, _AGORA) <= _AGORA


def test_every_vencido():
    ultimo = _AGORA - timedelta(seconds=70)
    assert proxima_execucao("@every 1m", ultimo, _AGORA) <= _AGORA


def test_every_ainda_nao_vencido():
    ultimo = _AGORA - timedelta(seconds=30)
    assert proxima_execucao("@every 1m", ultimo, _AGORA) > _AGORA


def test_daily_antes_do_horario_nao_vence():
    agora = _AGORA.replace(hour=20, minute=0)
    assert proxima_execucao("@daily 21:00", None, agora) > agora


def test_daily_no_horario_vence():
    agora = _AGORA.replace(hour=21, minute=30)
    assert proxima_execucao("@daily 21:00", None, agora) <= agora


def test_daily_nao_redispara_no_mesmo_dia():
    ultimo = _AGORA.replace(hour=21, minute=0)
    agora = _AGORA.replace(hour=21, minute=30)
    prox = proxima_execucao("@daily 21:00", ultimo, agora)
    assert prox > agora  # próximo é amanhã


# ---------------------------------------------------------------------------
# tick
# ---------------------------------------------------------------------------


def test_tick_dispara_rotina_vencida_e_marca_ultimo():
    db = _db()
    rotina = Rotina(nome="ping", descricao="d", agenda="@every 1m", modelo="none")
    # último run 70s atrás
    db.connection.execute(
        "INSERT INTO routine_state (rotina, chave, valor, atualizado_em) VALUES (?,?,?,?)",
        ("ping", "ultimo_run", (_AGORA - timedelta(seconds=70)).isoformat(), _AGORA.isoformat()),
    )
    db.connection.commit()

    disparadas: list[str] = []
    res = tick(_AGORA, [rotina], db, lambda r: disparadas.append(r.nome))

    assert disparadas == ["ping"]
    assert len(res) == 1
    novo = db.connection.execute(
        "SELECT valor FROM routine_state WHERE rotina='ping' AND chave='ultimo_run'"
    ).fetchone()[0]
    assert novo == _AGORA.isoformat()


def test_tick_nao_dispara_quando_nao_venceu():
    db = _db()
    rotina = Rotina(nome="ping", descricao="d", agenda="@every 1m", modelo="none")
    db.connection.execute(
        "INSERT INTO routine_state (rotina, chave, valor, atualizado_em) VALUES (?,?,?,?)",
        ("ping", "ultimo_run", (_AGORA - timedelta(seconds=30)).isoformat(), _AGORA.isoformat()),
    )
    db.connection.commit()

    disparadas: list[str] = []
    tick(_AGORA, [rotina], db, lambda r: disparadas.append(r.nome))
    assert disparadas == []


def test_tick_ignora_rotina_inativa_ou_sem_agenda():
    db = _db()
    inativa = Rotina(nome="a", descricao="d", agenda="@every 1m", ativa=False)
    sem_agenda = Rotina(nome="b", descricao="d", agenda=None)
    disparadas: list[str] = []
    tick(_AGORA, [inativa, sem_agenda], db, lambda r: disparadas.append(r.nome))
    assert disparadas == []


# ---------------------------------------------------------------------------
# catch_up (boot)
# ---------------------------------------------------------------------------


def test_catch_up_recupera_uma_vez_quando_catch_up_true():
    db = _db()
    rotina = Rotina(nome="ping", descricao="d", agenda="@every 1m", modelo="none", catch_up=True)
    # 3 disparos perdidos
    db.connection.execute(
        "INSERT INTO routine_state (rotina, chave, valor, atualizado_em) VALUES (?,?,?,?)",
        ("ping", "ultimo_run", (_AGORA - timedelta(minutes=3)).isoformat(), _AGORA.isoformat()),
    )
    db.connection.commit()

    disparadas: list[str] = []
    catch_up(_AGORA, [rotina], db, lambda r: disparadas.append(r.nome))
    assert disparadas == ["ping"]  # exatamente 1 recuperação, não enxurrada


def test_catch_up_false_pula_e_marca_em_dia():
    db = _db()
    rotina = Rotina(nome="ping", descricao="d", agenda="@every 1m", modelo="none", catch_up=False)
    db.connection.execute(
        "INSERT INTO routine_state (rotina, chave, valor, atualizado_em) VALUES (?,?,?,?)",
        ("ping", "ultimo_run", (_AGORA - timedelta(minutes=3)).isoformat(), _AGORA.isoformat()),
    )
    db.connection.commit()

    disparadas: list[str] = []
    catch_up(_AGORA, [rotina], db, lambda r: disparadas.append(r.nome))
    assert disparadas == []
    # marcado em dia
    novo = db.connection.execute(
        "SELECT valor FROM routine_state WHERE rotina='ping' AND chave='ultimo_run'"
    ).fetchone()[0]
    assert novo == _AGORA.isoformat()
