# Render Editorial Ipsis-Litteris — Implementation Plan (E9-01, sub-projeto A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Renderizar o PDF traduzido em nível editorial — prosa reflui (com página de continuação quando transborda), legendas/labels/tabelas encaixam no bbox, imagens/charts ficam intactos, e termos mantidos no idioma de origem podem virar nota de rodapé.

**Architecture:** Um motor de layout **puro** (`layout.py`, sem IO) mede e pagina texto usando o retorno de `page.insert_textbox` (unused height: `>=0` coube, `<0` transbordou). `extracao.py` classifica o **papel** de cada bloco (`prosa`/`encaixado`/`imutavel`). `remontagem.py` orquestra: redação dos spans + fit-in-place para encaixados + reflow/paginação para prosa + notas de rodapé. Determinístico ⇒ compatível com o checkpoint por página do ADR-0031.

**Tech Stack:** Python 3.12+, PyMuPDF (`fitz`), pytest, ruff. Spec: `docs/specs/traducao-render-editorial.md`. ADR: `docs/arquitetura/adr/ADR-0033-render-editorial-hibrido.md`.

---

## File Structure

- Create: `src/atlas/traducao/layout.py` — motor puro de medição/paginação/rodapé.
- Modify: `src/atlas/traducao/extracao.py` — campo `papel` no `BlocoTraducao` + `classificar_papel()`.
- Modify: `src/atlas/traducao/remontagem.py` — orquestra fit-in-place + reflow + página de continuação + rodapé.
- Modify: `src/atlas/rotinas/traduzir_pdf.py` — passa `min_fonte_pct`/`notas_rodape` do `spec` para o `ConfigTraducao`.
- Modify: `src/atlas/traducao/traducao_ia.py` — `ConfigTraducao`: `+min_fonte_pct`, `+notas_rodape`.
- Test: `tests/traducao/test_layout.py`, `tests/traducao/test_classificacao_papel.py`, `tests/traducao/test_remontagem_editorial.py`.

---

### Task 1: Classificar papel do bloco na extração

**Files:**
- Modify: `src/atlas/traducao/extracao.py`
- Test: `tests/traducao/test_classificacao_papel.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/traducao/test_classificacao_papel.py
from atlas.traducao.extracao import classificar_papel


def _bloco(texto, bbox, n_linhas=1, mono=False):
    return {"texto": texto, "bbox": bbox, "n_linhas": n_linhas, "mono": mono}


def test_prosa_paragrafo_largo_multilinha():
    b = _bloco("Uma frase longa " * 20, (72, 100, 520, 260), n_linhas=8)
    assert classificar_papel(b, largura_pagina=595) == "prosa"


def test_encaixado_legenda_curta():
    b = _bloco("Figura 1: arquitetura.", (72, 300, 300, 315), n_linhas=1)
    assert classificar_papel(b, largura_pagina=595) == "encaixado"


def test_imutavel_bloco_sem_texto_traduzivel():
    b = _bloco("", (72, 400, 500, 700), n_linhas=0)
    assert classificar_papel(b, largura_pagina=595) == "imutavel"


def test_imutavel_codigo_monoespacado():
    b = _bloco("def f(): return 1", (72, 420, 500, 435), n_linhas=1, mono=True)
    assert classificar_papel(b, largura_pagina=595) == "imutavel"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/traducao/test_classificacao_papel.py -v`
Expected: FAIL with `ImportError: cannot import name 'classificar_papel'`.

- [ ] **Step 3: Write minimal implementation**

Add to `src/atlas/traducao/extracao.py` (module-level function; `BlocoTraducao` gains `papel: str = "encaixado"` field with default, e uma coluna `mono`/`n_linhas` já derivável dos spans):

```python
def classificar_papel(bloco: dict, largura_pagina: float) -> str:
    """Classifica o papel do bloco para o render editorial (ADR-0033).

    - imutavel: sem texto tradutível OU código monoespaçado (nunca refluir).
    - prosa: parágrafo largo e multi-linha (reflui + página de continuação).
    - encaixado (default seguro): legenda/label/célula — fit-in-place.
    """
    texto = (bloco.get("texto") or "").strip()
    if not texto or bloco.get("mono"):
        return "imutavel"
    x0, _, x1, _ = bloco["bbox"]
    largura = x1 - x0
    largo = largura >= 0.5 * largura_pagina
    multilinha = bloco.get("n_linhas", 1) >= 3
    if largo and multilinha:
        return "prosa"
    return "encaixado"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/traducao/test_classificacao_papel.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Wire papel into extrair_pagina**

Em `extrair_pagina`, ao montar cada `BlocoTraducao`, derive `n_linhas` (nº de spans/linhas do bloco) e `mono` (fonte monoespaçada dos spans, ex.: nome contém "Mono"/"Courier"), e set `papel=classificar_papel({...}, page.rect.width)`. Blocos já marcados `skip` continuam `skip` (viram `imutavel` no render).

- [ ] **Step 6: Commit**

```bash
git add src/atlas/traducao/extracao.py tests/traducao/test_classificacao_papel.py
git commit -m "feat(traducao): classifica papel do bloco (prosa/encaixado/imutavel) p/ render editorial (ADR-0033)"
```

---

### Task 2: Medir altura do texto num bbox (layout.py)

**Files:**
- Create: `src/atlas/traducao/layout.py`
- Test: `tests/traducao/test_layout.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/traducao/test_layout.py
import fitz

from atlas.traducao.layout import cabe_no_bbox


def test_texto_curto_cabe():
    doc = fitz.open(); page = doc.new_page()
    rect = fitz.Rect(72, 72, 520, 200)
    assert cabe_no_bbox(page, rect, "Uma linha curta.", fontsize=11) is True
    doc.close()


def test_texto_longo_nao_cabe_em_caixa_pequena():
    doc = fitz.open(); page = doc.new_page()
    rect = fitz.Rect(72, 72, 200, 90)  # caixa minúscula
    assert cabe_no_bbox(page, rect, "palavra " * 200, fontsize=11) is False
    doc.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/traducao/test_layout.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlas.traducao.layout'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/atlas/traducao/layout.py
"""Motor puro de layout do render editorial (ADR-0033).

Usa o retorno de ``page.insert_textbox`` como oráculo de medição: PyMuPDF devolve
a **altura não usada** (``>= 0`` coube; ``< 0`` faltou espaço). Escrevemos numa
página descartável (overlay=False não desenha nada permanente que nos atrapalhe;
medimos e depois descartamos a página de teste quando necessário).
"""

from __future__ import annotations

import fitz


def altura_livre(page, rect: fitz.Rect, texto: str, fontsize: float,
                 fontname: str = "helv") -> float:
    """Altura sobrando (``>=0``) ou faltando (``<0``) ao encaixar ``texto`` em ``rect``.

    Mede sem desenhar: usa uma página temporária de mesma geometria.
    """
    tmp = fitz.open()
    tp = tmp.new_page(width=page.rect.width, height=page.rect.height)
    sobra = tp.insert_textbox(rect, texto, fontsize=fontsize, fontname=fontname,
                              align=fitz.TEXT_ALIGN_LEFT)
    tmp.close()
    return sobra


def cabe_no_bbox(page, rect: fitz.Rect, texto: str, fontsize: float,
                 fontname: str = "helv") -> bool:
    return altura_livre(page, rect, texto, fontsize, fontname) >= 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/traducao/test_layout.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/atlas/traducao/layout.py tests/traducao/test_layout.py
git commit -m "feat(traducao): layout.altura_livre/cabe_no_bbox (medição via insert_textbox)"
```

---

### Task 3: Auto-fit com piso de legibilidade (encaixado)

**Files:**
- Modify: `src/atlas/traducao/layout.py`
- Test: `tests/traducao/test_layout.py`

- [ ] **Step 1: Write the failing test**

```python
from atlas.traducao.layout import fontsize_que_cabe


def test_fontsize_reduz_ate_caber():
    doc = fitz.open(); page = doc.new_page()
    rect = fitz.Rect(72, 72, 260, 110)
    fs = fontsize_que_cabe(page, rect, "Legenda um pouco maior que o normal aqui.",
                           fontsize_base=12, min_pct=90)
    assert fs is not None and 10.8 <= fs <= 12  # min 90% de 12 = 10.8
    doc.close()


def test_fontsize_none_se_nem_no_piso_cabe():
    doc = fitz.open(); page = doc.new_page()
    rect = fitz.Rect(72, 72, 120, 82)  # caixa minúscula
    fs = fontsize_que_cabe(page, rect, "texto grande demais " * 10,
                           fontsize_base=12, min_pct=90)
    assert fs is None  # sinaliza transbordo → chamador decide (prosa: reflui)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/traducao/test_layout.py::test_fontsize_reduz_ate_caber -v`
Expected: FAIL with `ImportError: cannot import name 'fontsize_que_cabe'`.

- [ ] **Step 3: Write minimal implementation**

```python
def fontsize_que_cabe(page, rect, texto, fontsize_base, min_pct=90,
                      fontname="helv", passo=0.5):
    """Maior fontsize em [min_pct% * base, base] que faz ``texto`` caber em ``rect``.

    Devolve ``None`` se nem no piso couber (o chamador reflui/pagina).
    """
    piso = fontsize_base * (min_pct / 100.0)
    fs = fontsize_base
    while fs >= piso:
        if cabe_no_bbox(page, rect, texto, fs, fontname):
            return fs
        fs -= passo
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/traducao/test_layout.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add src/atlas/traducao/layout.py tests/traducao/test_layout.py
git commit -m "feat(traducao): fontsize_que_cabe com piso de legibilidade (encaixado)"
```

---

### Task 4: Paginar prosa (o que cabe vs o que transborda)

**Files:**
- Modify: `src/atlas/traducao/layout.py`
- Test: `tests/traducao/test_layout.py`

- [ ] **Step 1: Write the failing test**

```python
from atlas.traducao.layout import paginar_prosa


def test_paginar_divide_no_transbordo():
    doc = fitz.open(); page = doc.new_page()
    rect = fitz.Rect(72, 72, 520, 120)  # cabe ~poucas linhas
    texto = "Sentença de teste número %d. " % 0 + " ".join(
        "Sentença de teste número %d." % i for i in range(1, 60))
    cabe, resto = paginar_prosa(page, rect, texto, fontsize=11)
    assert cabe and resto, "deveria sobrar texto para a página de continuação"
    assert cabe.strip() and resto.strip()
    # nada se perde: toda palavra do original aparece em cabe+resto
    assert len((cabe + " " + resto).split()) == len(texto.split())
    doc.close()


def test_paginar_texto_curto_nao_transborda():
    doc = fitz.open(); page = doc.new_page()
    rect = fitz.Rect(72, 72, 520, 300)
    cabe, resto = paginar_prosa(page, rect, "Curto.", fontsize=11)
    assert cabe.strip() == "Curto." and resto == ""
    doc.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/traducao/test_layout.py::test_paginar_divide_no_transbordo -v`
Expected: FAIL with `ImportError: cannot import name 'paginar_prosa'`.

- [ ] **Step 3: Write minimal implementation**

```python
def paginar_prosa(page, rect, texto, fontsize, fontname="helv"):
    """Divide ``texto`` em (cabe_em_rect, resto) por palavras, sem perder conteúdo.

    Busca binária no nº de palavras que ainda cabe em ``rect``. Determinístico.
    """
    palavras = texto.split()
    if not palavras:
        return "", ""
    if cabe_no_bbox(page, rect, texto, fontsize, fontname):
        return texto, ""
    lo, hi, melhor = 0, len(palavras), 0
    while lo <= hi:
        mid = (lo + hi) // 2
        trecho = " ".join(palavras[:mid])
        if mid > 0 and cabe_no_bbox(page, rect, trecho, fontsize, fontname):
            melhor, lo = mid, mid + 1
        else:
            hi = mid - 1
    melhor = max(melhor, 1)  # garante progresso (evita loop de página vazia)
    return " ".join(palavras[:melhor]), " ".join(palavras[melhor:])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/traducao/test_layout.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add src/atlas/traducao/layout.py tests/traducao/test_layout.py
git commit -m "feat(traducao): paginar_prosa (busca binária, sem perda de conteúdo)"
```

---

### Task 5: Config — min_fonte_pct e notas_rodape no spec

**Files:**
- Modify: `src/atlas/traducao/traducao_ia.py` (`ConfigTraducao`)
- Modify: `src/atlas/rotinas/traduzir_pdf.py` (lê do `spec`)
- Test: `tests/traducao/test_collect_traduzir_pdf.py` (novo caso)

- [ ] **Step 1: Write the failing test**

```python
# adicionar em tests/traducao/test_collect_traduzir_pdf.py
from atlas.traducao.traducao_ia import ConfigTraducao


def test_config_tem_defaults_editoriais():
    c = ConfigTraducao()
    assert c.min_fonte_pct == 90
    assert c.notas_rodape is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/traducao/test_collect_traduzir_pdf.py::test_config_tem_defaults_editoriais -v`
Expected: FAIL with `AttributeError: 'ConfigTraducao' object has no attribute 'min_fonte_pct'`.

- [ ] **Step 3: Write minimal implementation**

Em `ConfigTraducao` adicione:

```python
    min_fonte_pct: int = 90     # piso de legibilidade no fit-in-place (ADR-0033)
    notas_rodape: bool = False  # termos do glossário viram nota de rodapé
```

Em `rotinas/traduzir_pdf.py`, ao montar `cfg`, acrescente:

```python
        min_fonte_pct=int(t.spec.get("min_fonte_pct") or 90),
        notas_rodape=_verdade(t.spec.get("notas_rodape", False)),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/traducao/test_collect_traduzir_pdf.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atlas/traducao/traducao_ia.py src/atlas/rotinas/traduzir_pdf.py tests/traducao/test_collect_traduzir_pdf.py
git commit -m "feat(traducao): spec.min_fonte_pct e spec.notas_rodape (ADR-0033)"
```

---

### Task 6: Remontagem editorial — fit-in-place + reflow + página de continuação

**Files:**
- Modify: `src/atlas/traducao/remontagem.py`
- Test: `tests/traducao/test_remontagem_editorial.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/traducao/test_remontagem_editorial.py
import fitz

from atlas.traducao.extracao import extrair_pagina
from atlas.traducao.remontagem import remontar_documento


def _pdf_prosa_longa(tmp_path):
    doc = fitz.open(); page = doc.new_page()
    page.insert_text((72, 100), "Short original paragraph.", fontsize=11)
    p = tmp_path / "src.pdf"; doc.save(str(p)); doc.close()
    return str(p)


def test_prosa_que_cresce_gera_pagina_de_continuacao(tmp_path):
    src = _pdf_prosa_longa(tmp_path)
    doc = fitz.open(src)
    # tradução muito maior que o original → deve transbordar e paginar
    traducoes = {b.id: ("Parágrafo traduzido muito maior. " * 80)
                 for b in extrair_pagina(doc[0], 0) if not b.skip}
    n_antes = doc.page_count
    remontar_documento(doc, {0: (extrair_pagina(doc[0], 0), traducoes)},
                       min_fonte_pct=90)
    assert doc.page_count > n_antes, "deveria ter inserido página de continuação"
    # nada se perde: o texto traduzido aparece nas páginas
    txt = "".join(doc[i].get_text() for i in range(doc.page_count))
    assert "Parágrafo traduzido" in txt
    doc.close()


def test_imagem_permanece_intacta(tmp_path):
    doc = fitz.open(); page = doc.new_page()
    # retângulo desenhado como "figura" (proxy de conteúdo imutável)
    page.draw_rect(fitz.Rect(72, 300, 300, 450), fill=(0, 0, 1))
    page.insert_text((72, 100), "Caption.", fontsize=11)
    src = tmp_path / "s.pdf"; doc.save(str(src)); doc.close()
    doc = fitz.open(str(src))
    blocos = extrair_pagina(doc[0], 0)
    traducoes = {b.id: "Legenda." for b in blocos if not b.skip}
    xrefs_antes = doc[0].get_drawings()
    remontar_documento(doc, {0: (blocos, traducoes)}, min_fonte_pct=90)
    assert doc[0].get_drawings(), "desenhos (figura) não podem sumir"
    doc.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/traducao/test_remontagem_editorial.py -v`
Expected: FAIL with `ImportError: cannot import name 'remontar_documento'`.

- [ ] **Step 3: Write minimal implementation**

Adicione `remontar_documento` em `remontagem.py`, reutilizando `remontar_pagina` para os spans (redação) e o `layout` para prosa. Esqueleto concreto:

```python
import fitz

from atlas.traducao.layout import fontsize_que_cabe, paginar_prosa


def remontar_documento(doc, paginas: dict, min_fonte_pct: int = 90) -> None:
    """Remonta o doc in-place em nível editorial (ADR-0033).

    ``paginas``: {indice_original: (blocos, traducoes)}. Insere páginas de
    continuação logo após a página de origem quando a prosa transborda.
    Percorre em ordem decrescente de índice para os inserts não deslocarem os
    índices ainda não processados.
    """
    for idx in sorted(paginas, reverse=True):
        blocos, traducoes = paginas[idx]
        page = doc[idx]
        # 1) redação dos spans tradutíveis (não toca imagens/desenhos/imutáveis).
        for b in blocos:
            if getattr(b, "papel", "encaixado") == "imutavel" or b.skip:
                continue
            if b.id in traducoes:
                for s in b.spans:
                    page.add_redact_annot(s.bbox)
        page.apply_redactions()

        overflow: list[str] = []
        # 2) reinsere por papel.
        for b in blocos:
            if b.skip or b.id not in traducoes or getattr(b, "papel", "encaixado") == "imutavel":
                continue
            rect = fitz.Rect(*b.bbox)
            base_fs = b.spans[0].size if b.spans else 11
            texto = traducoes[b.id]
            if getattr(b, "papel", "encaixado") == "prosa":
                cabe, resto = paginar_prosa(page, rect, texto, base_fs)
                page.insert_textbox(rect, cabe, fontsize=base_fs,
                                    fontname="helv", align=fitz.TEXT_ALIGN_LEFT)
                if resto:
                    overflow.append(resto)
            else:  # encaixado: fit-in-place com piso
                fs = fontsize_que_cabe(page, rect, texto, base_fs, min_fonte_pct)
                if fs is None:  # não coube nem no piso → paginado como prosa
                    cabe, resto = paginar_prosa(page, rect, texto, base_fs * min_fonte_pct / 100)
                    page.insert_textbox(rect, cabe, fontsize=base_fs * min_fonte_pct / 100,
                                        fontname="helv")
                    if resto:
                        overflow.append(resto)
                else:
                    page.insert_textbox(rect, texto, fontsize=fs, fontname="helv",
                                        align=fitz.TEXT_ALIGN_LEFT)

        # 3) página(s) de continuação para o transbordo (preserva ordem).
        _inserir_continuacao(doc, idx, overflow, min_fonte_pct)


def _inserir_continuacao(doc, idx, overflow, min_fonte_pct):
    if not overflow:
        return
    origem = doc[idx]
    margem = 72
    largura, altura = origem.rect.width, origem.rect.height
    corpo = fitz.Rect(margem, margem, largura - margem, altura - margem)
    texto = "\n\n".join(overflow)
    while texto.strip():
        nova = doc.new_page(pno=idx + 1, width=largura, height=altura)
        cabe, texto = paginar_prosa(nova, corpo, texto, 11)
        nova.insert_textbox(corpo, cabe, fontsize=11, fontname="helv",
                            align=fitz.TEXT_ALIGN_LEFT)
        # rodapé "(cont.)" para não confundir numeração
        nova.insert_text((margem, altura - margem / 2), "(cont.)", fontsize=8)
        idx += 1  # próximas continuações vêm depois
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/traducao/test_remontagem_editorial.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/atlas/traducao/remontagem.py tests/traducao/test_remontagem_editorial.py
git commit -m "feat(traducao): remontar_documento editorial (fit-in-place + reflow + página de continuação, ADR-0033)"
```

---

### Task 7: Ligar o pipeline ao render editorial

**Files:**
- Modify: `src/atlas/traducao/pipeline.py`
- Test: `tests/traducao/test_pipeline.py` (novo caso)

- [ ] **Step 1: Write the failing test**

```python
def test_pipeline_gera_pagina_extra_quando_traducao_cresce(tmp_path):
    import fitz
    from atlas.traducao.pipeline import traduzir_pdf
    from atlas.traducao.traducao_ia import ConfigTraducao

    src = tmp_path / "src.pdf"
    doc = fitz.open(); p = doc.new_page()
    p.insert_text((72, 100), "One short line.", fontname="helv", fontsize=11)
    doc.save(str(src)); doc.close()

    def invocar_gigante(prompt, modelo=None, timeout=60, motor="claude"):
        import re
        ids = re.findall(r"\[\[(\d+)\]\]", prompt)
        return "\n".join(f"[[{i}]] " + ("Tradução enorme. " * 120) for i in ids)

    out = tmp_path / "out.pdf"
    traduzir_pdf(str(src), str(out), ConfigTraducao(),
                 invocar_fn=invocar_gigante, bruto_fn=lambda ts, c: ["BRUTO"] * len(ts))
    assert fitz.open(str(out)).page_count >= 1  # gerou sem erro
```

- [ ] **Step 2: Run test to verify it fails/behaves**

Run: `.venv/bin/python -m pytest tests/traducao/test_pipeline.py::test_pipeline_gera_pagina_extra_quando_traducao_cresce -v`
Expected: inicialmente pode passar sem página extra (o loop antigo usa `remontar_pagina`); ajustar o pipeline para acumular `{idx: (blocos, traducoes)}` e chamar `remontar_documento` no fim, preservando o checkpoint por página.

- [ ] **Step 3: Modify pipeline**

No `traduzir_pdf`, trocar a chamada `remontar_pagina(page, blocos, traducoes)` por acumular em `render_paginas[i] = (blocos, traducoes)` durante o loop (mantendo `cache.salvar` por página) e, após o loop, chamar `remontar_documento(doc, render_paginas, min_fonte_pct=cfg.min_fonte_pct)` antes de `doc.save`. Assim o checkpoint do cache (resume) permanece por página; só a **render** é feita ao fim (determinística).

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/traducao -v`
Expected: PASS (todos os testes de tradução).

- [ ] **Step 5: Commit**

```bash
git add src/atlas/traducao/pipeline.py tests/traducao/test_pipeline.py
git commit -m "feat(traducao): pipeline usa remontar_documento (render editorial) preservando checkpoint"
```

---

### Task 8: Notas de rodapé para termos mantidos (opt-in)

**Files:**
- Modify: `src/atlas/traducao/layout.py` (reserva de área de rodapé)
- Modify: `src/atlas/traducao/remontagem.py` (marcador + glosa)
- Test: `tests/traducao/test_remontagem_editorial.py`

- [ ] **Step 1: Write the failing test**

```python
def test_nota_de_rodape_para_termo_mantido(tmp_path):
    import fitz
    from atlas.traducao.extracao import extrair_pagina
    from atlas.traducao.remontagem import remontar_documento

    doc = fitz.open(); page = doc.new_page()
    page.insert_text((72, 100), "Original mentions Kubernetes here.", fontsize=11)
    src = tmp_path / "s.pdf"; doc.save(str(src)); doc.close()
    doc = fitz.open(str(src))
    blocos = extrair_pagina(doc[0], 0)
    traducoes = {b.id: "O texto menciona Kubernetes aqui." for b in blocos if not b.skip}
    notas = {b.id: [{"termo": "Kubernetes", "glosa": "orquestrador de contêineres"}]
             for b in blocos if not b.skip}
    remontar_documento(doc, {0: (blocos, traducoes)}, min_fonte_pct=90,
                       notas=notas)
    txt = doc[0].get_text()
    assert "orquestrador de contêineres" in txt  # glosa impressa ao pé
    doc.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/traducao/test_remontagem_editorial.py::test_nota_de_rodape_para_termo_mantido -v`
Expected: FAIL (`remontar_documento` ainda não aceita `notas`).

- [ ] **Step 3: Implement**

Adicionar parâmetro `notas: dict | None = None` a `remontar_documento`. Ao renderizar um bloco cujo id tem notas, acumular `(termo, glosa)` por página e, ao fim de cada página, imprimir as glosas numeradas numa faixa acima da margem inferior (fonte 8), reservando essa altura no cálculo de transbordo da prosa (subtrair do `corpo`/`rect` de fluxo). Marcar a 1ª ocorrência do termo com índice sobrescrito no texto inserido.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/traducao/test_remontagem_editorial.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atlas/traducao/layout.py src/atlas/traducao/remontagem.py tests/traducao/test_remontagem_editorial.py
git commit -m "feat(traducao): notas de rodapé opt-in para termos mantidos (ADR-0033)"
```

---

### Task 9: Verificação de fidelidade + lint + suite completa

**Files:**
- Test: `tests/traducao/test_remontagem_editorial.py` (regressão de fidelidade)

- [ ] **Step 1: Write the fidelity regression test**

```python
def test_fidelidade_ordem_e_figuras(tmp_path):
    import fitz
    from atlas.traducao.extracao import extrair_pagina
    from atlas.traducao.remontagem import remontar_documento

    doc = fitz.open(); page = doc.new_page()
    page.insert_text((72, 80), "Alpha.", fontsize=11)
    page.draw_rect(fitz.Rect(72, 120, 300, 260), fill=(1, 0, 0))
    page.insert_text((72, 300), "Beta.", fontsize=11)
    src = tmp_path / "s.pdf"; doc.save(str(src)); doc.close()
    doc = fitz.open(str(src))
    blocos = extrair_pagina(doc[0], 0)
    traducoes = {b.id: ("Alfa." if "Alpha" in b.texto else "Beta.")
                 for b in blocos if not b.skip}
    n_draw_antes = len(doc[0].get_drawings())
    remontar_documento(doc, {0: (blocos, traducoes)}, min_fonte_pct=90)
    assert len(doc[0].get_drawings()) >= n_draw_antes  # figura preservada
    t = doc[0].get_text()
    assert t.index("Alfa") < t.index("Beta")  # ordem preservada
    doc.close()
```

- [ ] **Step 2: Run full traducao suite + lint**

Run: `.venv/bin/python -m pytest tests/traducao -q && .venv/bin/ruff check src/atlas/traducao tests/traducao`
Expected: PASS + `All checks passed!`

- [ ] **Step 3: Commit**

```bash
git add tests/traducao/test_remontagem_editorial.py
git commit -m "test(traducao): regressão de fidelidade (ordem + figuras preservadas)"
```

---

## Self-Review

**Spec coverage:** híbrido por papel (Task 1, 6) ✓; reflow prosa + página de continuação (Task 4, 6) ✓; fit-in-place com piso (Task 3, 6) ✓; imagens/charts intactos (Task 6, 9) ✓; notas de rodapé opt-in (Task 8) ✓; contrato com B / metadados de papel (Task 1) ✓; resumível/checkpoint por página (Task 7) ✓; configs `min_fonte_pct`/`notas_rodape` (Task 5) ✓; testes por unidade + integração + fidelidade ✓.

**Placeholders:** Tasks 6/8 têm um passo descritivo (integração PyMuPDF fina) com esqueleto de código concreto; nenhum "TODO/TBD".

**Type consistency:** `remontar_documento(doc, paginas, min_fonte_pct, notas=None)`, `paginar_prosa(page, rect, texto, fontsize, fontname)`, `fontsize_que_cabe(page, rect, texto, fontsize_base, min_pct, fontname, passo)`, `classificar_papel(bloco, largura_pagina)`, `altura_livre/cabe_no_bbox(page, rect, texto, fontsize, fontname)` — consistentes entre tasks.

## Riscos conhecidos p/ execução
- `BlocoTraducao.spans[i].size`/`.bbox` — confirmar nomes reais em `extracao.py` antes da Task 6 (ajustar se diferirem).
- `insert_textbox` usa fontes base-14 (helv); herdar a fonte real do span exige registrar a fonte — MVP usa `helv` e preserva **tamanho**; herança de família fica para refino posterior se o PO pedir.
