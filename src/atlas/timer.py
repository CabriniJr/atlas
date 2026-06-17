"""Kind Timer — cronômetro de atividades (E0-04 extensão).

/timer start <name>   — inicia; salva no ResourceStore com state=running
/timer finish <name>  — para; calcula duração, grava em activities
/timer status <name>  — mostra tempo decorrido
/timers               — lista todos os timers ativos
"""

from __future__ import annotations

from datetime import datetime

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.db import Database


def responder_timer(
    texto: str,
    db: Database,
    agora: datetime,
    store: ResourceStore | None = None,
) -> str | None:
    partes = texto.strip().split()
    if not partes:
        return None
    cmd = partes[0]

    if cmd == "/timers":
        return _listar(store, agora) if store else "❓ store não disponível"
    if cmd != "/timer":
        return None

    if len(partes) < 2:
        return "Usage: /timer start|finish|status <name> · /timers"

    sub = partes[1]
    nome = partes[2].lower() if len(partes) >= 3 else ""

    if sub == "start":
        if not nome:
            return "Usage: /timer start <name>"
        return _start(db, store, nome, agora) if store else "❓ store não disponível"
    if sub == "finish":
        if not nome:
            return "Usage: /timer finish <name>"
        return _finish(db, store, nome, agora) if store else "❓ store não disponível"
    if sub == "status":
        if not nome:
            return "Usage: /timer status <name>"
        return _status(store, nome, agora) if store else "❓ store não disponível"
    return f"❓ unknown subcommand '{sub}'. Use start / finish / status"


# ---------------------------------------------------------------------------


def _start(db: Database, store: ResourceStore, nome: str, agora: datetime) -> str:
    existente = store.get("Timer", nome)
    if existente is not None and existente.status.get("state") == "running":
        elapsed = _minutos_decorados(existente.status.get("started_at"), agora)
        return f"⚠️ timer '{nome}' já em andamento ({elapsed}). Use /timer finish {nome}"

    r = Resource(
        kind="Timer",
        name=nome,
        labels={"state": "running"},
        spec={"label": nome},
        status={"state": "running", "started_at": agora.isoformat()},
    )
    store.apply(r, agora)
    return f"⏱ timer '{nome}' started · /timer finish {nome} to stop"


def _finish(db: Database, store: ResourceStore, nome: str, agora: datetime) -> str:
    r = store.get("Timer", nome)
    if r is None or r.status.get("state") != "running":
        return f"❓ timer '{nome}' not found or not running. See /timers"

    started_at_str = r.status.get("started_at", agora.isoformat())
    try:
        started_at = datetime.fromisoformat(started_at_str)
    except ValueError:
        started_at = agora

    duracao = agora - started_at
    minutos = int(duracao.total_seconds() / 60)
    segundos = int(duracao.total_seconds() % 60)
    duracao_str = f"{minutos}min" + (f" {segundos}s" if segundos else "")

    db.insert(
        "activities",
        ts=agora.isoformat(),
        dominio="geral",
        rotina="timer",
        texto_cru=f"{nome} {duracao_str}",
        dados_json={"timer": nome, "duration_min": minutos, "started_at": started_at_str},
    )

    store.set_status("Timer", nome, {
        "state": "done",
        "started_at": started_at_str,
        "finished_at": agora.isoformat(),
        "duration_min": minutos,
    }, agora)

    return f"✅ timer '{nome}' done · {duracao_str}"


def _status(store: ResourceStore, nome: str, agora: datetime) -> str:
    r = store.get("Timer", nome)
    if r is None:
        return f"❓ timer '{nome}' not found. See /timers"
    state = r.status.get("state", "?")
    if state == "running":
        elapsed = _minutos_decorados(r.status.get("started_at"), agora)
        return f"⏱ {nome} · running · elapsed {elapsed}\n→ /timer finish {nome}"
    if state == "done":
        dur = r.status.get("duration_min", "?")
        return f"✅ {nome} · done · {dur}min"
    return f"⏱ {nome} · state={state}"


def _listar(store: ResourceStore, agora: datetime) -> str:
    timers = store.list("Timer", labels={"state": "running"})
    if not timers:
        return "⏱ No active timers. Start one: /timer start <name>"
    linhas = []
    for t in timers:
        elapsed = _minutos_decorados(t.status.get("started_at"), agora)
        linhas.append(f"• {t.name} — running {elapsed}")
    return "⏱ Active timers\n" + "\n".join(linhas) + "\n→ /timer finish <name>"


def _minutos_decorados(started_at: str | None, agora: datetime) -> str:
    if not started_at:
        return "?"
    try:
        inicio = datetime.fromisoformat(started_at)
    except ValueError:
        return "?"
    duracao = agora - inicio
    minutos = int(duracao.total_seconds() / 60)
    return f"{minutos}min"
