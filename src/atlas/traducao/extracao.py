"""Extração de blocos tradutíveis de uma página PDF (ADR-0030, estágio 1).

Usa ``page.get_text("dict")`` do PyMuPDF. Agrupa spans em blocos (unidades de
tradução). Marca ``skip=True`` para código (fonte monospace) e blocos sem letras.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from atlas.traducao.tipografia import bloco_e_mono

_FLAG_ITALIC = 1 << 1
_FLAG_BOLD = 1 << 4


@dataclass
class Span:
    text: str
    bbox: tuple[float, float, float, float]
    font: str
    size: float
    color: int
    flags: int


@dataclass
class BlocoTraducao:
    id: int
    pagina: int
    bbox: tuple[float, float, float, float]
    texto: str
    spans: list[Span] = field(default_factory=list)
    skip: bool = False
    papel: str = "encaixado"  # ADR-0033: prosa | encaixado | imutavel | indice
    indent: float = 0.0  # recuo (pt) dentro da coluna — só p/ entrada de índice


def _tem_letra(texto: str) -> bool:
    return any(c.isalpha() for c in texto)


def _bold_span(s: Span) -> bool:
    return bool(s.flags & _FLAG_BOLD) or "bold" in s.font.lower() or "black" in s.font.lower()


def _italic_span(s: Span) -> bool:
    return bool(s.flags & _FLAG_ITALIC) or "italic" in s.font.lower() or "oblique" in s.font.lower()


def _precisa_espaco(anterior: Span, atual: Span) -> bool:
    """``True`` se deve haver um espaço entre dois spans consecutivos: linha
    diferente, folga visível no eixo x, OU um dos dois já tem espaço embutido
    no próprio texto (PyMuPDF às vezes bota o espaço DENTRO do span seguinte,
    não como gap real entre bboxes — ex. tipografia versalete/small-caps
    "PART 3": o span " 3" começa colado no "ART" anterior, mas o próprio texto
    já tem o espaço embutido; achado real, auditoria visual, Kubernetes in
    Action). Sem essa checagem, o espaço embutido some no ``.strip()`` de cada
    span e nunca é reposto (ADR-0041 fix)."""
    mesma_linha = abs(atual.bbox[1] - anterior.bbox[1]) < 2.0
    gap = atual.bbox[0] - anterior.bbox[2]
    espaco_embutido = atual.text[:1] in (" ", "\t") or anterior.text[-1:] in (" ", "\t")
    return (not mesma_linha) or gap > 1.0 or espaco_embutido


def _juntar_spans(spans: list[Span]) -> str:
    """Junta o texto dos spans preservando o espaçamento REAL do PDF: só insere
    espaço entre dois spans quando havia uma folga visível entre eles (mesma
    linha, gap no eixo x) ou quando estão em linhas diferentes. Spans
    adjacentes token-a-token (comum em código com destaque de sintaxe — cada
    token/cor um span) não ganham espaço artificial. Sem isso, ``" ".join``
    simples quebrava código de verdade: ``"http" "." "server"`` virava
    ``"http . server"`` em vez de ``"http.server"`` (ADR-0041 fix)."""
    partes_validas = [s for s in spans if s.text.strip()]
    if not partes_validas:
        return ""
    saida = [partes_validas[0].text.strip()]
    for anterior, atual in zip(partes_validas, partes_validas[1:], strict=False):
        if _precisa_espaco(anterior, atual):
            saida.append(" ")
        saida.append(atual.text.strip())
    return "".join(saida)


def _juntar_linha_mono(spans_linha: list[Span]) -> str:
    """Junta os spans de UMA linha de código (mesma lógica de adjacência
    token-a-token do ``_juntar_spans``, pra sintaxe colorida), mas SEM
    stripar o início — a indentação de um span como ``"  name: foo"`` é
    conteúdo real, não espaço incidental de layout."""
    if not spans_linha:
        return ""
    saida = [spans_linha[0].text]
    for anterior, atual in zip(spans_linha, spans_linha[1:], strict=False):
        gap = atual.bbox[0] - anterior.bbox[2]
        if gap > 1.0:
            saida.append(" ")
        saida.append(atual.text)
    return "".join(saida).rstrip()


def _juntar_linhas_mono(linhas: list[list[Span]]) -> str:
    """Texto VERBATIM de um bloco de código: 1 linha do PDF = 1 linha do
    texto (``\\n`` real), indentação preservada. Achado real (auditoria
    visual, Kubernetes in Action): ``_juntar_spans`` colapsa todas as linhas
    num espaço só — ótimo pra prosa (que reflui), péssimo pra código, que
    virava uma única linha sem indentação/estrutura, ilegível e irreproduzível
    (código é ``skip=True``, nunca traduzido, e vira ``<pre>`` no render —
    precisa ser ipsis litteris, como uma imagem, ADR-0041 fix)."""
    return "\n".join(_juntar_linha_mono(linha) for linha in linhas)


def _marcar_enfase(spans: list[Span]) -> str:
    """Monta o texto do bloco marcando trechos que divergem do estilo dominante
    (negrito/itálico) com marcadores leves (``**b**``/``_i_``) — a tradução é
    instruída a preservá-los (ADR-0041); o render os converte em ``<b>``/``<i>``
    só no trecho, sem perder a ênfase de uma palavra isolada no meio do parágrafo.

    Junta os spans com a MESMA lógica de adjacência do ``_juntar_spans`` (só
    insere espaço quando havia folga real, ou linha diferente) — achado real
    (auditoria visual, Kubernetes in Action): tipografia versalete/small-caps
    é feita variando o TAMANHO por span ("P" maior + "ART" menor, sem gap
    real), e o join fixo em espaço virava "P ART 3 B EYOND" em vez de "PART 3
    BEYOND"."""
    partes_validas = [s for s in spans if s.text.strip()]
    if not partes_validas:
        return ""
    total = sum(max(1, len(s.text)) for s in partes_validas)
    peso_bold = sum(len(s.text) for s in partes_validas if _bold_span(s))
    peso_ital = sum(len(s.text) for s in partes_validas if _italic_span(s))
    dom_bold = peso_bold > total / 2
    dom_ital = peso_ital > total / 2

    def _marcado(s: Span) -> str:
        texto = s.text.strip()
        if _bold_span(s) and not dom_bold:
            texto = f"**{texto}**"
        if _italic_span(s) and not dom_ital:
            texto = f"_{texto}_"
        return texto

    saida = [_marcado(partes_validas[0])]
    for anterior, atual in zip(partes_validas, partes_validas[1:], strict=False):
        if _precisa_espaco(anterior, atual):
            saida.append(" ")
        saida.append(_marcado(atual))
    return "".join(saida)


_PALAVRAS_MIN_TITULO_EMBUTIDO = 3  # mínimo de palavras pro prefixo "parecer" um título
_CHARS_MIN_CORPO_EMBUTIDO = 20  # mínimo de caracteres pro restante "parecer" um parágrafo


def _e_upper(texto: str) -> bool:
    """``True`` se não houver letra minúscula — spans só de pontuação/espaço
    (ex. o "-" de "MULTI-TIER") não têm letra nenhuma e são compatíveis com
    maiúsculo por vacuidade (não devem cortar a sequência de um heading)."""
    return all(c.isupper() for c in texto if c.isalpha())


def _dividir_por_titulo_embutido(spans: list[Span]) -> tuple[list[Span], list[Span]] | None:
    """Um heading "run-in" (versalete colorido, ex. o estilo "SPLITTING MULTI-
    TIER APPS..." da Manning) às vezes fica GRUDADO ao parágrafo seguinte no
    mesmo "bloco" do PyMuPDF — sem quebra de linha real entre eles. Sem
    dividir, o heading nunca vira um elemento próprio: fica mascarado dentro
    do parágrafo (e a cor dominante do bloco inteiro decide, por peso de
    caractere, se o resultado parece "todo azul" ou "todo preto" dependendo de
    qual trecho é mais longo — bug real visto ao auditar Kubernetes in
    Action). Detecta um prefixo de spans TODO MAIÚSCULO com uma cor uniforme
    diferente da cor uniforme do restante — e divide em ``(spans_titulo,
    spans_corpo)``. ``None`` se o bloco não tiver essa forma (a esmagadora
    maioria dos blocos)."""
    partes_validas = [s for s in spans if s.text.strip()]
    if len(partes_validas) < 2:
        return None
    cor0 = partes_validas[0].color
    corte = 0
    for i, s in enumerate(partes_validas):
        if not _e_upper(s.text) or s.color != cor0:
            corte = i
            break
    else:
        return None  # bloco inteiro é maiúsculo/uniforme — não é heading+corpo
    titulo, corpo = partes_validas[:corte], partes_validas[corte:]
    if not corpo or corpo[0].color == cor0:
        return None
    if len({s.color for s in corpo}) != 1:
        return None  # corpo tem que ser uma cor só (senão pode ser link inline, etc.)
    texto_titulo = _juntar_spans(titulo)
    texto_corpo = _juntar_spans(corpo)
    if len(texto_titulo.split()) < _PALAVRAS_MIN_TITULO_EMBUTIDO:
        return None
    if len(texto_corpo) < _CHARS_MIN_CORPO_EMBUTIDO:
        return None
    return titulo, corpo


_PALAVRAS_MAX_ROTULO_CAPITULO = 4  # "CHAPTER 2", "PART I" etc. — rótulo é curto
_SALTO_MIN_TAMANHO_ROTULO = 3.0  # pt — título tem que ser NOTAVELMENTE maior que o rótulo


def _dividir_por_rotulo_capitulo(spans: list[Span]) -> tuple[list[Span], list[Span]] | None:
    """ "CHAPTER N"/"PART N" (rótulo pequeno) grudado ao título do capítulo
    (fonte bem maior) no MESMO bloco do PyMuPDF, sem espaço entre eles (ex.:
    "CHAPTER 2How Debugging Practices Differ..." — achado real, sistemático em
    TODOS os 20 capítulos ao auditar Observability Engineering). Sem dividir,
    o título nunca fica isolado com o tamanho de fonte correto: a mediana do
    bloco fica contaminada pelo rótulo menor, o título não bate com o cluster
    de tamanho dos OUTROS títulos de capítulo do documento, e — sem essa
    consistência — o capítulo deixa de abrir página sozinho (``taxa_abre_pagina``
    depende de um cluster de tamanho consistente pra cada nível de heading).
    Detecta um prefixo de tamanho MENOR seguido de um resto de tamanho MAIOR
    (uniforme, salto de pelo menos ``_SALTO_MIN_TAMANHO_ROTULO`` pt) — divide
    em ``(spans_rotulo, spans_titulo)``. ``None`` se o bloco não tiver essa
    forma (a esmagadora maioria dos blocos)."""
    partes_validas = [s for s in spans if s.text.strip()]
    if len(partes_validas) < 2:
        return None
    tam0 = partes_validas[0].size
    corte = 0
    for i, s in enumerate(partes_validas):
        if abs(s.size - tam0) > 0.5:
            corte = i
            break
    else:
        return None  # bloco inteiro tem um tamanho só — não é rótulo+título
    rotulo, titulo = partes_validas[:corte], partes_validas[corte:]
    if not titulo:
        return None
    tam_titulo = titulo[0].size
    if tam_titulo - tam0 < _SALTO_MIN_TAMANHO_ROTULO:
        return None
    if any(abs(s.size - tam_titulo) > 0.5 for s in titulo):
        return None  # título tem que ser um tamanho só (senão pode não ser isso)
    texto_rotulo = _juntar_spans(rotulo)
    if len(texto_rotulo.split()) > _PALAVRAS_MAX_ROTULO_CAPITULO:
        return None  # rótulo tem que ser curto — "CHAPTER 2", "PART I"
    return rotulo, titulo


def _bbox_uniao_spans(spans: list[Span]) -> tuple[float, float, float, float]:
    x0 = min(s.bbox[0] for s in spans)
    y0 = min(s.bbox[1] for s in spans)
    x1 = max(s.bbox[2] for s in spans)
    y1 = max(s.bbox[3] for s in spans)
    return (x0, y0, x1, y1)


def classificar_papel(bloco: dict, largura_pagina: float) -> str:
    """Classifica o papel do bloco para o render editorial (ADR-0033).

    - ``imutavel``: sem texto tradutível OU código monoespaçado (nunca reflui).
    - ``prosa``: parágrafo largo (≥ metade da página) e multi-linha (≥ 2 linhas) —
      reflui e empurra os blocos seguintes; gera página de continuação quando cresce.
    - ``encaixado`` (default seguro): legenda/label/título de 1 linha — fit-in-place.
    """
    texto = (bloco.get("texto") or "").strip()
    if not texto or bloco.get("mono"):
        return "imutavel"
    x0, _, x1, _ = bloco["bbox"]
    largo = (x1 - x0) >= 0.5 * largura_pagina
    multilinha = bloco.get("n_linhas", 1) >= 2
    if largo and multilinha:
        return "prosa"
    return "encaixado"


def _montar_bloco(
    prox_id: int,
    pagina: int,
    bbox,
    spans: list[Span],
    n_linhas: int,
    largura_pagina: float,
    linhas_spans: list[list[Span]] | None = None,
) -> BlocoTraducao:
    mono = bloco_e_mono(spans)
    if mono and linhas_spans:
        texto = _juntar_linhas_mono(linhas_spans)
        skip = True
    else:
        texto_plano = _juntar_spans(spans)
        skip = mono or not _tem_letra(texto_plano)
        texto = texto_plano if skip else _marcar_enfase(spans)
    papel = classificar_papel(
        {"texto": texto, "bbox": bbox, "n_linhas": n_linhas, "mono": mono}, largura_pagina
    )
    return BlocoTraducao(
        id=prox_id, pagina=pagina, bbox=bbox, texto=texto, spans=spans, skip=skip, papel=papel
    )


_TOLERANCIA_BBOX_DUPLICADO = 0.5  # pt — folga pro arredondamento de ponto flutuante do PDF


def _e_duplicata(span: Span, vistos: list[Span]) -> bool:
    """``True`` se ``span`` repete texto+posição de um span já coletado no
    MESMO bloco (achado real: alguns PDFs desenham o bullet de um item de
    lista DUAS vezes, como uma "linha" extra só com o glifo repetido no MESMO
    bbox — sem filtrar, o `•` extra vaza como um segundo bullet solto no fim
    do item, ADR-0041 fix)."""
    for v in vistos:
        if v.text != span.text:
            continue
        if all(
            abs(a - b) <= _TOLERANCIA_BBOX_DUPLICADO for a, b in zip(v.bbox, span.bbox, strict=True)
        ):
            return True
    return False


_RE_FIM_PAGINA_IDX = re.compile(r"\d[\d\s,;.–—-]*$")


def _termina_com_pagina(texto: str) -> bool:
    """``True`` se a linha termina numa referência de página (número/faixa) — o
    fim de uma entrada de índice remissivo."""
    return bool(_RE_FIM_PAGINA_IDX.search(texto.strip()))


def agrupar_entradas_indice(
    linhas: list[tuple[float, float, str]], tol: float = 3.0
) -> list[tuple[float, float, str]]:
    """Agrupa as LINHAS de uma coluna do índice remissivo em ENTRADAS lógicas
    (termo + sub-entrada + refs de página), juntando as linhas de continuação
    (quebradas pela largura estreita da coluna) de volta na entrada. Uma entrada
    fecha quando termina numa referência de página; um termo principal (no recuo
    MÍNIMO da coluna) é entrada própria — não gruda com a sub-entrada seguinte.

    ``linhas`` = ``[(x0, y0, texto)]`` em ordem de leitura (y crescente). Devolve
    ``[(x0, y0, texto)]`` da 1ª linha de cada entrada — o x0 vira o nível de
    indentação no render. Sem isso o índice saía fragmentado, linha por linha,
    cada fragmento traduzido solto e ilegível (achado real, Kubernetes in
    Action)."""
    linhas = [(x, y, t.strip()) for x, y, t in linhas if t.strip()]
    if not linhas:
        return []
    min_x = min(round(x) for x, _, _ in linhas)
    entradas: list[tuple[float, float, str]] = []
    cur_x, cur_y, cur_t = linhas[0]
    for x, y, txt in linhas[1:]:
        junta = not _termina_com_pagina(cur_t) and round(cur_x) > min_x and x > cur_x + tol
        if junta:
            cur_t = f"{cur_t} {txt}"
        else:
            entradas.append((cur_x, cur_y, cur_t))
            cur_x, cur_y, cur_t = x, y, txt
    entradas.append((cur_x, cur_y, cur_t))
    return entradas


def extrair_pagina(page, pagina: int) -> list[BlocoTraducao]:
    d = page.get_text("dict")
    blocos: list[BlocoTraducao] = []
    prox_id = 0
    for bloco in d.get("blocks", []):
        if "lines" not in bloco:  # bloco de imagem — ignora
            continue
        spans: list[Span] = []
        linhas_spans: list[list[Span]] = []
        for linha in bloco["lines"]:
            linha_atual: list[Span] = []
            for s in linha.get("spans", []):
                candidato = Span(
                    text=s["text"],
                    bbox=tuple(s["bbox"]),
                    font=s.get("font", ""),
                    size=s.get("size", 0.0),
                    color=s.get("color", 0),
                    flags=s.get("flags", 0),
                )
                if _e_duplicata(candidato, spans):
                    continue
                spans.append(candidato)
                linha_atual.append(candidato)
            if linha_atual:
                linhas_spans.append(linha_atual)
        if not spans:
            continue
        divisao_rotulo = _dividir_por_rotulo_capitulo(spans)
        if divisao_rotulo:
            rotulo_spans, titulo_spans = divisao_rotulo
            bloco_rotulo = _montar_bloco(
                prox_id, pagina, _bbox_uniao_spans(rotulo_spans), rotulo_spans, 1, page.rect.width
            )
            # marca o rótulo pra nunca ficar sozinho no fim da página anterior
            # quando o título (que abre página sozinho, ADR-0041) pula pra
            # próxima — rótulo e título têm que viajar juntos (ver _elemento).
            bloco_rotulo.papel = "rotulo_capitulo"
            blocos.append(bloco_rotulo)
            prox_id += 1
            blocos.append(
                _montar_bloco(
                    prox_id,
                    pagina,
                    _bbox_uniao_spans(titulo_spans),
                    titulo_spans,
                    1,
                    page.rect.width,
                )
            )
            prox_id += 1
            continue
        divisao = _dividir_por_titulo_embutido(spans)
        if divisao:
            for sub_spans in divisao:
                blocos.append(
                    _montar_bloco(
                        prox_id,
                        pagina,
                        _bbox_uniao_spans(sub_spans),
                        sub_spans,
                        1,
                        page.rect.width,
                    )
                )
                prox_id += 1
            continue
        blocos.append(
            _montar_bloco(
                prox_id,
                pagina,
                tuple(bloco["bbox"]),
                spans,
                len(bloco["lines"]),
                page.rect.width,
                linhas_spans,
            )
        )
        prox_id += 1
    return blocos
