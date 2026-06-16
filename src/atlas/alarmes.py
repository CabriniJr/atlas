"""Alarmes / lembretes (E5-07).

Modelo híbrido: o alarme é **dado** (tabela ``alarms``) e o disparo é feito por um
``tick_alarmes`` no loop do app (ao lado do scheduler). Sem IA. Comandos de
gestão (``/alarm``, ``/alarms``) respondem na hora; o disparo notifica o dono no
horário e recalcula o próximo (diário) ou desativa (uma vez).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from atlas.db import Database


def responder_alarmes(texto: str, db: Database, agora: datetime) -> str | None:
    """Route ``/alarm`` / ``/alarms``, or ``None`` if not an alarm command."""
    partes = texto.split()
    if not partes:
        return None
    cmd = partes[0]

    if cmd == "/alarms":
        return _listar(db)

    if cmd == "/alarm":
        if len(partes) == 1:
            return "Usage: /alarm HH:MM <message> [@once] · /alarm <id> remove · /alarms"
        # /alarm <id> remove
        if partes[1].isdigit() and len(partes) >= 3 and partes[2] == "remove":
            return _remover(db, int(partes[1]))
        # /alarm HH:MM <message> [@once]
        return _criar(db, partes, agora)

    return None


def _criar(db: Database, partes: list[str], agora: datetime) -> str:
    hm = _parse_hora(partes[1])
    if hm is None:
        return "⚠️ invalid time. Use HH:MM, e.g. /alarm 23:00 go to sleep"
    resto = partes[2:]
    uma_vez = False
    if resto and resto[-1] == "@once":
        uma_vez = True
        resto = resto[:-1]
    mensagem = " ".join(resto).strip()
    if not mensagem:
        return "Usage: /alarm HH:MM <message> [@once]"

    proximo = _proximo(hm, agora)
    alarme_id = db.insert(
        "alarms",
        horario=partes[1],
        mensagem=mensagem,
        recorrencia="uma_vez" if uma_vez else "diario",
        proximo_disparo=proximo.isoformat(),
        ativo=1,
        criado_em=agora.isoformat(),
    )
    quando = "once" if uma_vez else "daily"
    return f"⏰ alarm #{alarme_id} set for {partes[1]} ({quando})\n   next: {proximo.isoformat()}"


def _listar(db: Database) -> str:
    rows = db.connection.execute(
        "SELECT id, horario, recorrencia, proximo_disparo, mensagem "
        "FROM alarms WHERE ativo = 1 ORDER BY proximo_disparo ASC"
    ).fetchall()
    if not rows:
        return "⏰ No active alarms. Set one: /alarm 23:00 go to sleep"
    linhas = [
        f"#{r['id']} {r['horario']} ({r['recorrencia']}) → {r['mensagem']}"
        f"  · next {r['proximo_disparo']}"
        for r in rows
    ]
    return "⏰ Alarms\n" + "\n".join(linhas) + "\n→ /alarm <id> remove"


def _remover(db: Database, alarme_id: int) -> str:
    cur = db.connection.execute("UPDATE alarms SET ativo = 0 WHERE id = ?", (alarme_id,))
    db.connection.commit()
    if cur.rowcount == 0:
        return f"❓ alarm #{alarme_id} not found. See /alarms"
    return f"🗑 alarm #{alarme_id} removed"


def tick_alarmes(agora: datetime, db: Database, notificar: Callable[[str], None]) -> int:
    """Fire alarms whose time has come. Returns how many fired."""
    vencidos = db.connection.execute(
        "SELECT id, horario, mensagem, recorrencia FROM alarms "
        "WHERE ativo = 1 AND proximo_disparo <= ? ORDER BY proximo_disparo ASC",
        (agora.isoformat(),),
    ).fetchall()
    for a in vencidos:
        notificar(f"⏰ {a['mensagem']}")
        if a["recorrencia"] == "diario":
            prox = _proximo(_parse_hora(a["horario"]), agora)
            db.connection.execute(
                "UPDATE alarms SET proximo_disparo = ? WHERE id = ?",
                (prox.isoformat(), a["id"]),
            )
        else:
            db.connection.execute("UPDATE alarms SET ativo = 0 WHERE id = ?", (a["id"],))
    db.connection.commit()
    return len(vencidos)


# ---------------------------------------------------------------------------


def _parse_hora(texto: str) -> tuple[int, int] | None:
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


def _proximo(hm: tuple[int, int] | None, agora: datetime) -> datetime:
    """Próxima ocorrência futura de HH:MM (hoje, ou amanhã se já passou)."""
    hora, minuto = hm if hm else (0, 0)
    cand = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
    if cand <= agora:
        cand += timedelta(days=1)
    return cand
