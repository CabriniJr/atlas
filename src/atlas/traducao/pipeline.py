"""Orquestra a tradução de PDF (ADR-0030 + ADR-0031).

Por página: extrair → **MT bruta** (estágio 1) → **refino por LLM** (estágio 2) →
remontar → checkpoint do cache. Resumível: o cache guarda o refinado por bloco e é
salvo a cada página; se os tokens acabam, o run conclui com o bruto (fase
``parcial``) e um novo run refina o restante.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import fitz

from atlas.ia import invocar as _invocar_padrao
from atlas.traducao.editorial_html import remontar_editorial_html
from atlas.traducao.extracao import extrair_pagina
from atlas.traducao.remontagem import remontar_documento
from atlas.traducao.traducao_ia import (
    CacheTraducao,
    ConfigTraducao,
    aplicar_unificacao,
    detectar_glossario,
    refinar_blocos,
    unificar_termos,
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
    motivo_pausa: str | None = None  # ADR-0039: "timeout" (retry curto) | "erro" (escassez)


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


def _traduzir_pagina(traduziveis, cfg, cache, invocar_fn, esgotado, bruto_fn, on_evento=None):
    """Traduz os blocos de uma página: MT bruta (uncached) + refino.

    Devolve ``(traduções, esgotou, motivo)`` — ``motivo`` classifica a falha que
    esgotou (``"timeout"`` | ``"erro"`` | ``None``, ADR-0039)."""
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
        return traducoes, False, None

    return refinar_blocos(
        traduziveis, brutos, cfg, cache, invocar_fn=invocar_fn, on_evento=on_evento
    )


def _render_final(doc, paginas, destino, cfg) -> None:
    """Renderiza o PDF pelo motor escolhido (ADR-0036). ``html`` = editorial
    (WeasyPrint); cai para ``pymupdf`` in-place se o WeasyPrint faltar/falhar."""
    if getattr(cfg, "render_motor", "html") == "html":
        try:
            remontar_editorial_html(doc, paginas, destino, cfg)
            doc.close()
            return
        except Exception:  # noqa: BLE001 — fallback resiliente (ADR-0006)
            import logging

            logging.getLogger(__name__).exception("render editorial falhou; caindo p/ pymupdf")
    remontar_documento(doc, paginas, min_fonte_pct=cfg.min_fonte_pct)
    doc.save(destino, garbage=4, deflate=True)
    doc.close()


def _render_do_cache(doc, destino, cfg, cache, total, on_progress) -> ProgressoTraducao:
    """Re-renderiza o PDF usando só o que já está no cache (E9-05). Sem chamadas de IA:
    blocos sem tradução cacheada caem no texto original (nunca perde conteúdo)."""
    blocos_traduzidos = 0
    render_paginas: dict[int, tuple[list, dict[int, str]]] = {}
    for i in range(total):
        blocos = extrair_pagina(doc[i], i)
        traducoes: dict[int, str] = {}
        for b in blocos:
            if b.skip:
                continue
            # refino tem prioridade; cai no bruto (raw) se a run foi parcial (ADR-0031).
            cached = cache.get(b.texto, cfg) or cache.get_bruto(b.texto, cfg)
            if cached is not None:
                traducoes[b.id] = cached
        blocos_traduzidos += len(traducoes)
        render_paginas[i] = (blocos, traducoes)
        if on_progress:
            on_progress(ProgressoTraducao(total, i + 1, blocos_traduzidos, fase="traduzindo"))
    _render_final(doc, render_paginas, destino, cfg)
    return ProgressoTraducao(total, total, blocos_traduzidos)


def _processar_paginas_sequencial(
    doc,
    total,
    cfg,
    cache,
    invocar_fn,
    bruto_fn,
    cache_path,
    on_progress,
    on_evento,
    detectados,
    checar_pausa=None,
):
    """Loop original (paralelismo=1): página a página, na ordem. Devolve
    ``(render_paginas, blocos_traduzidos, esgotado, motivo_pausa)``.

    ``checar_pausa`` (ADR-0045, opcional): checado entre páginas; se devolver
    ``True``, para o loop AGORA (``motivo_pausa="manual"``) — mesma forma
    resumível de uma pausa por escassez, só que pedida pelo usuário."""
    blocos_traduzidos = 0
    esgotado = False
    motivo_pausa: str | None = None
    render_paginas: dict[int, tuple[list, dict[int, str]]] = {}
    for i in range(total):
        if checar_pausa is not None and checar_pausa():
            esgotado = True
            motivo_pausa = "manual"
            break
        page = doc[i]
        blocos = extrair_pagina(page, i)
        traduziveis = [b for b in blocos if not b.skip]
        ev_pag = (lambda ev, _p=i + 1: on_evento({**ev, "pagina": _p})) if on_evento else None
        traducoes, esg, motivo = _traduzir_pagina(
            traduziveis, cfg, cache, invocar_fn, esgotado, bruto_fn, on_evento=ev_pag
        )
        if esg and not esgotado:
            motivo_pausa = motivo
        esgotado = esgotado or esg
        blocos_traduzidos += len(traducoes)
        render_paginas[i] = (blocos, traducoes)  # render editorial acontece no fim
        if cache_path:
            cache.salvar(cache_path)  # checkpoint por página ⇒ resume real (ADR-0031)
        if on_progress:
            on_progress(
                ProgressoTraducao(
                    total, i + 1, blocos_traduzidos, detectados, fase="traduzindo", parcial=esgotado
                )
            )
    return render_paginas, blocos_traduzidos, esgotado, motivo_pausa


def _processar_paginas_paralelo(
    doc,
    total,
    cfg,
    cache,
    invocar_fn,
    bruto_fn,
    cache_path,
    on_progress,
    on_evento,
    detectados,
    paralelismo,
):
    """Distribui as páginas entre até ``paralelismo`` workers (ADR-0039) — o
    mesmo dial de "réplicas" do pool entre jobs (ADR-0038) vale pra páginas de
    UM job. Cada página é independente; um lock serializa só a contabilidade
    compartilhada (checkpoint do cache em disco + progresso), não a tradução
    em si (a chamada de IA, cara, roda fora do lock)."""
    lock = threading.Lock()
    esgotado_evt = threading.Event()
    estado = {"blocos_traduzidos": 0, "paginas_prontas": 0, "motivo_pausa": None}
    render_paginas: dict[int, tuple[list, dict[int, str]]] = {}

    def processar(i: int) -> None:
        page = doc[i]
        blocos = extrair_pagina(page, i)
        traduziveis = [b for b in blocos if not b.skip]
        ev_pag = (lambda ev, _p=i + 1: on_evento({**ev, "pagina": _p})) if on_evento else None
        # lê o esgotamento fora do lock (leitura de Event é segura); pode haver
        # algumas páginas em voo que ainda não "viram" um esgotamento recente —
        # aceitável (ADR-0039): dá mais sinal antes de declarar escassez.
        traducoes, esg, motivo = _traduzir_pagina(
            traduziveis, cfg, cache, invocar_fn, esgotado_evt.is_set(), bruto_fn, on_evento=ev_pag
        )
        with lock:
            if esg:
                if not esgotado_evt.is_set():
                    estado["motivo_pausa"] = motivo
                esgotado_evt.set()
            render_paginas[i] = (blocos, traducoes)
            estado["blocos_traduzidos"] += len(traducoes)
            estado["paginas_prontas"] += 1
            if cache_path:
                cache.salvar(cache_path)
            if on_progress:
                on_progress(
                    ProgressoTraducao(
                        total,
                        estado["paginas_prontas"],
                        estado["blocos_traduzidos"],
                        detectados,
                        fase="traduzindo",
                        parcial=esgotado_evt.is_set(),
                    )
                )

    with ThreadPoolExecutor(max_workers=max(1, paralelismo)) as ex:
        list(ex.map(processar, range(total)))

    return (
        render_paginas,
        estado["blocos_traduzidos"],
        esgotado_evt.is_set(),
        estado["motivo_pausa"],
    )


def traduzir_pdf(
    origem: str,
    destino: str,
    cfg: ConfigTraducao,
    invocar_fn=_invocar_padrao,
    on_progress=None,
    cache: CacheTraducao | None = None,
    cache_path: str | None = None,
    bruto_fn=None,
    somente_render: bool = False,
    on_evento=None,
    paralelismo: int = 1,
    checar_pausa=None,
) -> ProgressoTraducao:
    """Traduz um PDF (ADR-0030/0031) ou, com ``somente_render=True``, apenas
    **re-renderiza** a partir do cache já pago — zero IA (E9-05). É o que permite
    iterar o layout (``spec.render``) sem repagar a tradução (``spec.traducao``).

    ``paralelismo`` > 1 distribui as páginas restantes entre workers concorrentes
    (ADR-0039) — default 1 preserva o loop sequencial original.

    ``checar_pausa`` (ADR-0045): pausa manual pedida pelo usuário — só honrada
    no loop sequencial (``paralelismo=1``); pendência para o modo paralelo."""
    bruto_fn = bruto_fn or traduzir_bruto
    doc = fitz.open(origem)
    cache = cache or CacheTraducao()
    total = doc.page_count

    if somente_render:
        return _render_do_cache(doc, destino, cfg, cache, total, on_progress)

    # glossario_auto: detecta termos técnicos a preservar antes de traduzir (ADR-0030).
    detectados: list[str] = []
    if cfg.glossario_auto:
        if on_progress:
            on_progress(ProgressoTraducao(total, 0, 0, [], fase="glossario"))
        detectados = _amostra_para_glossario(doc, cfg, invocar_fn)
        if detectados:
            cfg.glossario = _mesclar_glossario(cfg.glossario, detectados)

    if paralelismo > 1:
        render_paginas, blocos_traduzidos, esgotado, motivo_pausa = _processar_paginas_paralelo(
            doc,
            total,
            cfg,
            cache,
            invocar_fn,
            bruto_fn,
            cache_path,
            on_progress,
            on_evento,
            detectados,
            paralelismo,
        )
    else:
        render_paginas, blocos_traduzidos, esgotado, motivo_pausa = _processar_paginas_sequencial(
            doc,
            total,
            cfg,
            cache,
            invocar_fn,
            bruto_fn,
            cache_path,
            on_progress,
            on_evento,
            detectados,
            checar_pausa,
        )

    # Comparador de consistência (ADR-0034): opt-in e só quando concluiu. Unifica
    # termos/nomes divergentes via mapa determinístico aplicado antes do render.
    if cfg.comparador and not esgotado:
        textos = [t for _, trs in render_paginas.values() for t in trs.values()]
        mapa = unificar_termos(textos, cfg, invocar_fn)
        if mapa:
            for _, trs in render_paginas.values():
                for bid in trs:
                    trs[bid] = aplicar_unificacao(trs[bid], mapa)

    # Render ao fim: motor editorial (WeasyPrint, ADR-0036) ou pymupdf in-place.
    _render_final(doc, render_paginas, destino, cfg)
    return ProgressoTraducao(
        total, total, blocos_traduzidos, detectados, parcial=esgotado, motivo_pausa=motivo_pausa
    )
