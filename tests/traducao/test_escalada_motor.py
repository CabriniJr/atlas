"""TDD — escalada visível Ollama→Claude no wrapper da rotina (E9-16/ADR-0048)."""

from __future__ import annotations

import threading

from atlas.ia import InvocarErro
from atlas.rotinas.traduzir_pdf import montar_invocar_escalavel
from atlas.traducao.traducao_ia import ConfigTraducao


def _wrapper(cfg, monkeypatch, roteiro):
    """Monta o wrapper com um `invocar` fake dirigido por `roteiro`:
    roteiro[motor] = lista de resultados; cada item é uma str (retorno) ou uma
    Exception (levantada). Consome em ordem por motor."""
    chamadas = []
    estado = {m: list(v) for m, v in roteiro.items()}

    def fake_invocar(prompt, modelo=None, timeout=60, motor="claude", fallback=True):
        chamadas.append((motor, modelo))
        item = estado[motor].pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr("atlas.rotinas.traduzir_pdf.invocar", fake_invocar)
    escalas = []
    inv = montar_invocar_escalavel(
        cfg, on_escala=lambda de, para, motivo: escalas.append((de, para, motivo)), lock=threading.Lock()
    )
    return inv, chamadas, escalas


def test_arranque_endpoint_fora_escala_para_claude(monkeypatch):
    cfg = ConfigTraducao(motor="ollama", escalonar_apos_falhas=3)
    conn = InvocarErro("ollama: <urlopen error [Errno 111] Connection refused>")
    inv, chamadas, escalas = _wrapper(
        cfg, monkeypatch,
        {"ollama": [conn, conn, conn], "claude": ["[[1]] OK"]},
    )
    out = inv("[[1]] texto", motor="ollama")
    assert out == "[[1]] OK"
    assert cfg.motor == "claude"  # job migrou de vez
    assert escalas == [("ollama", "claude", str(conn))]
    # 3 tentativas no ollama + 1 no claude, e o claude NÃO herda modelo do ollama
    assert [m for m, _ in chamadas] == ["ollama", "ollama", "ollama", "claude"]
    assert chamadas[-1][1] is None


def test_timeout_nao_escala_propaga_para_pipeline(monkeypatch):
    cfg = ConfigTraducao(motor="ollama", escalonar_apos_falhas=3)
    to = InvocarErro("timeout após 60s invocando IA")
    inv, chamadas, escalas = _wrapper(cfg, monkeypatch, {"ollama": [to], "claude": []})
    try:
        inv("[[1]] texto", motor="ollama")
        assert False, "deveria propagar o timeout"
    except InvocarErro:
        pass
    assert cfg.motor == "ollama"  # timeout não escala (Ollama ocupado ≠ fora)
    assert escalas == []
    assert [m for m, _ in chamadas] == ["ollama"]  # uma só; ADR-0039 decide o retry


def test_sucesso_no_ollama_nao_escala(monkeypatch):
    cfg = ConfigTraducao(motor="ollama", escalonar_apos_falhas=3)
    inv, chamadas, escalas = _wrapper(cfg, monkeypatch, {"ollama": ["[[1]] OK"], "claude": []})
    assert inv("[[1]] t", motor="ollama") == "[[1]] OK"
    assert cfg.motor == "ollama"
    assert escalas == []
