"""Comandos do Repo via chat (ADR-0023 §6) — caminho simples, 0 IA implícita.

Hoje expõe ``/repo backfill <label>``: dispara a varredura idempotente do
histórico (E7-06). Operações complexas (flags, edição fina de política) vivem no
``atlasctl``/verbos; aqui ficam só os atalhos do pool de acompanhamento.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from atlas.core.store import ResourceStore
from atlas.db import Database
from atlas.rotinas.repo_sync.backfill import backfill

_USAGE = "Usage: /repo backfill <label>"


def responder_repo(
    texto: str, db: Database, agora: datetime, store: ResourceStore | None = None
) -> str | None:
    """Trata ``/repo ...``. Devolve None se não casar (segue o roteamento)."""
    if texto != "/repo" and not texto.startswith("/repo "):
        return None
    if store is None:
        return "⚠️ store indisponível para /repo."
    args = texto[len("/repo") :].strip().split()
    if not args:
        return _USAGE
    sub, resto = args[0], args[1:]
    if sub == "backfill":
        if not resto:
            return _USAGE
        return backfill(resto[0], store, SimpleNamespace(agora=agora))
    return f"❓ /repo {sub}? {_USAGE}"
