"""TDD — dispatch do modo=code por motor (ADR-0042): claude vs ollama + fallback."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from atlas import agente_ollama, api
from atlas.core.resource import Resource
from atlas.core.store import ResourceStore


@pytest.fixture
def store(tmp_path):
    return ResourceStore(str(tmp_path / "t.db"))


def _make_agente(store, name, spec):
    from datetime import datetime

    store.apply(Resource(kind="Agente", name=name, spec=spec), datetime.now())


def _make_run(agente="a", task="faça X"):
    run = api._new_run(agente, task)
    return run


def test_run_agent_bg_motor_ollama_disponivel_despacha_pro_loop_nativo(
    store, tmp_path, monkeypatch
):
    monkeypatch.setattr(api, "_PROJECT_DIR", str(tmp_path))
    _make_agente(store, "a", {"modo": "code", "motor": "ollama", "modelo": "llama3.1"})
    run = _make_run("a", "escreva um teste")

    monkeypatch.setattr(agente_ollama, "ollama_disponivel", lambda ep, **k: True)
    vistos = {}

    def fake_rodar_loop(mensagem, **kw):
        vistos.update(kw)
        kw["on_evento"](
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}}
        )
        kw["on_evento"]({"type": "done"})

    monkeypatch.setattr(agente_ollama, "rodar_loop", fake_rodar_loop)

    api._run_agent_bg(run, store)

    tipos = [e["type"] for e in run["events"]]
    assert tipos == ["init", "assistant", "done"]
    assert run["events"][0]["modelo"] == "llama3.1"
    assert vistos["modelo"] == "llama3.1"
    assert run["done"] is True
    api._runs.pop(run["id"], None)


def test_run_agent_bg_motor_ollama_indisponivel_cai_pro_claude(store, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "_PROJECT_DIR", str(tmp_path))
    _make_agente(store, "a", {"modo": "code", "motor": "ollama"})
    run = _make_run("a", "tarefa")

    monkeypatch.setattr(agente_ollama, "ollama_disponivel", lambda ep, **k: False)
    monkeypatch.setattr("atlas.ia._resolver_claude", lambda: "/bin/echo")

    mock_proc = MagicMock()
    mock_proc.stdout = iter([])
    mock_proc.wait.return_value = None
    mock_proc.returncode = 0
    monkeypatch.setattr(api.subprocess, "Popen", lambda *a, **k: mock_proc)

    api._run_agent_bg(run, store)

    tipos = [e["type"] for e in run["events"]]
    assert "warning" in tipos  # avisa que caiu pro claude
    assert tipos[-1] == "done"
    assert any(
        e.get("modelo", "").startswith("claude") for e in run["events"] if e["type"] == "init"
    )
    api._runs.pop(run["id"], None)


def test_run_agent_bg_motor_claude_nao_verifica_ollama(store, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "_PROJECT_DIR", str(tmp_path))
    _make_agente(store, "a", {"modo": "code", "motor": "claude", "modelo": "claude-sonnet-4-6"})
    run = _make_run("a", "tarefa")

    checou = {"n": 0}

    def fake_disponivel(ep, **k):
        checou["n"] += 1
        return True

    monkeypatch.setattr(agente_ollama, "ollama_disponivel", fake_disponivel)
    monkeypatch.setattr("atlas.ia._resolver_claude", lambda: "/bin/echo")

    mock_proc = MagicMock()
    mock_proc.stdout = iter([])
    mock_proc.wait.return_value = None
    mock_proc.returncode = 0
    monkeypatch.setattr(api.subprocess, "Popen", lambda *a, **k: mock_proc)

    api._run_agent_bg(run, store)

    assert checou["n"] == 0  # motor já é claude — nem checa ollama
    api._runs.pop(run["id"], None)


def test_run_agent_bg_ollama_registra_custo_zero(store, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "_PROJECT_DIR", str(tmp_path))
    _make_agente(store, "a", {"modo": "code", "motor": "ollama", "modelo": "llama3.1"})
    run = _make_run("a", "tarefa")

    monkeypatch.setattr(agente_ollama, "ollama_disponivel", lambda ep, **k: True)
    monkeypatch.setattr(
        agente_ollama, "rodar_loop", lambda mensagem, **kw: kw["on_evento"]({"type": "done"})
    )

    api._run_agent_bg(run, store)

    ag = store.get("Agente", "a")
    assert ag.status["custo_total_usd"] == 0.0
    assert ag.status["ultimo_modelo"] == "llama3.1"
    api._runs.pop(run["id"], None)


def test_run_agent_bg_ollama_usa_max_turnos_do_spec(store, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "_PROJECT_DIR", str(tmp_path))
    _make_agente(
        store, "a", {"modo": "code", "motor": "ollama", "modelo": "llama3.1", "max_turnos": 100}
    )
    run = _make_run("a", "tarefa")

    monkeypatch.setattr(agente_ollama, "ollama_disponivel", lambda ep, **k: True)
    vistos = {}

    def fake_rodar_loop(mensagem, **kw):
        vistos.update(kw)
        kw["on_evento"]({"type": "done"})

    monkeypatch.setattr(agente_ollama, "rodar_loop", fake_rodar_loop)

    api._run_agent_bg(run, store)

    assert vistos["max_turnos"] == 100
    api._runs.pop(run["id"], None)


def test_run_agent_bg_ollama_sem_max_turnos_usa_default(store, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "_PROJECT_DIR", str(tmp_path))
    _make_agente(store, "a", {"modo": "code", "motor": "ollama", "modelo": "llama3.1"})
    run = _make_run("a", "tarefa")

    monkeypatch.setattr(agente_ollama, "ollama_disponivel", lambda ep, **k: True)
    vistos = {}

    def fake_rodar_loop(mensagem, **kw):
        vistos.update(kw)
        kw["on_evento"]({"type": "done"})

    monkeypatch.setattr(agente_ollama, "rodar_loop", fake_rodar_loop)

    api._run_agent_bg(run, store)

    assert vistos["max_turnos"] == agente_ollama.TURNOS_MAX_PADRAO
    api._runs.pop(run["id"], None)


def test_run_agent_bg_injeta_claude_md_no_system_prompt(store, tmp_path, monkeypatch):
    (tmp_path / "CLAUDE.md").write_text("REGRA-MARCADOR-DE-TESTE")
    monkeypatch.setattr(api, "_PROJECT_DIR", str(tmp_path))
    api._claude_md_cache.clear()
    _make_agente(store, "a", {"modo": "code", "motor": "ollama", "modelo": "llama3.1"})
    run = _make_run("a", "tarefa")

    monkeypatch.setattr(agente_ollama, "ollama_disponivel", lambda ep, **k: True)
    vistos = {}

    def fake_rodar_loop(mensagem, **kw):
        vistos.update(kw)
        kw["on_evento"]({"type": "done"})

    monkeypatch.setattr(agente_ollama, "rodar_loop", fake_rodar_loop)

    api._run_agent_bg(run, store)

    assert "REGRA-MARCADOR-DE-TESTE" in vistos["system_prompt"]
    api._runs.pop(run["id"], None)
