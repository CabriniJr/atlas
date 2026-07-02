"""Debug session — a diagnostics CLI exposed over Telegram.

Read-only inspection of the engine's state: system status, recent runs, loaded
routines, table counts and (non-secret) env. Full container rebuilds still stay
host-side in ``scripts/atlasctl.sh``. A local (non-containerized, systemd
--user) restart of *this* process is available to the modo=code agent via
``POST /_self_restart`` (admin-only, ADR-0044) — it self-updates after
committing new code, no human needed to run ``systemctl`` by hand.

Owner-only (the handler already filters by user id).
"""

from __future__ import annotations

import os
import platform
import sys
import time
from datetime import datetime
from pathlib import Path

from atlas.db import Database
from atlas.routines import carregar_rotinas

# Marca aproximada de início do processo (import no boot).
_INICIO = time.time()

_TABELAS = [
    "activities",
    "ideas",
    "alarms",
    "trackers",
    "goals",
    "goal_links",
    "books",
    "runs",
    "routine_state",
]


def responder_debug(texto: str, db: Database, agora: datetime) -> str | None:
    """Route ``/debug`` subcommands. Returns the reply, or ``None`` if not /debug."""
    partes = texto.split()
    if not partes or partes[0] != "/debug":
        return None
    sub = partes[1] if len(partes) > 1 else "status"

    if sub in ("help", "-h", "?"):
        return _help()
    if sub == "status":
        return _status(db, agora)
    if sub == "runs":
        n = int(partes[2]) if len(partes) > 2 and partes[2].isdigit() else 5
        return _runs(db, n)
    if sub == "routines":
        return _routines()
    if sub == "db":
        return _db_counts(db)
    if sub == "env":
        return _env()
    return f"❓ unknown: /debug {sub}\n{_help()}"


def _help() -> str:
    return (
        "🔧 /debug — diagnostics\n"
        "  /debug status     system overview (default)\n"
        "  /debug runs [n]   last n runs (default 5)\n"
        "  /debug routines   loaded routines\n"
        "  /debug db         table row counts\n"
        "  /debug env        runtime config (no secrets)\n\n"
        "Lifecycle (host-side): scripts/atlasctl.sh atualizar|restart|logs|status"
    )


def _status(db: Database, agora: datetime) -> str:
    res = carregar_rotinas(Path(os.environ.get("ATLAS_ROUTINES_DIR", "routines")))
    ult = db.connection.execute(
        "SELECT rotina, status, camada, iniciado_em FROM runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    ult_txt = (
        f"{ult['rotina']} {ult['status']}/{ult['camada']} @ {ult['iniciado_em']}" if ult else "—"
    )
    abertas = db.connection.execute(
        "SELECT COUNT(*) FROM ideas WHERE estado NOT IN ('descartada','arquivada')"
    ).fetchone()[0]
    return (
        "🩺 Atlas — status\n"
        f"uptime: {_uptime()}\n"
        f"python: {sys.version.split()[0]} · {platform.system().lower()}\n"
        f"routines: {len(res.ativas)} active / {len(res.rotinas)} loaded"
        + (f" · {len(res.erros)} errors" if res.erros else "")
        + "\n"
        f"pool: {abertas} open\n"
        f"runs: {_count(db, 'runs')} total · last: {ult_txt}"
    )


def _runs(db: Database, n: int) -> str:
    linhas = db.connection.execute(
        "SELECT id, rotina, status, camada, iniciado_em FROM runs ORDER BY id DESC LIMIT ?",
        (n,),
    ).fetchall()
    if not linhas:
        return "no runs yet."
    corpo = "\n".join(
        f"#{r['id']} {r['rotina']} {r['status']}/{r['camada']} @ {r['iniciado_em']}" for r in linhas
    )
    return f"🏃 last {len(linhas)} runs\n{corpo}"


def _routines() -> str:
    res = carregar_rotinas(Path(os.environ.get("ATLAS_ROUTINES_DIR", "routines")))
    if not res.rotinas and not res.erros:
        return "no routines loaded."
    linhas = [
        f"• {r.nome} [{'on' if r.ativa else 'off'}] model={r.modelo} agenda={r.agenda or '-'}"
        for r in res.rotinas
    ]
    if res.erros:
        linhas += [f"⚠️ {e.pasta}: {e.mensagem}" for e in res.erros]
    return "🧩 routines\n" + "\n".join(linhas)


def _db_counts(db: Database) -> str:
    linhas = [f"{t}: {_count(db, t)}" for t in _TABELAS]
    return "🗄 db rows\n" + "\n".join(linhas)


def _env() -> str:
    return (
        "⚙️ runtime (no secrets)\n"
        f"db_path: {os.environ.get('ATLAS_DB_PATH', 'atlas.sqlite')}\n"
        f"routines_dir: {os.environ.get('ATLAS_ROUTINES_DIR', 'routines')}\n"
        f"allowed_user_id set: {bool(os.environ.get('ATLAS_ALLOWED_USER_ID'))}\n"
        f"token set: {bool(os.environ.get('TELEGRAM_TOKEN'))}"
    )


def _count(db: Database, tabela: str) -> int:
    return db.connection.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]


def _uptime() -> str:
    s = int(time.time() - _INICIO)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h}h{m:02d}m{s:02d}s"
