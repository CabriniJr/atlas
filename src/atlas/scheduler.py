"""Scheduler de rotinas (E1-06).

Dispara rotinas com ``agenda`` por horário/intervalo e faz **catch-up** dos
disparos perdidos no boot (uma recuperação, não enxurrada — ADR-0006). O estado
do último disparo vive em ``routine_state`` (chave ``ultimo_run``). O disparo em
si é **injetado** (``disparar(rotina)``): em produção, embrulha o
[executor](executor-e-notificacao); aqui o scheduler não conhece o executor.

Gramática de ``agenda`` (MVP):
- ``@every <n>{s|m|h}`` — intervalo (ex.: ``@every 1m``, ``@every 2h``).
- ``@daily HH:MM`` — diário no horário (hora local).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from atlas.db import Database
from atlas.routines import Rotina

_log = logging.getLogger(__name__)

_UNIDADES = {"s": 1, "m": 60, "h": 3600}
_CHAVE_ULTIMO = "ultimo_run"

Disparar = Callable[[Rotina], object]


def proxima_execucao(agenda: str, ultimo: datetime | None, agora: datetime) -> datetime | None:
    """Quando a rotina deve rodar a seguir (None se a agenda é inválida)."""
    agenda = agenda.strip()

    if agenda.startswith("@every "):
        intervalo = _parse_intervalo(agenda[len("@every ") :])
        if intervalo is None:
            return None
        if ultimo is None:
            return agora  # nunca rodou: vence agora
        return ultimo + intervalo

    if agenda.startswith("@daily "):
        hm = _parse_hora(agenda[len("@daily ") :])
        if hm is None:
            return None
        hora, minuto = hm
        if ultimo is None:
            return agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
        cand = ultimo.replace(hour=hora, minute=minuto, second=0, microsecond=0)
        if cand <= ultimo:
            cand += timedelta(days=1)
        return cand

    return None


def tick(agora: datetime, rotinas: list[Rotina], db: Database, disparar: Disparar) -> list[object]:
    """Dispara as rotinas agendadas cujo próximo horário já venceu."""
    resultados: list[object] = []
    for rotina in rotinas:
        if not rotina.ativa or not rotina.agenda:
            continue
        ultimo = _ler_ultimo(db, rotina.nome)
        prox = proxima_execucao(rotina.agenda, ultimo, agora)
        if prox is None:
            _log.warning("Agenda inválida em '%s': %r", rotina.nome, rotina.agenda)
            continue
        if prox <= agora:
            resultados.append(disparar(rotina))
            _marcar_ultimo(db, rotina.nome, agora)
    return resultados


def catch_up(
    agora: datetime, rotinas: list[Rotina], db: Database, disparar: Disparar
) -> list[object]:
    """No boot: recupera disparos perdidos (1x se ``catch_up``; senão só marca em dia)."""
    resultados: list[object] = []
    for rotina in rotinas:
        if not rotina.ativa or not rotina.agenda:
            continue
        ultimo = _ler_ultimo(db, rotina.nome)
        prox = proxima_execucao(rotina.agenda, ultimo, agora)
        if prox is None or prox > agora:
            continue  # nada perdido
        if rotina.catch_up:
            resultados.append(disparar(rotina))  # uma recuperação, não enxurrada
        _marcar_ultimo(db, rotina.nome, agora)  # marca em dia (recuperou ou pulou)
    return resultados


# ---------------------------------------------------------------------------
# routine_state
# ---------------------------------------------------------------------------


def _ler_ultimo(db: Database, rotina: str) -> datetime | None:
    row = db.connection.execute(
        "SELECT valor FROM routine_state WHERE rotina = ? AND chave = ?",
        (rotina, _CHAVE_ULTIMO),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return datetime.fromisoformat(row[0])


def _marcar_ultimo(db: Database, rotina: str, agora: datetime) -> None:
    db.connection.execute(
        "INSERT INTO routine_state (rotina, chave, valor, atualizado_em) VALUES (?,?,?,?) "
        "ON CONFLICT(rotina, chave) DO UPDATE SET valor = excluded.valor, "
        "atualizado_em = excluded.atualizado_em",
        (rotina, _CHAVE_ULTIMO, agora.isoformat(), agora.isoformat()),
    )
    db.connection.commit()


# ---------------------------------------------------------------------------
# Parsing da agenda
# ---------------------------------------------------------------------------


def _parse_intervalo(texto: str) -> timedelta | None:
    texto = texto.strip()
    if len(texto) < 2 or texto[-1] not in _UNIDADES:
        return None
    try:
        n = int(texto[:-1])
    except ValueError:
        return None
    if n <= 0:
        return None
    return timedelta(seconds=n * _UNIDADES[texto[-1]])


def _parse_hora(texto: str) -> tuple[int, int] | None:
    texto = texto.strip()
    if ":" not in texto:
        return None
    hh, _, mm = texto.partition(":")
    try:
        hora, minuto = int(hh), int(mm)
    except ValueError:
        return None
    if 0 <= hora <= 23 and 0 <= minuto <= 59:
        return hora, minuto
    return None
