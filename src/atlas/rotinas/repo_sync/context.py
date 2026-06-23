"""Contexto do projeto — corpus (README + docs + metadados) resumido por IA (Opus).

Move o comportamento já existente do repo-sync: gera um ``Doc`` de contexto do
projeto com TTL, usado depois como base das análises de diff. Degrada em falha de
IA (ADR-0006). Nada multi-branch aqui.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore

from ._ia import invocar

_log = logging.getLogger(__name__)

_DEF_CONTEXT_MODEL = "claude-opus-4-8"
_DEF_CONTEXT_TTL_DAYS = 7
_DEF_CORPUS_MAX = 600_000

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
    except (ValueError, TypeError):
        return True
    return agora - gerado > timedelta(days=ttl_days)


def _contexto_atual(label: str, store: ResourceStore) -> str:
    """Body do Doc de contexto (integral, sem truncar) ou string vazia."""
    doc = store.get("Doc", f"repo-{label}-contexto")
    if doc is None:
        return ""
    return str(doc.spec.get("body", ""))
