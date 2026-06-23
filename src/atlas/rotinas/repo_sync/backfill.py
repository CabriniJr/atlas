"""Backfill de repos existentes (ADR-0023 §4, E7-06).

``git fetch --unshallow`` + varredura do histórico completo de todas as branches,
materializando ``Branch``/``Commit`` **leves** retroativos. Idempotente (pula sha
já materializado) e **0 IA por padrão**. Permite reconstruir o progresso de um
repositório que já existia antes desta decisão.
"""

from __future__ import annotations

import logging

from atlas.core.store import ResourceStore

from . import gitcmd, materialize

_log = logging.getLogger(__name__)
_DEF_STALE_DAYS = 30


def backfill(label: str, store: ResourceStore, ctx) -> str:
    """Varre todo o histórico e materializa Branch/Commit leves. Devolve um resumo."""
    repo_res = store.get("Repo", label)
    if repo_res is None:
        return f"❓ backfill/{label}: Repo não configurado."
    repo_dir = gitcmd.data_dir() / "repos" / label
    if not repo_dir.exists():
        return f"❓ backfill/{label}: clone ausente — rode o sync primeiro."

    try:
        gitcmd.fetch_unshallow(repo_dir)
    except Exception as exc:  # noqa: BLE001 — degrada
        _log.warning("backfill/%s: unshallow falhou: %s", label, exc)

    default = repo_res.spec.get("default_branch") or gitcmd.default_branch(repo_dir)
    raw_excl = str(repo_res.spec.get("branches_exclude") or "")
    excl = [g.strip() for g in raw_excl.split(",") if g.strip()]
    stale_days = _spec_int(repo_res, "stale_days", _DEF_STALE_DAYS)

    novos = 0
    branches = 0
    for branch in gitcmd.remote_branches(repo_dir):
        if _excluida(branch, excl):
            continue
        branches += 1
        last_activity = ""
        for sha in gitcmd.new_commits(repo_dir, None, branch):
            meta = gitcmd.commit_meta(repo_dir, sha)
            if materialize.materialize_commit(store, label, branch, meta, ctx):
                novos += 1
            last_activity = meta["date"] or last_activity
        materialize.materialize_branch(
            store, label, branch, repo_dir, default, last_activity, stale_days, ctx
        )
    return (
        f"⏬ backfill/{label}: {branches} branch(es), {novos} commit(s) novos "
        f"materializados (0 IA)."
    )


def _excluida(branch: str, globs: list[str]) -> bool:
    import fnmatch

    return any(fnmatch.fnmatch(branch, g) for g in globs)


def _spec_int(repo_res, key: str, default: int) -> int:
    try:
        return int(repo_res.spec.get(key, default))
    except (TypeError, ValueError, AttributeError):
        return default
