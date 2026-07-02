# Fidelidade Tipográfica e Paginação Adaptativa — Implementation Plan (E9-13)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer o motor editorial (`render_motor=html`, ADR-0036) parar de inventar layout — usar a fonte real do PDF, preservar ênfase inline (negrito/itálico no meio do parágrafo), herdar a cor original do link, reconhecer listas numeradas sem descartar blocos sem tradução, renderizar notas de rodapé nativas do original, mostrar o **fólio literal do original** (dinâmico via `string-set`, escala sozinho quando o reflow gera mais páginas) e forçar quebra de página **por nível de heading extraída do próprio documento** (não uma regra fixa).

**Architecture:** Novo módulo `tipografia.py` (motor puro, mesmo padrão de `layout.py`) concentra as funções sem I/O pesado (parse de ênfase, clustering de tamanho de heading, taxa de abertura de página) + a extração de fonte real (única função com I/O, análoga a `_imagens`/`_geometria`). `extracao.py` ganha marcação de ênfase inline no texto do bloco. `traducao_ia.py` ganha uma instrução de preservação desses marcadores no prompt de refino. `editorial_html.py` (motor de render) consome tudo isso: fonte real por bloco, ênfase inline convertida em `<b>`/`<i>`, cor de link herdada, listas `<ol>`/`<ul>`, nota de rodapé nativa, fólio via `string-set` e `break-before` por nível calculado por documento.

**Tech Stack:** Python 3.12+, PyMuPDF (`fitz`), WeasyPrint, pytest, ruff. ADR: `docs/arquitetura/adr/ADR-0041-fidelidade-tipografica-e-paginacao-adaptativa.md`. Spec: `docs/specs/traducao-render-editorial.md` (seção "Fidelidade avançada").

---

## File Structure

- Modify: `src/atlas/traducao/extracao.py` — ênfase inline no `texto` do bloco.
- Modify: `src/atlas/traducao/traducao_ia.py` — instrução de preservar marcador no prompt de refino.
- Create: `src/atlas/traducao/tipografia.py` — motor puro (conversão de marcador, clustering de heading, taxa de abertura de página) + extração de fonte real.
- Modify: `src/atlas/traducao/editorial_html.py` — usa `tipografia.py`: fonte real, ênfase inline, cor de link herdada, listas numeradas, nota de rodapé nativa, fólio dinâmico, quebra por nível.
- Test: `tests/traducao/test_extracao_enfase.py` (novo), `tests/traducao/test_traducao_ia.py` (caso novo), `tests/traducao/test_tipografia.py` (novo), `tests/traducao/test_editorial_html_fidelidade.py` (novo).

---

### Task 1: Ênfase inline na extração

**Files:**
- Modify: `src/atlas/traducao/extracao.py`
- Test: `tests/traducao/test_extracao_enfase.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/traducao/test_extracao_enfase.py
from atlas.traducao.extracao import Span, _marcar_enfase

_BOLD = 1 << 4
_ITALIC = 1 << 1


def _span(texto, flags=0):
    return Span(text=texto, bbox=(0, 0, 10, 10), font="Times", size=11.0, color=0, flags=flags)


def test_palavra_em_negrito_no_meio_ganha_marcador():
    spans = [
        _span("Isto é "),
        _span("muito", flags=_BOLD),
        _span(" importante."),
    ]
    assert _marcar_enfase(spans) == "Isto é **muito** importante."


def test_bloco_totalmente_em_negrito_nao_marca_nada():
    spans = [_span("Título", flags=_BOLD), _span("do capítulo", flags=_BOLD)]
    assert _marcar_enfase(spans) == "Título do capítulo"


def test_palavra_em_italico_no_meio_ganha_marcador():
    spans = [_span("Veja o termo "), _span("in situ", flags=_ITALIC), _span(" no texto.")]
    assert _marcar_enfase(spans) == "Veja o termo _in situ_ no texto."


def test_span_vazio_e_ignorado():
    spans = [_span("Texto"), _span("   "), _span(" normal.")]
    assert _marcar_enfase(spans) == "Texto normal."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/traducao/test_extracao_enfase.py -v`
Expected: FAIL with `ImportError: cannot import name '_marcar_enfase'`.

- [ ] **Step 3: Write minimal implementation**

Em `src/atlas/traducao/extracao.py`, adicione (após `_FLAG_MONOSPACE = 8`):

```python
_FLAG_ITALIC = 1 << 1
_FLAG_BOLD = 1 << 4


def _bold_span(s: Span) -> bool:
    return bool(s.flags & _FLAG_BOLD) or "bold" in s.font.lower() or "black" in s.font.lower()


def _italic_span(s: Span) -> bool:
    return bool(s.flags & _FLAG_ITALIC) or "italic" in s.font.lower() or "oblique" in s.font.lower()


def _marcar_enfase(spans: list[Span]) -> str:
    """Monta o texto do bloco marcando trechos que divergem do estilo dominante
    (negrito/itálico) com marcadores leves ``**b**``/``_i_`` — a tradução é
    instruída a preservá-los (ADR-0041); o render os converte em ``<b>``/``<i>``
    só no trecho, sem perder a ênfase de uma palavra isolada no meio do parágrafo.
    """
    partes_validas = [s for s in spans if s.text.strip()]
    if not partes_validas:
        return ""
    total = sum(max(1, len(s.text)) for s in partes_validas)
    peso_bold = sum(len(s.text) for s in partes_validas if _bold_span(s))
    peso_ital = sum(len(s.text) for s in partes_validas if _italic_span(s))
    dom_bold = peso_bold > total / 2
    dom_ital = peso_ital > total / 2
    saida: list[str] = []
    for s in partes_validas:
        texto = s.text.strip()
        if _bold_span(s) and not dom_bold:
            texto = f"**{texto}**"
        if _italic_span(s) and not dom_ital:
            texto = f"_{texto}_"
        saida.append(texto)
    return " ".join(saida)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/traducao/test_extracao_enfase.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Ligar `_marcar_enfase` em `extrair_pagina`**

Em `extrair_pagina`, o loop atual monta `partes: list[str]` span a span e depois faz
`texto = " ".join(p.strip() for p in partes if p.strip())`. Troque por: pare de
acumular `partes` (remova a lista e o `partes.append(s["text"])` do loop) e, depois
de montar `spans` para o bloco, calcule:

```python
        if not spans:
            continue
        texto_plano = " ".join(s.text.strip() for s in spans if s.text.strip())
        skip = mono or not _tem_letra(texto_plano)
        texto = texto_plano if skip else _marcar_enfase(spans)
```

(`skip` continua controlando blocos mono/sem-letra — esses usam `texto_plano`, sem
marcador, porque `_elemento` no render sempre usa `b.texto` verbatim pra código.)
O resto de `extrair_pagina` (classificação de papel, construção do `BlocoTraducao`)
usa a variável `texto` já calculada — sem mudança de assinatura.

- [ ] **Step 6: Run full extracao suite**

Run: `.venv/bin/python -m pytest tests/traducao/test_extracao.py tests/traducao/test_extracao_enfase.py tests/traducao/test_classificacao_papel.py -v`
Expected: PASS (todos).

- [ ] **Step 7: Commit**

```bash
git add src/atlas/traducao/extracao.py tests/traducao/test_extracao_enfase.py
git commit -m "feat(traducao): marca ênfase inline (negrito/itálico) no texto do bloco (ADR-0041)"
```

---

### Task 2: Instrução de preservar marcador no prompt de refino

**Files:**
- Modify: `src/atlas/traducao/traducao_ia.py`
- Test: `tests/traducao/test_traducao_ia.py`

- [ ] **Step 1: Write the failing test**

Adicione em `tests/traducao/test_traducao_ia.py`:

```python
def test_prompt_refino_instrui_preservar_enfase_inline():
    from atlas.traducao.traducao_ia import ConfigTraducao, montar_prompt_refino

    prompt = montar_prompt_refino([(1, "This is **very** important.", "Isto é **muito** importante.")], ConfigTraducao())
    assert "**" in prompt and "_" in prompt
    assert "marcador" in prompt.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/traducao/test_traducao_ia.py::test_prompt_refino_instrui_preservar_enfase_inline -v`
Expected: FAIL (assert `"marcador" in prompt.lower()` falso — a instrução ainda não existe).

- [ ] **Step 3: Write minimal implementation**

Em `montar_prompt_refino` (`src/atlas/traducao/traducao_ia.py`), o `instrucao` default
ganha uma frase extra. Troque:

```python
    instrucao = cfg.instrucao_refino.strip() or (
        f"Você revisa a tradução de {cfg.idioma_origem} para {cfg.idioma_destino} de um "
        f"livro técnico sobre: {cfg.assunto or 'tecnologia'}.\n"
        f"Para cada bloco há a ORIGEM e uma tradução BRUTA (automática). Corrija o BRUTO "
        f"para ficar FIEL à origem e natural, SEM PERDER informação, mantendo o tom técnico."
    )
    return (
        f"{instrucao}\n"
        f"NÃO traduza termos técnicos, nomes de APIs, comandos ou código; mantenha em "
        f"inglês os termos do glossário: {glossario}.\n"
        f"Responda cada bloco no MESMO formato numerado, só a versão final, sem "
        f"comentários:\n[[N]] <tradução final>\n\n{corpo}"
    )
```

por:

```python
    instrucao = cfg.instrucao_refino.strip() or (
        f"Você revisa a tradução de {cfg.idioma_origem} para {cfg.idioma_destino} de um "
        f"livro técnico sobre: {cfg.assunto or 'tecnologia'}.\n"
        f"Para cada bloco há a ORIGEM e uma tradução BRUTA (automática). Corrija o BRUTO "
        f"para ficar FIEL à origem e natural, SEM PERDER informação, mantendo o tom técnico."
    )
    return (
        f"{instrucao}\n"
        f"NÃO traduza termos técnicos, nomes de APIs, comandos ou código; mantenha em "
        f"inglês os termos do glossário: {glossario}.\n"
        f"O texto pode conter marcador de ênfase (**negrito** ou _itálico_) ao redor de "
        f"uma palavra/trecho — preserve esse marcador na MESMA posição relativa da "
        f"tradução (ao redor da palavra/trecho equivalente), sem adicionar nem remover "
        f"marcadores que não estejam na origem.\n"
        f"Responda cada bloco no MESMO formato numerado, só a versão final, sem "
        f"comentários:\n[[N]] <tradução final>\n\n{corpo}"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/traducao/test_traducao_ia.py -v`
Expected: PASS (todos, incluindo o novo).

- [ ] **Step 5: Commit**

```bash
git add src/atlas/traducao/traducao_ia.py tests/traducao/test_traducao_ia.py
git commit -m "feat(traducao): refino preserva marcador de ênfase inline (ADR-0041)"
```

---

### Task 3: `tipografia.py` — conversão de marcador de ênfase → HTML

**Files:**
- Create: `src/atlas/traducao/tipografia.py`
- Test: `tests/traducao/test_tipografia.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/traducao/test_tipografia.py
from atlas.traducao.tipografia import converter_enfase


def _escapar(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def test_converte_negrito_no_meio_do_texto():
    out = converter_enfase("Isto é **muito** importante.", _escapar)
    assert out == "Isto é <b>muito</b> importante."


def test_converte_italico_no_meio_do_texto():
    out = converter_enfase("Veja _in situ_ aqui.", _escapar)
    assert out == "Veja <i>in situ</i> aqui."


def test_marcador_desbalanceado_fica_literal():
    out = converter_enfase("Preço: R$ 10 * 2 = 20", _escapar)
    assert out == "Preço: R$ 10 * 2 = 20"


def test_texto_sem_marcador_so_escapa():
    out = converter_enfase("<script>alert(1)</script>", _escapar)
    assert out == "&lt;script&gt;alert(1)&lt;/script&gt;"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/traducao/test_tipografia.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlas.traducao.tipografia'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/atlas/traducao/tipografia.py
"""Motor puro de tipografia do render editorial (ADR-0041): conversão de marcador
de ênfase inline, clustering de nível de heading e taxa de abertura de página —
sem WeasyPrint/IO pesado (mesmo padrão de ``layout.py``). ``extrair_fontes`` é a
única função que precisa do documento aberto (fitz).
"""

from __future__ import annotations

import base64
import re
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/traducao/test_tipografia.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/atlas/traducao/tipografia.py tests/traducao/test_tipografia.py
git commit -m "feat(traducao): tipografia.converter_enfase (marcador → <b>/<i>, ADR-0041)"
```

---

### Task 4: `tipografia.py` — clustering de heading + taxa de abertura de página

**Files:**
- Modify: `src/atlas/traducao/tipografia.py`
- Test: `tests/traducao/test_tipografia.py`

- [ ] **Step 1: Write the failing test**

```python
from atlas.traducao.tipografia import clusters_titulo, nivel_titulo, taxa_abre_pagina


def test_clusters_titulo_ate_3_niveis_do_maior_pro_menor():
    tamanhos = [11, 11, 11, 24, 24, 18, 18, 18, 14, 14, 11, 11]
    clusters = clusters_titulo(tamanhos, corpo_sz=11)
    assert clusters == [24.0, 18.0, 14.0]


def test_clusters_titulo_sem_heading_e_vazio():
    assert clusters_titulo([11, 11, 11], corpo_sz=11) == []


def test_nivel_titulo_bate_no_cluster_mais_proximo():
    clusters = [24.0, 18.0, 14.0]
    assert nivel_titulo(24.2, clusters) == "h1"
    assert nivel_titulo(18.0, clusters) == "h2"
    assert nivel_titulo(14.1, clusters) == "h3"
    assert nivel_titulo(11.0, clusters) is None


def test_taxa_abre_pagina_forca_quebra_com_amostra_suficiente():
    ocorrencias = {"h1": [True, True, True, False], "h2": [True, False, False]}
    out = taxa_abre_pagina(ocorrencias)
    assert out["h1"] is True  # 3/4 = 75% >= 60%
    assert out["h2"] is False  # 1/3 = 33% < 60%


def test_taxa_abre_pagina_amostra_pequena_fica_falso():
    out = taxa_abre_pagina({"h3": [True, True]})  # só 2 ocorrências
    assert out["h3"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/traducao/test_tipografia.py::test_clusters_titulo_ate_3_niveis_do_maior_pro_menor -v`
Expected: FAIL with `ImportError: cannot import name 'clusters_titulo'`.

- [ ] **Step 3: Write minimal implementation**

Adicione em `src/atlas/traducao/tipografia.py`:

```python
def clusters_titulo(tamanhos: list[float], corpo_sz: float) -> list[float]:
    """Até 3 tamanhos-âncora (h1 > h2 > h3), do maior pro menor, agrupando os
    tamanhos de fonte "grandes" do documento (>= 1.15x o corpo) por proximidade
    (gap <= 0.75pt cai no mesmo cluster). Documento sem heading grande ⇒ ``[]``
    (nenhum nível é tratado como título)."""
    grandes = sorted({round(s, 1) for s in tamanhos if s >= corpo_sz * 1.15}, reverse=True)
    if not grandes:
        return []
    clusters: list[list[float]] = [[grandes[0]]]
    for s in grandes[1:]:
        if clusters[-1][-1] - s <= 0.75:
            clusters[-1].append(s)
        else:
            clusters.append([s])
    return [c[0] for c in clusters[:3]]


def nivel_titulo(sz: float, clusters: list[float], tol: float = 0.5) -> str | None:
    """``"h1"``/``"h2"``/``"h3"`` conforme o cluster mais próximo (dentro de
    ``tol``); ``None`` se não bater com nenhum (texto de corpo comum)."""
    for nivel, ref in zip(("h1", "h2", "h3"), clusters):
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/traducao/test_tipografia.py -v`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add src/atlas/traducao/tipografia.py tests/traducao/test_tipografia.py
git commit -m "feat(traducao): clustering de heading + taxa de abertura de página (ADR-0041)"
```

---

### Task 5: `tipografia.py` — fonte real embutida

**Files:**
- Modify: `src/atlas/traducao/tipografia.py`
- Test: `tests/traducao/test_tipografia.py`

- [ ] **Step 1: Write the failing test**

```python
def test_extrai_fonte_real_embutida(tmp_path):
    import fitz
    from atlas.traducao.tipografia import extrair_fontes, gerar_font_faces

    fonte_path = str(
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "src" / "atlas" / "traducao" / "fonts" / "LiberationSans-Regular.ttf"
    )
    doc = fitz.open()
    page = doc.new_page()
    page.insert_font(fontname="atlasteste", fontfile=fonte_path)
    page.insert_text((72, 100), "Hello world", fontname="atlasteste", fontsize=12)
    p = tmp_path / "f.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    fontes = extrair_fontes(doc)
    assert fontes  # pelo menos uma fonte extraída
    uri = next(iter(fontes.values()))
    assert uri.startswith("data:font/")
    css = gerar_font_faces(fontes)
    assert "@font-face" in css
    doc.close()


def test_extrai_fontes_documento_sem_fonte_embutida_nao_quebra(tmp_path):
    import fitz
    from atlas.traducao.tipografia import extrair_fontes

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Hello world", fontname="helv", fontsize=12)  # fonte base-14
    p = tmp_path / "f2.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    fontes = extrair_fontes(doc)  # não deve levantar exceção
    assert isinstance(fontes, dict)
    doc.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/traducao/test_tipografia.py::test_extrai_fonte_real_embutida -v`
Expected: FAIL with `ImportError: cannot import name 'extrair_fontes'`.

- [ ] **Step 3: Write minimal implementation**

Adicione em `src/atlas/traducao/tipografia.py`:

```python
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
        f'@font-face {{ font-family: "{nome}"; src: url({uri}); }}'
        for nome, uri in fontes.items()
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/traducao/test_tipografia.py -v`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add src/atlas/traducao/tipografia.py tests/traducao/test_tipografia.py
git commit -m "feat(traducao): tipografia.extrair_fontes (fonte real embutida, ADR-0041)"
```

---

### Task 6: `editorial_html.py` — fonte real + ênfase inline por bloco

**Files:**
- Modify: `src/atlas/traducao/editorial_html.py`
- Test: `tests/traducao/test_editorial_html_fidelidade.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/traducao/test_editorial_html_fidelidade.py
from atlas.traducao.editorial_html import _elemento
from atlas.traducao.extracao import BlocoTraducao, Span


def _bloco(texto, size=11.0, bold=False, italic=False, font="Times"):
    span = Span(text=texto, bbox=(72, 100, 400, 116), font=font, size=size, color=0,
                flags=(1 << 4 if bold else 0) | (1 << 1 if italic else 0))
    return BlocoTraducao(id=1, pagina=0, bbox=span.bbox, texto=texto, spans=[span])


def test_elemento_converte_marcador_de_enfase_inline():
    b = _bloco("Original com **muito** destaque.")
    from atlas.traducao.editorial_html import _estilo
    est = _estilo(b)
    html = _elemento(b, "Tradução com **muito** destaque.", est, body_sz=11.0, clusters=[])
    assert "<b>muito</b>" in html


def test_elemento_usa_fonte_real_do_span():
    b = _bloco("Texto qualquer.", font="MinhaFonteCustom")
    from atlas.traducao.editorial_html import _estilo
    est = _estilo(b)
    assert est["font"] == "MinhaFonteCustom"
    html = _elemento(b, "Texto qualquer.", est, body_sz=11.0, clusters=[])
    assert "MinhaFonteCustom" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/traducao/test_editorial_html_fidelidade.py -v`
Expected: FAIL — `_estilo` não tem chave `"font"`; `_elemento` não aceita `clusters`.

- [ ] **Step 3: Write minimal implementation**

Em `src/atlas/traducao/editorial_html.py`, adicione o import:

```python
from atlas.traducao.tipografia import converter_enfase, nivel_titulo
```

Troque `_estilo`:

```python
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
        "mono": any(_mono_span(s) for s in b.spans),
        "color": b.spans[0].color or 0,
        "font": font_dom,
    }
```

Troque `_elemento` (assinatura ganha `clusters`; `conteudo` usa `converter_enfase`;
heading usa `nivel_titulo`; estilo inline ganha `font-family`):

```python
_FALLBACK_FONTE = "'Liberation Serif','DejaVu Serif','Times New Roman',Georgia,serif"


def _elemento(b, texto: str, est: dict, body_sz: float, clusters: list[float],
              anchor: str = "", link=None) -> str:
    """HTML de um bloco conforme papel/estilo, com âncora, hyperlink e fonte
    real (ADR-0041)."""
    cor = _cor_hex(est["color"])
    cor_css = "" if cor in ("#000000", "#000") else f"color:{cor};"
    fonte_css = f"font-family:'{_e(est['font'])}',{_FALLBACK_FONTE};" if est["font"] else ""
    ida = f' id="{anchor}"' if anchor else ""
    if est["mono"]:
        return f'<pre{ida}>{_e(b.texto)}</pre>'  # código: original, verbatim
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
        return f'<{nivel}{ida} style="font-size:{sz:.1f}pt;{cor_css}{fonte_css}">{conteudo}</{nivel}>'
    if _e_lista(b.texto):
        item = converter_enfase(texto.lstrip()[1:].lstrip(), _e)
        if est["italic"]:
            item = f'<span class="it">{item}</span>'
        return f'<li{ida} style="font-size:{sz:.1f}pt;{cor_css}{fonte_css}">{item}</li>'
    return f'<p{ida} style="font-size:{sz:.1f}pt;{cor_css}{fonte_css}">{conteudo}</p>'
```

Atualize o único call site em `montar_html` (troque `_elemento(b, texto, est, body_sz, anchor=..., link=link)` por
`_elemento(b, texto, est, body_sz, [], anchor=_anchor(idx, b.id), link=link)` — passar `[]` como `clusters` por
enquanto é seguro (`nivel_titulo` devolve `None` sempre); a Task 10 troca isso pelo cluster real do documento.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/traducao/test_editorial_html_fidelidade.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run full render suite (checa que nada quebrou)**

Run: `.venv/bin/python -m pytest tests/traducao -q`
Expected: PASS (todos).

- [ ] **Step 6: Commit**

```bash
git add src/atlas/traducao/editorial_html.py tests/traducao/test_editorial_html_fidelidade.py
git commit -m "feat(traducao): render usa fonte real + converte ênfase inline (ADR-0041)"
```

---

### Task 7: Listas numeradas + zero bloco descartado sem tradução

**Files:**
- Modify: `src/atlas/traducao/editorial_html.py`
- Test: `tests/traducao/test_editorial_html_fidelidade.py`

- [ ] **Step 1: Write the failing test**

```python
def test_tipo_lista_reconhece_numerado_e_alfabetico():
    from atlas.traducao.editorial_html import _tipo_lista
    assert _tipo_lista("1. Primeiro item") == "ol"
    assert _tipo_lista("a) Item alfabético") == "ol"
    assert _tipo_lista("• Item com bullet") == "ul"
    assert _tipo_lista("Parágrafo comum, sem marcador.") is None


def test_montar_html_nunca_descarta_bloco_sem_traducao(tmp_path):
    import fitz
    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "This block never got translated.", fontname="helv", fontsize=12)
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    blocos = extrair_pagina(doc[0], 0)
    paginas = {0: (blocos, {})}  # dict de traduções vazio — nenhum bloco traduzido
    geo = _geometria(doc, paginas)
    html = montar_html(doc, paginas, geo)
    assert "This block never got translated" in html
    doc.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/traducao/test_editorial_html_fidelidade.py::test_tipo_lista_reconhece_numerado_e_alfabetico -v`
Expected: FAIL with `ImportError: cannot import name '_tipo_lista'`.

- [ ] **Step 3: Write minimal implementation**

Em `editorial_html.py`, adicione perto de `_e_lista`:

```python
_RE_LISTA_NUM = re.compile(r"^\s*(\d+[.)]|[a-zA-Z][.)])\s+")


def _tipo_lista(texto: str) -> str | None:
    """``"ul"``/``"ol"``/``None`` conforme o marcador do item (ADR-0041)."""
    t = texto.lstrip()
    if t[:1] in _BULLETS and len(t) > 2 and t[1:2] in (" ", "\t"):
        return "ul"
    if _RE_LISTA_NUM.match(texto):
        return "ol"
    return None
```

Em `montar_html`, troque o bloco de fechamento de lista (`aberto_ul`/`fecha_ul`) por
uma versão que também suporta `<ol>`:

```python
    partes: list[str] = []
    lista_aberta: str | None = None

    def fecha_lista():
        nonlocal lista_aberta
        if lista_aberta:
            partes.append("</ol>" if lista_aberta == "ol" else "</ul>")
            lista_aberta = None
```

E, no loop principal de blocos (onde hoje é `if el.startswith("<li")`), troque por:

```python
            texto = traducoes.get(b.id) or b.texto  # nunca descarta bloco sem tradução
            ...
            tipo_li = _tipo_lista(b.texto) if not est["mono"] else None
            el = _elemento(b, texto, est, body_sz, [], anchor=_anchor(idx, b.id), link=link)
            if tipo_li and el.startswith("<li"):
                if lista_aberta and lista_aberta != tipo_li:
                    fecha_lista()
                if not lista_aberta:
                    partes.append("<ol>" if tipo_li == "ol" else "<ul>")
                    lista_aberta = tipo_li
                partes.append(el)
            else:
                fecha_lista()
                partes.append(el)
        fecha_lista()
```

(o `texto = traducoes.get(b.id) or b.texto` substitui o antigo
`texto = traducoes.get(b.id) if not est["mono"] else b.texto; if texto is None: continue`
— agora bloco sem tradução cai no original, nunca é pulado; blocos mono continuam
usando `b.texto` porque `traducoes` não tem entrada pra eles mesmo.)

Ajuste também `_elemento`'s ramo de lista pra usar `_tipo_lista`/marcador numérico
em vez de assumir sempre bullet — troque o bloco:

```python
    if _e_lista(b.texto):
        item = converter_enfase(texto.lstrip()[1:].lstrip(), _e)
        if est["italic"]:
            item = f'<span class="it">{item}</span>'
        return f'<li{ida} style="font-size:{sz:.1f}pt;{cor_css}{fonte_css}">{item}</li>'
```

por:

```python
    tipo_li = _tipo_lista(b.texto)
    if tipo_li == "ul":
        bruto = texto.lstrip()
        if bruto[:1] in _BULLETS:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/traducao/test_editorial_html_fidelidade.py -v`
Expected: PASS (todos).

- [ ] **Step 5: Run full render suite**

Run: `.venv/bin/python -m pytest tests/traducao -q`
Expected: PASS (todos).

- [ ] **Step 6: Commit**

```bash
git add src/atlas/traducao/editorial_html.py tests/traducao/test_editorial_html_fidelidade.py
git commit -m "feat(traducao): listas numeradas (<ol>) + nunca descarta bloco sem tradução (ADR-0041)"
```

---

### Task 8: Nota de rodapé nativa do original

**Files:**
- Modify: `src/atlas/traducao/editorial_html.py`
- Test: `tests/traducao/test_editorial_html_fidelidade.py`

- [ ] **Step 1: Write the failing test**

```python
def test_e_rodape_nativo_distingue_nota_de_folio():
    from atlas.traducao.editorial_html import _e_rodape_nativo

    class Nota:
        bbox = (72.0, 745.0, 400.0, 760.0)
        texto = "1. Este termo tem uma explicação mais longa aqui embaixo."

    class Folio:
        bbox = (300.0, 820.0, 310.0, 832.0)
        texto = "42"

    assert _e_rodape_nativo(Nota(), ph=842.0) is True
    assert _e_rodape_nativo(Folio(), ph=842.0) is False


def test_montar_html_renderiza_nota_de_rodape_nativa(tmp_path):
    import fitz
    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    page = doc.new_page()  # altura default ~792pt
    page.insert_text((72, 100), "Corpo do texto principal da página.", fontname="helv", fontsize=12)
    page.insert_text((72, 760), "1. Nota explicativa ao pé da página aqui.", fontname="helv", fontsize=8)
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    blocos = extrair_pagina(doc[0], 0)
    traducoes = {b.id: b.texto for b in blocos if not b.skip}
    paginas = {0: (blocos, traducoes)}
    geo = _geometria(doc, paginas)
    html = montar_html(doc, paginas, geo)
    assert 'class="rodape-nativo"' in html
    assert "Nota explicativa" in html
    doc.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/traducao/test_editorial_html_fidelidade.py::test_e_rodape_nativo_distingue_nota_de_folio -v`
Expected: FAIL with `ImportError: cannot import name '_e_rodape_nativo'`.

- [ ] **Step 3: Write minimal implementation**

Adicione perto de `_e_folio`:

```python
def _e_rodape_nativo(b, ph: float) -> bool:
    """Nota de rodapé do próprio PDF (não fólio): frase de várias palavras na
    faixa inferior da página, acima da faixa mais estreita onde o fólio mora
    (ADR-0041). Fólio é um rótulo curto (`_e_folio`); nota é prosa."""
    if not b.bbox or not b.texto:
        return False
    y1 = b.bbox[3]
    na_faixa_inferior = ph * 0.70 < y1 <= ph * 0.92
    tem_frase = len(b.texto.split()) >= 4
    return na_faixa_inferior and tem_frase and not _e_folio(b, ph)
```

Em `montar_html`, dentro do loop `for idx in sorted(paginas):`, antes de montar
`itens`, colete as notas nativas da página e as remova da lista de blocos normais.
Troque a construção de `itens`:

```python
        itens: list[tuple] = [
            (b.bbox[1] if b.bbox else 0.0, "b", b)
            for b in blocos
            if (not b.skip or _estilo(b)["mono"]) and not _e_folio(b, ph)
        ]
```

por:

```python
        notas_pag: list[str] = []
        itens: list[tuple] = []
        for b in blocos:
            if not (not b.skip or _estilo(b)["mono"]):
                continue
            if _e_folio(b, ph):
                continue
            if not _estilo(b)["mono"] and _e_rodape_nativo(b, ph):
                notas_pag.append(traducoes.get(b.id) or b.texto)
                continue
            itens.append((b.bbox[1] if b.bbox else 0.0, "b", b))
```

E, ao final do loop da página (depois de `fecha_lista()`, antes de passar pra
próxima página), insira o bloco de notas:

```python
        fecha_lista()
        if notas_pag:
            corpo_notas = "".join(f"<p>{_e(t)}</p>" for t in notas_pag)
            partes.append(f'<div class="rodape-nativo">{corpo_notas}</div>')
```

Adicione a classe no `_CSS` (perto de `.it { ... }`):

```css
.rodape-nativo { margin-top: 1.1em; padding-top: .3em; border-top: 0.6pt solid #999;
                  font-size: 8pt; line-height: 1.25; }
.rodape-nativo p { margin: .12em 0; }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/traducao/test_editorial_html_fidelidade.py -v`
Expected: PASS (todos).

- [ ] **Step 5: Run full render suite**

Run: `.venv/bin/python -m pytest tests/traducao -q`
Expected: PASS (todos).

- [ ] **Step 6: Commit**

```bash
git add src/atlas/traducao/editorial_html.py tests/traducao/test_editorial_html_fidelidade.py
git commit -m "feat(traducao): nota de rodapé nativa do original, distinta do fólio (ADR-0041)"
```

---

### Task 9: Fólio dinâmico (número igual ao original)

**Files:**
- Modify: `src/atlas/traducao/editorial_html.py`
- Test: `tests/traducao/test_editorial_html_fidelidade.py`

- [ ] **Step 1: Write the failing test**

```python
def test_valor_folio_extrai_numero_arabico_e_romano():
    from atlas.traducao.editorial_html import _valor_folio

    class Arabico:
        texto = "18 | Chapter 1: What Is Observability?"

    class Romano:
        texto = "xviii | Preface"

    class SemNumero:
        texto = "Chapter Title"

    assert _valor_folio(Arabico()) == "18"
    assert _valor_folio(Romano()) == "xviii"
    assert _valor_folio(SemNumero()) is None


def test_montar_html_emite_marcador_de_folio_por_pagina(tmp_path):
    import fitz
    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Corpo da página quarenta e dois.", fontname="helv", fontsize=12)
    page.insert_text((300, 820), "42", fontname="helv", fontsize=9)  # fólio no rodapé
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    blocos = extrair_pagina(doc[0], 0)
    traducoes = {b.id: b.texto for b in blocos if not b.skip}
    paginas = {0: (blocos, traducoes)}
    geo = _geometria(doc, paginas)
    html = montar_html(doc, paginas, geo)
    assert "string-set: folio '42'" in html
    doc.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/traducao/test_editorial_html_fidelidade.py::test_valor_folio_extrai_numero_arabico_e_romano -v`
Expected: FAIL with `ImportError: cannot import name '_valor_folio'`.

- [ ] **Step 3: Write minimal implementation**

Adicione perto de `_e_folio`:

```python
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
```

Em `montar_html`, no início do loop `for idx in sorted(paginas):` (logo após
`links = _links_pagina(page)`), insira o marcador de fólio da página antes de
processar os itens:

```python
        folio_blocos = [b for b in blocos if b.bbox and _e_folio(b, ph)]
        if folio_blocos:
            alvo = max(folio_blocos, key=lambda b: b.bbox[3])  # mais perto do fundo
            valor = _valor_folio(alvo)
            if valor:
                partes.append(f"<span style=\"string-set: folio '{_e(valor)}'\"></span>")
```

No `_CSS`, troque as duas linhas que usam `counter(page)`:

```css
@page :left  { @bottom-left  { content: counter(page); }
                @bottom-right { content: string(cap); } }
@page :right { @bottom-left  { content: string(cap); }
                @bottom-right { content: counter(page); } }
```

por:

```css
@page :left  { @bottom-left  { content: string(folio); }
                @bottom-right { content: string(cap); } }
@page :right { @bottom-left  { content: string(cap); }
                @bottom-right { content: string(folio); } }
```

(mantenha a indentação/chaves duplas `{{`/`}}` do f-string existente — é só a
troca de `counter(page)` por `string(folio)`, a estrutura do template não muda.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/traducao/test_editorial_html_fidelidade.py -v`
Expected: PASS (todos).

- [ ] **Step 5: Run full render suite**

Run: `.venv/bin/python -m pytest tests/traducao -q`
Expected: PASS (todos).

- [ ] **Step 6: Commit**

```bash
git add src/atlas/traducao/editorial_html.py tests/traducao/test_editorial_html_fidelidade.py
git commit -m "feat(traducao): fólio dinâmico via string-set — número igual ao original (ADR-0041)"
```

---

### Task 10: Quebra de página por nível de heading extraída do documento

**Files:**
- Modify: `src/atlas/traducao/editorial_html.py`
- Test: `tests/traducao/test_editorial_html_fidelidade.py`

- [ ] **Step 1: Write the failing test**

```python
def test_abre_pagina_primeiro_bloco_perto_do_topo_e_true():
    from atlas.traducao.editorial_html import _abre_pagina

    class Titulo:
        bbox = (72.0, 70.0, 300.0, 90.0)
        texto = "Capítulo 1"
        skip = False

    class Corpo:
        bbox = (72.0, 200.0, 500.0, 400.0)
        texto = "Parágrafo qualquer bem no meio da página, bem longo mesmo."
        skip = False

    blocos = [Titulo(), Corpo()]
    assert _abre_pagina(Titulo(), blocos, ph=792.0) is True
    assert _abre_pagina(Corpo(), blocos, ph=792.0) is False


def test_montar_html_forca_quebra_quando_h1_sempre_abre_pagina(tmp_path):
    import fitz
    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    for titulo in ("Capítulo Um", "Capítulo Dois", "Capítulo Três"):
        page = doc.new_page()
        page.insert_text((72, 70), titulo, fontname="helv", fontsize=24)  # heading grande
        page.insert_text((72, 150), "Parágrafo de corpo normal desta página.", fontname="helv", fontsize=11)
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    paginas = {}
    for i in range(doc.page_count):
        blocos = extrair_pagina(doc[i], i)
        traducoes = {b.id: b.texto for b in blocos if not b.skip}
        paginas[i] = (blocos, traducoes)
    geo = _geometria(doc, paginas)
    html = montar_html(doc, paginas, geo)
    assert "break-before: page" in html  # aplicado no h1 (título sempre abre página)
    doc.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/traducao/test_editorial_html_fidelidade.py::test_abre_pagina_primeiro_bloco_perto_do_topo_e_true -v`
Expected: FAIL with `ImportError: cannot import name '_abre_pagina'`.

- [ ] **Step 3: Write minimal implementation**

Adicione em `editorial_html.py` (perto de `_e_folio`):

```python
def _abre_pagina(b, blocos: list, ph: float) -> bool:
    """``True`` se ``b`` é o primeiro bloco de conteúdo (não-fólio) da página,
    perto do topo — usado pra medir se um nível de heading tende a abrir página
    nova no documento original (ADR-0041)."""
    uteis = [x for x in blocos if x.bbox and not _e_folio(x, ph)]
    if not uteis:
        return False
    primeiro = min(uteis, key=lambda x: x.bbox[1])
    return primeiro is b and b.bbox[1] <= ph * 0.18
```

Adicione o import de `clusters_titulo`/`taxa_abre_pagina` (junto do já existente
`converter_enfase, nivel_titulo`):

```python
from atlas.traducao.tipografia import clusters_titulo, converter_enfase, nivel_titulo, taxa_abre_pagina
```

Em `montar_html`, ANTES do loop principal `for idx in sorted(paginas):` (a função
já tem um primeiro loop que calcula `body_sz` — reuse a mesma coleta), adicione o
cálculo de `clusters` e `quebra`:

```python
def montar_html(doc, paginas: dict, geo: dict) -> str:
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
        for b in blocos:
            if not b.bbox or b.skip or _e_folio(b, ph):
                continue
            nivel = nivel_titulo(_estilo(b)["size"], clusters)
            if nivel and len(b.texto.split()) <= 14:
                ocorrencias[nivel].append(_abre_pagina(b, blocos, ph))
    quebra = taxa_abre_pagina(ocorrencias)
```

(o restante do corpo da função continua igual, mas agora com `clusters`/`quebra`
disponíveis). Troque a chamada de `_elemento` (nos dois lugares que hoje passam
`[]`) por `clusters`:

```python
            el = _elemento(b, texto, est, body_sz, clusters, anchor=_anchor(idx, b.id), link=link)
```

No fim de `montar_html`, a linha `css = _CSS.format(**geo)` passa a incluir os
placeholders de quebra:

```python
    geo_css = {
        **geo,
        "h1_break": "page" if quebra.get("h1") else "auto",
        "h2_break": "page" if quebra.get("h2") else "auto",
        "h3_break": "page" if quebra.get("h3") else "auto",
    }
    css = _CSS.format(**geo_css)
```

No `_CSS`, troque:

```css
h1,h2,h3 {{ text-align: left; font-weight: bold; margin: .7em 0 .28em; line-height: 1.2;
            page-break-after: avoid; break-after: avoid; }}
/* o título de capítulo (h1) vira a cabeça de página corrente */
h1 {{ string-set: cap content(); page-break-before: auto; }}
```

por:

```css
h1,h2,h3 {{ text-align: left; font-weight: bold; margin: .7em 0 .28em; line-height: 1.2;
            page-break-after: avoid; break-after: avoid; }}
/* o título de capítulo (h1) vira a cabeça de página corrente; quebra por nível
   é calculada por documento (ADR-0041) — não é uma regra fixa. */
h1 {{ string-set: cap content(); break-before: {h1_break}; }}
h2 {{ break-before: {h2_break}; }}
h3 {{ break-before: {h3_break}; }}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/traducao/test_editorial_html_fidelidade.py -v`
Expected: PASS (todos).

- [ ] **Step 5: Run full render suite**

Run: `.venv/bin/python -m pytest tests/traducao -q`
Expected: PASS (todos).

- [ ] **Step 6: Commit**

```bash
git add src/atlas/traducao/editorial_html.py tests/traducao/test_editorial_html_fidelidade.py
git commit -m "feat(traducao): quebra de página por nível de heading extraída do PDF (ADR-0041)"
```

---

### Task 11: Fonte real no `<style>` + cor de link herdada

**Files:**
- Modify: `src/atlas/traducao/editorial_html.py`
- Test: `tests/traducao/test_editorial_html_fidelidade.py`

- [ ] **Step 1: Write the failing test**

```python
def test_montar_html_embute_font_face_real(tmp_path):
    import fitz
    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import extrair_pagina
    from pathlib import Path

    fonte_path = str(
        Path(__file__).resolve().parents[2] / "src" / "atlas" / "traducao" / "fonts" / "LiberationSans-Regular.ttf"
    )
    doc = fitz.open()
    page = doc.new_page()
    page.insert_font(fontname="atlasteste", fontfile=fonte_path)
    page.insert_text((72, 100), "Texto com fonte embutida.", fontname="atlasteste", fontsize=12)
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    blocos = extrair_pagina(doc[0], 0)
    traducoes = {b.id: b.texto for b in blocos if not b.skip}
    paginas = {0: (blocos, traducoes)}
    geo = _geometria(doc, paginas)
    html = montar_html(doc, paginas, geo)
    assert "@font-face" in html
    doc.close()


def test_css_nao_forca_cor_azul_no_link():
    from atlas.traducao.editorial_html import _CSS
    assert "#0645ad" not in _CSS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/traducao/test_editorial_html_fidelidade.py::test_css_nao_forca_cor_azul_no_link -v`
Expected: FAIL — `#0645ad` ainda está no `_CSS`.

- [ ] **Step 3: Write minimal implementation**

No `_CSS`, troque:

```css
a {{ color: #0645ad; text-decoration: none; }}
h1 a, h2 a, h3 a {{ color: inherit; }}
```

por:

```css
a {{ text-decoration: underline; }}
```

(remove a linha `h1 a, h2 a, h3 a` — sem cor forçada, não precisa mais de override;
o link já herda a cor do elemento pai por padrão em CSS.)

Adicione o placeholder de fontes no topo do `_CSS`, logo antes de `html {{ ... }}`:

```css
{font_faces}
html {{ font-family: 'Liberation Serif','DejaVu Serif','Times New Roman',Georgia,serif; }}
```

Em `montar_html`, importe e chame a extração de fontes (junto do import já
existente de `tipografia`):

```python
from atlas.traducao.tipografia import (
    clusters_titulo,
    converter_enfase,
    extrair_fontes,
    gerar_font_faces,
    nivel_titulo,
    taxa_abre_pagina,
)
```

E, no bloco final onde `geo_css`/`css` são montados:

```python
    fontes = extrair_fontes(doc)
    geo_css = {
        **geo,
        "h1_break": "page" if quebra.get("h1") else "auto",
        "h2_break": "page" if quebra.get("h2") else "auto",
        "h3_break": "page" if quebra.get("h3") else "auto",
        "font_faces": gerar_font_faces(fontes),
    }
    css = _CSS.format(**geo_css)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/traducao/test_editorial_html_fidelidade.py -v`
Expected: PASS (todos).

- [ ] **Step 5: Run full render suite**

Run: `.venv/bin/python -m pytest tests/traducao -q`
Expected: PASS (todos).

- [ ] **Step 6: Commit**

```bash
git add src/atlas/traducao/editorial_html.py tests/traducao/test_editorial_html_fidelidade.py
git commit -m "feat(traducao): embute @font-face real no CSS + link herda cor original (ADR-0041)"
```

---

### Task 12: Suite completa + lint + regressão de fidelidade + PDF de controle

**Files:**
- Test: `tests/traducao/test_editorial_html_fidelidade.py` (regressão final)

- [ ] **Step 1: Write the end-to-end regression test**

```python
def test_regressao_nenhum_texto_e_perdido_no_render(tmp_path):
    import fitz
    from atlas.traducao.editorial_html import remontar_editorial_html
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "1. Primeiro item da lista numerada aqui.", fontname="helv", fontsize=11)
    page.insert_text((72, 120), "2. Segundo item da lista numerada aqui.", fontname="helv", fontsize=11)
    page.insert_text((72, 300), "Parágrafo comum de corpo bem no meio da página inteira.", fontname="helv", fontsize=11)
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    blocos = extrair_pagina(doc[0], 0)
    traducoes = {b.id: b.texto for b in blocos if not b.skip}  # simula "tradução" = original
    out = tmp_path / "out.pdf"
    remontar_editorial_html(doc, {0: (blocos, traducoes)}, str(out))

    out_doc = fitz.open(str(out))
    texto_final = "".join(out_doc[i].get_text() for i in range(out_doc.page_count))
    assert "Primeiro item" in texto_final
    assert "Segundo item" in texto_final
    assert "Parágrafo comum" in texto_final
    out_doc.close()
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python -m pytest tests/traducao/test_editorial_html_fidelidade.py::test_regressao_nenhum_texto_e_perdido_no_render -v`
Expected: PASS (se falhar, algum passo anterior descartou conteúdo — investigue antes de prosseguir).

- [ ] **Step 3: Run full suite + lint**

Run: `.venv/bin/python -m pytest tests/traducao -q && .venv/bin/ruff check src/atlas/traducao tests/traducao`
Expected: PASS + `All checks passed!`

- [ ] **Step 4: Re-render o PDF de controle (observability) sem repagar IA**

Run:
```bash
.venv/bin/python -c "
from atlas.traducao.pipeline import traduzir_pdf
from atlas.traducao.traducao_ia import ConfigTraducao, CacheTraducao
cache = CacheTraducao.carregar('data/pdfs/observability-engineering-achieving-production-excellence-9781492076445-1492076449_compress.pt-BR.cache.json')
traduzir_pdf(
    'data/pdfs/observability-engineering-achieving-production-excellence-9781492076445-1492076449_compress.pdf',
    'data/pdfs/observability-FIDELIDADE-E9-13.pdf',
    ConfigTraducao(), cache=cache, somente_render=True,
)
print('ok')
"
```
Expected: `ok`, sem chamada de IA (usa só o cache já pago). Confira manualmente
`data/pdfs/observability-FIDELIDADE-E9-13.pdf`: fonte real, sem link azul, listas
completas, fólio igual ao original, capítulos abrindo página nova.

- [ ] **Step 5: Commit**

```bash
git add tests/traducao/test_editorial_html_fidelidade.py
git commit -m "test(traducao): regressão de fidelidade end-to-end (nenhum texto perdido, ADR-0041)"
```

---

## Self-Review

**Spec coverage:** fonte real embutida (Task 5, 11) ✓; ênfase inline negrito/itálico
(Task 1, 2, 3, 6) ✓; cor de link herdada (Task 11) ✓; listas numeradas + zero perda
por bloco sem tradução (Task 7) ✓; nota de rodapé nativa distinta do fólio (Task 8)
✓; fólio dinâmico via `string-set` (Task 9) ✓; quebra de página por nível extraída
do documento (Task 4, 10) ✓; regressão de fidelidade end-to-end (Task 12) ✓.

**Placeholders:** nenhum "TODO/TBD"; todo passo de código mostra a implementação
completa (função inteira ou o trecho exato a trocar, com before/after literal).

**Type consistency:** `_elemento(b, texto, est, body_sz, clusters, anchor="", link=None)`
consistente da Task 6 em diante (Task 7/8/9/10 só adicionam lógica ao redor, não
mudam a assinatura); `_estilo(b) -> dict` com chave `"font"` desde a Task 6;
`converter_enfase(texto, escapar)`, `clusters_titulo(tamanhos, corpo_sz)`,
`nivel_titulo(sz, clusters, tol=0.5)`, `taxa_abre_pagina(ocorrencias, min_amostra=3,
limiar=0.6)`, `extrair_fontes(doc)`, `gerar_font_faces(fontes)` — assinaturas
estáveis entre a definição (Task 3/4/5) e o uso (Task 6/10/11).

## Riscos conhecidos p/ execução

- Task 6 Step 3 reescreve `_elemento` inteira — como as Tasks 7/8/9/10 mexem em
  ramos específicos dela (lista, fonte, nível), rode a suite completa
  (`pytest tests/traducao -q`) depois de cada task, não só o teste novo.
- `page.get_fonts(full=True)` (Task 5): confirme o formato exato da tupla na
  versão do PyMuPDF instalada (`.venv/bin/python -c "import fitz; print(fitz.__version__)"`)
  antes de assumir os índices `[0..3]` — se divergir, ajuste o unpacking.
- O `_CSS` é um f-string com `{{`/`}}` escapados — ao adicionar `{font_faces}`,
  `{h1_break}`, `{h2_break}`, `{h3_break}` como placeholders **não-escapados**,
  confirme que `_CSS.format(**geo_css)` recebe todas as chaves (`geo_css`, não
  `geo` puro) nas Tasks 10 e 11.
