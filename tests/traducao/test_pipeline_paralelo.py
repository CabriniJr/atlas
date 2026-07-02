"""TDD — paralelismo de páginas dentro de um job (ADR-0039)."""

from __future__ import annotations

import re
import threading
import time

import fitz

from atlas.traducao.pipeline import traduzir_pdf
from atlas.traducao.traducao_ia import ConfigTraducao


def _pdf_com_n_paginas(tmp_path, n):
    src = tmp_path / "src.pdf"
    doc = fitz.open()
    for i in range(n):
        p = doc.new_page()
        p.insert_text((72, 100), f"Page {i} content here.", fontname="helv", fontsize=12)
    doc.save(src)
    return str(src)


def _fake_bruto(textos, cfg):
    return [f"BRUTO {t}" for t in textos]


def _fake_invocar_lento(contador_concorrencia, lock, delay=0.05):
    """Fake que registra o pico de chamadas concorrentes em voo — prova que o
    paralelismo=N realmente sobrepõe chamadas, não só finge."""
    em_voo = {"n": 0, "pico": 0}

    def fake(prompt, modelo=None, timeout=60, motor="claude"):
        with lock:
            em_voo["n"] += 1
            em_voo["pico"] = max(em_voo["pico"], em_voo["n"])
        time.sleep(delay)
        ids = re.findall(r"\[\[(\d+)\]\]", prompt)
        with lock:
            em_voo["n"] -= 1
        return "\n".join(f"[[{i}]] TRADUZIDO {i}" for i in ids)

    contador_concorrencia["estado"] = em_voo
    return fake


def test_paralelismo_1_preserva_comportamento_sequencial(tmp_path):
    src = _pdf_com_n_paginas(tmp_path, 4)
    out = tmp_path / "out.pdf"
    cfg = ConfigTraducao()
    res = traduzir_pdf(
        src, str(out), cfg,
        invocar_fn=lambda p, **k: "\n".join(
            f"[[{i}]] TRADUZIDO {i}" for i in re.findall(r"\[\[(\d+)\]\]", p)
        ),
        bruto_fn=_fake_bruto, paralelismo=1,
    )
    assert res.paginas_prontas == 4
    assert not res.parcial


def test_paralelismo_traduz_todas_as_paginas_e_sobrepoe_chamadas(tmp_path):
    src = _pdf_com_n_paginas(tmp_path, 8)
    out = tmp_path / "out.pdf"
    cfg = ConfigTraducao()
    lock = threading.Lock()
    estado_holder: dict = {}
    fake = _fake_invocar_lento(estado_holder, lock, delay=0.08)

    progresso = []
    res = traduzir_pdf(
        src, str(out), cfg,
        invocar_fn=fake,
        on_progress=lambda p: progresso.append(p.paginas_prontas),
        bruto_fn=_fake_bruto, paralelismo=4,
    )
    assert res.paginas_total == 8
    assert res.paginas_prontas == 8
    assert not res.parcial
    assert out.exists()
    # prova real de paralelismo: mais de uma chamada de IA em voo ao mesmo tempo.
    assert estado_holder["estado"]["pico"] > 1
    # progresso é monotônico e termina completo (mesmo fora de ordem entre workers).
    assert progresso[-1] == 8
    assert progresso == sorted(progresso)


def test_paralelismo_esgotamento_cai_pro_bruto_sem_perder_paginas(tmp_path):
    """Um timeout classificado deve marcar parcial=True e motivo_pausa="timeout",
    e nenhuma página fica sem conteúdo (cai pro bruto, ADR-0031/0039)."""
    src = _pdf_com_n_paginas(tmp_path, 6)
    out = tmp_path / "out.pdf"
    cfg = ConfigTraducao()

    from atlas.ia import InvocarErro

    def fake_com_timeout(prompt, modelo=None, timeout=60, motor="claude"):
        raise InvocarErro("timeout após 60s invocando IA")

    res = traduzir_pdf(
        src, str(out), cfg,
        invocar_fn=fake_com_timeout,
        bruto_fn=_fake_bruto, paralelismo=3,
    )
    assert res.parcial
    assert res.motivo_pausa == "timeout"
    assert res.paginas_prontas == 6  # todas processadas (bruto onde não refinou)
    texto = "".join(page.get_text() for page in fitz.open(out))
    assert "BRUTO" in texto  # nenhuma página ficou vazia
