"""Orquestra os 4 estágios da tradução de PDF (ADR-0030).

Por página: extrair → traduzir (IA, com cache) → remontar → salvar (checkpoint).
Resumível: o cache cobre blocos já traduzidos, então reprocessar é barato.
"""

from __future__ import annotations

from dataclasses import dataclass

import fitz

from atlas.ia import invocar as _invocar_padrao
from atlas.traducao.extracao import extrair_pagina
from atlas.traducao.remontagem import remontar_pagina
from atlas.traducao.traducao_ia import CacheTraducao, ConfigTraducao, traduzir_blocos


@dataclass
class ProgressoTraducao:
    paginas_total: int
    paginas_prontas: int
    blocos_traduzidos: int


def traduzir_pdf(
    origem: str,
    destino: str,
    cfg: ConfigTraducao,
    invocar_fn=_invocar_padrao,
    on_progress=None,
    cache: CacheTraducao | None = None,
) -> ProgressoTraducao:
    doc = fitz.open(origem)
    cache = cache or CacheTraducao()
    total = doc.page_count
    blocos_traduzidos = 0
    for i in range(total):
        page = doc[i]
        blocos = extrair_pagina(page, i)
        traduziveis = [b for b in blocos if not b.skip]
        traducoes = traduzir_blocos(traduziveis, cfg, cache, invocar_fn=invocar_fn)
        blocos_traduzidos += len(traducoes)
        remontar_pagina(page, blocos, traducoes)
        prog = ProgressoTraducao(total, i + 1, blocos_traduzidos)
        if on_progress:
            on_progress(prog)
    doc.save(destino, garbage=4, deflate=True)
    doc.close()
    return ProgressoTraducao(total, total, blocos_traduzidos)
