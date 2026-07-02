"""Motor editorial de alta fidelidade via modelo semântico + re-layout (ADR-0036).

A parte editorial é uma **substituição de texto no documento** respeitando estilo,
elementos e normas tipográficas. Em vez de reinserir texto in-place (PyMuPDF, que
perdia bold/itálico, não justificava e gerava páginas de 1 linha), aqui:

1. Extrai um **modelo semântico** do PDF: por bloco, o *papel* (título/parágrafo/
   lista/código/legenda) e o *estilo dominante* (bold, itálico, mono, tamanho, cor);
   e as **imagens** (preservadas como estão).
2. Reintroduz **só o texto bruto traduzido** — código e imagens seguem o original.
3. Re-diagrama o documento inteiro como um fluxo HTML+CSS (justificado, hifenização
   pt-BR, hierarquia de fontes, quebras controladas) e renderiza com **WeasyPrint**.

O documento "remolda" para acomodar o texto mais longo (como editar um Word),
preservando o design: sem sobreposição, sem páginas ralas, com estilo mantido.
"""

from __future__ import annotations

import base64
import html as _html
import statistics

import fitz

try:  # WeasyPrint é opcional em import-time (o motor pymupdf continua disponível)
    import weasyprint
except Exception:  # noqa: BLE001
    weasyprint = None

# flags de span do PyMuPDF (bits): 1=italic, 3=monospaced, 4=bold.
_ITALIC, _MONO, _BOLD = 1 << 1, 1 << 3, 1 << 4


def _e(txt: str) -> str:
    return _html.escape(txt or "")


def _bold(s) -> bool:
    return bool(s.flags & _BOLD) or "bold" in s.font.lower() or "black" in s.font.lower()


def _ital(s) -> bool:
    return bool(s.flags & _ITALIC) or "italic" in s.font.lower() or "oblique" in s.font.lower()


def _mono_span(s) -> bool:
    return bool(s.flags & _MONO) or "mono" in s.font.lower() or "courier" in s.font.lower()


def _estilo(b) -> dict:
    """Estilo dominante do bloco (por soma de caracteres em cada estilo)."""
    if not b.spans:
        return {"size": 11.0, "bold": False, "italic": False, "mono": False, "color": 0}
    total = sum(max(1, len(s.text)) for s in b.spans)
    peso = lambda pred: sum(len(s.text) for s in b.spans if pred(s))  # noqa: E731
    return {
        "size": statistics.median([s.size for s in b.spans if s.size] or [11.0]),
        "bold": peso(_bold) > total / 2,
        "italic": peso(_ital) > total / 2,
        "mono": any(_mono_span(s) for s in b.spans),
        "color": b.spans[0].color or 0,
    }


def _cor_hex(color: int) -> str:
    return f"#{(color & 0xFFFFFF):06x}"


def _geometria(doc, paginas) -> dict:
    """Tamanho da página e margens medianas do texto (para o @page do CSS)."""
    pw, ph = doc[0].rect.width, doc[0].rect.height
    lefts, rights, tops, bots = [], [], [], []
    for idx, (blocos, _tr) in paginas.items():  # noqa: B007 — idx documenta o loop
        uteis = [b for b in blocos if not b.skip and b.bbox]
        if not uteis:
            continue
        lefts.append(min(b.bbox[0] for b in uteis))
        rights.append(pw - max(b.bbox[2] for b in uteis))
        tops.append(min(b.bbox[1] for b in uteis))
        bots.append(ph - max(b.bbox[3] for b in uteis))
    med = lambda xs, d: statistics.median(xs) if xs else d  # noqa: E731
    return {
        "pw": pw, "ph": ph,
        "left": max(24.0, med(lefts, 72)), "right": max(24.0, med(rights, 72)),
        "top": max(24.0, med(tops, 60)), "bottom": max(24.0, med(bots, 60)),
    }


def _imagens(doc, page) -> list[tuple]:
    """(y0, largura_pt, altura_pt, data_uri) de cada imagem da página (preservadas)."""
    out = []
    for img in page.get_images(full=True):
        xref = img[0]
        try:
            rects = page.get_image_rects(xref)
        except Exception:  # noqa: BLE001
            rects = []
        if not rects:
            continue
        try:
            pix = fitz.Pixmap(doc, xref)
            if pix.alpha or (pix.n - pix.alpha) >= 4:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            uri = "data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode()
        except Exception:  # noqa: BLE001
            continue
        for r in rects:
            out.append((r.y0, r.width, r.height, uri))
    return out


_CSS = """
@page {{ size: {pw:.0f}pt {ph:.0f}pt;
         margin: {top:.0f}pt {right:.0f}pt {bottom:.0f}pt {left:.0f}pt; }}
html {{ font-family: 'Liberation Serif','DejaVu Serif','Times New Roman',Georgia,serif; }}
body {{ text-align: justify; hyphens: auto; line-height: 1.34; color: #000; }}
p {{ margin: 0 0 .45em 0; orphans: 2; widows: 2; }}
h1,h2,h3 {{ text-align: left; font-weight: bold; margin: .7em 0 .28em; line-height: 1.2;
            page-break-after: avoid; }}
ul {{ margin: .3em 0 .55em 1.3em; padding: 0; }}
li {{ margin: .12em 0; }}
pre {{ font-family: 'Liberation Mono','DejaVu Sans Mono',monospace; white-space: pre-wrap;
       background: #f6f6f6; border-radius: 4px; padding: 6px 9px; font-size: 8.5pt;
       text-align: left; line-height: 1.3; page-break-inside: avoid; }}
figure {{ margin: .6em 0; text-align: center; page-break-inside: avoid; }}
img {{ max-width: 100%; }}
.it {{ font-style: italic; }} .bd {{ font-weight: bold; }}
"""

_BULLETS = ("•", "◦", "▪", "-", "–", "—", "*")


def _e_lista(texto: str) -> bool:
    t = texto.lstrip()
    return t[:1] in _BULLETS and len(t) > 2 and t[1:2] in (" ", "\t")


def _elemento(b, texto: str, est: dict, body_sz: float) -> str:
    """HTML de um bloco de texto conforme seu papel/estilo (código não é traduzido)."""
    cor = _cor_hex(est["color"])
    cor_css = "" if cor in ("#000000", "#000") else f"color:{cor};"
    if est["mono"]:
        return f'<pre>{_e(b.texto)}</pre>'  # código: original, verbatim
    conteudo = _e(texto)
    if est["bold"]:
        conteudo = f'<span class="bd">{conteudo}</span>'
    if est["italic"]:
        conteudo = f'<span class="it">{conteudo}</span>'
    sz = est["size"]
    # título: fonte notavelmente maior que o corpo e poucas palavras
    if sz >= body_sz * 1.18 and len(texto.split()) <= 14:
        nivel = "h1" if sz >= body_sz * 1.6 else "h2"
        return f'<{nivel} style="font-size:{sz:.1f}pt;{cor_css}">{conteudo}</{nivel}>'
    if _e_lista(b.texto):
        item = _e(texto.lstrip()[1:].lstrip())
        if est["italic"]:
            item = f'<span class="it">{item}</span>'
        return f'<li style="font-size:{sz:.1f}pt;{cor_css}">{item}</li>'
    return f'<p style="font-size:{sz:.1f}pt;{cor_css}">{conteudo}</p>'


def montar_html(doc, paginas: dict, geo: dict) -> str:
    """Constrói o HTML do documento inteiro em ordem de leitura (texto + imagens)."""
    # tamanho do corpo = mediana dos tamanhos dos blocos de texto longos.
    sizes = []
    for _idx, (blocos, _tr) in paginas.items():
        for b in blocos:
            if not b.skip and len(b.texto) > 60:
                sizes.append(_estilo(b)["size"])
    body_sz = statistics.median(sizes) if sizes else 11.0

    partes: list[str] = []
    aberto_ul = False

    def fecha_ul():
        nonlocal aberto_ul
        if aberto_ul:
            partes.append("</ul>")
            aberto_ul = False

    for idx in sorted(paginas):
        blocos, traducoes = paginas[idx]
        page = doc[idx]
        # itens da página (blocos de texto + imagens) em ordem de leitura vertical.
        itens: list[tuple] = [
            (b.bbox[1] if b.bbox else 0.0, "b", b)
            for b in blocos if not b.skip or _estilo(b)["mono"]
        ]
        for y0, w, h, uri in _imagens(doc, page):
            itens.append((y0, "img", (w, h, uri)))
        itens.sort(key=lambda it: it[0])

        for _y, tipo, obj in itens:
            if tipo == "img":
                w, h, uri = obj
                tw = geo["pw"] - geo["left"] - geo["right"]
                pct = max(15, min(100, int(w / tw * 100))) if tw else 100
                fecha_ul()
                partes.append(f'<figure><img src="{uri}" style="width:{pct}%"></figure>')
                continue
            b = obj
            est = _estilo(b)
            # código/imutável: mantém o original; senão usa a tradução (ou o texto).
            texto = traducoes.get(b.id) if not est["mono"] else b.texto
            if texto is None:
                continue
            el = _elemento(b, texto, est, body_sz)
            if el.startswith("<li"):
                if not aberto_ul:
                    partes.append("<ul>")
                    aberto_ul = True
                partes.append(el)
            else:
                fecha_ul()
                partes.append(el)
        fecha_ul()

    css = _CSS.format(**geo)
    corpo = "\n".join(partes)
    return f'<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">' \
           f"<style>{css}</style></head><body>{corpo}</body></html>"


def remontar_editorial_html(doc, paginas: dict, destino: str, cfg=None) -> None:
    """Renderiza o PDF traduzido pelo motor editorial (ADR-0036). Levanta se o
    WeasyPrint não estiver disponível (o chamador pode cair no motor pymupdf)."""
    if weasyprint is None:
        raise RuntimeError("weasyprint não instalado — use render_motor='pymupdf'")
    geo = _geometria(doc, paginas)
    html = montar_html(doc, paginas, geo)
    weasyprint.HTML(string=html).write_pdf(destino)
