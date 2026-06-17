"""TDD — E1-05: invocar IA (modo análise 2a via claude -p)."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from atlas.ia import InvocarErro, invocar


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
