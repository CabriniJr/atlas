"""Alarmes / lembretes (E5-07 / E0-04).

ResourceStore é a fonte de verdade para leitura (kind="Alarm").
A tabela ``alarms`` permanece para o tick de scheduling.
Toda criação/remoção grava em ambos; o tick atualiza status no store.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.db import Database


def responder_alarmes(
    texto: str,
    db: Database,
    agora: datetime,
    store: ResourceStore | None = None,
) -> str | None:
    """Route ``/alarm`` / ``/alarms``, or ``None`` if not an alarm command."""
    partes = texto.split()
    if not partes:
        return None
    cmd = partes[0]

    if cmd == "/alarms":
        return _listar(db, store)

    if cmd == "/alarm":
        if len(partes) == 1:
            return "Usage: /alarm HH:MM <message> [@once] · /alarm <id> remove · /alarms"
        if partes[1].isdigit() and len(partes) >= 3 and partes[2] == "remove":
            return _remover(db, int(partes[1]), store=store, agora=agora)
        return _criar(db, partes, agora, store=store)

    return None


def _criar(
    db: Database,
    partes: list[str],
    agora: datetime,
    store: ResourceStore | None = None,
) -> str:
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
    if store is not None:
        r = Resource(
            kind="Alarm",
            name=f"alarm-{alarme_id}",
            labels={"mode": "once" if uma_vez else "daily", "active": "true"},
            spec={
                "time": partes[1],
                "mode": "once" if uma_vez else "daily",
                "message": mensagem,
                "active": True,
            },
            status={"active": True, "next_fire": proximo.isoformat(), "fire_count": 0},
        )
        store.apply(r, agora)
    quando = "once" if uma_vez else "daily"
    return f"⏰ alarm #{alarme_id} set for {partes[1]} ({quando})\n   next: {proximo.isoformat()}"


def _listar(db: Database, store: ResourceStore | None) -> str:
    if store is not None:
        recursos = [r for r in store.list("Alarm") if r.spec.get("active", True)]
        if not recursos:
            return "⏰ No active alarms. Set one: /alarm 23:00 go to sleep"
        linhas = []
        for r in recursos:
            modo = r.spec.get("mode", "daily")
            prox = r.status.get("next_fire", "?")
            linhas.append(
                f"{r.name}  {r.spec.get('time', '?')} ({modo}) → {r.spec.get('message', '')}"
                f"  · next {prox[:16]}"
            )
        return "⏰ Alarms\n" + "\n".join(linhas) + "\n→ /alarm <id> remove"

    # fallback
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


def _remover(
    db: Database,
    alarme_id: int,
    store: ResourceStore | None = None,
    agora: datetime | None = None,
) -> str:
    cur = db.connection.execute("UPDATE alarms SET ativo = 0 WHERE id = ?", (alarme_id,))
    db.connection.commit()
    if cur.rowcount == 0:
        return f"❓ alarm #{alarme_id} not found. See /alarms"
    if store is not None and agora is not None:
        name = f"alarm-{alarme_id}"
        r = store.get("Alarm", name)
        if r is not None:
            store.patch("Alarm", name, {"active": False}, agora)
            store.set_status("Alarm", name, {**r.status, "active": False}, agora)
    return f"🗑 alarm #{alarme_id} removed"


def tick_alarmes(
    agora: datetime,
    db: Database,
    notificar: Callable[[str], None],
    store: ResourceStore | None = None,
) -> int:
    """Fire alarms whose time has come. Returns how many fired."""
    vencidos = db.connection.execute(
        "SELECT id, horario, mensagem, recorrencia FROM alarms "
        "WHERE ativo = 1 AND proximo_disparo <= ? ORDER BY proximo_disparo ASC",
        (agora.isoformat(),),
    ).fetchall()
    for a in vencidos:
        notificar(f"⏰ {a['mensagem']}")
        name = f"alarm-{a['id']}"
        if a["recorrencia"] == "diario":
            prox = _proximo(_parse_hora(a["horario"]), agora)
            db.connection.execute(
                "UPDATE alarms SET proximo_disparo = ? WHERE id = ?",
                (prox.isoformat(), a["id"]),
            )
            if store is not None:
                r = store.get("Alarm", name)
                if r is not None:
                    count = r.status.get("fire_count", 0) + 1
                    store.set_status(
                        "Alarm",
                        name,
                        {"active": True, "next_fire": prox.isoformat(), "fire_count": count},
                        agora,
                    )
        else:
            db.connection.execute("UPDATE alarms SET ativo = 0 WHERE id = ?", (a["id"],))
            if store is not None:
                r = store.get("Alarm", name)
                if r is not None:
                    store.patch("Alarm", name, {"active": False}, agora)
                    store.set_status("Alarm", name, {**r.status, "active": False}, agora)
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
