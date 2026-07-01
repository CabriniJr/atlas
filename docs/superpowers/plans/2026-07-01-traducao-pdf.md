# Tradutor de PDFs de alta fidelidade — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um job acoplável do Atlas que traduz PDFs inteiros preservando 100% do design (fonte, cor, imagem, vetor, posição) e mudando apenas o texto, traduzido por IA com contexto técnico; termos técnicos e código permanecem em inglês.

**Architecture:** Kind novo `Traducao` (objeto na API, P11) processado por um collect acoplável `traduzir-pdf` (`@registrar`, espelhando `rotinas/prompt.py`). O motor de tradução é um pacote `atlas.traducao` com 4 estágios (extrair → traduzir → remontar → checkpoint) sobre PyMuPDF (`fitz`). A IA é a do Atlas (`ia.invocar`). On-demand via `/run`/API.

**Tech Stack:** Python 3.12+, PyMuPDF (`pymupdf`/`fitz`), stdlib (`hashlib`, `json`, `re`, `dataclasses`), pytest. IA via `atlas.ia.invocar`.

**Escopo deste plano:** o **motor backend + Kind + collect** — entregável testável e usável via `/apply Traducao ...` + `/run`. A **view no web shell (ADR-0029)** é um plano seguinte (fora deste).

---

## Estrutura de arquivos

- Create: `docs/arquitetura/adr/ADR-0030-kind-traducao-pdf.md` — decisão (Kind + dep PyMuPDF).
- Modify: `pyproject.toml` — adiciona dep `pymupdf`.
- Create: `src/atlas/traducao/__init__.py` — pacote do motor.
- Create: `src/atlas/traducao/extracao.py` — `Span`, `BlocoTraducao`, `extrair_pagina`.
- Create: `src/atlas/traducao/traducao_ia.py` — `ConfigTraducao`, `CacheTraducao`, `montar_prompt`, `parsear_resposta`, `traduzir_blocos`.
- Create: `src/atlas/traducao/remontagem.py` — `remontar_pagina` (redaction + insert_textbox auto-fit + fallback de glyphs).
- Create: `src/atlas/traducao/pipeline.py` — `traduzir_pdf` (orquestra estágios, progresso, resumível).
- Create: `src/atlas/rotinas/traduzir_pdf.py` — collect `@registrar("traduzir-pdf")`.
- Modify: `src/atlas/app.py:23` — importa o módulo do collect (registro).
- Create: `routines/traduzir-pdf/routine.toml` — job exemplo (on-demand).
- Create: `tests/traducao/conftest.py` — fixture que gera PDFs de teste com `fitz`.
- Create: `tests/traducao/test_extracao.py`, `test_traducao_ia.py`, `test_remontagem.py`, `test_pipeline.py`, `test_collect_traduzir_pdf.py`.
- Modify: `docs/arquitetura/adr/README.md` — lista o ADR-0030.

Convenções de dados (usadas em todas as tasks):

```python
# extracao.py
@dataclass
class Span:
    text: str
    bbox: tuple[float, float, float, float]
    font: str
    size: float
    color: int      # inteiro RGB do fitz (0xRRGGBB)
    flags: int      # bitmask do fitz; bit 3 (valor 8) = monospaced

@dataclass
class BlocoTraducao:
    id: int
    pagina: int
    bbox: tuple[float, float, float, float]   # união dos spans do bloco
    texto: str                                 # spans juntados por espaço
    spans: list[Span]
    skip: bool                                 # True = código/monospace/numérico → não traduz
```

```python
# traducao_ia.py
@dataclass
class ConfigTraducao:
    idioma_origem: str = "en"
    idioma_destino: str = "pt-BR"
    assunto: str = ""
    glossario: list[str] = field(default_factory=list)
    motor: str = "claude"
    modelo: str | None = None
```

---

## Task 1: ADR-0030 + dependência PyMuPDF

**Files:**
- Create: `docs/arquitetura/adr/ADR-0030-kind-traducao-pdf.md`
- Modify: `pyproject.toml` (linha 6)
- Modify: `docs/arquitetura/adr/README.md`

- [ ] **Step 1: Escrever o ADR-0030**

Crie `docs/arquitetura/adr/ADR-0030-kind-traducao-pdf.md` seguindo o template. Conteúdo essencial (preencher as seções do template `docs/arquitetura/adr/template-adr.md`):
- `status: aceito`, `atualizado-em: 2026-07-01`.
- **Contexto:** não há tradução de documentos; PDF fiel exige biblioteca; escolha entre in-place vs re-render (linkar SPEC-TRADUCAO-PDF em `docs/superpowers/specs/2026-07-01-traducao-pdf-design.md`).
- **Decisão:** (1) Kind `Traducao` (schema no spec); (2) collect acoplável `traduzir-pdf`; (3) adotar **PyMuPDF (`pymupdf`)** como dependência — abordagem in-place redaction+reinsert; (4) IA via `ia.invocar`, código/monospace nunca traduzido, termos do glossário em inglês.
- **Alternativas:** span-a-span (estoura); PDF→HTML→re-render (design deriva); ambas rejeitadas.
- **Consequências:** nova dep externa (colide com "zero deps" — justificada); Kind novo; custo de IA por livro mitigado por cache/estimativa.

- [ ] **Step 2: Adicionar a dependência**

Em `pyproject.toml`, linha 6, altere:
```toml
dependencies = ["pyyaml>=6", "cryptography>=42", "pymupdf>=1.24"]
```

- [ ] **Step 3: Instalar e verificar o import**

Run: `pip install -e . && python -c "import fitz; print(fitz.__doc__.splitlines()[0])"`
Expected: imprime a versão do PyMuPDF sem erro.

- [ ] **Step 4: Registrar o ADR no índice**

Em `docs/arquitetura/adr/README.md`, adicione a linha do ADR-0030 na lista (seguir o formato das demais entradas).

- [ ] **Step 5: Commit**

```bash
git add docs/arquitetura/adr/ADR-0030-kind-traducao-pdf.md docs/arquitetura/adr/README.md pyproject.toml
git commit -m "feat(traducao): ADR-0030 Kind Traducao + dep PyMuPDF"
```

---

## Task 2: Extração de blocos (`extracao.py`)

**Files:**
- Create: `src/atlas/traducao/__init__.py` (vazio com docstring)
- Create: `src/atlas/traducao/extracao.py`
- Create: `tests/traducao/conftest.py`
- Test: `tests/traducao/test_extracao.py`

- [ ] **Step 1: Fixture que gera PDFs de teste**

Crie `tests/traducao/conftest.py`:
```python
"""Fixtures: gera PDFs mínimos com fitz para testar o motor de tradução."""
from __future__ import annotations
import fitz
import pytest


@pytest.fixture
def pdf_simples(tmp_path):
    """1 página, 1 bloco de texto normal + 1 bloco monospace (código)."""
    path = tmp_path / "simples.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "The deployment scales the pod.", fontname="helv", fontsize=12)
    page.insert_text((72, 200), "kubectl get pods", fontname="cour", fontsize=12)  # monospace
    doc.save(path)
    doc.close()
    return str(path)
```

- [ ] **Step 2: Escrever o teste que falha**

Crie `tests/traducao/test_extracao.py`:
```python
from atlas.traducao.extracao import extrair_pagina, BlocoTraducao
import fitz


def test_extrai_blocos_com_metadados(pdf_simples):
    doc = fitz.open(pdf_simples)
    blocos = extrair_pagina(doc[0], 0)
    assert len(blocos) >= 2
    normal = [b for b in blocos if "deployment" in b.texto][0]
    assert isinstance(normal, BlocoTraducao)
    assert normal.pagina == 0
    assert normal.skip is False
    assert normal.spans[0].size == 12


def test_marca_monospace_como_skip(pdf_simples):
    doc = fitz.open(pdf_simples)
    blocos = extrair_pagina(doc[0], 0)
    codigo = [b for b in blocos if "kubectl" in b.texto][0]
    assert codigo.skip is True
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `pytest tests/traducao/test_extracao.py -v`
Expected: FAIL (ModuleNotFoundError: atlas.traducao.extracao).

- [ ] **Step 4: Implementar `extracao.py`**

Crie `src/atlas/traducao/__init__.py`:
```python
"""Motor de tradução de PDFs de alta fidelidade (ADR-0030)."""
```

Crie `src/atlas/traducao/extracao.py`:
```python
"""Extração de blocos tradutíveis de uma página PDF (ADR-0030, estágio 1).

Usa ``page.get_text("dict")`` do PyMuPDF. Agrupa spans em blocos (unidades de
tradução). Marca ``skip=True`` para código (fonte monospace) e blocos sem letras.
"""
from __future__ import annotations

from dataclasses import dataclass, field

_FLAG_MONOSPACE = 8  # bit 3 do flags do fitz


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


def _tem_letra(texto: str) -> bool:
    return any(c.isalpha() for c in texto)


def extrair_pagina(page, pagina: int) -> list[BlocoTraducao]:
    d = page.get_text("dict")
    blocos: list[BlocoTraducao] = []
    for bid, bloco in enumerate(d.get("blocks", [])):
        if "lines" not in bloco:  # bloco de imagem — ignora
            continue
        spans: list[Span] = []
        partes: list[str] = []
        mono = False
        for linha in bloco["lines"]:
            for s in linha.get("spans", []):
                spans.append(Span(
                    text=s["text"], bbox=tuple(s["bbox"]), font=s.get("font", ""),
                    size=s.get("size", 0.0), color=s.get("color", 0),
                    flags=s.get("flags", 0),
                ))
                partes.append(s["text"])
                if s.get("flags", 0) & _FLAG_MONOSPACE:
                    mono = True
        if not spans:
            continue
        texto = " ".join(p.strip() for p in partes if p.strip())
        skip = mono or not _tem_letra(texto)
        blocos.append(BlocoTraducao(
            id=bid, pagina=pagina, bbox=tuple(bloco["bbox"]),
            texto=texto, spans=spans, skip=skip,
        ))
    return blocos
```

- [ ] **Step 5: Rodar e ver passar**

Run: `pytest tests/traducao/test_extracao.py -v`
Expected: PASS (2 testes).

- [ ] **Step 6: Commit**

```bash
git add src/atlas/traducao/__init__.py src/atlas/traducao/extracao.py tests/traducao/conftest.py tests/traducao/test_extracao.py
git commit -m "feat(traducao): extracao de blocos com deteccao de codigo"
```

---

## Task 3: Tradução por IA com cache e glossário (`traducao_ia.py`)

**Files:**
- Create: `src/atlas/traducao/traducao_ia.py`
- Test: `tests/traducao/test_traducao_ia.py`

- [ ] **Step 1: Escrever os testes que falham**

Crie `tests/traducao/test_traducao_ia.py`:
```python
from atlas.traducao.traducao_ia import (
    ConfigTraducao, CacheTraducao, montar_prompt, parsear_resposta, traduzir_blocos,
)
from atlas.traducao.extracao import BlocoTraducao


def _bloco(bid, texto):
    return BlocoTraducao(id=bid, pagina=0, bbox=(0, 0, 1, 1), texto=texto, spans=[], skip=False)


def test_prompt_inclui_glossario_e_assunto():
    cfg = ConfigTraducao(assunto="Kubernetes", glossario=["pod", "deployment"])
    prompt = montar_prompt([_bloco(1, "The pod restarts.")], cfg)
    assert "Kubernetes" in prompt
    assert "pod" in prompt and "deployment" in prompt
    assert "[[1]]" in prompt  # marcador de bloco


def test_parseia_resposta_numerada():
    resp = "[[1]] O pod reinicia.\n[[2]] O deployment escala."
    out = parsear_resposta(resp, [1, 2])
    assert out == {1: "O pod reinicia.", 2: "O deployment escala."}


def test_traduz_usa_cache_e_nao_repaga(monkeypatch):
    cfg = ConfigTraducao()
    chamadas = []

    def fake_invocar(prompt, modelo=None, timeout=60, motor="claude"):
        chamadas.append(prompt)
        return "[[1]] O pod reinicia."

    cache = CacheTraducao()
    b = [_bloco(1, "The pod restarts.")]
    r1 = traduzir_blocos(b, cfg, cache, invocar_fn=fake_invocar)
    r2 = traduzir_blocos(b, cfg, cache, invocar_fn=fake_invocar)  # 2a vez: cache hit
    assert r1[1] == "O pod reinicia." and r2[1] == "O pod reinicia."
    assert len(chamadas) == 1  # só chamou a IA uma vez
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/traducao/test_traducao_ia.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implementar `traducao_ia.py`**

Crie `src/atlas/traducao/traducao_ia.py`:
```python
"""Tradução de blocos via IA (ADR-0030, estágio 2).

Envia blocos numerados ao ``ia.invocar`` num único prompt (batch), com instrução
de tradução técnica + glossário (termos que ficam em inglês). Cache por hash do
texto normalizado evita repagar blocos idênticos (repetições, reprocessamento).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from atlas.ia import _MODELO_PADRAO
from atlas.ia import invocar as _invocar_padrao
from atlas.traducao.extracao import BlocoTraducao

_RE_BLOCO = re.compile(r"\[\[(\d+)\]\]\s*(.*?)(?=\n\[\[\d+\]\]|\Z)", re.DOTALL)


@dataclass
class ConfigTraducao:
    idioma_origem: str = "en"
    idioma_destino: str = "pt-BR"
    assunto: str = ""
    glossario: list[str] = field(default_factory=list)
    motor: str = "claude"
    modelo: str | None = None


class CacheTraducao:
    """Cache texto-normalizado → tradução. Opcionalmente persistido em JSON."""

    def __init__(self, inicial: dict[str, str] | None = None) -> None:
        self._d: dict[str, str] = dict(inicial or {})

    @staticmethod
    def _chave(texto: str, cfg: "ConfigTraducao") -> str:
        base = f"{cfg.idioma_origem}>{cfg.idioma_destino}:{texto.strip()}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    def get(self, texto: str, cfg: "ConfigTraducao") -> str | None:
        return self._d.get(self._chave(texto, cfg))

    def put(self, texto: str, cfg: "ConfigTraducao", traducao: str) -> None:
        self._d[self._chave(texto, cfg)] = traducao

    def to_dict(self) -> dict[str, str]:
        return dict(self._d)


def montar_prompt(blocos: list[BlocoTraducao], cfg: ConfigTraducao) -> str:
    glossario = ", ".join(cfg.glossario) if cfg.glossario else "(nenhum)"
    corpo = "\n".join(f"[[{b.id}]] {b.texto}" for b in blocos)
    return (
        f"Traduza de {cfg.idioma_origem} para {cfg.idioma_destino} o texto de um livro "
        f"técnico sobre: {cfg.assunto or 'tecnologia'}.\n"
        f"Regras: preserve o tom técnico; NÃO traduza termos técnicos, nomes de APIs, "
        f"comandos ou código; mantenha em inglês os termos do glossário: {glossario}.\n"
        f"Responda cada bloco no MESMO formato numerado, sem comentários extras:\n"
        f"[[N]] <tradução>\n\n{corpo}"
    )


def parsear_resposta(resposta: str, ids: list[int]) -> dict[int, str]:
    achados = {int(n): t.strip() for n, t in _RE_BLOCO.findall(resposta)}
    return {i: achados[i] for i in ids if i in achados}


def traduzir_blocos(
    blocos: list[BlocoTraducao],
    cfg: ConfigTraducao,
    cache: CacheTraducao,
    invocar_fn=_invocar_padrao,
) -> dict[int, str]:
    resultado: dict[int, str] = {}
    pendentes: list[BlocoTraducao] = []
    for b in blocos:
        cached = cache.get(b.texto, cfg)
        if cached is not None:
            resultado[b.id] = cached
        else:
            pendentes.append(b)
    if pendentes:
        prompt = montar_prompt(pendentes, cfg)
        # cfg.modelo pode ser None → usa o padrão do motor (invocar não aceita None).
        resposta = invocar_fn(prompt, modelo=cfg.modelo or _MODELO_PADRAO, motor=cfg.motor)
        traducoes = parsear_resposta(resposta, [b.id for b in pendentes])
        for b in pendentes:
            t = traducoes.get(b.id, b.texto)  # fallback: mantém original se IA falhou
            cache.put(b.texto, cfg, t)
            resultado[b.id] = t
    return resultado
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/traducao/test_traducao_ia.py -v`
Expected: PASS (3 testes).

- [ ] **Step 5: Commit**

```bash
git add src/atlas/traducao/traducao_ia.py tests/traducao/test_traducao_ia.py
git commit -m "feat(traducao): traducao por IA com batch, cache e glossario"
```

---

## Task 4: Remontagem com fidelidade (`remontagem.py`)

**Files:**
- Create: `src/atlas/traducao/remontagem.py`
- Test: `tests/traducao/test_remontagem.py`

- [ ] **Step 1: Escrever os testes que falham**

Crie `tests/traducao/test_remontagem.py`:
```python
import fitz
from atlas.traducao.extracao import extrair_pagina
from atlas.traducao.remontagem import remontar_pagina


def test_substitui_texto_preservando_imagem_e_pulando_codigo(tmp_path):
    # PDF com texto normal, código e uma imagem (retângulo desenhado vira vetor;
    # usamos insert_image com um pixmap sólido para ter um stream de imagem).
    path = tmp_path / "in.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "The pod restarts.", fontname="helv", fontsize=12)
    page.insert_text((72, 200), "kubectl get pods", fontname="cour", fontsize=12)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 20, 20))
    pix.set_rect(pix.irect, (255, 0, 0))
    page.insert_image(fitz.Rect(300, 80, 320, 100), pixmap=pix)
    doc.save(path)

    doc = fitz.open(path)
    page = doc[0]
    blocos = extrair_pagina(page, 0)
    normal = [b for b in blocos if "pod" in b.texto][0]
    traducoes = {normal.id: "O contêiner reinicia."}
    remontar_pagina(page, blocos, traducoes)
    out = tmp_path / "out.pdf"
    doc.save(out)

    doc2 = fitz.open(out)
    texto = doc2[0].get_text()
    assert "The pod restarts" not in texto      # original removido
    assert "contêiner" in texto                  # tradução com acento presente
    assert "kubectl get pods" in texto           # código intacto (skip)
    assert len(doc2[0].get_images()) == 1        # imagem preservada
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/traducao/test_remontagem.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implementar `remontagem.py`**

Crie `src/atlas/traducao/remontagem.py`:
```python
"""Remontagem: apaga o texto original e reinsere a tradução (ADR-0030, estágio 3).

Só o texto é tocado: ``add_redact_annot`` + ``apply_redactions`` removem os glyphs
originais; imagens e vetores permanecem. A tradução é reinserida no bbox do bloco
com auto-fit (encolhe a fonte até caber). Fonte builtin ``helv`` cobre acentos
latinos, evitando falta de glyphs em fontes embutidas subsetadas.
"""
from __future__ import annotations

from atlas.traducao.extracao import BlocoTraducao

_FONTE_FALLBACK = "helv"       # Helvetica builtin — cobre latino/acentos
_MIN_FONTSIZE = 5.0


def _cor_rgb(color: int) -> tuple[float, float, float]:
    return ((color >> 16 & 255) / 255, (color >> 8 & 255) / 255, (color & 255) / 255)


def remontar_pagina(page, blocos: list[BlocoTraducao], traducoes: dict[int, str]) -> None:
    # 1) Redaction dos spans dos blocos que serão traduzidos (skip fica intacto).
    for b in blocos:
        if b.skip or b.id not in traducoes:
            continue
        for s in b.spans:
            page.add_redact_annot(s.bbox)
    page.apply_redactions()

    # 2) Reinsere a tradução no bbox do bloco, com auto-fit.
    for b in blocos:
        if b.skip or b.id not in traducoes:
            continue
        texto = traducoes[b.id]
        base_size = b.spans[0].size if b.spans else 11.0
        color = _cor_rgb(b.spans[0].color if b.spans else 0)
        rect = _com_folga(b.bbox)
        size = base_size
        while size >= _MIN_FONTSIZE:
            sobra = page.insert_textbox(
                rect, texto, fontname=_FONTE_FALLBACK, fontsize=size,
                color=color, align=0,
            )
            if sobra >= 0:   # >= 0: coube
                break
            size -= 0.5      # não coube: encolhe e tenta de novo


def _com_folga(bbox: tuple[float, float, float, float]) -> "object":
    import fitz
    x0, y0, x1, y1 = bbox
    # margem inferior extra p/ absorver PT mais longo sem estourar o bloco.
    return fitz.Rect(x0, y0, x1, y1 + (y1 - y0) * 0.6)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/traducao/test_remontagem.py -v`
Expected: PASS. Se `insert_textbox` reportar não-caber mesmo no mínimo, o texto ainda é inserido no último passo (size mínimo) — o teste só exige presença do texto.

- [ ] **Step 5: Commit**

```bash
git add src/atlas/traducao/remontagem.py tests/traducao/test_remontagem.py
git commit -m "feat(traducao): remontagem in-place com auto-fit e fallback de glyphs"
```

---

## Task 5: Pipeline orquestrador (`pipeline.py`)

**Files:**
- Create: `src/atlas/traducao/pipeline.py`
- Test: `tests/traducao/test_pipeline.py`

- [ ] **Step 1: Escrever os testes que falham**

Crie `tests/traducao/test_pipeline.py`:
```python
import fitz
from atlas.traducao.pipeline import traduzir_pdf, ProgressoTraducao
from atlas.traducao.traducao_ia import ConfigTraducao


def _fake_invocar_factory(contador):
    def fake(prompt, modelo=None, timeout=60, motor="claude"):
        contador.append(1)
        # devolve cada bloco com prefixo PT determinístico
        import re
        ids = re.findall(r"\[\[(\d+)\]\]", prompt)
        return "\n".join(f"[[{i}]] TRADUZIDO {i}" for i in ids)
    return fake


def test_traduz_pdf_gera_saida_e_reporta_progresso(tmp_path):
    src = tmp_path / "src.pdf"
    doc = fitz.open()
    for n in range(2):
        p = doc.new_page()
        p.insert_text((72, 100), f"Page {n} content here.", fontname="helv", fontsize=12)
    doc.save(src)

    out = tmp_path / "out.pdf"
    progresso = []
    contador = []
    cfg = ConfigTraducao()
    res = traduzir_pdf(
        str(src), str(out), cfg,
        invocar_fn=_fake_invocar_factory(contador),
        on_progress=lambda p: progresso.append(p.paginas_prontas),
    )
    assert isinstance(res, ProgressoTraducao)
    assert res.paginas_total == 2
    assert res.paginas_prontas == 2
    assert progresso == [1, 2]
    assert out.exists()
    assert "TRADUZIDO" in fitz.open(out)[0].get_text()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/traducao/test_pipeline.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implementar `pipeline.py`**

Crie `src/atlas/traducao/pipeline.py`:
```python
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
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/traducao/test_pipeline.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atlas/traducao/pipeline.py tests/traducao/test_pipeline.py
git commit -m "feat(traducao): pipeline orquestrador por pagina com checkpoint"
```

---

## Task 6: Collect acoplável `traduzir-pdf` (Kind Traducao)

**Files:**
- Create: `src/atlas/rotinas/traduzir_pdf.py`
- Modify: `src/atlas/app.py` (após a linha 23)
- Create: `routines/traduzir-pdf/routine.toml`
- Test: `tests/traducao/test_collect_traduzir_pdf.py`

- [ ] **Step 1: Escrever o teste que falha**

Crie `tests/traducao/test_collect_traduzir_pdf.py`:
```python
import fitz
from datetime import datetime, timezone
from types import SimpleNamespace

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
import atlas.rotinas.traduzir_pdf as mod
from atlas.rotinas import obter


def test_collect_registrado():
    assert obter("traduzir-pdf") is not None


def test_collect_traduz_e_atualiza_status(tmp_path, monkeypatch):
    src = tmp_path / "livro.pdf"
    doc = fitz.open(); p = doc.new_page()
    p.insert_text((72, 100), "The pod restarts.", fontname="helv", fontsize=12)
    doc.save(src); doc.close()

    store = ResourceStore(":memory:")
    agora = datetime.now(timezone.utc)
    store.apply(Resource(kind="Traducao", name="livro", spec={
        "origem": str(src), "idioma_destino": "pt-BR", "assunto": "Kubernetes",
        "glossario": ["pod"],
    }), agora)

    def fake_invocar(prompt, modelo=None, timeout=60, motor="claude"):
        import re
        ids = re.findall(r"\[\[(\d+)\]\]", prompt)
        return "\n".join(f"[[{i}]] O contêiner reinicia." for i in ids)

    monkeypatch.setattr(mod, "invocar", fake_invocar)

    ctx = SimpleNamespace(
        rotina=SimpleNamespace(nome="traduzir-pdf", label="livro"),
        store=store, agora=agora,
    )
    res = mod.collect(ctx)

    t = store.get("Traducao", "livro")
    assert t.status["fase"] == "pronto"
    assert t.status["saida"].endswith(".pt-BR.pdf")
    assert t.status["paginas_prontas"] == 1
    assert "✓" in res.data["_saida"]
    # arquivo de saída existe e tem a tradução
    assert "contêiner" in fitz.open(t.status["saida"])[0].get_text()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/traducao/test_collect_traduzir_pdf.py -v`
Expected: FAIL (ModuleNotFoundError: atlas.rotinas.traduzir_pdf).

- [ ] **Step 3: Implementar o collect**

Crie `src/atlas/rotinas/traduzir_pdf.py`:
```python
"""Collect acoplável ``traduzir-pdf`` — traduz um Kind ``Traducao`` (ADR-0030).

Espelha ``rotinas/prompt.py``: a rotina aponta um ``Traducao/<label>``; o collect
lê o spec, roda o pipeline de tradução e grava progresso/saída no ``status``.
On-demand (via ``/run``/API), não por cron.
"""
from __future__ import annotations

import logging
from pathlib import Path

from atlas.executor import CollectResult, ContextoExecucao
from atlas.ia import invocar  # noqa: F401 — referenciado; mockável nos testes
from atlas.rotinas import registrar
from atlas.traducao.pipeline import traduzir_pdf
from atlas.traducao.traducao_ia import ConfigTraducao

_log = logging.getLogger(__name__)


def _saida_para(origem: str, idioma_destino: str) -> str:
    p = Path(origem)
    return str(p.with_suffix(f".{idioma_destino}.pdf"))


@registrar("traduzir-pdf")
def collect(ctx: ContextoExecucao) -> CollectResult:
    label = getattr(ctx.rotina, "label", None) or ctx.rotina.nome
    store = getattr(ctx, "store", None)
    if store is None:
        return CollectResult(data={"_saida": f"⚠️ traduzir-pdf/{label}: store indisponível."})

    t = store.get("Traducao", label)
    if t is None:
        return CollectResult(data={"_saida": (
            f"❓ traduzir-pdf/{label}: Traducao não encontrada.\n"
            f'Crie com: /apply Traducao {label} spec.origem="data/pdfs/x.pdf"'
        )})

    origem = (t.spec.get("origem") or "").strip()
    if not origem or not Path(origem).exists():
        _erro(store, t, ctx, f"origem ausente/inexistente: {origem!r}")
        return CollectResult(data={"_saida": f"⚠️ traduzir-pdf/{label}: origem inválida ({origem!r})."})

    idioma_destino = t.spec.get("idioma_destino", "pt-BR")
    saida = _saida_para(origem, idioma_destino)
    cfg = ConfigTraducao(
        idioma_origem=t.spec.get("idioma_origem", "en"),
        idioma_destino=idioma_destino,
        assunto=t.spec.get("assunto", ""),
        glossario=list(t.spec.get("glossario", []) or []),
        motor=t.spec.get("motor", "claude"),
        modelo=t.spec.get("modelo"),
    )

    _status(store, t, ctx, {"fase": "traduzindo", "saida": None, "erro": None})

    def on_progress(prog):
        _status(store, t, ctx, {
            "fase": "traduzindo", "paginas_total": prog.paginas_total,
            "paginas_prontas": prog.paginas_prontas,
        })

    try:
        prog = traduzir_pdf(origem, saida, cfg, invocar_fn=invocar, on_progress=on_progress)
    except Exception as exc:  # noqa: BLE001 — nunca derruba o loop (ADR-0006)
        _log.exception("traduzir-pdf/%s falhou", label)
        _erro(store, t, ctx, str(exc))
        return CollectResult(data={"_saida": f"⚠️ traduzir-pdf/{label} falhou: {exc}"})

    _status(store, t, ctx, {
        "fase": "pronto", "saida": saida, "paginas_total": prog.paginas_total,
        "paginas_prontas": prog.paginas_prontas, "erro": None,
    })
    return CollectResult(data={"_saida": (
        f"✓ traduzir-pdf/{label}: {prog.paginas_prontas} páginas → {saida}"
    )})


def _status(store, t, ctx, patch: dict) -> None:
    novo = {**(store.get("Traducao", t.name).status or {}), **patch}
    store.set_status("Traducao", t.name, novo, ctx.agora)


def _erro(store, t, ctx, msg: str) -> None:
    _status(store, t, ctx, {"fase": "erro", "erro": msg})
```

- [ ] **Step 4: Registrar o import no app**

Em `src/atlas/app.py`, após a linha 23 (`import atlas.rotinas.treino ...`), adicione:
```python
import atlas.rotinas.traduzir_pdf  # noqa: F401 — registra collect de tradução de PDF (Kind=Traducao)
```

- [ ] **Step 5: Criar o job exemplo**

Crie `routines/traduzir-pdf/routine.toml`:
```toml
nome = "traduzir-pdf"
descricao = "Traduz um Kind Traducao/<label> preservando o design do PDF."
label = "exemplo"          # nome do Traducao a processar
coletar = "traduzir-pdf"
modelo = "none"            # a IA roda DENTRO do collect, não pelo executor
saida = "telegram"
ativa = false             # on-demand: dispara via /run, não por agenda
```

- [ ] **Step 6: Rodar e ver passar**

Run: `pytest tests/traducao/test_collect_traduzir_pdf.py -v`
Expected: PASS (2 testes).

- [ ] **Step 7: Commit**

```bash
git add src/atlas/rotinas/traduzir_pdf.py src/atlas/app.py routines/traduzir-pdf/routine.toml tests/traducao/test_collect_traduzir_pdf.py
git commit -m "feat(traducao): collect acoplavel traduzir-pdf (Kind Traducao)"
```

---

## Task 7: Teste de integração ponta-a-ponta

**Files:**
- Test: `tests/traducao/test_integracao.py`

- [ ] **Step 1: Escrever o teste ponta-a-ponta**

Crie `tests/traducao/test_integracao.py`:
```python
import fitz
from atlas.traducao.pipeline import traduzir_pdf
from atlas.traducao.traducao_ia import ConfigTraducao


def test_livro_multibloco_preserva_design_e_glossario(tmp_path):
    src = tmp_path / "livro.pdf"
    doc = fitz.open(); page = doc.new_page()
    page.insert_text((72, 100), "The pod scales automatically.", fontname="helv", fontsize=12)
    page.insert_text((72, 140), "kubectl apply -f pod.yaml", fontname="cour", fontsize=11)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 16, 16)); pix.set_rect(pix.irect, (0, 128, 255))
    page.insert_image(fitz.Rect(300, 90, 316, 106), pixmap=pix)
    doc.save(src); doc.close()

    def fake_invocar(prompt, modelo=None, timeout=60, motor="claude"):
        import re
        ids = re.findall(r"\[\[(\d+)\]\]", prompt)
        # mantém "pod" (glossário) em inglês, traduz o resto com acento
        return "\n".join(f"[[{i}]] O pod escala automaticamente." for i in ids)

    out = tmp_path / "out.pdf"
    cfg = ConfigTraducao(assunto="Kubernetes", glossario=["pod"])
    traduzir_pdf(str(src), str(out), cfg, invocar_fn=fake_invocar)

    r = fitz.open(out)[0]
    texto = r.get_text()
    assert "The pod scales automatically" not in texto   # original traduzido
    assert "pod" in texto                                  # glossário preservado
    assert "automaticamente" in texto                      # acento renderiza
    assert "kubectl apply -f pod.yaml" in texto            # código intacto
    assert len(r.get_images()) == 1                        # imagem preservada
```

- [ ] **Step 2: Rodar e ver passar**

Run: `pytest tests/traducao/test_integracao.py -v`
Expected: PASS. (Todos os módulos já existem das tasks anteriores.)

- [ ] **Step 3: Rodar a suíte inteira**

Run: `pytest tests/traducao/ -v`
Expected: todos PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/traducao/test_integracao.py
git commit -m "test(traducao): integracao ponta-a-ponta preservando design e glossario"
```

---

## Task 8: Documentação do Kind e fechamento

**Files:**
- Modify: `docs/superpowers/specs/2026-07-01-traducao-pdf-design.md` (marcar status implementado, se aplicável)
- Verify: suíte completa do projeto

- [ ] **Step 1: Rodar a suíte completa do projeto**

Run: `pytest -q`
Expected: sem regressões (todos os testes do projeto passam).

- [ ] **Step 2: Verificar o registro do collect no app**

Run: `python -c "import atlas.app; from atlas.rotinas import obter; print(obter('traduzir-pdf'))"`
Expected: imprime a função collect (não `None`).

- [ ] **Step 3: Commit final (se houve ajuste de doc)**

```bash
git add -A
git commit -m "docs(traducao): fecha implementacao do Kind Traducao"
```

---

## Follow-ups (fora deste plano)

- **View no web shell (ADR-0029):** upload do PDF, estimativa de custo antes de rodar, barra de progresso lendo `status`, download do resultado. Plano próprio.
- **Estimativa de custo / budget (ADR-0005):** contar caracteres tradutíveis e abortar se passar do budget.
- **`glossario_auto`:** passada de amostragem para a IA detectar termos técnicos além do glossário manual.
- **Resumo persistido do cache em disco** (`{origem}.cache.json`) para retomar entre execuções distintas.
- **OCR** para PDFs escaneados (sem camada de texto).
```
