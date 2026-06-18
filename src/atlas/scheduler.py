"""Scheduler de rotinas (E1-06).

Dispara rotinas com ``agenda`` por horário/intervalo e faz **catch-up** dos
disparos perdidos no boot (uma recuperação, não enxurrada — ADR-0006). O estado
do último disparo vive em ``routine_state`` (chave ``ultimo_run``). O disparo em
si é **injetado** (``disparar(rotina)``): em produção, embrulha o
[executor](executor-e-notificacao); aqui o scheduler não conhece o executor.

Gramática de ``agenda``:
- ``@every <n>{s|m|h}`` — intervalo (ex.: ``@every 1m``, ``@every 2h``).
- ``@daily HH:MM`` — diário no horário (hora local).
- ``min hora dia-mês mês dia-semana`` — cron padrão de 5 campos. Cada campo
  aceita ``*``, número, lista ``a,b``, faixa ``a-b`` e passo ``*/n``/``a-b/n``.
  Dia-da-semana usa 0=domingo … 6=sábado (7 também = domingo).
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

    # cron padrão de 5 campos
    if len(agenda.split()) == 5:
        return _proxima_cron(agenda, ultimo, agora)

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


# ---------------------------------------------------------------------------
# Cron (5 campos)
# ---------------------------------------------------------------------------

# limites (lo, hi) de cada campo: minuto, hora, dia-mês, mês, dia-semana
_CRON_LIMITES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]


def _parse_cron_campo(campo: str, lo: int, hi: int) -> set[int] | None:
    """Expande um campo de cron (``*``, ``a``, ``a-b``, ``*/n``, ``a,b``) num set."""
    valores: set[int] = set()
    for parte in campo.split(","):
        parte = parte.strip()
        passo = 1
        if "/" in parte:
            faixa, _, p = parte.partition("/")
            if not p.isdigit() or int(p) == 0:
                return None
            passo = int(p)
            parte = faixa
        if parte == "*":
            inicio, fim = lo, hi
        elif "-" in parte:
            a, _, b = parte.partition("-")
            if not (a.isdigit() and b.isdigit()):
                return None
            inicio, fim = int(a), int(b)
        elif parte.isdigit():
            inicio = fim = int(parte)
        else:
            return None
        if inicio < lo or fim > hi or inicio > fim:
            return None
        valores.update(range(inicio, fim + 1, passo))
    return valores or None


def _parse_cron(expr: str) -> dict | None:
    """Compila uma expressão cron de 5 campos (None se inválida)."""
    campos = expr.split()
    if len(campos) != 5:
        return None
    sets: list[set[int]] = []
    for campo, (lo, hi) in zip(campos, _CRON_LIMITES, strict=True):
        s = _parse_cron_campo(campo, lo, hi)
        if s is None:
            return None
        sets.append(s)
    minuto, hora, dia_mes, mes, dia_sem = sets
    if 7 in dia_sem:  # 7 e 0 são ambos domingo
        dia_sem = (dia_sem - {7}) | {0}
    return {
        "minuto": minuto,
        "hora": hora,
        "dia_mes": dia_mes,
        "mes": mes,
        "dia_sem": dia_sem,
        "dia_mes_star": campos[2].strip() == "*",
        "dia_sem_star": campos[4].strip() == "*",
    }


def _cron_casa(c: dict, t: datetime) -> bool:
    if t.minute not in c["minuto"] or t.hour not in c["hora"] or t.month not in c["mes"]:
        return False
    # cron: 0=domingo; Python weekday(): 0=segunda → converte
    cron_dow = (t.weekday() + 1) % 7
    dia_mes_ok = t.day in c["dia_mes"]
    dia_sem_ok = cron_dow in c["dia_sem"]
    # regra padrão do cron: se ambos restritos, casa com QUALQUER um (OR)
    if c["dia_mes_star"] and c["dia_sem_star"]:
        return True
    if c["dia_mes_star"]:
        return dia_sem_ok
    if c["dia_sem_star"]:
        return dia_mes_ok
    return dia_mes_ok or dia_sem_ok


def _proxima_cron(expr: str, ultimo: datetime | None, agora: datetime) -> datetime | None:
    c = _parse_cron(expr)
    if c is None:
        return None
    base = ultimo if ultimo is not None else agora - timedelta(minutes=1)
    t = base.replace(second=0, microsecond=0) + timedelta(minutes=1)
    fim = t + timedelta(days=367)  # cobre qualquer cron válido (guarda contra loop infinito)
    while t <= fim:
        if _cron_casa(c, t):
            return t
        t += timedelta(minutes=1)
    return None
