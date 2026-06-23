"""Helpers de teste — constroem repositórios git reais (origin + clone) para os
testes do repo-sync multi-branch (ADR-0023)."""

from __future__ import annotations

import subprocess
from pathlib import Path


def run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=str(cwd), check=True, capture_output=True)


def commit(repo: Path, nome: str, conteudo: str, msg: str) -> str:
    (repo / nome).write_text(conteudo)
    run(["git", "add", "-A"], repo)
    run(["git", "commit", "-m", msg], repo)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), capture_output=True, text=True
    ).stdout.strip()


def init_origin(path: Path) -> Path:
    """Cria um repositório 'remoto' com main + feat/x (commits pequenos)."""
    path.mkdir(parents=True, exist_ok=True)
    run(["git", "init", "-b", "main"], path)
    run(["git", "config", "user.email", "t@t"], path)
    run(["git", "config", "user.name", "Dev"], path)
    commit(path, "README.md", "# proj\n", "init")
    commit(path, "a.py", "x = 1\n", "feat: a")
    run(["git", "checkout", "-b", "feat/x"], path)
    commit(path, "b.py", "y = 2\n", "feat: b na branch")
    commit(path, "b.py", "y = 3\nz = 4\n", "feat: mais b")
    run(["git", "checkout", "main"], path)
    return path
