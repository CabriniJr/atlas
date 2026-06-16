"""Routine control over chat (E5-02).

List, inspect, run and toggle routines from Telegram. Read commands re-load
``routines/`` on demand; ``/run`` executes via the [executor] and returns its
output as the reply.

Activation toggle: in our container model the code/routines are baked into the
image, so editing ``routine.toml`` at runtime would be lost on the next rebuild.
Instead the active flag is stored as an **override in the DB** (``routine_state``,
key ``ativa``) — it lives in the data volume and survives rebuilds. Listing and
``/run`` honor it immediately; the scheduler picks it up on the next restart
(apply via :func:`aplicar_overrides` at boot).
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from atlas.db import Database
from atlas.executor import ContextoExecucao, executar
from atlas.routines import Rotina, carregar_rotinas

_CHAVE_ATIVA = "ativa"


def responder_controle(texto: str, db: Database, agora: datetime) -> str | None:
    """Route routine-control commands, or ``None`` if not one of them."""
    partes = texto.split()
    if not partes:
        return None
    cmd = partes[0]

    if cmd == "/routines":
        return _listar(db)
    if cmd == "/routine":
        return _detalhe(db, partes)
    if cmd == "/run":
        return _run(db, partes, agora)
    if cmd in ("/activate", "/deactivate"):
        return _toggle(db, partes, ativar=cmd == "/activate", agora=agora)
    return None


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------


def _listar(db: Database) -> str:
    rotinas = _carregar(db)
    if not rotinas:
        return "🧩 No routines found in routines/."
    linhas = [
        f"• {r.nome} [{'on' if r.ativa else 'off'}] model={r.modelo} agenda={r.agenda or '-'}"
        for r in rotinas
    ]
    return "🧩 Routines\n" + "\n".join(linhas) + "\n→ /routine <name> · /run <name>"


def _detalhe(db: Database, partes: list[str]) -> str:
    if len(partes) < 2:
        return "Usage: /routine <name>"
    rot = _achar(db, partes[1])
    if rot is None:
        return f"❓ routine '{partes[1]}' not found. See /routines"
    return (
        f"🧩 {rot.nome} [{'on' if rot.ativa else 'off'}]\n"
        f"{rot.descricao}\n"
        f"model: {rot.modelo} · agenda: {rot.agenda or '-'} · gate: {rot.gate or '-'}\n"
        f"triggers: {', '.join(rot.triggers) or '-'}\n"
        f"actions: /run {rot.nome} · /activate {rot.nome} · /deactivate {rot.nome}"
    )


def _run(db: Database, partes: list[str], agora: datetime) -> str:
    if len(partes) < 2:
        return "Usage: /run <name>"
    rot = _achar(db, partes[1])
    if rot is None:
        return f"❓ routine '{partes[1]}' not found. See /routines"
    saidas: list[str] = []
    res = executar(ContextoExecucao(agora=agora, rotina=rot, origem="manual"), db, saidas.append)
    corpo = "\n".join(saidas) if saidas else f"run {res.status} (layer {res.camada})"
    return f"▶️ {rot.nome}\n{corpo}"


def _toggle(db: Database, partes: list[str], *, ativar: bool, agora: datetime) -> str:
    if len(partes) < 2:
        return f"Usage: {'/activate' if ativar else '/deactivate'} <name>"
    rot = _achar(db, partes[1])
    if rot is None:
        return f"❓ routine '{partes[1]}' not found. See /routines"
    _set_override(db, rot.nome, ativar, agora)
    estado = "activated" if ativar else "deactivated"
    return f"✅ {rot.nome} {estado}.\n(scheduling applies on next restart)"


# ---------------------------------------------------------------------------
# Carga + overrides de ativação (persistidos no DB)
# ---------------------------------------------------------------------------


def _carregar(db: Database) -> list[Rotina]:
    res = carregar_rotinas(Path(os.environ.get("ATLAS_ROUTINES_DIR", "routines")))
    aplicar_overrides(db, res.rotinas)
    return res.rotinas


def _achar(db: Database, nome: str) -> Rotina | None:
    for r in _carregar(db):
        if r.nome == nome:
            return r
    return None


def aplicar_overrides(db: Database, rotinas: list[Rotina]) -> None:
    """Aplica o estado de ativação salvo no DB sobre o default do ``routine.toml``."""
    for r in rotinas:
        ov = _override(db, r.nome)
        if ov is not None:
            r.ativa = ov


def _override(db: Database, nome: str) -> bool | None:
    row = db.connection.execute(
        "SELECT valor FROM routine_state WHERE rotina = ? AND chave = ?",
        (nome, _CHAVE_ATIVA),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return row[0] == "true"


def _set_override(db: Database, nome: str, ativa: bool, agora: datetime) -> None:
    db.connection.execute(
        "INSERT INTO routine_state (rotina, chave, valor, atualizado_em) VALUES (?,?,?,?) "
        "ON CONFLICT(rotina, chave) DO UPDATE SET valor = excluded.valor, "
        "atualizado_em = excluded.atualizado_em",
        (nome, _CHAVE_ATIVA, "true" if ativa else "false", agora.isoformat()),
    )
    db.connection.commit()
