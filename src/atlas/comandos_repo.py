"""Comandos do Repo via chat (ADR-0023 §6) — caminho simples, 0 IA implícita.

Expõe ``/repo backfill <label>`` (varredura idempotente do histórico, E7-06) e
``/repo snapshot <label>`` (serializa a árvore inteira atual → Docs, sob demanda).
Operações complexas (flags, edição fina) vivem no ``atlasctl``/verbos; aqui ficam
só os atalhos do pool de acompanhamento.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from atlas.core.store import ResourceStore
from atlas.db import Database
from atlas.rotinas.repo_sync import gitcmd, serialize
from atlas.rotinas.repo_sync.backfill import backfill

_USAGE = "Usage: /repo backfill|snapshot <label>"


def _csv(val) -> list[str]:
    return [s.strip() for s in str(val or "").split(",") if s.strip()]


def _snapshot(label: str, store: ResourceStore, agora: datetime) -> str:
    """Serializa a árvore atual inteira do repo (sob demanda)."""
    repo_res = store.get("Repo", label)
    if repo_res is None:
        return f"❓ snapshot/{label}: Repo não configurado."
    repo_dir = gitcmd.data_dir() / "repos" / label
    if not repo_dir.exists():
        return f"❓ snapshot/{label}: clone ausente — rode o sync primeiro."
    preset = str(repo_res.spec.get("serialize", "off") or "off")
    if preset == "off":
        return (
            f"⚠️ snapshot/{label}: serialize=off. Defina serialize=docs ou docs+code "
            "na config do Repo primeiro."
        )
    extra = _csv(repo_res.spec.get("serialize_globs"))
    res = serialize.snapshot_tree(
        repo_dir, label, preset, extra, store, SimpleNamespace(agora=agora)
    )
    trunc = " (truncado)" if res.get("truncado") else ""
    return (
        f"📸 snapshot/{label}: {res['serializados']} arquivo(s) serializado(s) de "
        f"{res.get('candidatos', 0)} candidato(s) na árvore (commit {res.get('commit','')}) "
        f"— preset={preset}{trunc}. 0 IA."
    )


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
    if sub == "snapshot":
        if not resto:
            return _USAGE
        return _snapshot(resto[0], store, agora)
    return f"❓ /repo {sub}? {_USAGE}"
