"""Orquestra a tradução de PDF (ADR-0030 + ADR-0031).

Por página: extrair → **MT bruta** (estágio 1) → **refino por LLM** (estágio 2) →
remontar → checkpoint do cache. Resumível: o cache guarda o refinado por bloco e é
salvo a cada página; se os tokens acabam, o run conclui com o bruto (fase
``parcial``) e um novo run refina o restante.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import fitz

from atlas.ia import invocar as _invocar_padrao
from atlas.traducao.extracao import extrair_pagina
from atlas.traducao.remontagem import remontar_pagina
from atlas.traducao.traducao_ia import (
    CacheTraducao,
    ConfigTraducao,
    detectar_glossario,
    refinar_blocos,
)
from atlas.traducao.tradutor_bruto import traduzir_bruto


@dataclass
class ProgressoTraducao:
    paginas_total: int
    paginas_prontas: int
    blocos_traduzidos: int
    glossario_auto: list[str] = field(default_factory=list)
    fase: str = "traduzindo"  # "preparando" | "glossario" | "traduzindo"
    parcial: bool = False  # ADR-0031: tokens acabaram; restante ficou no bruto (resumível)


def _mesclar_glossario(base: list[str], extra: list[str]) -> list[str]:
    """Une glossários preservando ordem e sem duplicar (case-insensitive)."""
    vistos = {t.lower() for t in base}
    out = list(base)
    for t in extra:
        if t.lower() not in vistos:
            vistos.add(t.lower())
            out.append(t)
    return out


def _amostra_para_glossario(doc, cfg, invocar_fn, max_paginas: int = 5, limite: int = 40):
    """Extrai blocos das primeiras páginas e detecta o glossário automático (1 chamada IA)."""
    amostra = []
    for i in range(min(doc.page_count, max_paginas)):
        amostra.extend(b for b in extrair_pagina(doc[i], i) if not b.skip)
        if len(amostra) >= limite:
            break
    return detectar_glossario(amostra, cfg, invocar_fn=invocar_fn, limite=limite)


def _traduzir_pagina(traduziveis, cfg, cache, invocar_fn, esgotado, bruto_fn):
    """Traduz os blocos de uma página: MT bruta (uncached) + refino. Devolve (traduções, esgotou)."""  # noqa: E501
    pend = [b for b in traduziveis if cache.get(b.texto, cfg) is None]
    brutos: dict[int, str] = {}
    if pend:
        # MT bruta também é cacheada (namespace "raw:"): num resume, só rodamos a
        # rede para blocos cujo bruto ainda não foi feito — o resto reusa do cache.
        # Sem isso, cada "Continuar" re-traduzia o bruto do doc todo (lento, ADR-0031).
        faltam_bruto = [b for b in pend if cache.get_bruto(b.texto, cfg) is None]
        if faltam_bruto:
            novos = bruto_fn([b.texto for b in faltam_bruto], cfg)
            for b, bt in zip(faltam_bruto, novos, strict=False):
                cache.put_bruto(b.texto, cfg, bt)
        for b in pend:
            brutos[b.id] = cache.get_bruto(b.texto, cfg) or b.texto

    # Sem refino (config) ou tokens já esgotados ⇒ usa o bruto direto.
    if not cfg.refino or esgotado:
        traducoes: dict[int, str] = {}
        for b in traduziveis:
            cached = cache.get(b.texto, cfg)
            if cached is not None:
                traducoes[b.id] = cached
            else:
                traducoes[b.id] = brutos.get(b.id, b.texto)
                if not cfg.refino:  # modo MT puro: cacheia o bruto como final
                    cache.put(b.texto, cfg, traducoes[b.id])
        return traducoes, False

    return refinar_blocos(traduziveis, brutos, cfg, cache, invocar_fn=invocar_fn)


def traduzir_pdf(
    origem: str,
    destino: str,
    cfg: ConfigTraducao,
    invocar_fn=_invocar_padrao,
    on_progress=None,
    cache: CacheTraducao | None = None,
    cache_path: str | None = None,
    bruto_fn=None,
) -> ProgressoTraducao:
    bruto_fn = bruto_fn or traduzir_bruto
    doc = fitz.open(origem)
    cache = cache or CacheTraducao()
    total = doc.page_count

    # glossario_auto: detecta termos técnicos a preservar antes de traduzir (ADR-0030).
    detectados: list[str] = []
    if cfg.glossario_auto:
        if on_progress:
            on_progress(ProgressoTraducao(total, 0, 0, [], fase="glossario"))
        detectados = _amostra_para_glossario(doc, cfg, invocar_fn)
        if detectados:
            cfg.glossario = _mesclar_glossario(cfg.glossario, detectados)

    blocos_traduzidos = 0
    esgotado = False
    for i in range(total):
        page = doc[i]
        blocos = extrair_pagina(page, i)
        traduziveis = [b for b in blocos if not b.skip]
        traducoes, esg = _traduzir_pagina(
            traduziveis, cfg, cache, invocar_fn, esgotado, bruto_fn
        )
        esgotado = esgotado or esg
        blocos_traduzidos += len(traducoes)
        remontar_pagina(page, blocos, traducoes)
        if cache_path:
            cache.salvar(cache_path)  # checkpoint por página ⇒ resume real (ADR-0031)
        prog = ProgressoTraducao(
            total, i + 1, blocos_traduzidos, detectados, fase="traduzindo", parcial=esgotado
        )
        if on_progress:
            on_progress(prog)
    doc.save(destino, garbage=4, deflate=True)
    doc.close()
    return ProgressoTraducao(
        total, total, blocos_traduzidos, detectados, parcial=esgotado
    )
