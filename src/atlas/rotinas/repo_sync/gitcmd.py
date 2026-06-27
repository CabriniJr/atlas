"""Wrappers de git para o repo-sync — multi-branch, sem checkout (ADR-0023).

Toda a leitura do repositório passa por aqui: ``fetch`` de todas as remotas,
enumeração de branches, descoberta de commits novos por branch, metadados leves
de commit (incl. ``parents`` para o git-graph) e ``ahead/behind`` vs. a default.
Nada aqui usa IA nem dá ``checkout`` — o detalhe pesado (``git show``) é puxado
sob demanda pela fase de análise.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

_log = logging.getLogger(__name__)


def data_dir() -> Path:
    db = os.environ.get("ATLAS_DB_PATH", "atlas.sqlite")
    return Path(db).resolve().parent


def git(
    args: list[str],
    cwd: Path | None = None,
    *,
    check: bool = True,
    auth_args: list[str] | None = None,
) -> str:
    """Roda ``git`` e devolve stdout. Levanta ``RuntimeError`` se ``check`` e falhar.

    ``auth_args`` (ex.: ``["-c", "http.extraheader=..."]``, de
    :func:`atlas.github_auth.git_auth_args`) são injetados logo após ``git`` —
    autenticam por invocação, sem persistir o token em ``.git/config``.
    """
    proc = subprocess.run(
        ["git", *(auth_args or []), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        timeout=180,
    )
    if proc.returncode != 0 and check:
        raise RuntimeError(proc.stderr.strip() or f"git {args[0]} code={proc.returncode}")
    return proc.stdout


# ── fetch / branches ───────────────────────────────────────────────────────────


def fetch_all(
    repo_dir: Path, depth: int | None = 100, *, auth_args: list[str] | None = None
) -> None:
    """Busca **todas** as branches remotas em ``refs/remotes/origin/*`` (sem checkout)."""
    args = ["fetch", "origin", "+refs/heads/*:refs/remotes/origin/*", "--prune"]
    if depth:
        args.append(f"--depth={depth}")
    git(args, cwd=repo_dir, auth_args=auth_args)


def fetch_unshallow(repo_dir: Path) -> None:
    """Converte um clone raso em completo (backfill). Idempotente: ignora se já completo."""
    try:
        git(["fetch", "origin", "+refs/heads/*:refs/remotes/origin/*", "--unshallow"], cwd=repo_dir)
    except RuntimeError as exc:
        # "--unshallow on a complete repository does not make sense" → já completo
        _log.debug("unshallow ignorado: %s", exc)
        git(["fetch", "origin", "+refs/heads/*:refs/remotes/origin/*"], cwd=repo_dir, check=False)


def default_branch(repo_dir: Path) -> str:
    """Branch default do remoto (curta, ex.: ``main``). Cai em main/master se indefinida."""
    out = git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=repo_dir, check=False)
    ref = out.strip()
    if ref.startswith("origin/"):
        return ref[len("origin/") :]
    for cand in ("main", "master"):
        if git(["rev-parse", "--verify", f"refs/remotes/origin/{cand}"], cwd=repo_dir, check=False):
            return cand
    return "main"


def remote_branches(repo_dir: Path) -> list[str]:
    """Nomes curtos das branches remotas (sem ``origin/HEAD``)."""
    out = git(
        ["for-each-ref", "--format=%(refname)", "refs/remotes/origin"],
        cwd=repo_dir,
        check=False,
    )
    prefixo = "refs/remotes/origin/"
    nomes = []
    for linha in out.splitlines():
        ref = linha.strip()
        if not ref.startswith(prefixo):
            continue
        nome = ref[len(prefixo) :]
        if not nome or nome == "HEAD":
            continue
        nomes.append(nome)
    return nomes


# ── commits ────────────────────────────────────────────────────────────────────


def new_commits(repo_dir: Path, since_sha: str | None, branch: str) -> list[str]:
    """SHAs novos em ``origin/<branch>`` desde ``since_sha`` (mais antigo primeiro).

    Se ``since_sha`` é vazio/desconhecido, lista todos os alcançáveis (limitado pela
    profundidade do clone).
    """
    ref = f"refs/remotes/origin/{branch}"
    valido = False
    if since_sha:
        verif = git(["rev-parse", "--verify", f"{since_sha}^{{commit}}"], cwd=repo_dir, check=False)
        valido = bool(verif.strip())
    rng = f"{since_sha}..{ref}" if valido else ref
    out = git(["rev-list", "--reverse", rng], cwd=repo_dir, check=False)
    return [s.strip() for s in out.splitlines() if s.strip()]


_FMT = "%H%x00%s%x00%an%x00%ae%x00%cI%x00%P"


def commit_meta(repo_dir: Path, sha: str) -> dict:
    """Metadados leves de um commit, incl. ``parents`` e estatística (``--numstat``)."""
    out = git(["log", "-1", f"--format={_FMT}", "--numstat", sha], cwd=repo_dir, check=False)
    linhas = out.split("\n")
    cabec = linhas[0].split("\x00") if linhas else []

    def g(i: int) -> str:
        return cabec[i].strip() if len(cabec) > i else ""

    full = g(0)
    parents = [p[:7] for p in g(5).split() if p]
    files = ins = dels = 0
    files_list: list[str] = []
    for ln in linhas[1:]:
        ln = ln.strip()
        if not ln:
            continue
        partes = ln.split("\t")
        if len(partes) < 3:
            continue
        a, d, caminho = partes[0], partes[1], partes[2]
        files += 1
        if a.isdigit():
            ins += int(a)
        if d.isdigit():
            dels += int(d)
        files_list.append(caminho)
    return {
        "sha": full,
        "sha7": full[:7],
        "subject": g(1),
        "author": g(2),
        "author_email": g(3),
        "date": g(4),
        "parents": parents,
        "is_merge": len(parents) > 1,
        "files": files,
        "insertions": ins,
        "deletions": dels,
        "files_list": files_list,
        "lines_changed": ins + dels,
    }


def ahead_behind(repo_dir: Path, base: str, branch: str) -> tuple[int, int]:
    """``(ahead, behind)`` de ``origin/<branch>`` vs. ``origin/<base>``."""
    out = git(
        [
            "rev-list",
            "--left-right",
            "--count",
            f"refs/remotes/origin/{base}...refs/remotes/origin/{branch}",
        ],
        cwd=repo_dir,
        check=False,
    )
    partes = out.split()
    if len(partes) != 2:
        return (0, 0)
    behind, ahead = int(partes[0]), int(partes[1])
    return (ahead, behind)


def branch_head(repo_dir: Path, branch: str) -> str:
    return git(["rev-parse", f"refs/remotes/origin/{branch}"], cwd=repo_dir, check=False).strip()


def commit_count(repo_dir: Path, branch: str) -> int:
    out = git(["rev-list", "--count", f"refs/remotes/origin/{branch}"], cwd=repo_dir, check=False)
    return int(out.strip()) if out.strip().isdigit() else 0


def all_commit_count(repo_dir: Path) -> int:
    """Total de commits distintos em todas as branches remotas."""
    out = git(["rev-list", "--count", "--remotes=origin"], cwd=repo_dir, check=False)
    return int(out.strip()) if out.strip().isdigit() else 0


def show_diff(repo_dir: Path, sha: str) -> str:
    """Diff pesado de um commit (``git show``), para a fase de análise/demanda."""
    return git(["show", sha, "--stat", "-p", "--no-color"], cwd=repo_dir, check=False)


def file_at(repo_dir: Path, sha: str, path: str) -> bytes | None:
    """Conteúdo bruto (bytes) de ``path`` no commit ``sha`` — sem checkout."""
    proc = subprocess.run(
        ["git", "show", f"{sha}:{path}"],
        capture_output=True,
        cwd=str(repo_dir),
        timeout=60,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout


def list_tree(repo_dir: Path, ref: str = "HEAD") -> list[str]:
    """Lista todos os paths de arquivo da árvore em ``ref`` (recursivo, sem checkout)."""
    out = git(["ls-tree", "-r", "--name-only", ref], cwd=repo_dir, check=False)
    return [ln for ln in out.splitlines() if ln.strip()]
