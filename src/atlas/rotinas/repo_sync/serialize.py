"""Serialização incremental dos arquivos alterados → Doc (ADR-0023 §3, E7-04).

Atua só sobre os arquivos que mudaram num pull. Extrai **texto** de cada um por um
registry por extensão (script-primeiro, sem dependência nova obrigatória):

- texto/código: decodifica direto;
- office OOXML/ODF (.docx/.pptx/.odt): ``zipfile`` + ``xml`` da stdlib;
- PDF: ``pdftotext`` (poppler) se disponível — degrada se ausente;
- binário compilado: nunca (sem valor textual).

Cada arquivo vira um ``Doc/repo-<label>-file-<slug>`` chaveado por path (atualiza
in-place). O conteúdo é lido **no commit** via ``git show`` (sem checkout).
"""

from __future__ import annotations

import io
import logging
import re
import subprocess
import zipfile
from xml.etree import ElementTree as ET

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore

from . import gitcmd

_log = logging.getLogger(__name__)

# Presets de extensão (minúsculas, com ponto).
_TEXT_EXTS = {".md", ".mdx", ".rst", ".txt", ".adoc", ".tex", ".csv"}
_CODE_EXTS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".c", ".h", ".cpp", ".hpp", ".cc",
    ".go", ".rs", ".java", ".kt", ".rb", ".php", ".cs", ".swift", ".scala",
    ".sh", ".sql", ".html", ".css", ".scss", ".vue", ".toml", ".yaml", ".yml",
    ".json", ".xml",
}
_OFFICE_EXTS = {".docx", ".pptx", ".odt"}
_PDF_EXTS = {".pdf"}

_PRESETS: dict[str, set[str]] = {
    "off": set(),
    "docs": _TEXT_EXTS | _OFFICE_EXTS | _PDF_EXTS,
    "docs+code": _TEXT_EXTS | _OFFICE_EXTS | _PDF_EXTS | _CODE_EXTS,
}


def _ext(path: str) -> str:
    i = path.rfind(".")
    return path[i:].lower() if i >= 0 else ""


def _glob_match(path: str, globs: list[str]) -> bool:
    import fnmatch

    nome = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(path, g) or fnmatch.fnmatch(nome, g) for g in globs)


def should_serialize(path: str, preset: str, extra_globs: list[str] | None = None) -> bool:
    """True se ``path`` casa o preset de serialização (ou um glob extra)."""
    extra_globs = extra_globs or []
    if _glob_match(path, extra_globs):
        return True
    return _ext(path) in _PRESETS.get(preset, set())


# ── extratores ─────────────────────────────────────────────────────────────────


def _extrair_texto(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _xml_texts(zf: zipfile.ZipFile, membros: list[str], localname: str | None) -> list[str]:
    out: list[str] = []
    for m in membros:
        try:
            raw = zf.read(m)
        except KeyError:
            continue
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            continue
        for el in root.iter():
            tag = el.tag.rsplit("}", 1)[-1]
            if localname is None or tag == localname:
                if el.text and el.text.strip():
                    out.append(el.text)
    return out


def _extrair_office(data: bytes, ext: str) -> str | None:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError):
        return None
    nomes = zf.namelist()
    if ext == ".docx":
        membros = [n for n in nomes if n == "word/document.xml" or n.startswith("word/header")]
        partes = _xml_texts(zf, membros or ["word/document.xml"], "t")
    elif ext == ".pptx":
        membros = sorted(n for n in nomes if re.match(r"ppt/slides/slide\d+\.xml", n))
        partes = _xml_texts(zf, membros, "t")
    elif ext == ".odt":
        partes = _xml_texts(zf, ["content.xml"], None)
    else:
        return None
    texto = " ".join(p.strip() for p in partes if p.strip())
    return texto or None


def _extrair_pdf(data: bytes) -> str | None:
    try:
        proc = subprocess.run(
            ["pdftotext", "-", "-"],
            input=data,
            capture_output=True,
            timeout=60,
        )
    except (FileNotFoundError, OSError):
        return None  # pdftotext ausente → degrada
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", errors="replace").strip() or None


def extrair(data: bytes, path: str) -> str | None:
    """Roteia o conteúdo bruto para o extrator certo conforme a extensão."""
    ext = _ext(path)
    if ext in _OFFICE_EXTS:
        return _extrair_office(data, ext)
    if ext in _PDF_EXTS:
        return _extrair_pdf(data)
    return _extrair_texto(data)


# ── persistência ───────────────────────────────────────────────────────────────


def _slug(path: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", path).strip("-").lower()


def _serializar_um(
    repo_dir, label: str, sha: str, path: str,
    preset: str, extra_globs: list[str], store: ResourceStore, ctx,
) -> bool:
    """Serializa um único ``path`` (no commit ``sha``) → Doc. True se persistiu."""
    if not should_serialize(path, preset, extra_globs):
        return False
    data = gitcmd.file_at(repo_dir, sha, path)
    if data is None:  # arquivo ausente nesse commit
        return False
    texto = extrair(data, path)
    if not texto:
        return False
    store.apply(
        Resource(
            kind="Doc",
            name=f"repo-{label}-file-{_slug(path)}",
            labels={"topic": "repo", "repo": label, "path": path, "tipo": "serial"},
            spec={"title": f"{label} · {path}", "body": texto, "source": path},
            status={"serialized_at": ctx.agora.isoformat(), "commit": sha[:7]},
        ),
        ctx.agora,
    )
    return True


def serializar_arquivos(
    repo_dir,
    label: str,
    sha: str,
    files: list[str],
    preset: str,
    extra_globs: list[str],
    store: ResourceStore,
    ctx,
) -> list[str]:
    """Serializa os ``files`` alterados (no commit ``sha``) que casam o preset → Doc.

    Devolve a lista de paths serializados. 0 IA.
    """
    if preset == "off":
        return []
    serializados: list[str] = []
    for path in files:
        if _serializar_um(repo_dir, label, sha, path, preset, extra_globs, store, ctx):
            serializados.append(path)
    return serializados


def snapshot_tree(
    repo_dir,
    label: str,
    preset: str,
    extra_globs: list[str],
    store: ResourceStore,
    ctx,
    ref: str = "HEAD",
    *,
    max_files: int = 2000,
) -> dict:
    """Serializa a **árvore inteira** em ``ref`` (não só o que mudou) → Docs.

    Sob demanda: permite acompanhar o conteúdo atual de todos os arquivos do repo
    que casam o preset. 0 IA. Devolve {serializados, total, pulados, truncado}.
    """
    if preset == "off":
        return {"serializados": 0, "total": 0, "pulados": 0, "truncado": False, "erro": "serialize=off"}
    sha = gitcmd.branch_head(repo_dir, ref) if ref != "HEAD" else gitcmd.git(
        ["rev-parse", "HEAD"], cwd=repo_dir, check=False
    ).strip()
    paths = gitcmd.list_tree(repo_dir, ref)
    candidatos = [p for p in paths if should_serialize(p, preset, extra_globs)]
    truncado = len(candidatos) > max_files
    candidatos = candidatos[:max_files]
    feitos = 0
    for path in candidatos:
        if _serializar_um(repo_dir, label, sha, path, preset, extra_globs, store, ctx):
            feitos += 1
    return {
        "serializados": feitos,
        "total": len(paths),
        "candidatos": len(candidatos),
        "pulados": len(candidatos) - feitos,
        "truncado": truncado,
        "commit": (sha or "")[:7],
    }
