"""Materialização dos Kinds ocultos Branch/Commit e do Repo.status (ADR-0023 §1).

Tudo é ``Resource`` ligado por label ``repo=<label>``. O ``Commit`` é **leve**
(sem ``diff_raw``); seu ``spec.parents`` reconstrói o git-graph offline. O
``Branch`` carrega ponteiros e métricas (ahead/behind/stale). Nada usa IA.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore

from . import gitcmd


def branch_slug(branch: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", branch).strip("-").lower()


def commit_name(label: str, sha7: str) -> str:
    return f"{label}-{sha7}"


def branch_name(label: str, branch: str) -> str:
    return f"{label}-{branch_slug(branch)}"


def materialize_commit(store: ResourceStore, label: str, branch: str, meta: dict, ctx) -> bool:
    """Cria/atualiza o Commit leve. Devolve False se já existia (idempotência)."""
    name = commit_name(label, meta["sha7"])
    ja_existe = store.get("Commit", name) is not None
    store.apply(
        Resource(
            kind="Commit",
            name=name,
            labels={"repo": label, "branch": branch, "commit": meta["sha7"]},
            spec={
                "sha": meta["sha"],
                "subject": meta["subject"],
                "author": meta["author"],
                "author_email": meta["author_email"],
                "date": meta["date"],
                "parents": meta["parents"],
                "is_merge": meta["is_merge"],
                "files": meta["files"],
                "insertions": meta["insertions"],
                "deletions": meta["deletions"],
                "files_list": meta["files_list"][:50],
            },
            status={"materialized_at": ctx.agora.isoformat()},
        ),
        ctx.agora,
    )
    return not ja_existe


def _parse_date(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def materialize_branch(
    store: ResourceStore,
    label: str,
    branch: str,
    repo_dir,
    default: str,
    last_activity: str,
    stale_days: int,
    ctx,
) -> dict:
    """Atualiza o Branch (head, ahead/behind, contagem, stale). Devolve o status gravado."""
    head = gitcmd.branch_head(repo_dir, branch)
    ahead, behind = gitcmd.ahead_behind(repo_dir, default, branch) if branch != default else (0, 0)
    commits = gitcmd.commit_count(repo_dir, branch)
    stale = _is_stale(last_activity, ctx.agora, stale_days)
    status = {
        "head": head[:7],
        "ahead": ahead,
        "behind": behind,
        "commits": commits,
        "last_activity": last_activity,
        "stale": stale,
        "is_default": branch == default,
        "synced_at": ctx.agora.isoformat(),
    }
    store.apply(
        Resource(
            kind="Branch",
            name=branch_name(label, branch),
            labels={"repo": label, "branch": branch},
            spec={"branch": branch},
            status=status,
        ),
        ctx.agora,
    )
    return status


def _is_stale(last_activity: str, agora: datetime, stale_days: int) -> bool:
    dt = _parse_date(last_activity)
    if dt is None:
        return False
    if dt.tzinfo is not None and agora.tzinfo is None:
        agora = agora.replace(tzinfo=UTC)
    if dt.tzinfo is None and agora.tzinfo is not None:
        dt = dt.replace(tzinfo=UTC)
    return (agora - dt) > timedelta(days=stale_days)


def update_repo_status(store: ResourceStore, label: str, resumo: dict, ctx) -> None:
    """Atualiza o Repo.status com ponteiros + métricas-resumo do pull multi-branch."""
    repo_res = store.get("Repo", label)
    if repo_res is None:
        return
    store.apply(
        Resource(
            kind="Repo",
            name=label,
            labels=repo_res.labels,
            spec=repo_res.spec,
            status={**repo_res.status, **resumo},
        ),
        ctx.agora,
    )
