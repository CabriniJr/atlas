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
import re
import statistics

import fitz

from atlas.traducao.tipografia import (
    bloco_e_mono,
    clusters_titulo,
    converter_enfase,
    extrair_fontes,
    gerar_font_faces,
    nivel_titulo,
    taxa_abre_pagina,
)

# fim de linha de sumário: leaders (pontos) + número de página do original (que a
# repaginação invalida — o CSS regenera via target-counter).
_RE_TOC_FIM = re.compile(r"[\s.·•…\-–—]*\d+\s*$")

try:  # WeasyPrint é opcional em import-time (o motor pymupdf continua disponível)
    import weasyprint
except Exception:  # noqa: BLE001
    weasyprint = None

# flags de span do PyMuPDF (bits): 1=italic, 4=bold.
_ITALIC, _BOLD = 1 << 1, 1 << 4


def _e(txt: str) -> str:
    return _html.escape(txt or "")


def _bold(s) -> bool:
    return bool(s.flags & _BOLD) or "bold" in s.font.lower() or "black" in s.font.lower()


def _ital(s) -> bool:
    return bool(s.flags & _ITALIC) or "italic" in s.font.lower() or "oblique" in s.font.lower()


def _estilo(b) -> dict:
    """Estilo dominante do bloco (por soma de caracteres em cada estilo)."""
    if not b.spans:
        return {"size": 11.0, "bold": False, "italic": False, "mono": False, "color": 0, "font": ""}
    total = sum(max(1, len(s.text)) for s in b.spans)
    peso = lambda pred: sum(len(s.text) for s in b.spans if pred(s))  # noqa: E731
    fontes: dict[str, int] = {}
    for s in b.spans:
        fontes[s.font] = fontes.get(s.font, 0) + len(s.text)
    font_dom = max(fontes, key=fontes.get) if fontes else ""
    return {
        "size": statistics.median([s.size for s in b.spans if s.size] or [11.0]),
        "bold": peso(_bold) > total / 2,
        "italic": peso(_ital) > total / 2,
        "mono": bloco_e_mono(b.spans),
        "color": b.spans[0].color or 0,
        "font": font_dom,
    }


def _cor_hex(color: int) -> str:
    return f"#{(color & 0xFFFFFF):06x}"


# Piso de largura/altura útil: abaixo disso a margem calculada não é confiável
# (documento com pouco texto/páginas esparsas) — evita coluna estreita demais,
# que faz o texto traduzido (mais longo) colidir/paginar em cima do folio.
_MIN_CONTEUDO_LARGURA = 300.0
_MIN_CONTEUDO_ALTURA = 400.0


def _geometria(doc, paginas) -> dict:
    """Tamanho da página e margens do texto (para o @page do CSS).

    ``left``/``top`` usam a mediana **por página** de onde o texto *começa* — um
    parágrafo normal quase sempre começa perto da margem real, então isso é
    robusto mesmo em páginas com só linhas curtas.

    ``right``/``bottom`` são diferentes: só uma linha que *alcança* a borda real
    revela a margem verdadeira (uma página de sumário/lista/código, cheia de
    linhas curtas, nunca chega perto). Por isso são calculados a partir de um
    **quantil alto de todos os blocos do documento** (não mediana por página) —
    com dados suficientes, algumas linhas longas em algum lugar do livro chegam
    perto da margem real. Documentos com pouquíssimo texto (poucos blocos) não
    têm dado suficiente pra confiar nisso, então há um piso mínimo de largura/
    altura útil (``_MIN_CONTEUDO_*``) que evita colunas absurdamente estreitas —
    e a paginação/wrap excessivo (texto colidindo com o folio) que isso causava.
    """
    pw, ph = doc[0].rect.width, doc[0].rect.height
    lefts, tops = [], []
    direitas_abs, fundos_abs = [], []
    for idx, (blocos, _tr) in paginas.items():  # noqa: B007 — idx documenta o loop
        uteis = [b for b in blocos if not b.skip and b.bbox and not _e_folio(b, ph)]
        if not uteis:
            continue
        lefts.append(min(b.bbox[0] for b in uteis))
        tops.append(min(b.bbox[1] for b in uteis))
        direitas_abs.extend(b.bbox[2] for b in uteis)
        fundos_abs.extend(b.bbox[3] for b in uteis)
    med = lambda xs, d: statistics.median(xs) if xs else d  # noqa: E731
    quantil_alto = lambda xs, d: sorted(xs)[max(0, round(len(xs) * 0.95) - 1)] if xs else d  # noqa: E731

    left = max(24.0, med(lefts, 72))
    top = max(24.0, med(tops, 60))
    right = max(24.0, pw - quantil_alto(direitas_abs, pw - 72))
    bottom = max(24.0, ph - quantil_alto(fundos_abs, ph - 60))

    if pw - left - right < _MIN_CONTEUDO_LARGURA:
        right = max(24.0, pw - left - _MIN_CONTEUDO_LARGURA)
    if ph - top - bottom < _MIN_CONTEUDO_ALTURA:
        bottom = max(24.0, ph - top - _MIN_CONTEUDO_ALTURA)

    return {"pw": pw, "ph": ph, "left": left, "right": right, "top": top, "bottom": bottom}


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


def _uniao_rect(a: fitz.Rect, b: fitz.Rect) -> fitz.Rect:
    return fitz.Rect(min(a.x0, b.x0), min(a.y0, b.y0), max(a.x1, b.x1), max(a.y1, b.y1))


def _mesclar_retangulos(rects: list, folga: float = 6.0) -> list:
    """Agrupa retângulos que se tocam/sobrepõem (com uma folga em pt) em clusters,
    devolvendo o bounding box de cada cluster — usado p/ juntar os muitos
    fragmentos de um desenho vetorial (linhas, setas, caixas) numa única região
    (ADR-0041 fix: diagramas)."""
    pendentes = list(rects)
    saida: list = []
    while pendentes:
        atual = pendentes.pop()
        mudou = True
        while mudou:
            mudou = False
            i = 0
            while i < len(pendentes):
                expandido = fitz.Rect(
                    atual.x0 - folga, atual.y0 - folga, atual.x1 + folga, atual.y1 + folga
                )
                if expandido.intersects(pendentes[i]):
                    atual = _uniao_rect(atual, pendentes[i])
                    pendentes.pop(i)
                    mudou = True
                else:
                    i += 1
        saida.append(atual)
    return saida


def _fracao_contida(bbox, regiao: fitz.Rect) -> float:
    """Fração da área de ``bbox`` que cai dentro de ``regiao`` (0.0–1.0)."""
    b = fitz.Rect(bbox)
    area_b = b.width * b.height
    if area_b <= 0:
        return 0.0
    inter = b & regiao
    area_i = max(0.0, inter.width) * max(0.0, inter.height)
    return area_i / area_b


_AREA_MIN_DESENHO = 400.0  # ignora linhas finas/sublinhados (ADR-0041)
_LARGURA_MIN_REGIAO = 80.0
_ALTURA_MIN_REGIAO = 40.0
_PALAVRAS_MIN_PROSA = 15  # bloco com >= isso é prosa (destaque), não rótulo de diagrama


_ESPESSURA_MAX_REGRA = 2.0  # pt — "espessura" de uma linha/régua (não uma caixa)
_FRACAO_MIN_REGRA_TOTAL = 0.85  # regra deve cobrir a maior parte da largura/altura da região
_MIN_REGRAS_PARA_TABELA = 1  # 1+ régua INTERNA (não é a própria borda) = grade de tabela
_TOLERANCIA_BORDA = 3.0  # pt — régua "colada" na borda da região é só o contorno da caixa


def _parece_tabela(regiao: fitz.Rect, retangulos: list) -> bool:
    """Uma tabela comum (mesmo com cabeçalho/linhas com fundo colorido, o que
    também passa no filtro de "forma cheia" abaixo — achado real ao auditar
    Kubernetes in Action: uma tabela de referência da API virou uma imagem
    rasterizada em INGLÊS, perdendo a tradução inteira) tem réguas finas
    (bordas de linha/coluna) que atravessam quase toda a largura ou altura da
    região — um diagrama (caixas+setas) não tem: suas linhas finas (setas) são
    curtas/locais, e caixas repetidas (ex. 3 pods lado a lado) têm dimensão
    cheia nos dois eixos, não finas num deles. Só conta réguas INTERNAS (longe
    da própria borda da região) — senão o contorno de uma caixa de destaque
    simples (2 réguas H + 2 V = seu próprio retângulo) seria confundido com
    tabela (achado real ao auditar Prometheus Up & Running, ADR-0041 fix)."""
    for r in retangulos:
        if not regiao.intersects(r):
            continue
        larga_o_bastante = regiao.width * _FRACAO_MIN_REGRA_TOTAL
        alta_o_bastante = regiao.height * _FRACAO_MIN_REGRA_TOTAL
        fina_h = r.height <= _ESPESSURA_MAX_REGRA and r.width >= larga_o_bastante
        if fina_h and (
            r.y0 - regiao.y0 > _TOLERANCIA_BORDA and regiao.y1 - r.y1 > _TOLERANCIA_BORDA
        ):
            return True
        fina_v = r.width <= _ESPESSURA_MAX_REGRA and r.height >= alta_o_bastante
        if fina_v and (
            r.x0 - regiao.x0 > _TOLERANCIA_BORDA and regiao.x1 - r.x1 > _TOLERANCIA_BORDA
        ):
            return True
    return False


_TOLERANCIA_CONTAINER = 3.0  # pt — forma igual à região inteira (contêiner) não conta como subforma


def _tem_subformas(regiao: fitz.Rect, retangulos: list) -> bool:
    """Um diagrama de verdade (caixas+setas) tem >=1 forma "cheia" DISTINTA do
    retângulo-contêiner da região inteira — várias caixas internas conectadas.
    Uma caixa de destaque simples (ex. quadro "This chapter covers" com uma
    lista, achado real ao auditar Kubernetes in Action) é desenhada como UM
    único retângulo preenchido do tamanho exato da região — sem subformas —
    mesmo tendo vários blocos de texto curtos dentro (título + itens de
    lista), o que por si só não basta pra distinguir de um diagrama."""
    for r in retangulos:
        if not regiao.intersects(r) or r.width * r.height < _AREA_MIN_DESENHO:
            continue
        eh_o_proprio_container = (
            abs(r.x0 - regiao.x0) <= _TOLERANCIA_CONTAINER
            and abs(r.y0 - regiao.y0) <= _TOLERANCIA_CONTAINER
            and abs(r.x1 - regiao.x1) <= _TOLERANCIA_CONTAINER
            and abs(r.y1 - regiao.y1) <= _TOLERANCIA_CONTAINER
        )
        if not eh_o_proprio_container:
            return True
    return False


def _regioes_diagrama(page, blocos: list) -> list[tuple]:
    """Detecta regiões de desenho vetorial que contêm vários blocos de texto
    curtos — um diagrama (caixas/setas/rótulos) desenhado com operadores de
    path, não uma imagem raster (``_imagens`` não o vê). Devolve
    ``[(regiao, [blocos_contidos]), ...]``: cada região com >=2 blocos
    majoritariamente dentro dela vira UMA imagem rasterizada no render, em vez
    de uma lista de parágrafos soltos e sem estrutura (ADR-0041 fix)."""
    try:
        desenhos = page.get_drawings()
    except Exception:  # noqa: BLE001
        return []
    retangulos = [fitz.Rect(d["rect"]) for d in desenhos if d.get("rect") is not None]
    if not retangulos:
        return []
    regioes = _mesclar_retangulos(retangulos)
    out = []
    for reg in regioes:
        if reg.width < _LARGURA_MIN_REGIAO or reg.height < _ALTURA_MIN_REGIAO:
            continue
        # exige ao menos UMA forma "cheia" (caixa/preenchimento) na região — o
        # que distingue um diagrama (caixas+setas) de uma régua/sublinhado
        # isolado (só linhas finas, sem forma robusta).
        maior_forma = max(
            (r.width * r.height for r in retangulos if reg.intersects(r)), default=0.0
        )
        if maior_forma < _AREA_MIN_DESENHO:
            continue
        if not _tem_subformas(reg, retangulos):
            continue
        if _parece_tabela(reg, retangulos):
            continue
        contidos = [b for b in blocos if b.bbox and _fracao_contida(b.bbox, reg) > 0.6]
        # uma caixa de destaque (título + parágrafo de prosa) também passa nos
        # filtros acima (fundo preenchido, >=2 blocos) — mas rótulos de
        # diagrama são curtos (mesmo passos numerados, ex. "3. Docker pulls
        # busybox image..."); um bloco de PROSA de verdade (frase longa)
        # denuncia que é conteúdo textual, não um rótulo — deixa pra
        # ``_regioes_destaque`` tratar e traduzir em vez de rasterizar em
        # inglês (achado real ao auditar Prometheus Up & Running, ADR-0041 fix).
        if any(len(b.texto.split()) >= _PALAVRAS_MIN_PROSA for b in contidos):
            continue
        if len(contidos) >= 2:
            out.append((reg, contidos))
    return out


def _injetar_string_set(html_el: str, valor: str) -> str:
    """Injeta ``string-set: folio '<valor>'`` no PRIMEIRO elemento renderizado da
    página, em vez de um `<span>` vazio separado. Um `<span>` vazio, quando a
    página anterior já está 100% cheia, pode ser empurrado sozinho pra uma nova
    página pelo WeasyPrint — e a quebra forçada do heading seguinte (h1/h2/h3
    por nível, ADR-0041) então empurra o conteúdo real por MAIS uma página,
    deixando uma página quase em branco entre elas (bug real, achado por
    amostragem visual do Observability Engineering, ADR-0041 fix). Anexar a
    própria declaração ao elemento com conteúdo real elimina essa página
    fantasma, porque o elemento nunca fica "sozinho" — ele sempre carrega
    conteúdo visível junto."""
    decl = f"string-set: folio '{valor}';"
    if 'style="' in html_el:
        return html_el.replace('style="', f'style="{decl}', 1)
    m = re.match(r"^(<[a-zA-Z][a-zA-Z0-9]*)", html_el)
    if not m:
        return html_el
    return html_el[: m.end()] + f' style="{decl}"' + html_el[m.end() :]


def _renderizar_diagrama(page, regiao: fitz.Rect) -> str:
    """Rasteriza a região do diagrama como PNG (data URI) — preserva o desenho
    vetorial (caixas/setas/rótulos) tal como no original; a legenda ao redor
    segue traduzida normalmente como texto (ADR-0041 fix)."""
    pix = page.get_pixmap(clip=regiao, matrix=fitz.Matrix(2, 2))
    return "data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode()


def _regioes_destaque(page, blocos: list, ids_diagrama: set) -> list[tuple]:
    """Detecta caixas de destaque (callout/tip/nota) do original: uma forma com
    PREENCHIMENTO (fundo colorido/cinza) que envolve prosa — diferente de um
    diagrama (rótulos curtos e desconexos, ``_regioes_diagrama``): aqui exige
    pelo menos um bloco de frase de verdade (>=6 palavras). Os blocos
    continuam sendo traduzidos/renderizados normalmente como ``<p>``/``<li>``
    — só ganham um contêiner com fundo/borda (``.destaque``) em vez de se
    perderem soltos no corpo (ADR-0041 fix)."""
    try:
        desenhos = page.get_drawings()
    except Exception:  # noqa: BLE001
        return []
    # réguas/sublinhados finos (ex. a linha colorida sob um título de capítulo)
    # também têm preenchimento, mas não são o fundo de uma caixa de destaque —
    # excluir evita que se juntem (por proximidade) ao fundo cinza decorativo
    # do numeral "fantasma" do capítulo e formem uma região que por acaso cobre
    # o BLOCO DO TÍTULO, fazendo o título de capítulo virar uma caixa de
    # destaque (achado real ao auditar Kubernetes in Action, ADR-0041 fix).
    retangulos = [
        fitz.Rect(d["rect"])
        for d in desenhos
        if d.get("rect") is not None
        and d.get("fill") is not None
        and min(fitz.Rect(d["rect"]).width, fitz.Rect(d["rect"]).height) > _ESPESSURA_MAX_REGRA
    ]
    if not retangulos:
        return []
    regioes = _mesclar_retangulos(retangulos)
    out = []
    for reg in regioes:
        if reg.width < _LARGURA_MIN_REGIAO or reg.height < _ALTURA_MIN_REGIAO:
            continue
        contidos = [
            b
            for b in blocos
            if b.bbox and b.id not in ids_diagrama and _fracao_contida(b.bbox, reg) > 0.6
        ]
        if not contidos:
            continue
        tem_frase = any(len(b.texto.split()) >= 6 for b in contidos)
        if tem_frase:
            contidos.sort(key=lambda b: b.bbox[1])
            out.append((reg, contidos))
    return out


_CSS = """
/* folio do original: régua fina no rodapé + "página | capítulo" (nº na borda
   externa, alternando recto/verso) — o "chartzinho" com capítulo + página. */
@page {{ size: {pw:.0f}pt {ph:.0f}pt;
         margin: {top:.0f}pt {right:.0f}pt {bottom:.0f}pt {left:.0f}pt;
         @bottom-left {{ border-top: 0.6pt solid #000; padding-top: 4pt; vertical-align: top;
                         font: 600 8.5pt 'Liberation Sans Narrow','Liberation Sans',sans-serif;
                         color: #222; }}
         @bottom-center {{ content: ""; border-top: 0.6pt solid #000; }}
         @bottom-right {{ border-top: 0.6pt solid #000; padding-top: 4pt; vertical-align: top;
                          font: 600 8.5pt 'Liberation Sans Narrow','Liberation Sans',sans-serif;
                          color: #222; }} }}
/* verso (par): nº à esquerda, capítulo à direita. recto (ímpar): o inverso. */
@page :left  {{ @bottom-left  {{ content: string(folio); }}
                @bottom-right {{ content: string(cap); }} }}
@page :right {{ @bottom-left  {{ content: string(cap); }}
                @bottom-right {{ content: string(folio); }} }}
{font_faces}
html {{ font-family: 'Liberation Serif','DejaVu Serif','Times New Roman',Georgia,serif; }}
body {{ text-align: justify; hyphens: auto; line-height: 1.34; color: #000; }}
/* orphans/widows 3: um parágrafo nunca começa/termina com 1 linha solta na quebra */
p {{ margin: 0 0 .45em 0; orphans: 3; widows: 3; }}
h1,h2,h3 {{ text-align: left; font-weight: bold; margin: .7em 0 .28em; line-height: 1.2;
            page-break-after: avoid; break-after: avoid; }}
/* o título de capítulo (h1) vira a cabeça de página corrente; quebra por nível
   é calculada por documento (ADR-0041) — não é uma regra fixa. */
h1 {{ string-set: cap content(); break-before: {h1_break}; }}
h2 {{ break-before: {h2_break}; }}
h3 {{ break-before: {h3_break}; }}
ul {{ margin: .3em 0 .55em 1.3em; padding: 0; }}
li {{ margin: .12em 0; }}
pre {{ font-family: 'Liberation Mono','DejaVu Sans Mono',monospace; white-space: pre-wrap;
       background: #f6f6f6; border-radius: 4px; padding: 6px 9px; font-size: 8.5pt;
       text-align: left; line-height: 1.3; page-break-inside: avoid; }}
figure {{ margin: .6em 0; text-align: center; page-break-inside: avoid; }}
img {{ max-width: 100%; }}
.it {{ font-style: italic; }} .bd {{ font-weight: bold; }}
.rodape-nativo {{ margin-top: 1.1em; padding-top: .3em; border-top: 0.6pt solid #999;
                  font-size: 8pt; line-height: 1.25; }}
.rodape-nativo p {{ margin: .12em 0; }}
/* caixa de destaque (callout/tip/nota do original, ADR-0041) */
.destaque {{ background: #f0f0f0; border: 0.6pt solid #ccc; border-radius: 4px;
             padding: 10px 14px; margin: .6em 0; page-break-inside: avoid; }}
.destaque p, .destaque li {{ margin: .2em 0; }}
a {{ text-decoration: underline; }}
/* sumário: rótulo + leader de pontos + número de página recalculado (E9-09) */
p.toc {{ text-align: left; margin: .12em 0; }}
p.toc a {{ color: #000; }}
p.toc a::after {{ content: leader('.') ' ' target-counter(attr(href url), page); color: #000; }}
.tocnum::before {{ content: leader('.') ' '; }}
"""


def _e_folio(b, ph: float) -> bool:
    """Bloco de margem (cabeça de página / número de página): linha curta na faixa
    superior/inferior. Não entra no corpo — vira elemento de margem repetido no CSS."""
    if not b.bbox or not b.texto:
        return False
    y0, y1 = b.bbox[1], b.bbox[3]
    curto = len(b.texto) < 90
    uma_linha = (y1 - y0) < 26
    na_margem = y0 < ph * 0.075 or y1 > ph * 0.925
    return curto and uma_linha and na_margem


def _abre_pagina(b, blocos: list, ph: float) -> bool:
    """``True`` se ``b`` é o primeiro bloco de conteúdo (não-fólio) da página,
    perto do topo — usado pra medir se um nível de heading tende a abrir página
    nova no documento original (ADR-0041)."""
    uteis = [x for x in blocos if x.bbox and not _e_folio(x, ph)]
    if not uteis:
        return False
    primeiro = min(uteis, key=lambda x: x.bbox[1])
    return primeiro.bbox == b.bbox and b.bbox[1] <= ph * 0.20


_RE_FOLIO_NUM = re.compile(r"\b\d+\b")
_RE_FOLIO_ROMANO = re.compile(r"\b[ivxlcdm]+\b", re.IGNORECASE)


def _valor_folio(b) -> str | None:
    """Só o número (arábico ou romano) do bloco de fólio — não o rótulo de
    capítulo/seção que o acompanha (esse já vira o cabeçalho corrente ``cap``,
    E9-09). ``None`` se o bloco não tiver número (ADR-0041)."""
    if not b.texto:
        return None
    m = _RE_FOLIO_NUM.search(b.texto)
    if m:
        return m.group(0)
    m = _RE_FOLIO_ROMANO.search(b.texto)
    return m.group(0) if m else None


_RAZAO_MAX_TAMANHO_RODAPE = 0.9  # nota de rodapé é tipograficamente menor que o corpo


def _e_rodape_nativo(b, ph: float, body_sz: float | None = None) -> bool:
    """Nota de rodapé do próprio PDF (não fólio): frase de várias palavras na
    faixa inferior da página, acima da faixa mais estreita onde o fólio mora
    (ADR-0041). Fólio é um rótulo curto (`_e_folio`); nota é prosa.

    ``body_sz`` (ADR-0041 fix, achado ao auditar Observability Engineering):
    sem checar o tamanho da fonte, o ÚLTIMO PARÁGRAFO normal de uma seção —
    que a tradução, ao crescer, empurra pra faixa inferior da página com
    facilidade — é confundido com nota de rodapé (ganha régua + estilo de
    rodapé por engano). Nota de rodapé de verdade é tipograficamente MENOR que
    o corpo (ex.: 8pt vs. 10.5pt nesse livro); texto do mesmo tamanho do corpo
    não é nota, é só o final de um parágrafo comum. ``None`` (chamador não
    informou o tamanho do corpo) preserva a heurística antiga só por posição."""
    if not b.bbox or not b.texto:
        return False
    y1 = b.bbox[3]
    na_faixa_inferior = ph * 0.70 < y1 <= ph * 0.92
    tem_frase = len(b.texto.split()) >= 4
    if not (na_faixa_inferior and tem_frase and not _e_folio(b, ph)):
        return False
    if body_sz is None or not getattr(b, "spans", None):
        return True
    return _estilo(b)["size"] < body_sz * _RAZAO_MAX_TAMANHO_RODAPE


def _comeca_minuscula(texto: str) -> bool:
    """``True`` se o primeiro caractere alfabético do texto é minúsculo — sinal
    de que o bloco é CONTINUAÇÃO de algo cortado pela quebra de página original
    (parágrafo normal e nota de rodapé sempre começam com maiúscula/número).
    Usado pra detectar nota de rodapé que estoura pro topo da página seguinte,
    fora da faixa de margem que `_e_rodape_nativo` reconhece (ADR-0041 fix)."""
    for ch in texto:
        if ch.isalpha():
            return ch.islower()
    return False


_BULLETS = ("•", "◦", "▪", "-", "–", "—", "*")
_RE_LISTA_NUM = re.compile(r"^\s*(\d+[.)]|[a-zA-Z][.)])\s+")


def _e_marcador_bullet(ch: str) -> bool:
    """Um marcador de item de lista: bullet Unicode comum OU um glifo de fonte
    de ícone (Wingdings/Symbol, ex. ````) — área de Uso Privado
    (U+E000–U+F8FF). Editoras (Manning, entre outras) usam glifos PUA pro
    "quadrado" de bullet em caixas como "This chapter covers"; sem isso o
    item nunca vira ``<li>`` — fica um `<p>` solto com o glifo cru, sem
    marcador visível (achado real ao auditar Kubernetes in Action, ADR-0041
    fix)."""
    return ch in _BULLETS or 0xE000 <= ord(ch) <= 0xF8FF


def _e_lista(texto: str) -> bool:
    t = texto.lstrip()
    return len(t) > 2 and _e_marcador_bullet(t[0]) and t[1:2] in (" ", "\t")


def _tipo_lista(texto: str) -> str | None:
    """``"ul"``/``"ol"``/``None`` conforme o marcador do item (ADR-0041)."""
    t = texto.lstrip()
    if len(t) > 2 and _e_marcador_bullet(t[0]) and t[1:2] in (" ", "\t"):
        return "ul"
    if _RE_LISTA_NUM.match(texto):
        return "ol"
    return None


def _anchor(pi: int, bid: int) -> str:
    return f"u{pi}_{bid}"


def _links_pagina(page) -> list[tuple]:
    """(rect_origem, tipo, alvo) dos hyperlinks da página. tipo: 'uri' | 'goto'."""
    out = []
    try:
        for lk in page.get_links():
            r = lk.get("from")
            if r is None:
                continue
            if lk.get("kind") == fitz.LINK_URI and lk.get("uri"):
                out.append((r, "uri", lk["uri"]))
            # GOTO e NAMED (destino nomeado, ex.: sumário) — ambos já trazem page+to.
            elif lk.get("kind") in (fitz.LINK_GOTO, fitz.LINK_NAMED) and lk.get("page", -1) >= 0:
                out.append((r, "goto", (lk.get("page", -1), lk.get("to"))))
    except Exception:  # noqa: BLE001
        pass
    return out


def _alvo_goto(paginas: dict, pageidx: int, pt) -> str | None:
    """Âncora do bloco mais próximo do destino de um link interno (na repaginação)."""
    entry = paginas.get(pageidx)
    if not entry:
        return None
    blocos = [b for b in entry[0] if b.bbox and (not b.skip or _estilo(b)["mono"])]
    if not blocos:
        return None
    y = getattr(pt, "y", None)
    alvo = blocos[0] if y is None else min(blocos, key=lambda b: abs(b.bbox[1] - y))
    return _anchor(pageidx, alvo.id)


def _goto_anchors(b, links: list[tuple], paginas: dict) -> list:
    """Âncoras dos links internos que cobrem o bloco, em ordem de leitura (p/ TOC)."""
    if not b.bbox:
        return []
    bx = fitz.Rect(b.bbox)
    gl = []
    for r, tipo, alvo in links:
        if tipo != "goto":
            continue
        inter = bx & r
        if not inter.is_empty and inter.width * inter.height > 0:
            gl.append((r.y0, alvo))
    gl.sort(key=lambda x: x[0])
    return [_alvo_goto(paginas, pg, pt) for _y, (pg, pt) in gl]


def _entradas_toc(texto: str) -> list[tuple]:
    """Quebra 'Título 12 Outro Título 34 …' em [(título, nº|None), …]."""
    ent, buf = [], []
    for tok in texto.split():
        if tok.isdigit() and buf:
            ent.append((" ".join(buf), tok))
            buf = []
        else:
            buf.append(tok)
    if buf:
        ent.append((" ".join(buf), None))
    return ent


def _elemento_toc(texto: str, anchors: list) -> str:
    """Um bloco de sumário mesclado → uma linha por entrada, com link + página
    recalculada (target-counter). Fallback: mostra o número original (E9-09)."""
    linhas = []
    for i, (titulo, num) in enumerate(_entradas_toc(texto)):
        alvo = anchors[i] if i < len(anchors) else None
        if alvo:
            linhas.append(f'<p class="toc"><a href="#{alvo}">{_e(titulo)}</a></p>')
        else:
            n = f' <span class="tocnum">{_e(num)}</span>' if num else ""
            linhas.append(f'<p class="toc">{_e(titulo)}{n}</p>')
    return "\n".join(linhas)


_FRACAO_MIN_LINK = 0.5  # ADR-0041 fix: ver docstring de _link_do_bloco


def _link_do_bloco(b, links: list[tuple]):
    """Link cujo retângulo mais cobre o bloco (ou None). Exige que o link cubra
    ao menos ``_FRACAO_MIN_LINK`` da área do bloco — senão uma URL de UMA linha
    dentro de um parágrafo de várias linhas faria o PARÁGRAFO INTEIRO virar
    `<a>` (bug real: título/legenda de 1 linha cujo link já cobre quase tudo
    continua funcionando; só o caso "link pontual dentro de prosa" é rejeitado,
    ADR-0041 fix)."""
    if not b.bbox or not links:
        return None
    bx = fitz.Rect(b.bbox)
    area_bloco = bx.width * bx.height
    if area_bloco <= 0:
        return None
    melhor, area = None, 0.0
    for r, tipo, alvo in links:
        inter = bx & r
        a = 0.0 if inter.is_empty else inter.width * inter.height
        if a > area:
            area, melhor = a, (tipo, alvo)
    if area / area_bloco < _FRACAO_MIN_LINK:
        return None
    return melhor if area > 0 else None


_FALLBACK_FONTE = "'Liberation Serif','DejaVu Serif','Times New Roman',Georgia,serif"


def _elemento(
    b, texto: str, est: dict, body_sz: float, clusters: list[float], anchor: str = "", link=None
) -> str:
    """HTML de um bloco conforme papel/estilo, com âncora, hyperlink e fonte
    real (ADR-0041)."""
    cor = _cor_hex(est["color"])
    cor_css = "" if cor in ("#000000", "#000") else f"color:{cor};"
    fonte_css = f"font-family:'{_e(est['font'])}',{_FALLBACK_FONTE};" if est["font"] else ""
    ida = f' id="{anchor}"' if anchor else ""
    if est["mono"]:
        return f"<pre{ida}>{_e(b.texto)}</pre>"  # código: original, verbatim
    # sumário: link interno + linha terminando em nº de página → regenera a página.
    if link and link[0] == "goto" and link[1] and _RE_TOC_FIM.search(texto):
        rotulo = _e(_RE_TOC_FIM.sub("", texto).rstrip(" .·•…-–—\t"))
        return f'<p class="toc"{ida}><a href="#{link[1]}">{rotulo}</a></p>'
    conteudo = converter_enfase(texto, _e)
    if est["bold"]:
        conteudo = f'<span class="bd">{conteudo}</span>'
    if est["italic"]:
        conteudo = f'<span class="it">{conteudo}</span>'
    if link:  # hyperlink normal: URI externa ou goto interno
        href = link[1] if link[0] == "uri" else (f"#{link[1]}" if link[1] else "")
        if href:
            conteudo = f'<a href="{_e(href)}">{conteudo}</a>'
    sz = est["size"]
    nivel = nivel_titulo(sz, clusters) if len(texto.split()) <= 14 else None
    if nivel:
        style = f"font-size:{sz:.1f}pt;{cor_css}{fonte_css}"
        return f'<{nivel}{ida} style="{style}">{conteudo}</{nivel}>'
    tipo_li = _tipo_lista(b.texto)
    if tipo_li == "ul":
        bruto = texto.lstrip()
        if bruto[:1] and _e_marcador_bullet(bruto[0]):
            bruto = bruto[1:].lstrip()
        item = converter_enfase(bruto, _e)
        if est["italic"]:
            item = f'<span class="it">{item}</span>'
        return f'<li{ida} style="font-size:{sz:.1f}pt;{cor_css}{fonte_css}">{item}</li>'
    if tipo_li == "ol":
        bruto = _RE_LISTA_NUM.sub("", texto.lstrip(), count=1)
        item = converter_enfase(bruto, _e)
        if est["italic"]:
            item = f'<span class="it">{item}</span>'
        return f'<li{ida} style="font-size:{sz:.1f}pt;{cor_css}{fonte_css}">{item}</li>'
    return f'<p{ida} style="font-size:{sz:.1f}pt;{cor_css}{fonte_css}">{conteudo}</p>'


def montar_html(doc, paginas: dict, geo: dict) -> str:
    """Constrói o HTML do documento inteiro em ordem de leitura (texto + imagens)."""
    # tamanho do corpo = mediana dos tamanhos dos blocos de texto longos.
    ph = geo["ph"]
    sizes = []
    for _idx, (blocos, _tr) in paginas.items():
        for b in blocos:
            if not b.skip and len(b.texto) > 60 and not _e_folio(b, ph):
                sizes.append(_estilo(b)["size"])
    body_sz = statistics.median(sizes) if sizes else 11.0

    tamanhos_doc = [
        _estilo(b)["size"]
        for _idx, (blocos, _tr) in paginas.items()
        for b in blocos
        if b.bbox and not b.skip and not _e_folio(b, ph)
    ]
    clusters = clusters_titulo(tamanhos_doc, body_sz)

    ocorrencias: dict[str, list[bool]] = {"h1": [], "h2": [], "h3": []}
    for _idx, (blocos, _tr) in paginas.items():
        nivel_anterior: str | None = None
        for b in sorted(
            (x for x in blocos if x.bbox and not x.skip and not _e_folio(x, ph)),
            key=lambda x: x.bbox[1],
        ):
            nivel = nivel_titulo(_estilo(b)["size"], clusters)
            eh_titulo = nivel and len(b.texto.split()) <= 14
            # título longo quebrado em várias linhas (cada linha = 1 bloco) conta
            # como UMA única ocorrência (a primeira) — senão a taxa de abertura
            # de página é diluída pela metade+ em qualquer título com 2+ linhas,
            # e o nível nunca atinge o limiar de quebra forçada (achado real:
            # Kubernetes in Action tem 18 capítulos, boa parte com título de
            # 2-3 linhas, ADR-0041 fix).
            if eh_titulo and nivel != nivel_anterior:
                ocorrencias[nivel].append(_abre_pagina(b, blocos, ph))
            nivel_anterior = nivel if eh_titulo else None
    quebra = taxa_abre_pagina(ocorrencias)

    partes: list[str] = []
    lista_aberta: str | None = None
    pendente_notas: list[str] = []
    heading_aberto: str | None = None

    def _tag_heading(el: str) -> str | None:
        for tag in ("h1", "h2", "h3"):
            if el.startswith(f"<{tag}"):
                return tag
        return None

    def fecha_lista():
        nonlocal lista_aberta
        if lista_aberta:
            partes.append("</ol>" if lista_aberta == "ol" else "</ul>")
            lista_aberta = None

    def flush_notas():
        if pendente_notas:
            corpo_notas = "".join(f"<p>{converter_enfase(t, _e)}</p>" for t in pendente_notas)
            partes.append(f'<div class="rodape-nativo">{corpo_notas}</div>')
            pendente_notas.clear()

    for idx in sorted(paginas):
        blocos, traducoes = paginas[idx]
        page = doc[idx]
        links = _links_pagina(page)
        folio_blocos = [b for b in blocos if b.bbox and _e_folio(b, ph)]
        valor_folio_pagina = None
        if folio_blocos:
            alvo = max(folio_blocos, key=lambda b: b.bbox[3])  # mais perto do fundo
            valor_folio_pagina = _valor_folio(alvo)
        # diagramas vetoriais (caixas/setas + rótulos, sem imagem raster): a
        # região inteira vira UMA imagem rasterizada — evita despejar os rótulos
        # como parágrafos soltos e sem estrutura (ADR-0041 fix).
        diagramas = _regioes_diagrama(page, blocos)
        blocos_em_diagrama = {b.id for _reg, contidos in diagramas for b in contidos}
        # caixas de destaque (callout/tip/nota, fundo colorido): os blocos
        # continuam traduzidos normalmente, só ganham um contêiner (ADR-0041 fix).
        destaques = _regioes_destaque(page, blocos, blocos_em_diagrama)
        blocos_em_destaque = {b.id for _reg, contidos in destaques for b in contidos}

        # continuação de nota de rodapé que estourou pro topo desta página (fora
        # da faixa de margem que _e_rodape_nativo reconhece): gruda no final da
        # última nota pendente em vez de vazar como parágrafo comum solto no
        # meio do corpo (ADR-0041 fix).
        id_continuacao = None
        if pendente_notas:
            uteis_ordem = sorted(
                (
                    b
                    for b in blocos
                    if b.bbox
                    and not b.skip
                    and not _e_folio(b, ph)
                    and b.id not in blocos_em_diagrama
                    and b.id not in blocos_em_destaque
                ),
                key=lambda b: b.bbox[1],
            )
            if uteis_ordem:
                primeiro = uteis_ordem[0]
                texto_primeiro = traducoes.get(primeiro.id) or primeiro.texto
                if texto_primeiro and _comeca_minuscula(texto_primeiro):
                    pendente_notas[-1] = f"{pendente_notas[-1]} {texto_primeiro}"
                    id_continuacao = primeiro.id
        flush_notas()
        marca_pagina = len(partes)  # 1º elemento desta página (p/ injetar o fólio, ADR-0041)

        # itens da página (blocos de texto + imagens) em ordem de leitura vertical.
        itens: list[tuple] = []
        for b in blocos:
            if b.id in blocos_em_diagrama or b.id in blocos_em_destaque or b.id == id_continuacao:
                continue
            if not (not b.skip or _estilo(b)["mono"]):
                continue
            if _e_folio(b, ph):
                continue
            if not _estilo(b)["mono"] and _e_rodape_nativo(b, ph, body_sz):
                pendente_notas.append(traducoes.get(b.id) or b.texto)
                continue
            itens.append((b.bbox[1] if b.bbox else 0.0, "b", b))
        for y0, w, h, uri in _imagens(doc, page):
            itens.append((y0, "img", (w, h, uri)))
        for reg, _contidos in diagramas:
            itens.append((reg.y0, "img", (reg.width, reg.height, _renderizar_diagrama(page, reg))))
        for reg, contidos in destaques:
            itens.append((reg.y0, "destaque", contidos))
        itens.sort(key=lambda it: it[0])

        for _y, tipo, obj in itens:
            if tipo == "img":
                w, h, uri = obj
                tw = geo["pw"] - geo["left"] - geo["right"]
                pct = max(15, min(100, int(w / tw * 100))) if tw else 100
                fecha_lista()
                heading_aberto = None
                partes.append(f'<figure><img src="{uri}" style="width:{pct}%"></figure>')
                continue
            if tipo == "destaque":
                fecha_lista()
                heading_aberto = None
                partes.append('<div class="destaque">')
                lista_local: str | None = None
                for cb in obj:
                    cest = _estilo(cb)
                    ctexto = traducoes.get(cb.id) or cb.texto
                    clink = _link_do_bloco(cb, links)
                    if clink and clink[0] == "goto":
                        destpage, pt = clink[1]
                        alvo = _alvo_goto(paginas, destpage, pt)
                        clink = ("goto", alvo) if alvo else None
                    cel = _elemento(
                        cb, ctexto, cest, body_sz, clusters, anchor=_anchor(idx, cb.id), link=clink
                    )
                    ctipo_li = _tipo_lista(cb.texto) if not cest["mono"] else None
                    # continuação de um item de lista quebrado em 2+ linhas (cada
                    # linha é um bloco próprio): a linha de continuação não tem
                    # marcador de bullet — gruda no <li> anterior em vez de virar
                    # um <p> solto (que perdia o estilo/indentação da lista e
                    # quebrava a frase ao meio, achado real ao auditar Kubernetes
                    # in Action, ADR-0041 fix).
                    if (
                        not ctipo_li
                        and lista_local
                        and partes
                        and partes[-1].startswith("<li")
                        and _comeca_minuscula(ctexto)
                    ):
                        extra = converter_enfase(ctexto, _e)
                        if cest["italic"]:
                            extra = f'<span class="it">{extra}</span>'
                        partes[-1] = partes[-1].removesuffix("</li>") + " " + extra + "</li>"
                        continue
                    if ctipo_li and cel.startswith("<li"):
                        if lista_local and lista_local != ctipo_li:
                            partes.append("</ol>" if lista_local == "ol" else "</ul>")
                            lista_local = None
                        if not lista_local:
                            partes.append("<ol>" if ctipo_li == "ol" else "<ul>")
                            lista_local = ctipo_li
                    elif lista_local:
                        partes.append("</ol>" if lista_local == "ol" else "</ul>")
                        lista_local = None
                    partes.append(cel)
                if lista_local:
                    partes.append("</ol>" if lista_local == "ol" else "</ul>")
                partes.append("</div>")
                continue
            b = obj
            est = _estilo(b)
            # código/imutável e sem tradução: cai no original — nunca descarta bloco (ADR-0041).
            texto = traducoes.get(b.id) or b.texto
            # sumário mesclado (bloco com ≥2 links internos): uma linha por entrada.
            if not est["mono"]:
                ganchors = _goto_anchors(b, links, paginas)
                if len(ganchors) >= 2:
                    fecha_lista()
                    heading_aberto = None
                    partes.append(_elemento_toc(texto, ganchors))
                    continue
            link = _link_do_bloco(b, links)
            if link and link[0] == "goto":  # resolve destino → âncora na repaginação
                destpage, pt = link[1]
                alvo = _alvo_goto(paginas, destpage, pt)
                link = ("goto", alvo) if alvo else None
            tipo_li = _tipo_lista(b.texto) if not est["mono"] else None
            el = _elemento(b, texto, est, body_sz, clusters, anchor=_anchor(idx, b.id), link=link)
            tag_atual = _tag_heading(el)
            # título de capítulo quebrado em 2+ linhas (cada linha um bloco próprio
            # no PDF) vira 1 <hN> por linha — a regra "esse nível SEMPRE abre
            # página" (ADR-0041) então dispara em CADA linha, deixando a 1ª
            # sozinha numa página e empurrando o resto do título pra próxima
            # (achado real: "First steps with Docker" / "and Kubernetes" viravam
            # 2 páginas). Linha de heading adjacente ao MESMO nível gruda na
            # anterior em vez de virar um <hN> novo.
            if tag_atual and tag_atual == heading_aberto:
                fechamento = f"</{tag_atual}>"
                conteudo_extra = el[el.index(">") + 1 : -len(fechamento)]
                partes[-1] = partes[-1].removesuffix(fechamento) + " " + conteudo_extra + fechamento
                continue
            if tipo_li and el.startswith("<li"):
                heading_aberto = None
                if lista_aberta and lista_aberta != tipo_li:
                    fecha_lista()
                if not lista_aberta:
                    partes.append("<ol>" if tipo_li == "ol" else "<ul>")
                    lista_aberta = tipo_li
                partes.append(el)
            else:
                fecha_lista()
                heading_aberto = tag_atual
                partes.append(el)
        fecha_lista()
        if valor_folio_pagina and len(partes) > marca_pagina:
            partes[marca_pagina] = _injetar_string_set(partes[marca_pagina], _e(valor_folio_pagina))
    flush_notas()  # nota(s) pendente(s) da última página (ADR-0041)

    fontes = extrair_fontes(doc)
    geo_css = {
        **geo,
        "h1_break": "page" if quebra.get("h1") else "auto",
        "h2_break": "page" if quebra.get("h2") else "auto",
        "h3_break": "page" if quebra.get("h3") else "auto",
        "font_faces": gerar_font_faces(fontes),
    }
    css = _CSS.format(**geo_css)
    corpo = "\n".join(partes)
    return (
        f'<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">'
        f"<style>{css}</style></head><body>{corpo}</body></html>"
    )


def remontar_editorial_html(doc, paginas: dict, destino: str, cfg=None) -> None:
    """Renderiza o PDF traduzido pelo motor editorial (ADR-0036). Levanta se o
    WeasyPrint não estiver disponível (o chamador pode cair no motor pymupdf)."""
    if weasyprint is None:
        raise RuntimeError("weasyprint não instalado — use render_motor='pymupdf'")
    geo = _geometria(doc, paginas)
    html = montar_html(doc, paginas, geo)
    weasyprint.HTML(string=html).write_pdf(destino)
