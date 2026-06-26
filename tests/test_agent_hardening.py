"""TDD — endurecimento do Agente modo `code` (ADR-0028).

Cobre as funções puras de controle: allow/deny de tools, confinamento de
workspace e o teto de concorrência de runs. Funções puras testadas isoladamente
(espelha o padrão de tests/test_scoping.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas import api
from atlas.core.store import ResourceStore


@pytest.fixture
def store(tmp_path):
    return ResourceStore(str(tmp_path / "t.db"))


# ── allow/deny de tools (ADR-0028 §2) ────────────────────────────────────────


def test_build_tool_args_vazio_nao_gera_flags():
    assert api.build_tool_args("", "") == []
    assert api.build_tool_args(None, None) == []


def test_build_tool_args_so_allowed():
    assert api.build_tool_args("Read,Edit,Write", "") == [
        "--allowedTools",
        "Read,Edit,Write",
    ]


def test_build_tool_args_so_denied():
    assert api.build_tool_args("", "Bash") == ["--disallowedTools", "Bash"]


def test_build_tool_args_allowed_e_denied():
    args = api.build_tool_args("Read,Edit,Write", "Bash")
    assert args == [
        "--allowedTools",
        "Read,Edit,Write",
        "--disallowedTools",
        "Bash",
    ]


def test_build_tool_args_normaliza_espacos_e_vazios():
    # "Read, , Edit ,Write," → "Read,Edit,Write"
    assert api.build_tool_args(" Read, , Edit ,Write,", "") == [
        "--allowedTools",
        "Read,Edit,Write",
    ]


# ── workspace restrito (ADR-0028 §1) ─────────────────────────────────────────


def test_resolve_workspace_vazio_eh_a_raiz(tmp_path):
    root = str(tmp_path)
    assert api.resolve_workspace(root, "") == str(Path(root).resolve())
    assert api.resolve_workspace(root, None) == str(Path(root).resolve())


def test_resolve_workspace_subdir_valido(tmp_path):
    (tmp_path / "sandbox").mkdir()
    out = api.resolve_workspace(str(tmp_path), "sandbox")
    assert out == str((tmp_path / "sandbox").resolve())


def test_resolve_workspace_recusa_traversal(tmp_path):
    with pytest.raises(ValueError):
        api.resolve_workspace(str(tmp_path), "../fora")


def test_resolve_workspace_recusa_absoluto(tmp_path):
    with pytest.raises(ValueError):
        api.resolve_workspace(str(tmp_path), "/etc")


def test_resolve_workspace_recusa_inexistente(tmp_path):
    with pytest.raises(ValueError):
        api.resolve_workspace(str(tmp_path), "nao-existe")


def test_resolve_workspace_recusa_symlink_que_escapa(tmp_path):
    fora = tmp_path.parent / "fora_alvo"
    fora.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(fora, target_is_directory=True)
    except OSError:
        pytest.skip("symlink não suportado neste ambiente")
    with pytest.raises(ValueError):
        api.resolve_workspace(str(tmp_path), "link")


# ── limite de concorrência (ADR-0028 §3) ─────────────────────────────────────


def test_active_runs_count_conta_so_nao_terminados():
    api._runs.clear()
    r1 = api._new_run("a", "t1")
    r2 = api._new_run("a", "t2")
    assert api.active_runs_count() == 2
    api._finish_run(r1)
    assert api.active_runs_count() == 1
    api._finish_run(r2)
    assert api.active_runs_count() == 0
    api._runs.clear()


# ── persistência de runs (ADR-0028 §5) ───────────────────────────────────────


def _make_run(**over):
    run = api._new_run(over.get("agente", "atlas-builder"), over.get("task", "faça X"))
    run.update(over)
    return run


def test_summarize_run_done():
    run = _make_run()
    run["events"] = [{"type": "init"}, {"type": "done"}]
    run["done"] = True
    s = api.summarize_run(run)
    assert s["status"] == "done"
    assert s["events"] == 2
    assert s["agente"] == "atlas-builder"
    api._runs.clear()


def test_summarize_run_error():
    run = _make_run()
    run["events"] = [{"type": "init"}, {"type": "error", "message": "x"}]
    run["done"] = True
    assert api.summarize_run(run)["status"] == "error"
    api._runs.clear()


def test_summarize_run_running_quando_nao_terminou():
    run = _make_run()
    run["events"] = [{"type": "init"}]
    assert api.summarize_run(run)["status"] == "running"
    api._runs.clear()


def test_persist_agent_run_grava_kind_escopado_por_dono(store):
    run = _make_run(owner="luigi")
    run["events"] = [{"type": "done"}]
    run["done"] = True
    run["cost"] = 0.42
    api.persist_agent_run(store, run)

    res = store.get("AgentRun", run["id"])
    assert res is not None
    assert res.labels["owner"] == "luigi"
    assert res.status["status"] == "done"
    assert res.status["cost_usd"] == 0.42
    assert res.spec["agente"] == "atlas-builder"
    api._runs.clear()


def test_persist_agent_run_sem_owner_usa_default(store):
    run = _make_run()
    run["done"] = True
    api.persist_agent_run(store, run)
    res = store.get("AgentRun", run["id"])
    assert res.labels["owner"] == api._DEFAULT_OWNER
    api._runs.clear()


def test_persist_agent_run_store_none_nao_quebra():
    run = _make_run()
    api.persist_agent_run(None, run)  # não deve levantar
    api._runs.clear()
