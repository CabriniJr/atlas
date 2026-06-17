"""Sincronização do ResourceStore com dados existentes no boot (E0-04).

Popula o store a partir das tabelas legadas (trackers, alarms) e das rotinas
carregadas de TOML. Idempotente — usa ``apply`` (upsert). Roda uma vez no boot.
"""

from __future__ import annotations

import logging
from datetime import datetime

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.db import Database
from atlas.routines import Rotina

_log = logging.getLogger("atlas.sync")


def sincronizar_store(
    db: Database,
    store: ResourceStore,
    rotinas: list[Rotina],
    agora: datetime | None = None,
) -> None:
    """Popula o store com dados existentes. Idempotente."""
    agora = agora or datetime.now()
    _sync_trackers(db, store, agora)
    _sync_alarms(db, store, agora)
    _sync_routines(rotinas, store, agora)
    kinds = store.kinds()
    _log.info("Store sincronizado: %s", ", ".join(f"{k}={len(store.list(k))}" for k in kinds))


def _sync_trackers(db: Database, store: ResourceStore, agora: datetime) -> None:
    rows = db.connection.execute(
        "SELECT nome, dominio, tipo, unidade, sintaxe, agregacao, ativo, criado_em FROM trackers"
    ).fetchall()
    for r in rows:
        res = Resource(
            kind="Tracker",
            name=r["nome"],
            labels={"domain": r["dominio"] or "geral", "active": str(bool(r["ativo"])).lower()},
            spec={
                "unit": r["unidade"] or "",
                "type": r["tipo"] or "number",
                "syntax": r["sintaxe"] or f"{r['nome']}:",
                "aggregation": r["agregacao"] or "last",
                "active": bool(r["ativo"]),
            },
        )
        store.apply(res, agora)


def _sync_alarms(db: Database, store: ResourceStore, agora: datetime) -> None:
    rows = db.connection.execute(
        "SELECT id, horario, mensagem, recorrencia, proximo_disparo, ativo FROM alarms"
    ).fetchall()
    for r in rows:
        mode = "once" if r["recorrencia"] == "uma_vez" else "daily"
        res = Resource(
            kind="Alarm",
            name=f"alarm-{r['id']}",
            labels={"mode": mode, "active": str(bool(r["ativo"])).lower()},
            spec={"time": r["horario"], "mode": mode, "message": r["mensagem"]},
            status={"active": bool(r["ativo"]), "next_fire": r["proximo_disparo"]},
        )
        store.apply(res, agora)


def _sync_routines(rotinas: list[Rotina], store: ResourceStore, agora: datetime) -> None:
    for rot in rotinas:
        res = Resource(
            kind="Routine",
            name=rot.nome,
            labels={"model": rot.modelo, "active": str(rot.ativa).lower()},
            spec={
                "description": rot.descricao,
                "schedule": rot.agenda or "",
                "model": rot.modelo,
                "triggers": rot.triggers,
                "active": rot.ativa,
            },
        )
        store.apply(res, agora)
