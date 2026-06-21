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
from datetime import datetime, timedelta
from pathlib import Path

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.executor import CollectResult, ContextoExecucao
from atlas.ia import invocar
from atlas.rotinas import registrar

_log = logging.getLogger(__name__)

# Modelos
_DEF_DIFF_MODEL = "claude-sonnet-4-6"  # insight por diff
_DEF_CONTEXT_MODEL = "claude-opus-4-8"  # resumo de contexto do projeto
# Política de frescor do contexto
_DEF_CONTEXT_TTL_DAYS = 7
# Tetos de caracteres (altos, perto da janela do modelo; configuráveis por Repo)
_DEF_CORPUS_MAX = 600_000  # corpus enviado ao Opus
_DEF_DIFF_PROMPT_MAX = 120_000  # diff enviado ao insight
_DEF_DIFF_STORE_MAX = 200_000  # diff guardado no Resource Diff

_METADATA_FILES = {
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "composer.json",
}
_DOC_EXTS = {".md", ".mdx", ".rst"}


def _spec_int(repo_res, key: str, default: int) -> int:
    """Lê um inteiro do spec do Repo, com fallback no default."""
    try:
        return int(repo_res.spec.get(key, default))
    except (TypeError, ValueError, AttributeError):
        return default


def _ler_arquivo(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _coletar_contexto(repo_dir: Path, corpus_max: int = _DEF_CORPUS_MAX) -> tuple[str, list[str]]:
    """Monta o corpus de contexto do clone: README + docs/** + metadados.

    Prioriza README e docs/ (metadados por último ao truncar). Devolve
    ``(corpus, arquivos_incluidos)``.
    """
    prioritarios: list[tuple[str, str]] = []
    for p in sorted(repo_dir.glob("README*")):
        if p.is_file():
            prioritarios.append((p.name, _ler_arquivo(p)))
    docs = repo_dir / "docs"
    if docs.is_dir():
        for p in sorted(docs.rglob("*")):
            if p.is_file() and p.suffix.lower() in _DOC_EXTS:
                prioritarios.append((str(p.relative_to(repo_dir)), _ler_arquivo(p)))
    metadados: list[tuple[str, str]] = []
    for p in sorted(repo_dir.iterdir()):
        if p.is_file() and (p.name in _METADATA_FILES or p.suffix == ".csproj"):
            metadados.append((p.name, _ler_arquivo(p)))

    corpus = ""
    arquivos: list[str] = []
    truncado = False
    for rel, conteudo in [*prioritarios, *metadados]:
        bloco = f"\n\n===== {rel} =====\n{conteudo}"
        if corpus and len(corpus) + len(bloco) > corpus_max:
            truncado = True
            break
        corpus += bloco
        arquivos.append(rel)
    if truncado:
        corpus += "\n\n[corpus truncado: excedeu o limite configurado]"
    return corpus.strip(), arquivos


def _gerar_contexto(repo_res, repo_dir: Path, store: ResourceStore, ctx) -> None:
    """Gera (Opus) e represa o resumo de contexto do projeto num Doc. Degrada em falha."""
    label = repo_res.name
    corpus_max = _spec_int(repo_res, "context_corpus_max", _DEF_CORPUS_MAX)
    corpus, arquivos = _coletar_contexto(repo_dir, corpus_max)
    if not corpus:
        return
    modelo = repo_res.spec.get("context_model") or _DEF_CONTEXT_MODEL
    prompt = (
        f"Crie um RESUMO DE CONTEXTO do projeto '{label}' para servir de base a "
        "futuras revisões de código (entender o que muda e sugerir melhorias). "
        "Seja rico e abrangente — sem limite de tamanho. Cubra: propósito, "
        "arquitetura e módulos principais, fluxos importantes, convenções/estilo, "
        "domínio/termos e pontos de atenção. Responda em PT-BR.\n\n"
        f"Documentação e metadados do projeto:\n{corpus}"
    )
    try:
        resumo = invocar(prompt, modelo=modelo, timeout=180)
    except Exception as exc:  # noqa: BLE001 — degrada (ADR-0006)
        _log.warning("contexto/%s: IA indisponível: %s", label, exc)
        return
    store.apply(
        Resource(
            kind="Doc",
            name=f"repo-{label}-contexto",
            labels={"topic": "repo", "repo": label, "tipo": "contexto"},
            spec={"title": f"{label} · contexto do projeto", "body": resumo},
            status={
                "generated_at": ctx.agora.isoformat(),
                "model": modelo,
                "source_files": arquivos,
            },
        ),
        ctx.agora,
    )
    atual = store.get("Repo", label)
    if atual is not None:
        store.apply(
            Resource(
                kind="Repo",
                name=label,
                labels=atual.labels,
                spec=atual.spec,
                status={**atual.status, "last_context_at": ctx.agora.isoformat()},
            ),
            ctx.agora,
        )


def _contexto_obsoleto(label: str, store: ResourceStore, agora: datetime, ttl_days: int) -> bool:
    """True se o Doc de contexto não existe ou é mais antigo que ttl_days."""
    doc = store.get("Doc", f"repo-{label}-contexto")
    if doc is None:
        return True
    ts = doc.status.get("generated_at") if doc.status else None
    if not ts:
        return True
    try:
        gerado = datetime.fromisoformat(ts)
    except ValueError:
        return True
    return agora - gerado > timedelta(days=ttl_days)


def _contexto_atual(label: str, store: ResourceStore) -> str:
    """Body do Doc de contexto (integral, sem truncar) ou string vazia."""
    doc = store.get("Doc", f"repo-{label}-contexto")
    if doc is None:
        return ""
    return str(doc.spec.get("body", ""))


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
        ttl = _spec_int(repo_res, "context_ttl_days", _DEF_CONTEXT_TTL_DAYS)
        if _contexto_obsoleto(label, store, ctx.agora, ttl):
            _gerar_contexto(repo_res, repo_dir, store, ctx)
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
    repo_res = store.get("Repo", label)
    if repo_res is not None:
        _gerar_contexto(repo_res, repo_dir, store, ctx)
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
    repo_res = store.get("Repo", label)
    diff_store_max = (
        _spec_int(repo_res, "diff_store_max", _DEF_DIFF_STORE_MAX)
        if repo_res
        else _DEF_DIFF_STORE_MAX
    )
    diff_prompt_max = (
        _spec_int(repo_res, "diff_prompt_max", _DEF_DIFF_PROMPT_MAX)
        if repo_res
        else _DEF_DIFF_PROMPT_MAX
    )
    diff_store = diff[:diff_store_max]
    diff_prompt = diff[:diff_prompt_max]
    modelo = (repo_res.spec.get("model") if repo_res else None) or _DEF_DIFF_MODEL
    contexto = _contexto_atual(label, store)
    explicacao = _analisar(diff_prompt, label, modelo, contexto)
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
        diff_store + ("…[truncado]" if len(diff) > diff_store_max else ""),
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
