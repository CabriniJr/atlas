"""Core do Atlas — API de objetos estilo Kubernetes (ADR-0015).

Tudo é ``Resource`` (kind+spec+status); ``ResourceStore`` oferece verbos
uniformes (get/list/apply/patch/delete) para qualquer kind. É o motor central;
Telegram e web são adapters em volta dele.
"""

from __future__ import annotations

from atlas.core.resource import Resource
from atlas.core.store import ResourceJaExiste, ResourceNaoEncontrado, ResourceStore

__all__ = [
    "Resource",
    "ResourceStore",
    "ResourceJaExiste",
    "ResourceNaoEncontrado",
]
