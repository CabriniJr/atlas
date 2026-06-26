"""Isolamento por dono (ADR-0027, Fase 5) — políticas puras + migração.

Todo recurso tem dono em ``labels.owner``. A **API** escopa list/get/put/delete
pelo dono da sessão; o ``admin`` enxerga e altera tudo. Recursos marcados
``labels.scope=system`` são **globais** (visíveis a todos, **read-only** para
não-admin). As funções aqui são puras (testáveis) e aplicadas na camada HTTP — os
usos internos do store (sync, rotinas, scheduler) **não** passam por aqui.
"""

from __future__ import annotations

from datetime import datetime

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore

_SYSTEM = "system"


def _labels(resource: Resource) -> dict:
    return resource.labels or {}


def is_system(resource: Resource) -> bool:
    return _labels(resource).get("scope") == _SYSTEM


def can_see(resource: Resource, owner: str, role: str) -> bool:
    """Pode ver o recurso? admin tudo; system a todos; senão só o próprio dono."""
    if role == "admin":
        return True
    if is_system(resource):
        return True
    return _labels(resource).get("owner") == owner


def can_write(existing: Resource | None, owner: str, role: str) -> bool:
    """Pode criar/alterar/apagar? admin tudo; criar novo ok; system read-only; senão só o seu."""
    if role == "admin":
        return True
    if existing is None:
        return True  # criação nova — será estampada com o dono (stamp_owner)
    if is_system(existing):
        return False
    return _labels(existing).get("owner") == owner


def stamp_owner(labels: dict, owner: str, role: str) -> dict:
    """Carimba o dono nos labels de um recurso sendo criado/atualizado.

    Não-admin **sempre** recebe o próprio dono (não pode se passar por outro).
    Admin mantém o ``owner`` informado (ou nenhum — pode criar global/system).
    """
    out = dict(labels or {})
    if role != "admin":
        out["owner"] = owner
    return out


def visible(resources: list[Resource], owner: str, role: str) -> list[Resource]:
    """Filtra uma lista pelo que ``owner``/``role`` pode ver."""
    return [r for r in resources if can_see(r, owner, role)]


def migrate_unowned(store: ResourceStore, owner: str, *, agora: datetime | None = None) -> int:
    """Estampa ``labels.owner=<owner>`` nos recursos sem dono (pula ``scope=system``).

    Idempotente. Devolve quantos foram migrados. Não toca recursos já com dono.
    """
    agora = agora or datetime.now()
    migrados = 0
    for kind in store.kinds():
        for r in store.list(kind):
            labels = _labels(r)
            if labels.get("owner") or labels.get("scope") == _SYSTEM:
                continue
            new_labels = {**labels, "owner": owner}
            store.apply(
                Resource(kind=r.kind, name=r.name, labels=new_labels, spec=r.spec, status=r.status),
                agora,
            )
            migrados += 1
    return migrados
