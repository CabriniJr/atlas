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
_CAMPOS_EDITAVEIS = {"agenda"}


def responder_controle(
    texto: str,
    db: Database,
    agora: datetime,
    store: object = None,
) -> str | None:
    """Route routine-control commands, or ``None`` if not one of them."""
    partes = texto.split()
    if not partes:
        return None
    cmd = partes[0]

    if cmd in ("/routines", "/rotinas"):
        return _listar(db)
    if cmd in ("/routine", "/rotina"):
        return _detalhe_ou_set(db, partes, agora)
    if cmd == "/run":
        return _run(db, partes, agora, store=store)
    if cmd in ("/activate", "/deactivate", "/ativar", "/desativar"):
        return _toggle(db, partes, ativar=cmd in ("/activate", "/ativar"), agora=agora)
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


def _detalhe_ou_set(db: Database, partes: list[str], agora: datetime) -> str:
    if len(partes) < 2:
        return "Usage: /routine <name> [set <field> <value>]"
    nome = partes[1]
    if len(partes) >= 3 and partes[2] == "set":
        return _set(db, nome, partes[3:], agora)
    return _detalhe(db, nome)


def _detalhe(db: Database, nome: str) -> str:
    rot = _achar(db, nome)
    if rot is None:
        return f"❓ routine '{nome}' not found. See /routines"
    return (
        f"🧩 {rot.nome} [{'on' if rot.ativa else 'off'}]\n"
        f"{rot.descricao}\n"
        f"model: {rot.modelo} · agenda: {rot.agenda or '-'} · gate: {rot.gate or '-'}\n"
        f"triggers: {', '.join(rot.triggers) or '-'}\n"
        f"actions: /run {rot.nome} · /activate {rot.nome} · /deactivate {rot.nome}"
        f" · /routine {rot.nome} set agenda <cron>"
    )


def _set(db: Database, nome: str, args: list[str], agora: datetime) -> str:
    if not args:
        campos = ", ".join(sorted(_CAMPOS_EDITAVEIS))
        return f"⚠️ Usage: /routine {nome} set <field> <value>  (editable: {campos})"

    campo = args[0]
    if campo not in _CAMPOS_EDITAVEIS:
        campos = ", ".join(sorted(_CAMPOS_EDITAVEIS))
        return f"⚠️ unknown field '{campo}'. Editable fields: {campos}"

    valor_partes = args[1:]
    if not valor_partes:
        return f"⚠️ Usage: /routine {nome} set {campo} <value>"

    rot = _achar(db, nome)
    if rot is None:
        return f"❓ routine '{nome}' not found. See /routines"

    valor = " ".join(valor_partes)

    if campo == "agenda":
        if not _cron_valido(valor):
            return f"⚠️ invalid cron expression '{valor}'. Expected 5 fields, e.g. '0 20 * * *'"

    _set_override_str(db, nome, campo, valor, agora)
    return f"✅ {nome}.{campo} = {valor}\n   (applies on next scheduler tick)"


def _cron_valido(expr: str) -> bool:
    partes = expr.strip().split()
    return len(partes) == 5


def _run(db: Database, partes: list[str], agora: datetime, store: object = None) -> str:
    if len(partes) < 2:
        return "Usage: /run <name> [--test]"
    nome = partes[1]

    # /run <nome> --test → harness sem executor completo
    if "--test" in partes[2:]:
        from atlas.harness import inspecionar
        return inspecionar(nome, db=db, store=store, agora=agora)

    rot = _achar(db, nome)
    if rot is None:
        return f"❓ routine '{nome}' not found. See /routines"
    saidas: list[str] = []
    ctx = ContextoExecucao(agora=agora, rotina=rot, origem="manual", store=store)
    res = executar(ctx, db, saidas.append)
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
    """Aplica overrides salvos no DB sobre os defaults do ``routine.toml``."""
    for r in rotinas:
        ov_ativa = _override_str(db, r.nome, _CHAVE_ATIVA)
        if ov_ativa is not None:
            r.ativa = ov_ativa == "true"
        ov_agenda = _override_str(db, r.nome, "agenda")
        if ov_agenda is not None:
            r.agenda = ov_agenda


def _override_str(db: Database, nome: str, chave: str) -> str | None:
    row = db.connection.execute(
        "SELECT valor FROM routine_state WHERE rotina = ? AND chave = ?",
        (nome, chave),
    ).fetchone()
    return row[0] if row and row[0] is not None else None


def _set_override(db: Database, nome: str, ativa: bool, agora: datetime) -> None:
    _set_override_str(db, nome, _CHAVE_ATIVA, "true" if ativa else "false", agora)


def _set_override_str(db: Database, nome: str, chave: str, valor: str, agora: datetime) -> None:
    db.connection.execute(
        "INSERT INTO routine_state (rotina, chave, valor, atualizado_em) VALUES (?,?,?,?) "
        "ON CONFLICT(rotina, chave) DO UPDATE SET valor = excluded.valor, "
        "atualizado_em = excluded.atualizado_em",
        (nome, chave, valor, agora.isoformat()),
    )
    db.connection.commit()
