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
    # nenhuma (ou quase nenhuma) página processada: a pausa é vista já na 1ª checagem
    assert processadas["n"] < 12


def test_paralelo_sem_pausa_traduz_tudo(tmp_path):
    """Regressão: sem pausa, o paralelo continua traduzindo todas as páginas."""
    src = _pdf_com_n_paginas(tmp_path, 6)
    out = tmp_path / "out.pdf"
    res = traduzir_pdf(
        src, str(out), ConfigTraducao(),
        invocar_fn=_fake_invocar, bruto_fn=_fake_bruto,
        paralelismo=3, checar_pausa=lambda: False,
    )
    assert res.paginas_prontas == 6
    assert not res.parcial
