"""TDD — E1-05: invocar IA (modo análise 2a via claude -p) + E7-26 adapter Ollama."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock

import pytest

from atlas.ia import InvocarErro, invocar, invocar_ollama

# ---------------------------------------------------------------------------
# Modo análise (2a) — resposta de texto
# ---------------------------------------------------------------------------


def test_invocar_retorna_texto(monkeypatch):
    mock = MagicMock(returncode=0, stdout="Análise pronta.", stderr="")
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock)
    resultado = invocar("Analise X")
    assert resultado == "Análise pronta."


def test_invocar_passa_prompt_como_stdin(monkeypatch):
    chamadas = []

    def mock_run(args, **kwargs):
        chamadas.append(kwargs.get("input", ""))
        return MagicMock(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", mock_run)
    invocar("Meu prompt")
    assert "Meu prompt" in chamadas[0]


def test_invocar_usa_modelo_padrao_haiku(monkeypatch):
    chamadas = []

    def mock_run(args, **kwargs):
        chamadas.append(args)
        return MagicMock(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", mock_run)
    invocar("X")
    assert any("haiku" in str(a).lower() for a in chamadas[0])


def test_invocar_modelo_override(monkeypatch):
    chamadas = []

    def mock_run(args, **kwargs):
        chamadas.append(args)
        return MagicMock(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", mock_run)
    invocar("X", modelo="claude-sonnet-4-6")
    assert any("sonnet" in str(a).lower() for a in chamadas[0])


def test_invocar_erro_returncode_levanta_excecao(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: MagicMock(returncode=1, stdout="", stderr="auth error"),
    )
    with pytest.raises(InvocarErro, match="auth error"):
        invocar("X")


def test_invocar_timeout_levanta_excecao(monkeypatch):
    def mock_run(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=30)

    monkeypatch.setattr(subprocess, "run", mock_run)
    with pytest.raises(InvocarErro, match="timeout"):
        invocar("X")


def test_invocar_timeout_configuravel(monkeypatch):
    chamadas = []

    def mock_run(args, **kwargs):
        chamadas.append(kwargs.get("timeout"))
        return MagicMock(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", mock_run)
    invocar("X", timeout=120)
    assert chamadas[0] == 120


def test_invocar_strip_saida(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: MagicMock(returncode=0, stdout="  resposta  \n", stderr=""),
    )
    assert invocar("X") == "resposta"


# ---------------------------------------------------------------------------
# E7-26 — Adapter Ollama (invocar_ollama + motor plugável)
# ---------------------------------------------------------------------------


def _mock_ollama_response(content: str) -> MagicMock:
    """Simula urllib.request.urlopen com resposta Ollama."""
    payload = json.dumps({"message": {"role": "assistant", "content": content}}).encode()
    resp = MagicMock()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    resp.read = MagicMock(return_value=payload)
    return resp


def test_invocar_ollama_retorna_conteudo(monkeypatch):
    resp = _mock_ollama_response("Resposta do Gemma")
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: resp)
    resultado = invocar_ollama("Oi", "gemma4", "http://localhost:11434")
    assert resultado == "Resposta do Gemma"


def test_invocar_ollama_formato_payload(monkeypatch):
    payloads = []

    def fake_urlopen(req, timeout=60):
        payloads.append(json.loads(req.data))
        return _mock_ollama_response("ok")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    invocar_ollama("Meu prompt", "gemma4", "http://localhost:11434")
    p = payloads[0]
    assert p["model"] == "gemma4"
    assert p["messages"][0]["role"] == "user"
    assert p["messages"][0]["content"] == "Meu prompt"
    assert p["stream"] is False


def test_invocar_ollama_falha_levanta_invocar_erro(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        MagicMock(side_effect=Exception("connection refused")),
    )
    with pytest.raises(InvocarErro, match="ollama"):
        invocar_ollama("X", "gemma4", "http://localhost:11434")


def test_invocar_motor_ollama_despacha(monkeypatch):
    chamadas = []

    def fake_invocar_ollama(prompt, modelo, endpoint, timeout=60):
        chamadas.append((prompt, modelo, endpoint))
        return "resultado local"

    monkeypatch.setattr("atlas.ia.invocar_ollama", fake_invocar_ollama)
    monkeypatch.setenv("ATLAS_OLLAMA_ENDPOINT", "http://meu-ollama:11434")
    resultado = invocar("teste", modelo="gemma4", motor="ollama")
    assert resultado == "resultado local"
    assert chamadas[0][0] == "teste"
    assert chamadas[0][1] == "gemma4"
    assert "meu-ollama" in chamadas[0][2]


def test_invocar_motor_claude_default_nao_usa_ollama(monkeypatch):
    """motor='claude' continua usando subprocess (comportamento original)."""
    mock = MagicMock(returncode=0, stdout="resposta claude", stderr="")
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock)
    resultado = invocar("X")  # motor default = "claude"
    assert resultado == "resposta claude"
