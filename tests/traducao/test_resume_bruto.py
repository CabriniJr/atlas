"""Resume não re-roda a MT bruta (regressão do 'Continuar recomeça do início').

Antes, a MT bruta (rede) não era cacheada: cada re-disparo re-traduzia o bruto do
doc inteiro (lento — o usuário 'perdia 30 min'). Agora o bruto é cacheado; um 2º
run só chama ``bruto_fn`` para blocos novos.
"""

from __future__ import annotations

import re

import fitz

from atlas.traducao.pipeline import traduzir_pdf
from atlas.traducao.traducao_ia import CacheTraducao, ConfigTraducao


def _pdf(tmp_path, paginas):
    src = tmp_path / "src.pdf"
    doc = fitz.open()
    for n in range(paginas):
        p = doc.new_page()
        p.insert_text((72, 100), f"Page {n} content here.", fontname="helv", fontsize=12)
    doc.save(str(src))
    doc.close()
    return src


def _invocar_ok(prompt, modelo=None, timeout=60, motor="claude"):
    ids = re.findall(r"\[\[(\d+)\]\]", prompt)
    return "\n".join(f"[[{i}]] TRADUZIDO {i}" for i in ids)


def _invocar_falha(prompt, modelo=None, timeout=60, motor="claude"):
    raise RuntimeError("tokens acabaram")  # força fase 'parcial' (nada refinado)


def test_resume_nao_retraduz_bruto(tmp_path):
    src = _pdf(tmp_path, 2)
    out = tmp_path / "out.pdf"
    cfg = ConfigTraducao()
    cache_path = tmp_path / "c.cache.json"

    chamadas_bruto: list[list[str]] = []

    def bruto_contado(textos, cfg):
        chamadas_bruto.append(list(textos))
        return [f"BRUTO {t}" for t in textos]

    # 1º run: refino FALHA (parcial) → bruto é feito e cacheado, refino não cacheia.
    cache = CacheTraducao()
    traduzir_pdf(
        str(src), str(out), cfg,
        invocar_fn=_invocar_falha, cache=cache, cache_path=str(cache_path),
        bruto_fn=bruto_contado,
    )
    blocos_run1 = sum(len(c) for c in chamadas_bruto)
    assert blocos_run1 > 0, "1º run deveria ter traduzido o bruto"

    # 2º run (Continuar): recarrega o cache do disco; refino agora OK.
    chamadas_bruto.clear()
    cache2 = CacheTraducao.carregar(str(cache_path))
    prog = traduzir_pdf(
        str(src), str(out), cfg,
        invocar_fn=_invocar_ok, cache=cache2, cache_path=str(cache_path),
        bruto_fn=bruto_contado,
    )
    blocos_run2 = sum(len(c) for c in chamadas_bruto)

    assert blocos_run2 == 0, (
        f"resume re-traduziu o bruto de {blocos_run2} blocos (deveria reusar cache)"
    )
    assert not prog.parcial and prog.paginas_prontas == 2
    assert "TRADUZIDO" in fitz.open(str(out))[0].get_text()
