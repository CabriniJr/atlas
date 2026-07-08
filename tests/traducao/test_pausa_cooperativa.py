"""TDD — pausa manual cooperativa honrada também no loop paralelo (E9-16)."""

from __future__ import annotations

import re
import threading

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


def _fake_invocar(prompt, modelo=None, timeout=60, motor="claude"):
    ids = re.findall(r"\[\[(\d+)\]\]", prompt)
    return "\n".join(f"[[{i}]] TRADUZIDO {i}" for i in ids)


def test_pausa_paralela_para_e_marca_manual(tmp_path):
    """Com checar_pausa=True desde o início, o run paralelo encerra parcial e
    motivo_pausa='manual', sem processar todas as páginas."""
    src = _pdf_com_n_paginas(tmp_path, 12)
    out = tmp_path / "out.pdf"
    cfg = ConfigTraducao()

    lock = threading.Lock()
    processadas = {"n": 0}

    def conta_e_traduz(prompt, modelo=None, timeout=60, motor="claude"):
        with lock:
            processadas["n"] += 1
        return _fake_invocar(prompt)

    res = traduzir_pdf(
        src, str(out), cfg,
        invocar_fn=conta_e_traduz,
        bruto_fn=_fake_bruto,
        paralelismo=4,
        checar_pausa=lambda: True,  # pausa pedida antes de tudo
    )
    assert res.parcial
    assert res.motivo_pausa == "manual"
    # a pausa é vista já na 1ª checagem (antes da chamada de IA): nenhuma página
    # chega a invocar a IA. Guard forte: pega quem mover a checagem para DEPOIS.
    assert processadas["n"] == 0


def test_paralelo_sem_pausa_traduz_tudo(tmp_path):
    """Regressão: sem pausa, o paralelo continua traduzindo todas as páginas."""
    src = _pdf_com_n_paginas(tmp_path, 6)
    out = tmp_path / "out.pdf"

    lock = threading.Lock()
    processadas = {"n": 0}

    def conta_e_traduz(prompt, modelo=None, timeout=60, motor="claude"):
        with lock:
            processadas["n"] += 1
        return _fake_invocar(prompt)

    res = traduzir_pdf(
        src, str(out), ConfigTraducao(),
        invocar_fn=conta_e_traduz, bruto_fn=_fake_bruto,
        paralelismo=3, checar_pausa=lambda: False,
    )
    assert res.paginas_prontas == 6
    assert not res.parcial
    # cada página faz 1 chamada de IA (refino) — todas as 6 rodaram de fato.
    assert processadas["n"] == 6


def test_pausa_paralela_mid_run(tmp_path):
    """Pausa pedida no meio do run: as primeiras páginas concluem, mas o restante
    é pulado — parcial + motivo_pausa='manual'."""
    src = _pdf_com_n_paginas(tmp_path, 10)
    out = tmp_path / "out.pdf"

    lock = threading.Lock()
    estado = {"checagens": 0, "processadas": 0}

    def conta_e_traduz(prompt, modelo=None, timeout=60, motor="claude"):
        with lock:
            estado["processadas"] += 1
        return _fake_invocar(prompt)

    def pausa_no_meio():
        # False nas primeiras checagens, True depois: força pausa após arrancar.
        with lock:
            estado["checagens"] += 1
            return estado["checagens"] > 3

    res = traduzir_pdf(
        src, str(out), ConfigTraducao(),
        invocar_fn=conta_e_traduz, bruto_fn=_fake_bruto,
        paralelismo=2, checar_pausa=pausa_no_meio,
    )
    assert res.parcial
    assert res.motivo_pausa == "manual"
    # robusto a nondeterminismo de escalonamento: algumas rodaram, nem todas.
    assert 0 < estado["processadas"] < 10
