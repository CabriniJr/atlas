"""Rotina genérica repo-sync — monitora qualquer repo git (multi-branch, ADR-0023).

Especializa o Kind Repo num **agregado** (Repo + Branch/Commit/Diff ocultos + Doc)
ligado por label ``repo=<label>``. O pull é **multi-branch sem checkout**:
materializa ``Branch``/``Commit`` leves (git-graph offline via ``Commit.parents``),
serializa os arquivos alterados e roda a IA **sob política** (degradada).

Configuração via Repo Resource no store (ver ``api_schema._KIND_SCHEMA["Repo"]``):
    /apply Repo nora spec.url=https://github.com/sys0xFF/nora

Submódulos: ``gitcmd`` (git), ``materialize`` (Branch/Commit/status),
``serialize`` (arquivos→Doc), ``analyze`` (policy+IA+Diff), ``context`` (Doc de
contexto Opus), ``backfill`` (histórico retroativo).
"""

from __future__ import annotations

import logging

from atlas.executor import CollectResult, ContextoExecucao
from atlas.ia import invocar  # seam de IA (patchável nos testes)
from atlas.rotinas import registrar

from . import analyze, context, gitcmd, materialize, serialize
from .analyze import _analisar
from .backfill import backfill
from .context import (
    _coletar_contexto,
    _contexto_atual,
    _contexto_obsoleto,
    _gerar_contexto,
    _spec_int,
)

__all__ = [
    "collect",
    "backfill",
    "invocar",
    "_analisar",
    "_coletar_contexto",
    "_contexto_atual",
    "_contexto_obsoleto",
    "_gerar_contexto",
    "_spec_int",
]

_log = logging.getLogger(__name__)

_DEF_STALE_DAYS = 30
_DEF_MAX_ANALYSES = 5


@registrar("repo-sync")
def collect(ctx: ContextoExecucao) -> CollectResult:
    label: str = getattr(ctx.rotina, "label", None) or ctx.rotina.nome
    store = getattr(ctx, "store", None)

    if store is None:
        return CollectResult(data={"_saida": f"⚠️ repo-sync/{label}: store não disponível."})

    repo_res = store.get("Repo", label)
    if repo_res is None:
        return CollectResult(
            data={
                "_saida": (
                    f"❓ repo-sync/{label}: Repo não configurado.\n"
                    f"Crie com: /apply Repo {label} spec.url=https://github.com/..."
                )
            }
        )

    url = repo_res.spec.get("url", "").strip()
    if not url:
        return CollectResult(
            data={"_saida": f"❓ repo-sync/{label}: spec.url ausente no Repo/{label}."}
        )

    repo_dir = gitcmd.data_dir() / "repos" / label
    try:
        if not repo_dir.exists():
            return _clonar(url, repo_dir, label, store, ctx)
        ttl = context._spec_int(repo_res, "context_ttl_days", context._DEF_CONTEXT_TTL_DAYS)
        if context._contexto_obsoleto(label, store, ctx.agora, ttl):
            context._gerar_contexto(repo_res, repo_dir, store, ctx)
        return _sincronizar(repo_dir, label, store, ctx)
    except Exception as exc:  # noqa: BLE001 — degrada (ADR-0006)
        _log.warning("repo-sync/%s falhou: %s", label, exc)
        return CollectResult(data={"_saida": f"⚠️ repo-sync/{label}: {exc}"})


# ── clone inicial ─────────────────────────────────────────────────────────────


def _clonar(url, repo_dir, label, store, ctx) -> CollectResult:
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    gitcmd.git(["clone", "--depth=100", url, str(repo_dir)])
    repo_res = store.get("Repo", label)
    if repo_res is not None:
        context._gerar_contexto(repo_res, repo_dir, store, ctx)
    # materializa o estado inicial de todas as branches (0 IA no clone)
    try:
        _processar(repo_dir, label, store, ctx, analisar=False)
    except Exception as exc:  # noqa: BLE001
        _log.warning("repo-sync/%s: materialização inicial falhou: %s", label, exc)
    return CollectResult(
        data={
            "_saida": (
                f"📦 {label} · repositório clonado.\n"
                "Próximas execuções reportarão as mudanças por branch."
            )
        }
    )


# ── sync multi-branch ─────────────────────────────────────────────────────────


def _sincronizar(repo_dir, label, store, ctx) -> CollectResult:
    resumo = _processar(repo_dir, label, store, ctx, analisar=True)
    return CollectResult(data={"_saida": _mensagem(label, resumo, ctx)})


def _csv(valor) -> list[str]:
    return [g.strip() for g in str(valor or "").split(",") if g.strip()]


def _excluida(branch: str, globs: list[str]) -> bool:
    import fnmatch

    return any(fnmatch.fnmatch(branch, g) for g in globs)


def _processar(repo_dir, label, store, ctx, *, analisar: bool) -> dict:
    """Fetch + materialização multi-branch. Devolve um resumo para a notificação."""
    repo_res = store.get("Repo", label)
    gitcmd.fetch_all(repo_dir)

    default = repo_res.spec.get("default_branch") or gitcmd.default_branch(repo_dir)
    excl = _csv(repo_res.spec.get("branches_exclude"))
    preset = str(repo_res.spec.get("serialize", "off") or "off")
    extra_globs = _csv(repo_res.spec.get("serialize_globs"))
    stale_days = context._spec_int(repo_res, "stale_days", _DEF_STALE_DAYS)
    max_run = context._spec_int(repo_res, "analyze_max_per_run", _DEF_MAX_ANALYSES)
    budget = max_run if analisar else 0
    contexto = context._contexto_atual(label, store)

    por_branch: list[dict] = []
    total_novos = total_analises = stale_count = 0
    default_meta = None

    for branch in gitcmd.remote_branches(repo_dir):
        if _excluida(branch, excl):
            continue
        br_res = store.get("Branch", materialize.branch_name(label, branch))
        since = br_res.status.get("head") if br_res else None
        novos = gitcmd.new_commits(repo_dir, since, branch)
        last_activity = ""
        last_subject = ""
        for sha in novos:
            meta = gitcmd.commit_meta(repo_dir, sha)
            materialize.materialize_commit(store, label, branch, meta, ctx)
            if preset != "off":
                serialize.serializar_arquivos(
                    repo_dir, label, sha, meta["files_list"], preset, extra_globs, store, ctx
                )
            if budget > 0 and analyze.deve_analisar(meta, branch, default, repo_res):
                analyze.analisar_commit(
                    repo_dir, label, branch, meta, contexto, repo_res, store, ctx
                )
                budget -= 1
                total_analises += 1
            last_activity = meta["date"] or last_activity
            last_subject = meta["subject"] or last_subject
            if branch == default:
                default_meta = meta
        st = materialize.materialize_branch(
            store, label, branch, repo_dir, default, last_activity, stale_days, ctx
        )
        if st.get("stale"):
            stale_count += 1
        if novos:
            por_branch.append(
                {
                    "branch": branch,
                    "novos": len(novos),
                    "head": st["head"],
                    "subject": last_subject,
                    "is_default": branch == default,
                }
            )
            total_novos += len(novos)

    resumo = {
        "por_branch": por_branch,
        "total_novos": total_novos,
        "total_analises": total_analises,
        "default": default,
        "branches_total": sum(
            1 for b in gitcmd.remote_branches(repo_dir) if not _excluida(b, excl)
        ),
        "stale_count": stale_count,
    }
    _atualizar_repo(store, label, default, resumo, default_meta, repo_dir, ctx)
    return resumo


def _atualizar_repo(store, label, default, resumo, default_meta, repo_dir, ctx) -> None:
    status = {
        "default_branch": default,
        "branches_total": resumo["branches_total"],
        "branches_stale": resumo["stale_count"],
        "commits_total": gitcmd.all_commit_count(repo_dir),
        "last_sync": ctx.agora.isoformat(),
        "last_check": ctx.agora.isoformat(),
    }
    if default_meta is not None:
        autor = f" · {default_meta['author']}" if default_meta["author"] else ""
        status.update(
            {
                "last_commit": default_meta["sha7"],
                "last_commit_msg": default_meta["subject"],
                "last_author": default_meta["author"],
                "last_commit_date": default_meta["date"],
                "files_changed": default_meta["files"],
                "insertions": default_meta["insertions"],
                "deletions": default_meta["deletions"],
                "last_activity": default_meta["date"],
                "last_summary": (
                    f"{default_meta['subject'] or '(sem mensagem)'} · "
                    f"{default_meta['files']} arq "
                    f"+{default_meta['insertions']}/-{default_meta['deletions']}{autor}"
                ),
            }
        )
    materialize.update_repo_status(store, label, status, ctx)


def _mensagem(label, resumo, ctx) -> str:
    if resumo["total_novos"] == 0:
        return f"✅ {label} · sem mudanças ({resumo['branches_total']} branch(es))."
    data_str = ctx.agora.strftime("%d/%m %H:%M")
    linhas = [
        f"🔄 {label} · {resumo['total_novos']} commit(s) novos em "
        f"{len(resumo['por_branch'])} branch(es) ({data_str})"
    ]
    for b in resumo["por_branch"]:
        marca = "⭐" if b["is_default"] else "•"
        subj = f" — {b['subject']}" if b["subject"] else ""
        linhas.append(f"{marca} {b['branch']}: +{b['novos']} ({b['head']}){subj}")
    if resumo["total_analises"]:
        linhas.append("")
        linhas.append(f"🧠 {resumo['total_analises']} análise(s) de IA (sob política).")
    if resumo["stale_count"]:
        linhas.append(f"💤 {resumo['stale_count']} branch(es) stale.")
    return "\n".join(linhas)
