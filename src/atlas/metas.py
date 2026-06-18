"""Kind Goal — metas mensuráveis com checkup (E3-04).

/goal set <name> target=<val> unit=<u> [tracker=<name>] [start=<val>] [direction=up|down]
/goals                     — lista todas as metas
/goal status <name>        — detalhe de uma meta
/goal check <name>         — recalcula progresso lendo o último valor do tracker
/goal done <name>          — marca como atingida
"""

from __future__ import annotations

from datetime import datetime

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.db import Database


def responder_metas(
    texto: str,
    db: Database,
    agora: datetime,
    store: ResourceStore | None = None,
) -> str | None:
    partes = texto.strip().split()
    if not partes:
        return None
    cmd = partes[0]

    if cmd == "/goals":
        return _listar(store) if store else "❓ store não disponível"
    if cmd != "/goal":
        return None
    if not store:
        return "❓ store não disponível"

    if len(partes) < 2:
        return (
            "Usage: /goal set <name> target=<val> unit=<u> [tracker=<name>] [direction=up|down]\n"
            "       /goals · /goal status <name> · /goal check <name> · /goal done <name>"
        )

    sub = partes[1]
    if sub == "set":
        return _set(store, partes[2:], agora)
    if sub == "status":
        nome = partes[2] if len(partes) >= 3 else ""
        return _status(store, nome) if nome else "Usage: /goal status <name>"
    if sub == "check":
        nome = partes[2] if len(partes) >= 3 else ""
        return _check(db, store, nome, agora) if nome else "Usage: /goal check <name>"
    if sub == "done":
        nome = partes[2] if len(partes) >= 3 else ""
        return _done(store, nome, agora) if nome else "Usage: /goal done <name>"
    return f"❓ unknown subcommand '{sub}'. Use set/status/check/done"


# ---------------------------------------------------------------------------


def _set(store: ResourceStore, args: list[str], agora: datetime) -> str:
    if not args:
        return "Usage: /goal set <name> target=<val> unit=<u> [tracker=<name>]"
    nome = args[0]
    spec: dict[str, str] = {}
    for tok in args[1:]:
        if "=" in tok:
            k, _, v = tok.partition("=")
            spec[k] = v

    if "target" not in spec:
        return "⚠️ target= required. e.g. /goal set peso target=80 unit=kg tracker=peso"

    existente = store.get("Goal", nome)
    merged_spec = {**(existente.spec if existente else {}), **spec}
    r = Resource(
        kind="Goal",
        name=nome,
        labels={"state": "active"},
        spec=merged_spec,
        status=existente.status if existente else {},
    )
    store.apply(r, agora)
    target = spec.get("target", "?")
    unit = spec.get("unit", "")
    return f"🎯 goal '{nome}' set → target {target}{unit}"


def _listar(store: ResourceStore | None) -> str:
    if store is None:
        return "❓ store não disponível"
    metas = store.list("Goal")
    if not metas:
        return "🎯 No goals yet. Set one: /goal set peso target=80 unit=kg tracker=peso"
    linhas = ["🎯 Goals"]
    for m in metas:
        target = m.spec.get("target", "?")
        unit = m.spec.get("unit", "")
        current = m.status.get("current", "?")
        progress = m.status.get("progress", "—")
        state = m.labels.get("state", "active")
        mark = "✅" if state == "done" else "🎯"
        linhas.append(f"{mark} {m.name}  current={current}{unit} → {target}{unit}  [{progress}]")
    return "\n".join(linhas)


def _status(store: ResourceStore, nome: str) -> str:
    r = store.get("Goal", nome)
    if r is None:
        return f"❓ goal '{nome}' not found. See /goals"
    target = r.spec.get("target", "?")
    unit = r.spec.get("unit", "")
    start = r.spec.get("start", "?")
    current = r.status.get("current", "—")
    progress = r.status.get("progress", "—")
    tracker = r.spec.get("tracker", "—")
    direction = r.spec.get("direction", "down")
    state = r.labels.get("state", "active")
    linhas = [
        f"🎯 Goal: {nome}  [{state}]",
        f"   target:    {target}{unit}  (direction: {direction})",
        f"   start:     {start}{unit}",
        f"   current:   {current}{unit}",
        f"   progress:  {progress}",
        f"   tracker:   {tracker}",
    ]
    if r.criado_em:
        linhas.append(f"   created:   {r.criado_em[:10]}")
    linhas.append(f"→ /goal check {nome} to refresh · /goal done {nome} to close")
    return "\n".join(linhas)


def _check(db: Database, store: ResourceStore, nome: str, agora: datetime) -> str:
    r = store.get("Goal", nome)
    if r is None:
        return f"❓ goal '{nome}' not found. See /goals"

    tracker = r.spec.get("tracker")
    if not tracker:
        return f"⚠️ goal '{nome}' has no tracker linked. /goal set {nome} tracker=<name>"

    row = db.connection.execute(
        "SELECT json_extract(dados_json,'$.valor') AS v "
        "FROM activities WHERE rotina='tracking' "
        "  AND json_extract(dados_json,'$.tracker')=? "
        "ORDER BY id DESC LIMIT 1",
        (tracker,),
    ).fetchone()

    if row is None or row["v"] is None:
        return f"⚠️ no tracker entries for '{tracker}' yet. Log with '{tracker}: <value>'"

    current = float(row["v"])
    target = float(r.spec.get("target", 0))
    start_val = r.spec.get("start")
    direction = r.spec.get("direction", "down")

    progress_str = _calcular_progresso(current, target, start_val, direction)
    unit = r.spec.get("unit", "")

    store.set_status(
        "Goal",
        nome,
        {
            "current": str(current),
            "progress": progress_str,
            "checked_at": agora.isoformat(),
        },
        agora,
    )

    return (
        f"🎯 {nome}\n"
        f"   current: {current}{unit}  target: {target}{unit}\n"
        f"   progress: {progress_str}"
    )


def _done(store: ResourceStore, nome: str, agora: datetime) -> str:
    r = store.get("Goal", nome)
    if r is None:
        return f"❓ goal '{nome}' not found. See /goals"
    updated = Resource(
        kind="Goal",
        name=nome,
        labels={"state": "done"},
        spec=r.spec,
        status={**r.status, "done_at": agora.isoformat()},
    )
    store.apply(updated, agora)
    return f"✅ goal '{nome}' marked done 🎉"


def _calcular_progresso(current: float, target: float, start: str | None, direction: str) -> str:
    if start is None:
        pct = 100.0 if current == target else 0.0
    else:
        try:
            start_f = float(start)
        except ValueError:
            return "?"
        total = abs(target - start_f)
        if total == 0:
            return "100%" if current == target else "0%"
        if direction == "down":
            done = max(0.0, start_f - current)
        else:
            done = max(0.0, current - start_f)
        pct = min(100.0, done / total * 100)
    return f"{pct:.0f}%"
