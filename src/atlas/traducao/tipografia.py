"""Motor puro de tipografia do render editorial (ADR-0041): conversão de marcador
de ênfase inline, clustering de nível de heading e taxa de abertura de página —
sem WeasyPrint/IO pesado (mesmo padrão de ``layout.py``). ``extrair_fontes`` é a
única função que precisa do documento aberto (fitz).
"""

from __future__ import annotations

import base64
import re
from collections import Counter
from collections.abc import Callable

_RE_ENFASE = re.compile(r"\*\*(.+?)\*\*|_(.+?)_", re.DOTALL)


def converter_enfase(texto: str, escapar: Callable[[str], str]) -> str:
    """Converte marcador ``**negrito**``/``_itálico_`` em ``<b>``/``<i>``, escapando
    o restante do texto com ``escapar`` (ex.: ``html.escape``). Marcador que não
    fecha (desbalanceado) fica literal — nunca quebra o parse (ADR-0041)."""
    partes: list[str] = []
    pos = 0
    for m in _RE_ENFASE.finditer(texto):
        if m.start() > pos:
            partes.append(escapar(texto[pos : m.start()]))
        if m.group(1) is not None:
            partes.append(f"<b>{escapar(m.group(1))}</b>")
        else:
            partes.append(f"<i>{escapar(m.group(2))}</i>")
        pos = m.end()
    partes.append(escapar(texto[pos:]))
    return "".join(partes)


def clusters_titulo(
    tamanhos: list[float], corpo_sz: float, max_niveis: int = 3, min_ocorrencias: int = 2
) -> list[float]:
    """Até ``max_niveis`` tamanhos-âncora (h1 > h2 > h3…), do maior pro menor,
    agrupando os tamanhos de fonte "grandes" do documento (>= 1.15x o corpo) por
    proximidade (gap <= 0.75pt cai no mesmo cluster). Documento sem heading
    grande ⇒ ``[]`` (nenhum nível é tratado como título).

    **Filtro de frequência (ADR-0041 fix):** um tamanho só define um NÍVEL de
    heading se RECORRE (>= ``min_ocorrencias`` blocos) — um tamanho que aparece
    uma vez é ruído (título de capa, rótulo de figura, variação de render),
    não uma tier estrutural. Sem esse filtro, ``{round(s,1) ...}`` (set) tratava
    o título de capa (1 ocorrência) igual a um cabeçalho de seção (127
    ocorrências), e os "3 maiores tamanhos" pegavam capa/parte/capítulo (raros)
    e DESCARTAVAM os cabeçalhos de seção/subseção (frequentes) — que renderizavam
    como parágrafo comum, sem virar heading, sem atualizar o folio corrente, sem
    proteção de órfão (achado real, auditoria visual, Observability Engineering:
    o folio ficava travado no título do livro porque as seções nunca eram
    headings)."""
    freq = Counter(round(s, 1) for s in tamanhos if s >= corpo_sz * 1.15)
    grandes = sorted((s for s, n in freq.items() if n >= min_ocorrencias), reverse=True)
    if not grandes:
        return []
    clusters: list[list[float]] = [[grandes[0]]]
    for s in grandes[1:]:
        if clusters[-1][-1] - s <= 0.75:
            clusters[-1].append(s)
        else:
            clusters.append([s])
    return [c[0] for c in clusters[:max_niveis]]


_TOKENS_MONO = ("mono", "courier", "consol", "menlo", "inconsolata", "source code")
_TOKENS_SANS = (
    "myriad",
    "franklin",
    "futura",
    "helvetica",
    "arial",
    "frutiger",
    "gotham",
    "univers",
    "avenir",
    "calibri",
    "segoe",
    "roboto",
    "tahoma",
    "verdana",
    "grotesk",
    "gothic",
    "sans",
    "optima",
    "akzidenz",
    "proxima",
    "interstate",
)
_TOKENS_SERIF = (
    "minion",
    "baskerville",
    "times",
    "georgia",
    "garamond",
    "caslon",
    "palatino",
    "sabon",
    "janson",
    "bembo",
    "dante",
    "miller",
    "freight",
    "warnock",
    "utopia",
    "century",
    "cambria",
    "constantia",
    "serif",
    "roman",
    "goudy",
    "plantin",
    "scala",
    "book antiqua",
    "adobe garamond",
    "chaparral",
)
_TOKENS_PESO = ("bold", "semibold", "demi", "black", "heavy", "ultra")


def familia_fonte(font: str) -> str:
    """Classifica o basefont extraído do PDF numa família CSS genérica:
    ``"serif"`` | ``"sans"`` | ``"mono"``. As fontes reais dos livros quase nunca
    são embutíveis (subset CFF/Type1) — sem isso, TODO texto cai num único
    fallback serifado, e o heading sem serifa do O'Reilly (Myriad) / Manning
    (Franklin Gothic) sai serifado, descaracterizando o miolo (achado real,
    auditoria visual, Observability Engineering + Kubernetes in Action). Ordem
    mono → sans → serif; default serif (corpo de livro é serifado)."""
    f = font.lower()
    if any(t in f for t in _TOKENS_MONO):
        return "mono"
    if any(t in f for t in _TOKENS_SANS):
        return "sans"
    if any(t in f for t in _TOKENS_SERIF):
        return "serif"
    return "serif"


_RE_PALAVRA_CAPS = r"[A-ZÀ-Þ][A-ZÀ-Þ0-9'’.\-/&]*(?![a-zà-þ])"
_RE_RUN_CAPS = re.compile(rf"^({_RE_PALAVRA_CAPS}(?:\s+{_RE_PALAVRA_CAPS})*)\s*")
_ADMOESTACOES = {
    "NOTE",
    "TIP",
    "WARNING",
    "CAUTION",
    "IMPORTANT",
    "NOTA",
    "DICA",
    "AVISO",
    "CUIDADO",
    "IMPORTANTE",
    "ATENÇÃO",
    "OBSERVAÇÃO",
}


def dividir_versalete(texto: str) -> tuple[str | None, str]:
    """Separa um prefixo em CAIXA ALTA que deveria ser VERSALETE (small-caps), não
    caixa-alta literal — diretriz do usuário: nada sai em caixa-alta inteira se o
    original não for literalmente maiúsculo. No original, cabeçalho run-in e
    rótulo de admoestação ("NOTE") são versalete (glifos maiúsculos sobre texto
    caixa-baixa), e o PyMuPDF os entrega grudados ao corpo, em maiúscula
    (achado real, auditoria visual, Kubernetes in Action:
    "SCALING MICROSERVICES Scaling microservices, unlike...").

    Devolve ``(prefixo_caps, resto)`` quando o prefixo é cabeçalho/rótulo, senão
    ``(None, texto)``. Discriminador seguro (verificado em ~140 páginas reais):
    o cabeçalho run-in é seguido de FRASE CAPITALIZADA ("...MICROSERVICES
    Scaling..."), enquanto uma sigla no meio do fluxo ("REST API allows...") é
    seguida de minúscula — então "REST API"/"HTTP POST" nunca são tocados."""
    m = _RE_RUN_CAPS.match(texto)
    if not m:
        return None, texto
    run = m.group(1)
    palavras = run.split()
    resto = texto[m.end() :]
    e_admoestacao = len(palavras) == 1 and palavras[0].strip(".:") in _ADMOESTACOES
    seguido_de_frase = not resto or resto[:1].isupper()
    if e_admoestacao or (len(palavras) >= 2 and seguido_de_frase):
        return run, resto
    return None, texto


def fonte_seminegrito(font: str) -> bool:
    """``True`` se o NOME da fonte indica peso forte (``Bold``/``Semibold``/
    ``Demi``/``Black``…). O fitz só marca a flag bold em fontes "Bold" cravado —
    "Demi"/"Semibold" (o peso dos headings Manning/O'Reilly) passa batido e o
    heading sai leve (achado real, auditoria visual, Kubernetes in Action)."""
    return any(t in font.lower() for t in _TOKENS_PESO)


def nivel_titulo(sz: float, clusters: list[float], tol: float = 0.5) -> str | None:
    """``"h1"``/``"h2"``/``"h3"`` conforme o cluster mais próximo (dentro de
    ``tol``); ``None`` se não bater com nenhum (texto de corpo comum)."""
    for nivel, ref in zip(("h1", "h2", "h3"), clusters, strict=False):
        if abs(sz - ref) <= tol:
            return nivel
    return None


def taxa_abre_pagina(
    ocorrencias: dict[str, list[bool]], min_amostra: int = 3, limiar: float = 0.6
) -> dict[str, bool]:
    """Por nível de heading, decide se ele deve forçar quebra de página: taxa de
    ocorrências que abriram a página original >= ``limiar``, com amostra mínima
    ``min_amostra`` (evita decidir por 1-2 casos isolados — ADR-0041)."""
    out: dict[str, bool] = {}
    for nivel, flags in ocorrencias.items():
        if len(flags) < min_amostra:
            out[nivel] = False
            continue
        taxa = sum(1 for f in flags if f) / len(flags)
        out[nivel] = taxa >= limiar
    return out


_MIME_FONTE = {"ttf": "font/ttf", "otf": "font/otf", "woff": "font/woff", "woff2": "font/woff2"}


def extrair_fontes(doc) -> dict[str, str]:
    """``Span.font`` (basefont) → data URI da fonte real embutida no PDF
    (ADR-0041). Fonte não extraível (Type3, CFF cru, subset corrompido) fica de
    fora do mapa — o chamador cai no fallback genérico do CSS, nunca quebra."""
    vistos: dict[str, str] = {}
    for page in doc:
        for entry in page.get_fonts(full=True):
            xref, ext, _ftype, basefont = entry[0], entry[1], entry[2], entry[3]
            if not basefont or basefont in vistos:
                continue
            if (ext or "").lower() not in _MIME_FONTE:
                continue
            try:
                _nome, ext_real, _tipo, buf = doc.extract_font(xref)
            except Exception:  # noqa: BLE001 — extração é best-effort (ADR-0006)
                continue
            if not buf:
                continue
            mime = _MIME_FONTE.get((ext_real or ext).lower(), "font/ttf")
            vistos[basefont] = f"data:{mime};base64," + base64.b64encode(buf).decode()
    return vistos


def gerar_font_faces(fontes: dict[str, str]) -> str:
    """``@font-face`` p/ cada fonte real extraída — pronto p/ embutir no
    ``<style>`` do render editorial (ADR-0041)."""
    return "\n".join(
        f'@font-face {{ font-family: "{nome}"; src: url({uri}); }}' for nome, uri in fontes.items()
    )


_FLAG_MONOSPACE = 1 << 3  # bit 3 do flags do fitz


def _span_mono(s) -> bool:
    font = s.font.lower()
    return bool(s.flags & _FLAG_MONOSPACE) or "mono" in font or "courier" in font


def bloco_e_mono(spans: list) -> bool:
    """Um bloco só é tratado como código/imutável (ADR-0033: nunca traduz, nunca
    reflui) se a MAIORIA do texto (por peso de caracteres) estiver em fonte
    monoespaçada — não basta UM span isolado. Um parágrafo de prosa com um termo
    técnico inline em Courier (ex.: ``mycompany.com/foo``) não deve virar um
    bloco de código inteiro: senão a prosa nunca é traduzida (vaza pro `<pre>`
    verbatim, sem passar por `converter_enfase`) — bug real visto em produção,
    ADR-0041 fix. Usado tanto na extração (decide ``skip``) quanto no render
    (decide `<pre>` vs. parágrafo) — a MESMA função nos dois lugares evita que
    um bloco seja marcado com ênfase na extração (achando que não é código) e
    depois vire `<pre>` verbatim no render (vazando o marcador ``**``)."""
    partes_validas = [s for s in spans if s.text.strip()]
    if not partes_validas:
        return False
    total = sum(max(1, len(s.text)) for s in partes_validas)
    peso_mono = sum(len(s.text) for s in partes_validas if _span_mono(s))
    return peso_mono > total / 2
