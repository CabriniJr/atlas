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
# cron padrão: min hora dia-do-mês mês dia-da-semana
# ---------------------------------------------------------------------------


def test_cron_no_horario_vence():
    agora = _AGORA.replace(hour=9, minute=0, second=30)
    assert proxima_execucao("0 9 * * *", None, agora) <= agora


def test_cron_depois_do_horario_proximo_dia():
    agora = _AGORA.replace(hour=10, minute=0)  # 09:00 já passou hoje
    prox = proxima_execucao("0 9 * * *", None, agora)
    assert prox > agora
    assert prox.hour == 9 and prox.minute == 0
    assert prox.day == agora.day + 1


def test_cron_nao_redispara_no_mesmo_slot():
    ultimo = _AGORA.replace(hour=9, minute=0)
    agora = _AGORA.replace(hour=9, minute=30)
    prox = proxima_execucao("0 9 * * *", ultimo, agora)
    assert prox.day == agora.day + 1 and prox.hour == 9


def test_cron_intervalo_passo():
    agora = _AGORA.replace(hour=10, minute=7)
    prox = proxima_execucao("*/15 * * * *", None, agora)
    assert prox.minute == 15 and prox.hour == 10


def test_cron_dia_da_semana_segunda():
    # cron dow 1 = segunda; Python weekday() segunda = 0
    prox = proxima_execucao("0 12 * * 1", None, _AGORA)
    assert prox.weekday() == 0
    assert prox.hour == 12 and prox.minute == 0


def test_cron_lista_de_dias():
    # treino: seg(1), ter(2), qui(4) às 20h → Python weekday {0,1,3}
    prox = proxima_execucao("0 20 * * 1,2,4", None, _AGORA)
    assert prox.weekday() in {0, 1, 3}
    assert prox.hour == 20 and prox.minute == 0


def test_cron_invalido_retorna_none():
    assert proxima_execucao("0 9 * *", None, _AGORA) is None       # 4 campos
    assert proxima_execucao("99 9 * * *", None, _AGORA) is None     # minuto inválido
    assert proxima_execucao("0 25 * * *", None, _AGORA) is None     # hora inválida


def test_tick_dispara_rotina_cron(monkeypatch):
    db = _db()
    agora = _AGORA.replace(hour=21, minute=0, second=5)
    disparadas = []
    rot = Rotina(nome="resumo", descricao="d", agenda="0 21 * * *", ativa=True)
    tick(agora, [rot], db, lambda r: disparadas.append(r.nome) or "ok")
    assert disparadas == ["resumo"]


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
