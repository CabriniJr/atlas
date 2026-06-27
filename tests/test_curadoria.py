"""TDD — curadoria do gate (SPEC-CURADORIA-GATE / ADR-0028 §4).

Funções puras sobre git, testadas com um repositório real em ``tmp_path``.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from atlas import api, curadoria
from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.rotinas.repo_sync import gitcmd


@pytest.fixture
def repo(tmp_path):
    """Repo git com um commit inicial e um subdir ``ws`` (workspace do agente)."""
    root = tmp_path / "proj"
    root.mkdir()
    gitcmd.git(["init", "-q", "-b", "main"], cwd=root)
    gitcmd.git(["config", "user.email", "t@t"], cwd=root)
    gitcmd.git(["config", "user.name", "t"], cwd=root)
    (root / "ws").mkdir()
    (root / "ws" / "base.txt").write_text("v1\n")
    (root / "keep.txt").write_text("fora do ws\n")
    gitcmd.git(["add", "-A"], cwd=root)
    gitcmd.git(["commit", "-q", "-m", "init"], cwd=root)
    return root


def _agent_edits(root: Path) -> None:
    """Simula o que o agente faz: edita um rastreado e cria um arquivo novo."""
    (root / "ws" / "base.txt").write_text("v2\n")
    (root / "ws" / "novo.py").write_text("print('oi')\n")


# ── workspace_diff ────────────────────────────────────────────────────────────


def test_diff_vazio_sem_mudancas(repo):
    assert curadoria.workspace_diff(str(repo), "ws").strip() == ""


def test_diff_mostra_edicao_e_arquivo_novo(repo):
    _agent_edits(repo)
    diff = curadoria.workspace_diff(str(repo), "ws")
    assert "base.txt" in diff
    assert "v2" in diff
    assert "novo.py" in diff  # arquivo novo aparece (intent-to-add)


def test_diff_nao_estaga_de_verdade(repo):
    # add -N não deve deixar conteúdo realmente staged (commit não captura).
    _agent_edits(repo)
    curadoria.workspace_diff(str(repo), "ws")
    staged = gitcmd.git(["diff", "--cached", "--name-only"], cwd=repo)
    assert "novo.py" not in staged  # -N marca intent, não estaga conteúdo


# ── discard_workspace ─────────────────────────────────────────────────────────


def test_discard_reverte_rastreado_e_remove_novo(repo):
    _agent_edits(repo)
    curadoria.discard_workspace(str(repo), "ws")
    assert (repo / "ws" / "base.txt").read_text() == "v1\n"
    assert not (repo / "ws" / "novo.py").exists()


def test_discard_nao_toca_fora_do_workspace(repo):
    _agent_edits(repo)
    (repo / "keep.txt").write_text("alterado fora\n")
    curadoria.discard_workspace(str(repo), "ws")
    assert (repo / "keep.txt").read_text() == "alterado fora\n"


# ── approve_to_branch ─────────────────────────────────────────────────────────


def test_approve_cria_branch_comita_e_volta_limpo(repo):
    _agent_edits(repo)
    branch = curadoria.approve_to_branch(str(repo), "ws", "agent/x1", "agent(a): faz X")
    assert branch == "agent/x1"

    # voltou para main, working tree limpa do que foi promovido
    cur = gitcmd.git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).strip()
    assert cur == "main"
    assert (repo / "ws" / "base.txt").read_text() == "v1\n"
    assert not (repo / "ws" / "novo.py").exists()

    # a branch tem o commit com o conteúdo do agente
    files = gitcmd.git(["show", "--stat", "--name-only", "agent/x1"], cwd=repo)
    assert "novo.py" in files
    base_na_branch = gitcmd.git(["show", "agent/x1:ws/base.txt"], cwd=repo)
    assert base_na_branch == "v2\n"


def test_approve_so_comita_o_workspace(repo):
    _agent_edits(repo)
    (repo / "keep.txt").write_text("mudou fora\n")
    curadoria.approve_to_branch(str(repo), "ws", "agent/x2", "msg")
    # keep.txt fora do ws não entra no commit da branch
    files = gitcmd.git(["show", "--name-only", "--format=", "agent/x2"], cwd=repo)
    assert "keep.txt" not in files


def test_approve_branch_existente_erro(repo):
    _agent_edits(repo)
    curadoria.approve_to_branch(str(repo), "ws", "agent/dup", "m")
    _agent_edits(repo)
    with pytest.raises(RuntimeError):
        curadoria.approve_to_branch(str(repo), "ws", "agent/dup", "m")


# ── escopo por dono no _curate_run (ADR-0027) ─────────────────────────────────


def _store_with_run(tmp_path, owner="luigi"):
    store = ResourceStore(str(tmp_path / "s.db"))
    store.apply(
        Resource(kind="AgentRun", name="r1", labels={"owner": owner},
                 spec={"agente": "a", "workspace": "ws"}, status={"review": "pending"}),
        datetime.now(),
    )
    return store


def test_curate_run_dono_ve(tmp_path):
    store = _store_with_run(tmp_path)
    assert api._curate_run(store, "r1", "luigi", "member") is not None


def test_curate_run_outro_dono_404(tmp_path):
    store = _store_with_run(tmp_path)
    assert api._curate_run(store, "r1", "outro", "member") is None


def test_curate_run_admin_ve_tudo(tmp_path):
    store = _store_with_run(tmp_path)
    assert api._curate_run(store, "r1", "admin", "admin") is not None


def test_curate_run_inexistente_none(tmp_path):
    store = _store_with_run(tmp_path)
    assert api._curate_run(store, "nao-existe", "luigi", "member") is None
