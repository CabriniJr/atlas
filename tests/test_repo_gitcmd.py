"""TDD — wrappers git multi-branch do repo-sync (ADR-0023), contra repos git reais."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atlas.rotinas.repo_sync import gitcmd


def _run(args, cwd):
    subprocess.run(args, cwd=str(cwd), check=True, capture_output=True)


def _commit(repo: Path, nome: str, conteudo: str, msg: str) -> str:
    (repo / nome).write_text(conteudo)
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-m", msg], repo)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def origin_e_clone(tmp_path):
    """Cria um 'remoto' com main + feat/x e um clone que enxerga as duas branches."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _run(["git", "init", "-b", "main"], origin)
    _run(["git", "config", "user.email", "t@t"], origin)
    _run(["git", "config", "user.name", "T"], origin)
    _commit(origin, "README.md", "# proj\n", "init")
    _commit(origin, "a.py", "x = 1\n", "feat: a")
    _run(["git", "checkout", "-b", "feat/x"], origin)
    _commit(origin, "b.py", "y = 2\n", "feat: b na branch")
    _commit(origin, "b.py", "y = 3\nz = 4\n", "feat: mais b")
    _run(["git", "checkout", "main"], origin)

    clone = tmp_path / "clone"
    _run(["git", "clone", str(origin), str(clone)], tmp_path)
    return origin, clone


def test_fetch_e_branches(origin_e_clone):
    _, clone = origin_e_clone
    gitcmd.fetch_all(clone, depth=None)
    branches = set(gitcmd.remote_branches(clone))
    assert {"main", "feat/x"} <= branches


def test_default_branch(origin_e_clone):
    _, clone = origin_e_clone
    gitcmd.fetch_all(clone, depth=None)
    assert gitcmd.default_branch(clone) == "main"


def test_new_commits_e_parents(origin_e_clone):
    _, clone = origin_e_clone
    gitcmd.fetch_all(clone, depth=None)
    novos = gitcmd.new_commits(clone, None, "feat/x")
    assert len(novos) >= 4  # init, a, b, mais-b
    meta = gitcmd.commit_meta(clone, novos[-1])
    assert meta["subject"] == "feat: mais b"
    assert meta["author"] == "T"
    assert len(meta["parents"]) == 1
    assert meta["is_merge"] is False
    assert meta["files"] == 1
    assert meta["insertions"] >= 1


def test_new_commits_incremental(origin_e_clone):
    origin, clone = origin_e_clone
    gitcmd.fetch_all(clone, depth=None)
    head_antes = gitcmd.branch_head(clone, "main")
    _commit(origin, "c.py", "w = 9\n", "feat: c")
    gitcmd.fetch_all(clone, depth=None)
    novos = gitcmd.new_commits(clone, head_antes, "main")
    assert len(novos) == 1
    assert gitcmd.commit_meta(clone, novos[0])["subject"] == "feat: c"


def test_ahead_behind(origin_e_clone):
    _, clone = origin_e_clone
    gitcmd.fetch_all(clone, depth=None)
    ahead, behind = gitcmd.ahead_behind(clone, "main", "feat/x")
    assert ahead == 2  # dois commits exclusivos da feat/x
    assert behind == 0


def test_file_at(origin_e_clone):
    _, clone = origin_e_clone
    gitcmd.fetch_all(clone, depth=None)
    head = gitcmd.branch_head(clone, "feat/x")
    conteudo = gitcmd.file_at(clone, head, "b.py")
    assert conteudo == b"y = 3\nz = 4\n"
    assert gitcmd.file_at(clone, head, "nao-existe.txt") is None
