"""Rotina genérica repo-sync — monitora qualquer repo git e persiste diffs.

Configuração via dois recursos no store:

  1. **Repo/<label>** — criado pelo usuário com a URL do repositório:
       /apply Repo nora spec.url=https://github.com/sys0xFF/nora

  2. **Diff/<label>-<sha7>** — criado automaticamente a cada sync com mudanças;
     guarda diff_raw, explicação Haiku e status do sync.

Routine TOML mínimo:
    nome     = "nora-sync"
    label    = "nora"          # corresponde ao nome do Repo Resource
    coletar  = "repo-sync"
    agenda   = "0 9 * * *"
    modelo   = "none"
    saida    = "telegram"
    ativa    = false
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.executor import CollectResult, ContextoExecucao
from atlas.ia import invocar
from atlas.rotinas import registrar

_log = logging.getLogger(__name__)

_HAIKU = "claude-haiku-4-5-20251001"
_MAX_DIFF_PROMPT = 5000  # chars enviados ao Haiku
_MAX_DIFF_STORE = 8000  # chars gravados no Diff Resource


def _data_dir() -> Path:
    db = os.environ.get("ATLAS_DB_PATH", "atlas.sqlite")
    return Path(db).resolve().parent


def _git(args: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git {args[0]} code={proc.returncode}")
    return proc.stdout


# ── extração de metadados ──────────────────────────────────────────────────────


def _parse_diff_stat(diff: str) -> dict:
    """Extrai arquivos/insercoes/delecoes do summary do ``git diff --stat``."""
    files = ins = dels = 0
    m = re.search(r"(\d+) files? changed", diff)
    if m:
        files = int(m.group(1))
    m = re.search(r"(\d+) insertions?\(\+\)", diff)
    if m:
        ins = int(m.group(1))
    m = re.search(r"(\d+) deletions?\(-\)", diff)
    if m:
        dels = int(m.group(1))
    files_list = re.findall(r"^diff --git a/(.+?) b/", diff, re.MULTILINE)
    return {"files": files, "insertions": ins, "deletions": dels, "files_list": files_list[:20]}


def _commit_meta(repo_dir: Path, sha: str) -> dict:
    """Mensagem, autor e data do commit (best-effort; campos vazios se falhar)."""
    try:
        out = _git(["log", "-1", "--format=%s%n%an%n%ae%n%cI%n%cr", sha], cwd=repo_dir)
    except Exception as exc:  # noqa: BLE001
        _log.debug("git log falhou para %s: %s", sha, exc)
        out = ""
    p = out.split("\n")

    def g(i: int) -> str:
        return p[i].strip() if len(p) > i else ""

    return {
        "subject": g(0),
        "author": g(1),
        "author_email": g(2),
        "date": g(3),
        "date_rel": g(4),
    }


@registrar("repo-sync")
def collect(ctx: ContextoExecucao) -> CollectResult:
    label: str = getattr(ctx.rotina, "label", None) or ctx.rotina.nome
    store: ResourceStore | None = getattr(ctx, "store", None)

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

    repo_dir = _data_dir() / "repos" / label
    try:
        if not repo_dir.exists():
            return _clonar(url, repo_dir, label, store, ctx)
        return _sincronizar(url, repo_dir, label, store, ctx)
    except Exception as exc:  # noqa: BLE001
        _log.warning("repo-sync/%s falhou: %s", label, exc)
        return CollectResult(data={"_saida": f"⚠️ repo-sync/{label}: {exc}"})


# ── clone inicial ─────────────────────────────────────────────────────────────


def _clonar(
    url: str, repo_dir: Path, label: str, store: ResourceStore, ctx: ContextoExecucao
) -> CollectResult:
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    _git(["clone", "--depth=100", url, str(repo_dir)])
    sha = _git(["rev-parse", "HEAD"], cwd=repo_dir).strip()
    meta = _commit_meta(repo_dir, sha)
    _atualizar_repo_status(label, sha[:7], meta, _STAT_ZERO, store, ctx)
    desc = f" — {meta['subject']}" if meta["subject"] else ""
    return CollectResult(
        data={
            "_saida": (
                f"📦 {label} · repositório clonado (commit {sha[:7]}){desc}.\n"
                "Próximas execuções reportarão as mudanças."
            )
        }
    )


# ── pull + diff ───────────────────────────────────────────────────────────────

_STAT_ZERO = {"files": 0, "insertions": 0, "deletions": 0, "files_list": []}


def _sincronizar(
    url: str, repo_dir: Path, label: str, store: ResourceStore, ctx: ContextoExecucao
) -> CollectResult:
    old_sha = _git(["rev-parse", "HEAD"], cwd=repo_dir).strip()
    _git(["fetch", "--depth=100", "origin"], cwd=repo_dir)
    diff = _git(["diff", "HEAD..origin/HEAD", "--stat", "-p"], cwd=repo_dir)

    if not diff.strip():
        meta = _commit_meta(repo_dir, old_sha)
        _marcar_check(label, old_sha[:7], meta, store, ctx)
        return CollectResult(data={"_saida": f"✅ {label} · sem mudanças (HEAD {old_sha[:7]})."})

    _git(["merge", "--ff-only", "origin/HEAD"], cwd=repo_dir)
    sha = _git(["rev-parse", "HEAD"], cwd=repo_dir).strip()
    meta = _commit_meta(repo_dir, sha)
    stat = _parse_diff_stat(diff)
    return _reportar(diff, sha, meta, stat, label, store, ctx)


# ── persistência e notificação ────────────────────────────────────────────────


def _reportar(
    diff: str,
    sha: str,
    meta: dict,
    stat: dict,
    label: str,
    store: ResourceStore,
    ctx: ContextoExecucao,
) -> CollectResult:
    sha7 = sha[:7]
    diff_store = diff[:_MAX_DIFF_STORE]
    diff_prompt = diff[:_MAX_DIFF_PROMPT]

    repo_res = store.get("Repo", label)
    modelo = (repo_res.spec.get("model") if repo_res else None) or _HAIKU
    explicacao = _analisar(diff_prompt, label, modelo)
    _salvar_diff(label, sha7, diff_store, explicacao, meta, stat, store, ctx)
    _salvar_doc(label, sha7, meta, stat, diff_store, explicacao, store, ctx)
    _atualizar_repo_status(label, sha7, meta, stat, store, ctx)

    data_str = ctx.agora.strftime("%d/%m %H:%M")
    linhas = [f"🔄 {label} · nova atualização ({data_str})"]
    if meta["subject"]:
        linhas.append(f"📝 {meta['subject']} ({sha7})")
    else:
        linhas.append(f"commit {sha7}")
    autor = f"👤 {meta['author']} · " if meta["author"] else ""
    linhas.append(f"{autor}🗂 {stat['files']} arq · +{stat['insertions']}/-{stat['deletions']}")
    if stat["files_list"]:
        mostra = stat["files_list"][:6]
        extra = "…" if len(stat["files_list"]) > 6 else ""
        linhas.append("   " + ", ".join(mostra) + extra)
    linhas += [
        "",
        "```diff",
        diff_store + ("…[truncado]" if len(diff) > _MAX_DIFF_STORE else ""),
        "```",
    ]
    if explicacao:
        linhas += ["", "🧠 Análise + sugestões da IA:", "", explicacao]
        linhas += ["", f"📄 arquivado em Doc/repo-{label}-{sha7}"]

    return CollectResult(data={"_saida": "\n".join(linhas)})


def _salvar_diff(
    label: str,
    sha7: str,
    diff_raw: str,
    explicacao: str | None,
    meta: dict,
    stat: dict,
    store: ResourceStore,
    ctx: ContextoExecucao,
) -> None:
    name = f"{label}-{sha7}"
    res = Resource(
        kind="Diff",
        name=name,
        labels={"repo": label},
        spec={
            "commit": sha7,
            "subject": meta["subject"],
            "author": meta["author"],
            "date": meta["date"],
            "files_changed": stat["files"],
            "insertions": stat["insertions"],
            "deletions": stat["deletions"],
            "files_list": stat["files_list"],
            "diff_raw": diff_raw,
            "explicacao": explicacao or "",
        },
        status={"synced_at": ctx.agora.isoformat()},
    )
    store.apply(res, ctx.agora)


def _atualizar_repo_status(
    label: str, sha7: str, meta: dict, stat: dict, store: ResourceStore, ctx: ContextoExecucao
) -> None:
    repo_res = store.get("Repo", label)
    if repo_res is None:
        return
    resumo = meta["subject"] or "(sem mensagem)"
    autor = f" · {meta['author']}" if meta["author"] else ""
    updated = Resource(
        kind="Repo",
        name=label,
        labels=repo_res.labels,
        spec=repo_res.spec,
        status={
            **repo_res.status,
            "last_commit": sha7,
            "last_commit_msg": meta["subject"],
            "last_author": meta["author"],
            "last_commit_date": meta["date"],
            "last_sync": ctx.agora.isoformat(),
            "last_check": ctx.agora.isoformat(),
            "files_changed": stat["files"],
            "insertions": stat["insertions"],
            "deletions": stat["deletions"],
            "last_summary": (
                f"{resumo} · {stat['files']} arq +{stat['insertions']}/-{stat['deletions']}{autor}"
            ),
        },
    )
    store.apply(updated, ctx.agora)


def _marcar_check(
    label: str, sha7: str, meta: dict, store: ResourceStore, ctx: ContextoExecucao
) -> None:
    """Sem mudanças: registra a verificação e mantém os metadados do HEAD atual."""
    repo_res = store.get("Repo", label)
    if repo_res is None:
        return
    novo = {
        "last_check": ctx.agora.isoformat(),
        "last_commit": sha7,
    }
    # mantém os metadados do HEAD sempre frescos (mesmo sem novo diff)
    if meta.get("subject"):
        novo["last_commit_msg"] = meta["subject"]
    if meta.get("author"):
        novo["last_author"] = meta["author"]
    if meta.get("date"):
        novo["last_commit_date"] = meta["date"]
    updated = Resource(
        kind="Repo",
        name=label,
        labels=repo_res.labels,
        spec=repo_res.spec,
        status={**repo_res.status, **novo},
    )
    store.apply(updated, ctx.agora)


def _analisar(diff: str, label: str, modelo: str) -> str | None:
    """IA avalia as mudanças e sugere o que dá para propor (insights acionáveis)."""
    prompt = (
        f"Você é um revisor técnico do repositório '{label}'. Analise o diff e "
        "responda em PT-BR, conciso (máximo 220 palavras), em duas seções com bullets:\n\n"
        "## O que mudou\n"
        "- o que mudou e por quê (infira do contexto)\n"
        "- pontos de atenção ou risco\n\n"
        "## Sugestões\n"
        "- o que eu poderia sugerir/propor (melhorias, testes, refactors, próximos passos)\n\n"
        f"```diff\n{diff}\n```"
    )
    try:
        return invocar(prompt, modelo=modelo, timeout=90)
    except Exception as exc:  # noqa: BLE001
        _log.warning("IA indisponível para repo-sync/%s: %s", label, exc)
        return f"_(IA indisponível: {exc})_"


def _salvar_doc(
    label: str,
    sha7: str,
    meta: dict,
    stat: dict,
    diff_excerpt: str,
    analise: str | None,
    store: ResourceStore,
    ctx: ContextoExecucao,
) -> None:
    """Arquiva a atualização como Doc (histórico represado), rotulado p/ hierarquia."""
    titulo = meta.get("subject") or sha7
    arquivos = ", ".join(stat.get("files_list", [])[:15]) or "—"
    body = "\n".join(
        [
            f"# {label} · {titulo}",
            "",
            f"- **commit:** `{sha7}`",
            f"- **autor:** {meta.get('author') or '—'}",
            f"- **data:** {meta.get('date') or '—'}",
            f"- **arquivos:** {stat.get('files', 0)} "
            f"(+{stat.get('insertions', 0)}/-{stat.get('deletions', 0)})",
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
    res = Resource(
        kind="Doc",
        name=f"repo-{label}-{sha7}",
        labels={"topic": "repo", "repo": label, "tipo": "diff"},
        spec={"title": f"{label} · {titulo} ({sha7})", "body": body},
        status={"synced_at": ctx.agora.isoformat(), "commit": sha7},
    )
    store.apply(res, ctx.agora)
