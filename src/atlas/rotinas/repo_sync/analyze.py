"""Fase de análise (IA) sob política — degradada (ADR-0023 §2/§4, E7-05°).

A análise é separada do collect e **barata por padrão**: um gating decide quando a
IA roda (branch, merges, mínimo de linhas) e um **disjuntor** limita o nº de
análises por execução (ADR-0005). Quando passa, monta o ``Diff`` pesado
(``git show``) e chama a IA (Sonnet) com o contexto do projeto represado.

O ponto de chamada da IA está isolado (``_ia.invocar``): quando o Kind ``Agente``
(ADR-0024) existir, basta trocar ``_analisar`` por um despacho ao Agente.
"""

from __future__ import annotations

import logging

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore

from . import gitcmd
from ._ia import invocar

_log = logging.getLogger(__name__)

_DEF_DIFF_MODEL = "claude-sonnet-4-6"
_DEF_DIFF_PROMPT_MAX = 120_000
_DEF_DIFF_STORE_MAX = 200_000


def _spec_int(repo_res, key: str, default: int) -> int:
    try:
        return int(repo_res.spec.get(key, default))
    except (TypeError, ValueError, AttributeError):
        return default


def _spec_str(repo_res, key: str, default: str) -> str:
    v = repo_res.spec.get(key) if repo_res else None
    return str(v) if v else default


def _spec_bool(repo_res, key: str, default: bool) -> bool:
    v = repo_res.spec.get(key) if repo_res else None
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "sim", "yes"}


def deve_analisar(meta: dict, branch: str, default: str, repo_res) -> bool:
    """Gating por política (sem contar o disjuntor, que é controlado por quem chama)."""
    sel = _spec_str(repo_res, "analyze_branches", "default").strip()
    if sel == "all":
        ok_branch = True
    elif sel == "default" or not sel:
        ok_branch = branch == default
    else:
        allow = {b.strip() for b in sel.split(",") if b.strip()}
        ok_branch = branch in allow
    if not ok_branch:
        return False
    if _spec_bool(repo_res, "analyze_skip_merges", True) and meta.get("is_merge"):
        return False
    if meta.get("lines_changed", 0) < _spec_int(repo_res, "analyze_min_lines", 20):
        return False
    return True


def _analisar(diff: str, label: str, modelo: str, contexto: str = "") -> str | None:
    """IA explica o que mudou e sugere — usando o contexto do projeto + o diff."""
    bloco_ctx = f"## Contexto do projeto (resumo represado)\n{contexto}\n\n" if contexto else ""
    prompt = (
        f"Você é um revisor técnico do repositório '{label}'. "
        + bloco_ctx
        + "Analise o diff e responda em PT-BR, em duas seções com bullets:\n\n"
        "## O que mudou\n"
        "- o que mudou e por quê (use o contexto do projeto para inferir)\n"
        "- pontos de atenção ou risco\n\n"
        "## Sugestões\n"
        "- melhorias, testes, refactors, próximos passos acionáveis\n\n"
        f"```diff\n{diff}\n```"
    )
    try:
        return invocar(prompt, modelo=modelo, timeout=90)
    except Exception as exc:  # noqa: BLE001 — degrada (ADR-0006)
        _log.warning("IA indisponível para repo-sync/%s: %s", label, exc)
        return f"_(IA indisponível: {exc})_"


def analisar_commit(
    repo_dir,
    label: str,
    branch: str,
    meta: dict,
    contexto: str,
    repo_res,
    store: ResourceStore,
    ctx,
) -> str | None:
    """Monta o Diff pesado, chama a IA e persiste Diff + Doc. Devolve a explicação."""
    sha = meta["sha"]
    sha7 = meta["sha7"]
    diff = gitcmd.show_diff(repo_dir, sha)
    diff_store_max = _spec_int(repo_res, "diff_store_max", _DEF_DIFF_STORE_MAX)
    diff_prompt_max = _spec_int(repo_res, "diff_prompt_max", _DEF_DIFF_PROMPT_MAX)
    modelo = _spec_str(repo_res, "model", _DEF_DIFF_MODEL)
    diff_store = diff[:diff_store_max]
    explicacao = _analisar(diff[:diff_prompt_max], label, modelo, contexto)
    _salvar_diff(label, sha7, branch, diff_store, explicacao, meta, store, ctx)
    _salvar_doc(label, sha7, meta, diff_store, explicacao, store, ctx)
    return explicacao


def _salvar_diff(
    label: str,
    sha7: str,
    branch: str,
    diff_raw: str,
    explicacao: str | None,
    meta: dict,
    store: ResourceStore,
    ctx,
) -> None:
    store.apply(
        Resource(
            kind="Diff",
            name=f"{label}-{sha7}",
            labels={"repo": label, "branch": branch, "commit": sha7},
            spec={
                "commit": sha7,
                "subject": meta["subject"],
                "author": meta["author"],
                "date": meta["date"],
                "files_changed": meta["files"],
                "insertions": meta["insertions"],
                "deletions": meta["deletions"],
                "files_list": meta["files_list"][:20],
                "diff_raw": diff_raw,
                "explicacao": explicacao or "",
            },
            status={"synced_at": ctx.agora.isoformat()},
        ),
        ctx.agora,
    )


def _salvar_doc(
    label: str,
    sha7: str,
    meta: dict,
    diff_excerpt: str,
    analise: str | None,
    store: ResourceStore,
    ctx,
) -> None:
    titulo = meta.get("subject") or sha7
    arquivos = ", ".join(meta.get("files_list", [])[:15]) or "—"
    body = "\n".join(
        [
            f"# {label} · {titulo}",
            "",
            f"- **commit:** `{sha7}`",
            f"- **autor:** {meta.get('author') or '—'}",
            f"- **data:** {meta.get('date') or '—'}",
            f"- **arquivos:** {meta.get('files', 0)} "
            f"(+{meta.get('insertions', 0)}/-{meta.get('deletions', 0)})",
            f"- **lista:** {arquivos}",
            "",
            "## Análise + sugestões (IA)",
            "",
            analise or "_(sem análise)_",
            "",
            "## Diff",
            "",
            "```diff",
            diff_excerpt,
            "```",
        ]
    )
    store.apply(
        Resource(
            kind="Doc",
            name=f"repo-{label}-{sha7}",
            labels={"topic": "repo", "repo": label, "tipo": "diff"},
            spec={"title": f"{label} · {titulo} ({sha7})", "body": body},
            status={"synced_at": ctx.agora.isoformat(), "commit": sha7},
        ),
        ctx.agora,
    )
