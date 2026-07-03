"""TDD — E1-05: invocar IA (modo análise 2a via claude -p) + E7-26 adapter Ollama."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock

import pytest

from atlas.ia import InvocarErro, _chamar_claude, invocar, invocar_ollama, modelo_padrao

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
    """Mecânica pura do adapter claude (sem fallback) — ver invocar() para o dispatch."""
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: MagicMock(returncode=1, stdout="", stderr="auth error"),
    )
    with pytest.raises(InvocarErro, match="auth error"):
        _chamar_claude("X", None, 60)


def test_invocar_timeout_levanta_excecao(monkeypatch):
    """Mecânica pura do adapter claude (sem fallback) — ver invocar() para o dispatch."""

    def mock_run(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=30)

    monkeypatch.setattr(subprocess, "run", mock_run)
    with pytest.raises(InvocarErro, match="timeout"):
        _chamar_claude("X", None, 60)


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


def test_modelo_padrao_por_motor():
    assert modelo_padrao("ollama") == "gemma4"
    assert modelo_padrao("claude") == "claude-haiku-4-5-20251001"


def test_invocar_motor_ollama_sem_modelo_usa_default_do_ollama_nao_do_claude(monkeypatch):
    """Sem override, motor='ollama' nunca deve pedir um modelo 'claude-*' ao Ollama."""
    chamadas = []

    def fake_invocar_ollama(prompt, modelo, endpoint, timeout=60):
        chamadas.append(modelo)
        return "ok"

    monkeypatch.setattr("atlas.ia.invocar_ollama", fake_invocar_ollama)
    invocar("teste", motor="ollama")
    assert chamadas[0] == "gemma4"


def test_invocar_motor_ollama_indisponivel_cai_para_claude(monkeypatch):
    """Rede de segurança (plug-and-play): ollama fora do ar não trava o chamador."""

    def fake_invocar_ollama(prompt, modelo, endpoint, timeout=60):
        raise InvocarErro("ollama: connection refused")

    monkeypatch.setattr("atlas.ia.invocar_ollama", fake_invocar_ollama)
    chamadas_claude = []

    def mock_run(args, **kwargs):
        chamadas_claude.append(args)
        return MagicMock(returncode=0, stdout="resposta claude", stderr="")

    monkeypatch.setattr(subprocess, "run", mock_run)
    resultado = invocar("teste", motor="ollama")
    assert resultado == "resposta claude"
    # nunca deve pedir ao claude o modelo do ollama (ex.: "gemma4")
    assert "gemma4" not in str(chamadas_claude[0]).lower()


def test_invocar_motor_ollama_falha_do_claude_no_fallback_propaga(monkeypatch):
    """Se o fallback (claude) também falhar, o erro real do claude deve propagar."""

    def fake_invocar_ollama(prompt, modelo, endpoint, timeout=60):
        raise InvocarErro("ollama: connection refused")

    monkeypatch.setattr("atlas.ia.invocar_ollama", fake_invocar_ollama)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: MagicMock(returncode=1, stdout="", stderr="auth error"),
    )
    with pytest.raises(InvocarErro, match="auth error"):
        invocar("teste", motor="ollama")


def test_invocar_fallback_false_propaga_erro_sem_tentar_outro_motor(monkeypatch):
    """ADR-0045: jobs que pedem fallback=False (ex.: tradução) não trocam de
    motor às escondidas — a falha do motor pedido propaga direto."""

    def fake_invocar_ollama(prompt, modelo, endpoint, timeout=60):
        raise InvocarErro("ollama: connection refused")

    monkeypatch.setattr("atlas.ia.invocar_ollama", fake_invocar_ollama)
    chamadas_claude = []
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: chamadas_claude.append(a) or MagicMock()
    )
    with pytest.raises(InvocarErro, match="connection refused"):
        invocar("teste", motor="ollama", fallback=False)
    assert not chamadas_claude  # nunca chegou a chamar o claude


def test_invocar_motor_claude_bate_limite_cai_para_ollama(monkeypatch):
    """Fallback no sentido oposto: claude bateu limite/sessão ⇒ tenta ollama."""
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: MagicMock(returncode=1, stdout="", stderr="You've hit your session limit"),
    )
    chamadas = []

    def fake_invocar_ollama(prompt, modelo, endpoint, timeout=60):
        chamadas.append(modelo)
        return "resposta do ollama"

    monkeypatch.setattr("atlas.ia.invocar_ollama", fake_invocar_ollama)
    resultado = invocar("teste")  # motor default = claude
    assert resultado == "resposta do ollama"
    assert chamadas[0] == "gemma4"  # nunca herda o modelo claude no fallback


def test_invocar_motor_claude_falha_e_ollama_tambem_falha_propaga_erro_do_ollama(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: MagicMock(returncode=1, stdout="", stderr="session limit"),
    )
    monkeypatch.setattr(
        "atlas.ia.invocar_ollama",
        MagicMock(side_effect=InvocarErro("ollama: connection refused")),
    )
    with pytest.raises(InvocarErro, match="connection refused"):
        invocar("teste")
