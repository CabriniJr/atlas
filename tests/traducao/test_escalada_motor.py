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


def test_escalada_persiste_para_proxima_chamada(monkeypatch):
    # Depois de escalar, o resto do job vai direto pro claude: o pipeline relê
    # cfg.motor (== "claude") e passa motor="claude" na chamada seguinte, sem
    # pagar as 3 tentativas no ollama de novo.
    cfg = ConfigTraducao(motor="ollama", escalonar_apos_falhas=3)
    conn = InvocarErro("ollama: <urlopen error [Errno 111] Connection refused>")
    inv, chamadas, escalas = _wrapper(
        cfg, monkeypatch,
        {"ollama": [conn, conn, conn], "claude": ["[[1]] A", "[[2]] B"]},
    )
    assert inv("[[1]] x", motor="ollama") == "[[1]] A"
    assert cfg.motor == "claude"  # migrou de vez
    # 2ª chamada: o pipeline relê cfg.motor → passa "claude", sem retry no ollama.
    assert inv("[[2]] y", motor=cfg.motor) == "[[2]] B"
    assert [m for m, _ in chamadas] == ["ollama", "ollama", "ollama", "claude", "claude"]
    assert chamadas[-1] == ("claude", None)  # 2ª chamada no claude, modelo None
    assert len(escalas) == 1  # escalou uma única vez


def test_escalada_concorrente_dispara_on_escala_uma_vez(monkeypatch):
    # Dois workers cruzam o limiar ao mesmo tempo: o lock + o guard
    # `if cfg.motor == "ollama"` tornam a escalada idempotente (on_escala 1x só).
    cfg = ConfigTraducao(motor="ollama", escalonar_apos_falhas=3)
    conn = InvocarErro("ollama: <urlopen error [Errno 111] Connection refused>")
    fake_lock = threading.Lock()

    def fake_invocar(prompt, modelo=None, timeout=60, motor="claude", fallback=True):
        if motor == "ollama":
            raise conn  # suprimento ilimitado de erro de conexão (endpoint fora)
        return "[[1]] OK"

    monkeypatch.setattr("atlas.rotinas.traduzir_pdf.invocar", fake_invocar)
    escalas = []
    escalas_lock = threading.Lock()

    def on_escala(de, para, motivo):
        with escalas_lock:
            escalas.append((de, para, motivo))

    inv = montar_invocar_escalavel(cfg, on_escala=on_escala, lock=fake_lock)
    barreira = threading.Barrier(2)

    def worker():
        barreira.wait()  # sincroniza o arranque dos dois threads
        inv("[[1]] t", motor="ollama")

    ts = [threading.Thread(target=worker) for _ in range(2)]
    for th in ts:
        th.start()
    for th in ts:
        th.join()

    assert len(escalas) == 1  # on_escala disparou exatamente uma vez
    assert cfg.motor == "claude"
