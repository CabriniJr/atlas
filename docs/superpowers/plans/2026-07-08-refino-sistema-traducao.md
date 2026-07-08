# Refino do Sistema de Tradução (E9-16) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fechar os gaps de controle e fallback da tradução — pausa cooperativa em paralelo, escalada visível Ollama→Claude, ajustes finos de UI e revisão do render — mantendo a fidelidade já conquistada.

**Architecture:** Pausa passa a valer nos dois loops do pipeline via checagem cooperativa entre páginas. A escalada de motor vive num **wrapper de `invocar`** construído na rotina: retries rápidos no Ollama para erro de conexão e, esgotados, muta `cfg.motor` para Claude (fonte única do motor atual, já relida pelo pipeline a cada lote) e retenta — sem switch silencioso por chamada de IA. UI e docs acompanham.

**Tech Stack:** Python 3.12, PyMuPDF (`fitz`), pytest, dashboard JS/CSS vanilla (`src/atlas/dashboard`).

**Convenções deste repo:**
- Rodar testes: `python -m pytest <caminho> -v` (venv em `.venv`; ative ou use `.venv/bin/python -m pytest`).
- Commits: Conventional Commits, direto em `main`. Terminar a mensagem com `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Testes de tradução em `tests/traducao/`; helpers `_pdf_com_n_paginas`, `_fake_bruto` já existem em `tests/traducao/test_pipeline_paralelo.py` (copiar o padrão).

---

## Estrutura de arquivos

| Arquivo | Responsabilidade | Ação |
|---|---|---|
| `src/atlas/traducao/pipeline.py` | Orquestração; honrar pausa nos dois loops | Modificar `_processar_paginas_paralelo` + `traduzir_pdf` |
| `src/atlas/traducao/traducao_ia.py` | Classificação de falha (3 classes) + config de escalada | Modificar `_classificar_erro`, `ConfigTraducao` |
| `src/atlas/rotinas/traduzir_pdf.py` | Wrapper de escalada + status `motor_efetivo` | Modificar `collect`, novo `montar_invocar_escalavel` |
| `src/atlas/dashboard/style.css` | Scroll horizontal do tabbar | Modificar `#tabbar` |
| `src/atlas/dashboard/main.js` | Wheel→scrollLeft no tabbar | Modificar `renderTabs` |
| `src/atlas/dashboard/kinds/traducao.js` | Badge de motor efetivo/escalada | Modificar `renderTraducao` |
| `src/atlas/traducao/editorial_html.py` | Revisão de sanidade do render | Revisar (só mexe com teste verde) |
| `docs/arquitetura/adr/ADR-0048-fallback-escalado-e-pausa-cooperativa.md` | ADR novo | Criar |
| `docs/roadmap/backlog.md`, `docs/specs/traducao-redesenho-e9.md` | Docs de controle | Modificar |
| Testes | `tests/traducao/test_pausa_cooperativa.py`, `test_escalada_motor.py`; `tests/test_ia.py` | Criar/estender |

---

## Task 1: Pausa cooperativa no loop paralelo

**Files:**
- Modify: `src/atlas/traducao/pipeline.py` (`_processar_paginas_paralelo`, `traduzir_pdf`)
- Test: `tests/traducao/test_pausa_cooperativa.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/traducao/test_pausa_cooperativa.py
"""TDD — pausa manual cooperativa honrada também no loop paralelo (E9-16)."""

from __future__ import annotations

import re
import threading

import fitz

from atlas.traducao.pipeline import traduzir_pdf
from atlas.traducao.traducao_ia import ConfigTraducao


def _pdf_com_n_paginas(tmp_path, n):
    src = tmp_path / "src.pdf"
    doc = fitz.open()
    for i in range(n):
        p = doc.new_page()
        p.insert_text((72, 100), f"Page {i} content here.", fontname="helv", fontsize=12)
    doc.save(src)
    return str(src)


def _fake_bruto(textos, cfg):
    return [f"BRUTO {t}" for t in textos]


def _fake_invocar(prompt, modelo=None, timeout=60, motor="claude"):
    ids = re.findall(r"\[\[(\d+)\]\]", prompt)
    return "\n".join(f"[[{i}]] TRADUZIDO {i}" for i in ids)


def test_pausa_paralela_para_e_marca_manual(tmp_path):
    """Com checar_pausa=True desde o início, o run paralelo encerra parcial e
    motivo_pausa='manual', sem processar todas as páginas."""
    src = _pdf_com_n_paginas(tmp_path, 12)
    out = tmp_path / "out.pdf"
    cfg = ConfigTraducao()

    lock = threading.Lock()
    processadas = {"n": 0}

    def conta_e_traduz(prompt, modelo=None, timeout=60, motor="claude"):
        with lock:
            processadas["n"] += 1
        return _fake_invocar(prompt)

    res = traduzir_pdf(
        src, str(out), cfg,
        invocar_fn=conta_e_traduz,
        bruto_fn=_fake_bruto,
        paralelismo=4,
        checar_pausa=lambda: True,  # pausa pedida antes de tudo
    )
    assert res.parcial
    assert res.motivo_pausa == "manual"
    # nenhuma (ou quase nenhuma) página processada: a pausa é vista já na 1ª checagem
    assert processadas["n"] < 12


def test_paralelo_sem_pausa_traduz_tudo(tmp_path):
    """Regressão: sem pausa, o paralelo continua traduzindo todas as páginas."""
    src = _pdf_com_n_paginas(tmp_path, 6)
    out = tmp_path / "out.pdf"
    res = traduzir_pdf(
        src, str(out), ConfigTraducao(),
        invocar_fn=_fake_invocar, bruto_fn=_fake_bruto,
        paralelismo=3, checar_pausa=lambda: False,
    )
    assert res.paginas_prontas == 6
    assert not res.parcial
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/traducao/test_pausa_cooperativa.py -v`
Expected: `test_pausa_paralela_para_e_marca_manual` FAILS (hoje o paralelo ignora `checar_pausa`: `res.parcial` é False / todas processadas).

- [ ] **Step 3: Add `checar_pausa` param to the parallel loop and honor it**

Em `src/atlas/traducao/pipeline.py`, altere a assinatura de `_processar_paginas_paralelo` para receber `checar_pausa` (após `paralelismo`):

```python
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
    checar_pausa=None,
):
```

Logo após `render_paginas: dict[...] = {}` (antes de `def processar`), crie o evento de pausa:

```python
    pausa_evt = threading.Event()
```

No começo de `def processar(i: int) -> None:`, antes de `page = doc[i]`, adicione a checagem cooperativa (páginas ainda não iniciadas são puladas quando há pausa):

```python
        # Pausa cooperativa (E9-16): entre páginas, checa o pedido de pausa. Uma
        # página em voo termina; as não iniciadas são puladas — mesmo resume de
        # uma pausa por escassez, só que pedida pelo usuário (motivo="manual").
        if not pausa_evt.is_set() and checar_pausa is not None and checar_pausa():
            pausa_evt.set()
        if pausa_evt.is_set():
            with lock:
                if estado["motivo_pausa"] is None:
                    estado["motivo_pausa"] = "manual"
            return
```

No `return` da função, marque `parcial` também quando pausado:

```python
    return (
        render_paginas,
        estado["blocos_traduzidos"],
        esgotado_evt.is_set() or pausa_evt.is_set(),
        estado["motivo_pausa"],
    )
```

- [ ] **Step 4: Pass `checar_pausa` through `traduzir_pdf` to the parallel branch**

Em `traduzir_pdf`, no ramo `if paralelismo > 1:`, acrescente `checar_pausa` na chamada:

```python
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
            checar_pausa,
        )
```

Atualize a docstring de `traduzir_pdf`: troque a linha
```checar_pausa`` (ADR-0045): pausa manual pedida pelo usuário — só honrada`
`no loop sequencial (``paralelismo=1``); pendência para o modo paralelo.`
por:
`` `checar_pausa` (ADR-0045/E9-16): pausa manual cooperativa, honrada nos dois``
`` loops (sequencial e paralelo) — para entre páginas, nunca mata chamada em voo.``

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/traducao/test_pausa_cooperativa.py tests/traducao/test_pipeline_paralelo.py -v`
Expected: PASS (novos + regressão do paralelismo).

- [ ] **Step 6: Commit**

```bash
git add src/atlas/traducao/pipeline.py tests/traducao/test_pausa_cooperativa.py
git commit -m "fix(traducao): pausa manual honrada também no loop paralelo (E9-16)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Classificação de falha em 3 classes (`conexao`)

**Files:**
- Modify: `src/atlas/traducao/traducao_ia.py` (`_classificar_erro`)
- Test: `tests/traducao/test_traducao_ia.py`

- [ ] **Step 1: Write the failing test**

Acrescente ao fim de `tests/traducao/test_traducao_ia.py`:

```python
def test_classificar_erro_tres_classes():
    from atlas.traducao.traducao_ia import _classificar_erro

    assert _classificar_erro(Exception("timeout após 60s invocando IA")) == "timeout"
    assert _classificar_erro(Exception("ollama: <urlopen error [Errno 111] Connection refused>")) == "conexao"
    assert _classificar_erro(Exception("ollama: <urlopen error [Errno -2] Name or service not known>")) == "conexao"
    assert _classificar_erro(Exception("rate limit exceeded")) == "erro"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/traducao/test_traducao_ia.py::test_classificar_erro_tres_classes -v`
Expected: FAIL (hoje "conexao" cai em "erro").

- [ ] **Step 3: Extend `_classificar_erro`**

Substitua a função em `src/atlas/traducao/traducao_ia.py`:

```python
def _classificar_erro(exc: Exception) -> str:
    """Classifica a falha do motor de IA em três classes:

    - ``"timeout"``: transitório, elegível a retry curto (ADR-0039).
    - ``"conexao"``: endpoint fora do ar (connection refused/DNS/unreachable) —
      motor local caído; alimenta a escalada Ollama→Claude (E9-16/ADR-0048), não
      a espera de cota (esperar não ressuscita um servidor local fora).
    - ``"erro"``: outra falha (ex.: rate-limit explícito) → escassez confirmada.
    """
    low = str(exc).lower()
    if "timeout" in low:
        return "timeout"
    marcadores_conexao = (
        "connection refused",
        "urlopen error",
        "connection error",
        "name or service not known",
        "no route to host",
        "network is unreachable",
        "errno 111",
        "errno -2",
        "max retries",
    )
    if any(m in low for m in marcadores_conexao):
        return "conexao"
    return "erro"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/traducao/test_traducao_ia.py -v`
Expected: PASS (novo + os existentes que dependem de timeout/erro seguem verdes).

- [ ] **Step 5: Commit**

```bash
git add src/atlas/traducao/traducao_ia.py tests/traducao/test_traducao_ia.py
git commit -m "feat(traducao): classifica falha de conexão do motor (3 classes) — E9-16

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Campos de escalada em `ConfigTraducao`

**Files:**
- Modify: `src/atlas/traducao/traducao_ia.py` (`ConfigTraducao`)
- Test: `tests/traducao/test_traducao_ia.py`

- [ ] **Step 1: Write the failing test**

Acrescente a `tests/traducao/test_traducao_ia.py`:

```python
def test_config_tem_campos_de_escalada_com_defaults():
    from atlas.traducao.traducao_ia import ConfigTraducao

    cfg = ConfigTraducao()
    assert cfg.escalonar_apos_falhas == 3
    assert cfg.escalonar_para == "claude"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/traducao/test_traducao_ia.py::test_config_tem_campos_de_escalada_com_defaults -v`
Expected: FAIL (`AttributeError`).

- [ ] **Step 3: Add the fields**

Em `ConfigTraducao` (após `instrucao_refino: str = ""`), acrescente:

```python
    # E9-16 / ADR-0048: escalada visível do motor. Ollama é o padrão; após N falhas
    # de CONEXÃO consecutivas (endpoint fora), o restante do job migra p/ escalonar_para.
    escalonar_apos_falhas: int = 3  # tentativas rápidas no Ollama antes de escalar
    escalonar_para: str = "claude"  # motor de destino da escalada
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/traducao/test_traducao_ia.py::test_config_tem_campos_de_escalada_com_defaults -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atlas/traducao/traducao_ia.py tests/traducao/test_traducao_ia.py
git commit -m "feat(traducao): config de escalada de motor (escalonar_apos_falhas/para) — E9-16

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Wrapper de escalada Ollama→Claude na rotina

**Files:**
- Modify: `src/atlas/rotinas/traduzir_pdf.py` (novo `montar_invocar_escalavel`, uso em `collect`)
- Test: `tests/traducao/test_escalada_motor.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/traducao/test_escalada_motor.py
"""TDD — escalada visível Ollama→Claude no wrapper da rotina (E9-16/ADR-0048)."""

from __future__ import annotations

import threading

from atlas.ia import InvocarErro
from atlas.rotinas.traduzir_pdf import montar_invocar_escalavel
from atlas.traducao.traducao_ia import ConfigTraducao


def _wrapper(cfg, monkeypatch, roteiro):
    """Monta o wrapper com um `invocar` fake dirigido por `roteiro`:
    roteiro[motor] = lista de resultados; cada item é uma str (retorno) ou uma
    Exception (levantada). Consome em ordem por motor."""
    chamadas = []
    estado = {m: list(v) for m, v in roteiro.items()}

    def fake_invocar(prompt, modelo=None, timeout=60, motor="claude", fallback=True):
        chamadas.append((motor, modelo))
        item = estado[motor].pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr("atlas.rotinas.traduzir_pdf.invocar", fake_invocar)
    escalas = []
    inv = montar_invocar_escalavel(
        cfg, on_escala=lambda de, para, motivo: escalas.append((de, para, motivo)), lock=threading.Lock()
    )
    return inv, chamadas, escalas


def test_arranque_endpoint_fora_escala_para_claude(monkeypatch):
    cfg = ConfigTraducao(motor="ollama", escalonar_apos_falhas=3)
    conn = InvocarErro("ollama: <urlopen error [Errno 111] Connection refused>")
    inv, chamadas, escalas = _wrapper(
        cfg, monkeypatch,
        {"ollama": [conn, conn, conn], "claude": ["[[1]] OK"]},
    )
    out = inv("[[1]] texto", motor="ollama")
    assert out == "[[1]] OK"
    assert cfg.motor == "claude"  # job migrou de vez
    assert escalas == [("ollama", "claude", conn.args[0] if conn.args else str(conn))]
    # 3 tentativas no ollama + 1 no claude, e o claude NÃO herda modelo do ollama
    assert [m for m, _ in chamadas] == ["ollama", "ollama", "ollama", "claude"]
    assert chamadas[-1][1] is None


def test_timeout_nao_escala_propaga_para_pipeline(monkeypatch):
    cfg = ConfigTraducao(motor="ollama", escalonar_apos_falhas=3)
    to = InvocarErro("timeout após 60s invocando IA")
    inv, chamadas, escalas = _wrapper(cfg, monkeypatch, {"ollama": [to], "claude": []})
    try:
        inv("[[1]] texto", motor="ollama")
        assert False, "deveria propagar o timeout"
    except InvocarErro:
        pass
    assert cfg.motor == "ollama"  # timeout não escala (Ollama ocupado ≠ fora)
    assert escalas == []
    assert [m for m, _ in chamadas] == ["ollama"]  # uma só; ADR-0039 decide o retry


def test_sucesso_no_ollama_nao_escala(monkeypatch):
    cfg = ConfigTraducao(motor="ollama", escalonar_apos_falhas=3)
    inv, chamadas, escalas = _wrapper(cfg, monkeypatch, {"ollama": ["[[1]] OK"], "claude": []})
    assert inv("[[1]] t", motor="ollama") == "[[1]] OK"
    assert cfg.motor == "ollama"
    assert escalas == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/traducao/test_escalada_motor.py -v`
Expected: FAIL (`ImportError: cannot import name 'montar_invocar_escalavel'`).

- [ ] **Step 3: Implement `montar_invocar_escalavel` and use it in `collect`**

Em `src/atlas/rotinas/traduzir_pdf.py`, garanta `import threading` no topo (junto aos imports da stdlib, ao lado de `import logging`) e adicione `_classificar_erro`/`InvocarErro`:

```python
import threading  # (junto aos imports stdlib do topo)
```

```python
from atlas.ia import InvocarErro, invocar
from atlas.traducao.traducao_ia import (
    CacheTraducao,
    ConfigTraducao,
    _classificar_erro,
    resolver_agente_refino,
)
```

Substitua `_invocar_sem_fallback_de_motor` por `montar_invocar_escalavel` (a nova política substitui o "sem fallback nenhum" do 0045 por "sem switch por chamada, mas com escalada de job visível"):

```python
def montar_invocar_escalavel(cfg: ConfigTraducao, on_escala=None, lock=None):
    """Wrapper de ``ia.invocar`` com escalada de MOTOR no nível do job (E9-16/ADR-0048).

    Contrato (substitui o `fallback=False` cru do ADR-0045):
    - Nunca troca de motor por chamada às escondidas (o problema que o 0045 evitou).
    - Motor pedido (``cfg.motor``, default ollama) é usado à risca enquanto funciona.
    - Erro de CONEXÃO no ollama (endpoint fora): tenta rápido até
      ``cfg.escalonar_apos_falhas`` vezes; esgotado, muta ``cfg.motor`` para
      ``cfg.escalonar_para`` (Claude) — o RESTANTE do job vai pro Claude, visível
      via ``on_escala`` — e retenta ESTA chamada no novo motor (modelo=None, nunca
      herda o modelo do outro motor). ``cfg.motor`` é a fonte única do motor atual,
      relida pelo pipeline a cada lote, então a escalada vale pro resto do job.
    - Timeout/erro no ollama propaga direto: o pipeline aplica o retry/pausa do
      ADR-0039 (Ollama ocupado ≠ Ollama fora; cota do Claude recupera com o tempo).
    - Já em Claude (pedido ou escalado): comportamento do 0039 intacto.
    """
    lock = lock or threading.Lock()

    def inv(prompt, modelo=None, timeout=60, motor="claude"):
        motor_atual = motor  # == cfg.motor no momento da chamada (pipeline relê)
        if motor_atual != "ollama":
            return invocar(prompt, modelo=modelo, timeout=timeout, motor=motor_atual, fallback=False)
        ultimo: Exception | None = None
        for _ in range(max(1, cfg.escalonar_apos_falhas)):
            try:
                return invocar(prompt, modelo=modelo, timeout=timeout, motor="ollama", fallback=False)
            except InvocarErro as exc:
                if _classificar_erro(exc) != "conexao":
                    raise  # timeout/erro → ADR-0039 no pipeline
                ultimo = exc
        # esgotou as tentativas de conexão no ollama → escala o restante do job.
        with lock:
            if cfg.motor == "ollama":
                cfg.motor = cfg.escalonar_para
                cfg.modelo = None  # não herda modelo do ollama no motor de destino
                if on_escala is not None:
                    on_escala("ollama", cfg.escalonar_para, str(ultimo))
        return invocar(prompt, modelo=None, timeout=timeout, motor=cfg.escalonar_para, fallback=False)

    return inv
```

Em `collect`, logo após montar `cfg` e resolver o agente de refino (após o bloco `if instrucao_ag:`), construa o callback de escalada e o invocar:

```python
    def _on_escala(de: str, para: str, motivo: str) -> None:
        atual = store.get("Traducao", t.name).status or {}
        log = list(atual.get("log") or [])
        log.append(_evento(f"⚡ motor {de} indisponível — escalado p/ {para}"))
        _status(
            store, t, ctx,
            {
                "motor_efetivo": para,
                "escalonado_em": ctx.agora.isoformat(),
                "escalonado_motivo": (motivo or "")[:200],
                "log": log[-40:],
            },
        )

    invocar_escalavel = montar_invocar_escalavel(cfg, on_escala=_on_escala)
```

No patch de status inicial (`fase="preparando"`), acrescente o motor efetivo inicial:

```python
            "pausar_solicitado": False,  # reseta um pedido de pausa de um run anterior
            "motor_efetivo": cfg.motor,  # E9-16: motor realmente em uso (muda se escalar)
```

Na chamada `traduzir_pdf(...)`, troque `invocar_fn=_invocar_sem_fallback_de_motor` por `invocar_fn=invocar_escalavel` e atualize o comentário do `checar_pausa`:

```python
            invocar_fn=invocar_escalavel,
            ...
            checar_pausa=checar_pausa,  # E9-16: honrado nos dois modos (seq + paralelo)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/traducao/test_escalada_motor.py tests/traducao/test_collect_traduzir_pdf.py -v`
Expected: PASS (novos + regressão do collect).

- [ ] **Step 5: Run the full translation suite (no regressions)**

Run: `python -m pytest tests/traducao tests/test_ia.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/atlas/rotinas/traduzir_pdf.py tests/traducao/test_escalada_motor.py
git commit -m "feat(traducao): escalada visível Ollama→Claude no nível do job — E9-16/ADR-0048

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: UI — abas roláveis (wheel → scroll horizontal)

**Files:**
- Modify: `src/atlas/dashboard/style.css` (`#tabbar`)
- Modify: `src/atlas/dashboard/main.js` (`renderTabs`)

- [ ] **Step 1: Widen the tabbar scrollbar + edge affordance**

Em `src/atlas/dashboard/style.css`, substitua as regras do scrollbar do `#tabbar`:

```css
#tabbar::-webkit-scrollbar{height:6px}
#tabbar::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
#tabbar::-webkit-scrollbar-thumb:hover{background:var(--muted)}
```

- [ ] **Step 2: Translate vertical wheel to horizontal scroll**

Em `src/atlas/dashboard/main.js`, dentro de `renderTabs` (função que começa em `const bar = document.getElementById('tabbar');`), após `bar.innerHTML = tabs + ...`, adicione um listener idempotente:

```javascript
  // Abas roláveis (E9-16): roda-do-mouse vertical rola o tabbar na horizontal —
  // um listener só, marcado com dataset pra não empilhar a cada re-render.
  if (!bar.dataset.wheelBound) {
    bar.addEventListener('wheel', (e) => {
      if (e.deltaY === 0) return;
      if (bar.scrollWidth <= bar.clientWidth) return;  // nada a rolar
      e.preventDefault();
      bar.scrollLeft += e.deltaY;
    }, { passive: false });
    bar.dataset.wheelBound = '1';
  }
```

- [ ] **Step 3: Manual verify (dashboard)**

Run: inicie o app (`python -m atlas`) e abra `http://atlas.local:8080`; abra abas suficientes para estourar a largura; role o mouse sobre a barra de abas.
Expected: a barra rola na horizontal com a roda vertical; scrollbar de 6px visível e arrastável. (Sem teste automatizado: é comportamento de DOM/CSS do dashboard vanilla.)

- [ ] **Step 4: Commit**

```bash
git add src/atlas/dashboard/style.css src/atlas/dashboard/main.js
git commit -m "feat(ui): tabbar rolável na horizontal com a roda do mouse — E9-16

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: UI — badge de motor efetivo + escalada visível

**Files:**
- Modify: `src/atlas/dashboard/kinds/traducao.js` (`renderTraducao`, badge)

- [ ] **Step 1: Show the effective engine / escalation badge**

Em `src/atlas/dashboard/kinds/traducao.js`, na `renderTraducao`, onde hoje está:

```javascript
  const motor = s.motor || 'ollama';
```

adicione, logo abaixo, a leitura do motor efetivo do status:

```javascript
  const st0 = r.status || {};
  const motorEfetivo = st0.motor_efetivo || motor;
  const escalado = motorEfetivo !== motor;
```

E onde o badge de motor é renderizado:

```javascript
          <span class="ag-badge ${esc(motor)}">${esc(motor)}</span>
```

troque por (mostra a escalada quando houver, com tooltip do motivo):

```javascript
          <span class="ag-badge ${esc(motorEfetivo)}" title="${escalado ? 'escalado: ' + esc(st0.escalonado_motivo || 'motor pedido indisponível') : 'motor pedido'}">${esc(motor)}${escalado ? ' → ' + esc(motorEfetivo) + ' ⚡' : ''}</span>
```

- [ ] **Step 2: Manual verify (dashboard)**

Run: com uma `Traducao` cujo `status.motor_efetivo` difira de `spec.motor` (pode-se simular via `/apply` no status, ou após uma escalada real com o endpoint Ollama fora), abra a aba da tradução.
Expected: badge mostra `ollama → claude ⚡` com tooltip do motivo; sem escalada, mostra só o motor.

- [ ] **Step 3: Commit**

```bash
git add src/atlas/dashboard/kinds/traducao.js
git commit -m "feat(ui): badge de motor efetivo com escalada visível na tradução — E9-16

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Revisão de sanidade do render + serialização

**Files:**
- Review: `src/atlas/traducao/editorial_html.py`
- Verify: `tests/traducao/test_editorial_html_*.py`, `test_remontagem_editorial.py`

Este é um passe de **revisão cirúrgica** — sem redesenho. Modularizar só se os testes existentes cobrirem e continuarem verdes.

- [ ] **Step 1: Baseline — todos os testes de render verdes**

Run: `python -m pytest tests/traducao/test_editorial_html_fidelidade.py tests/traducao/test_editorial_html_geometria.py tests/traducao/test_remontagem_editorial.py tests/traducao/test_config_editorial.py -v`
Expected: PASS (baseline antes de tocar em qualquer coisa).

- [ ] **Step 2: Leitura dirigida a classes de bug**

Leia `src/atlas/traducao/editorial_html.py` procurando por: (a) blocos sem tradução descartados silenciosamente (deve cair no original, ADR-0041); (b) geometria de página com piso mínimo de largura/altura (regressão do E9-09); (c) escape de HTML de texto traduzido; (d) fólio/`string-set` dinâmico. Anote cada achado como comentário `# REVISÃO E9-16:` no ponto exato — NÃO mude comportamento sem um teste que prove o bug.

- [ ] **Step 3: Para cada bug real encontrado — TDD**

Se achar um bug concreto: escreva primeiro um teste em `tests/traducao/` que o reproduza (falha), depois o mínimo para passar. Rode `python -m pytest tests/traducao/<novo_teste>.py -v`. Se NÃO houver bug concreto, pule para o Step 5 (a revisão em si é a entrega).

- [ ] **Step 4: Modularização opcional (só se clarear e com teste verde)**

Se `editorial_html.py` tiver um bloco coeso e testado isoladamente (candidato: geometria de página, coberto por `test_editorial_html_geometria.py`), extraia para `src/atlas/traducao/editorial_geometria.py` reexportando os nomes usados. Rode `python -m pytest tests/traducao -q` — TUDO verde. Se a extração exigir tocar em testes além do import, reverta: não vale o risco nesta leva.

- [ ] **Step 5: Sanidade de serialização/checkpoint**

Confirme por leitura + teste que: (a) `CacheTraducao.salvar` usa escrita atômica (tmp+replace — já existe); (b) uma pausa manual em paralelo não perde blocos (coberto pela Task 1). Adicione, se ausente, um teste que salve o cache concorrentemente de 2 threads e releia sem `JSONDecodeError`:

```python
# tests/traducao/test_cache_serial.py
import threading
from atlas.traducao.traducao_ia import CacheTraducao, ConfigTraducao


def test_cache_salvar_concorrente_nao_corrompe(tmp_path):
    cache = CacheTraducao()
    cfg = ConfigTraducao()
    for i in range(200):
        cache.put(f"t{i}", cfg, f"v{i}")
    path = tmp_path / "c.json"

    erros = []

    def salva():
        try:
            for _ in range(20):
                cache.salvar(path)
        except Exception as e:  # noqa: BLE001
            erros.append(e)

    ts = [threading.Thread(target=salva) for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not erros
    lido = CacheTraducao.carregar(path)
    assert lido.get("t0", cfg) == "v0"
```

Run: `python -m pytest tests/traducao/test_cache_serial.py -v`
Expected: PASS (a escrita atômica garante releitura íntegra).

- [ ] **Step 6: Commit**

```bash
git add src/atlas/traducao/ tests/traducao/
git commit -m "refactor(traducao): revisão de sanidade do render + serialização do cache — E9-16

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Docs de controle — ADR-0048 + backlog + spec

**Files:**
- Create: `docs/arquitetura/adr/ADR-0048-fallback-escalado-e-pausa-cooperativa.md`
- Modify: `docs/roadmap/backlog.md`, `docs/specs/traducao-redesenho-e9.md`, `docs/arquitetura/adr/README.md`

- [ ] **Step 1: Write ADR-0048**

Crie `docs/arquitetura/adr/ADR-0048-fallback-escalado-e-pausa-cooperativa.md` seguindo `docs/arquitetura/adr/template-adr.md`. Conteúdo essencial:

- **Contexto:** ADR-0045 desligou o fallback na tradução (`fallback=False`) para não misturar tom nem queimar cota escondido. O PO quer Ollama-first com queda pra Claude quando o endpoint local está fora.
- **Decisão:** (1) **Pausa cooperativa** honrada nos dois loops do pipeline (conserta o bug de `checar_pausa` só-sequencial). (2) **Escalada de motor no nível do job**, não por chamada: erro de conexão no Ollama → até `escalonar_apos_falhas` tentativas rápidas → muta `cfg.motor` p/ `escalonar_para` (Claude) e migra o RESTANTE do job, visível em `status.motor_efetivo`. Timeout segue o retry/pausa do ADR-0039; cache independe de motor, então o já-feito em Ollama não é re-traduzido.
- **Consequências:** supersede a *postura de fallback* do ADR-0045 (mantém "Ollama padrão" e o controle real); refina ADR-0040 (o fallback bidirecional de `ia.invocar` continua existindo para outros usos, mas a tradução usa a política de job, não o switch por chamada) e ADR-0039.
- **Alternativas rejeitadas:** reativar `fallback=True` no `ia.invocar` para a tradução (reintroduz o switch silencioso por chamada); escalar re-traduzindo tudo num motor só (desperdiça o cache já pago).
- Header + histórico de revisão (data 2026-07-08).

- [ ] **Step 2: Register the ADR in the index**

Em `docs/arquitetura/adr/README.md`, adicione a linha do ADR-0048 na lista (mesmo formato das entradas vizinhas), marcando que supersede a postura de fallback do ADR-0045.

- [ ] **Step 3: Update the backlog**

Em `docs/roadmap/backlog.md`, no épico E9, adicione a linha E9-16 (marcada **feito** ao concluir a implementação) descrevendo: pausa cooperativa nos dois loops, escalada visível Ollama→Claude (ADR-0048), abas roláveis, badge de motor efetivo, revisão de render/serialização. Ajuste a nota de E9-11 e E9-15 removendo a pendência "pausa só honrada com paralelismo=1" (agora resolvida), referenciando E9-16.

- [ ] **Step 4: Update the spec**

Em `docs/specs/traducao-redesenho-e9.md`, acrescente uma seção curta apontando para o ADR-0048 e a nova política de escalada + pausa cooperativa (fonte de verdade: o ADR).

- [ ] **Step 5: Commit**

```bash
git add docs/arquitetura/adr/ADR-0048-fallback-escalado-e-pausa-cooperativa.md docs/arquitetura/adr/README.md docs/roadmap/backlog.md docs/specs/traducao-redesenho-e9.md
git commit -m "docs(traducao): ADR-0048 (fallback escalado + pausa cooperativa) + backlog E9-16

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Verificação final

- [ ] Suíte completa de tradução verde: `python -m pytest tests/traducao tests/test_ia.py -q`
- [ ] Lint: `ruff check src/atlas/traducao src/atlas/rotinas/traduzir_pdf.py`
- [ ] App sobe e a aba de tradução renderiza sem erro de console: `python -m atlas` → `http://atlas.local:8080`
- [ ] Doc de verdade atualizada (ADR-0048 registrado, backlog E9-16 marcado feito).
