# Contexto de projeto no Repo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gerar (Opus) um resumo de contexto rico do projeto a partir da doc/metadados, represá-lo num `Doc tipo=contexto`, e injetá-lo integralmente (+ diff) no insight de cada mudança (Sonnet) — para análises que entendem o projeto.

**Architecture:** Tudo no collect `repo-sync` (`src/atlas/rotinas/repo_sync.py`). Na criação do `Repo` (e a cada `context_ttl_days`), varre o clone (README + `docs/**` + metadados), chama Opus e salva o resumo num `Doc`. O `_analisar` por diff carrega esse `Doc` e monta `prompt = contexto íntegro + diff`. Limites altos e configuráveis por `Repo.spec`.

**Tech Stack:** Python 3.12, stdlib. IA via `atlas.ia.invocar` (`claude -p --model`). pytest (IA mockada). Spec: [docs/superpowers/specs/2026-06-21-repo-contexto-projeto-design.md](../specs/2026-06-21-repo-contexto-projeto-design.md).

> Arquivo central: [src/atlas/rotinas/repo_sync.py](../../../src/atlas/rotinas/repo_sync.py). Testes em `tests/test_repo_sync.py` (já existe; usa fake de git via `monkeypatch` de `subprocess.run` e `patch("atlas.rotinas.repo_sync.invocar", …)`).

---

### Task 1: Defaults configuráveis + coleta de corpus

**Files:**
- Modify: `src/atlas/rotinas/repo_sync.py`
- Test: `tests/test_repo_contexto.py` (novo)

- [ ] **Step 1: Escrever os testes**

Criar `tests/test_repo_contexto.py`:
```python
"""TDD — contexto de projeto no repo-sync."""

from __future__ import annotations

from pathlib import Path

from atlas.rotinas.repo_sync import _coletar_contexto, _spec_int
from atlas.core.resource import Resource


def _montar_repo(tmp: Path) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "README.md").write_text("# Projeto X\nFaz coisas.", encoding="utf-8")
    docs = tmp / "docs"
    docs.mkdir()
    (docs / "arquitetura.md").write_text("## Arquitetura\nCamadas A/B.", encoding="utf-8")
    (docs / "sub").mkdir()
    (docs / "sub" / "guia.md").write_text("Guia interno.", encoding="utf-8")
    (tmp / "pyproject.toml").write_text("[project]\nname='x'", encoding="utf-8")
    (tmp / "ignorar.py").write_text("print(1)", encoding="utf-8")
    return tmp


def test_coleta_readme_docs_e_metadados(tmp_path):
    corpus, arquivos = _coletar_contexto(_montar_repo(tmp_path))
    assert "Projeto X" in corpus
    assert "Arquitetura" in corpus
    assert "Guia interno" in corpus
    assert "[project]" in corpus
    assert "print(1)" not in corpus  # .py fora da allowlist
    assert "README.md" in arquivos
    assert "docs/arquitetura.md" in arquivos
    assert "docs/sub/guia.md" in arquivos


def test_coleta_respeita_corpus_max_priorizando_docs(tmp_path):
    corpus, arquivos = _coletar_contexto(_montar_repo(tmp_path), corpus_max=40)
    assert len(corpus) <= 120  # cabeçalho + 1 bloco + aviso, bem curto
    assert "README.md" in arquivos  # README entra antes dos metadados


def test_spec_int_le_e_faz_fallback():
    r = Resource(kind="Repo", name="x", spec={"diff_prompt_max": "50"})
    assert _spec_int(r, "diff_prompt_max", 10) == 50
    assert _spec_int(r, "ausente", 7) == 7
    assert _spec_int(Resource(kind="Repo", name="y", spec={"k": "abc"}), "k", 9) == 9
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_repo_contexto.py -v`
Expected: FAIL (`_coletar_contexto`/`_spec_int` não existem)

- [ ] **Step 3: Implementar defaults, `_spec_int`, `_coletar_contexto`**

Em `src/atlas/rotinas/repo_sync.py`, **substituir** o bloco de constantes antigo:
```python
_HAIKU = "claude-haiku-4-5-20251001"
_MAX_DIFF_PROMPT = 5000  # chars enviados ao Haiku
_MAX_DIFF_STORE = 8000  # chars gravados no Diff Resource
```
por:
```python
# Modelos
_DEF_DIFF_MODEL = "claude-sonnet-4-6"  # insight por diff
_DEF_CONTEXT_MODEL = "claude-opus-4-8"  # resumo de contexto do projeto
# Política de frescor do contexto
_DEF_CONTEXT_TTL_DAYS = 7
# Tetos de caracteres (altos, perto da janela do modelo; configuráveis por Repo)
_DEF_CORPUS_MAX = 600_000  # corpus enviado ao Opus
_DEF_DIFF_PROMPT_MAX = 120_000  # diff enviado ao insight
_DEF_DIFF_STORE_MAX = 200_000  # diff guardado no Resource Diff

_METADATA_FILES = {
    "pyproject.toml", "package.json", "Cargo.toml", "go.mod", "pom.xml", "composer.json",
}
_DOC_EXTS = {".md", ".mdx", ".rst"}


def _spec_int(repo_res, key: str, default: int) -> int:
    """Lê um inteiro do spec do Repo, com fallback no default."""
    try:
        return int(repo_res.spec.get(key, default))
    except (TypeError, ValueError, AttributeError):
        return default


def _ler_arquivo(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _coletar_contexto(repo_dir: Path, corpus_max: int = _DEF_CORPUS_MAX) -> tuple[str, list[str]]:
    """Monta o corpus de contexto do clone: README + docs/** + metadados.

    Prioriza README e docs/ (metadados por último ao truncar). Devolve
    ``(corpus, arquivos_incluidos)``.
    """
    prioritarios: list[tuple[str, str]] = []
    for p in sorted(repo_dir.glob("README*")):
        if p.is_file():
            prioritarios.append((p.name, _ler_arquivo(p)))
    docs = repo_dir / "docs"
    if docs.is_dir():
        for p in sorted(docs.rglob("*")):
            if p.is_file() and p.suffix.lower() in _DOC_EXTS:
                prioritarios.append((str(p.relative_to(repo_dir)), _ler_arquivo(p)))
    metadados: list[tuple[str, str]] = []
    for p in sorted(repo_dir.iterdir()):
        if p.is_file() and (p.name in _METADATA_FILES or p.suffix == ".csproj"):
            metadados.append((p.name, _ler_arquivo(p)))

    corpus = ""
    arquivos: list[str] = []
    truncado = False
    for rel, conteudo in [*prioritarios, *metadados]:
        bloco = f"\n\n===== {rel} =====\n{conteudo}"
        if len(corpus) + len(bloco) > corpus_max:
            truncado = True
            break
        corpus += bloco
        arquivos.append(rel)
    if truncado:
        corpus += "\n\n[corpus truncado: excedeu o limite configurado]"
    return corpus.strip(), arquivos
```
Garanta os imports no topo do arquivo: `from pathlib import Path` (já existe) e
`from datetime import datetime, timedelta` (adicionar — usado na Task 2).

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_repo_contexto.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atlas/rotinas/repo_sync.py tests/test_repo_contexto.py
git commit -m "feat(repo-sync): defaults configuráveis e coleta de corpus de contexto"
```

---

### Task 2: Geração (Opus), frescor e leitura do contexto

**Files:**
- Modify: `src/atlas/rotinas/repo_sync.py`
- Test: `tests/test_repo_contexto.py`

- [ ] **Step 1: Escrever os testes**

Adicionar a `tests/test_repo_contexto.py`:
```python
from datetime import datetime, timedelta
from unittest.mock import patch

from atlas.core.store import ResourceStore
from atlas.rotinas.repo_sync import (
    _contexto_atual,
    _contexto_obsoleto,
    _gerar_contexto,
)


class _Ctx:
    def __init__(self, agora):
        self.agora = agora


def _store(tmp_path):
    return ResourceStore(str(tmp_path / "s.db"))


def test_gerar_contexto_cria_doc_tipo_contexto(tmp_path):
    repo_dir = _montar_repo(tmp_path / "repo")
    store = _store(tmp_path)
    agora = datetime(2026, 6, 21, 9, 0)
    store.apply(Resource(kind="Repo", name="nora", spec={"url": "x"}), agora)
    with patch("atlas.rotinas.repo_sync.invocar", return_value="RESUMO RICO DO PROJETO") as inv:
        _gerar_contexto(store.get("Repo", "nora"), repo_dir, store, _Ctx(agora))
    doc = store.get("Doc", "repo-nora-contexto")
    assert doc is not None
    assert doc.labels["tipo"] == "contexto"
    assert doc.spec["body"] == "RESUMO RICO DO PROJETO"
    assert doc.status["generated_at"] == agora.isoformat()
    # usou o modelo de contexto (Opus por default)
    assert inv.call_args.kwargs["modelo"] == "claude-opus-4-8"
    # marcou no Repo
    assert store.get("Repo", "nora").status["last_context_at"] == agora.isoformat()


def test_gerar_contexto_degrada_se_ia_falha(tmp_path):
    repo_dir = _montar_repo(tmp_path / "repo")
    store = _store(tmp_path)
    agora = datetime(2026, 6, 21, 9, 0)
    store.apply(Resource(kind="Repo", name="nora", spec={"url": "x"}), agora)
    with patch("atlas.rotinas.repo_sync.invocar", side_effect=RuntimeError("sem ia")):
        _gerar_contexto(store.get("Repo", "nora"), repo_dir, store, _Ctx(agora))
    assert store.get("Doc", "repo-nora-contexto") is None  # não grava


def test_contexto_obsoleto_e_atual(tmp_path):
    store = _store(tmp_path)
    agora = datetime(2026, 6, 21, 9, 0)
    assert _contexto_obsoleto("nora", store, agora, 7) is True  # ausente
    store.apply(
        Resource(
            kind="Doc",
            name="repo-nora-contexto",
            labels={"tipo": "contexto"},
            spec={"body": "CTX"},
            status={"generated_at": (agora - timedelta(days=2)).isoformat()},
        ),
        agora,
    )
    assert _contexto_obsoleto("nora", store, agora, 7) is False  # fresco
    assert _contexto_obsoleto("nora", store, agora, 1) is True  # vencido
    assert _contexto_atual("nora", store) == "CTX"
    assert _contexto_atual("ausente", store) == ""
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_repo_contexto.py -v`
Expected: FAIL (funções não existem)

- [ ] **Step 3: Implementar `_gerar_contexto`, `_contexto_obsoleto`, `_contexto_atual`**

Adicionar a `src/atlas/rotinas/repo_sync.py` (após `_coletar_contexto`):
```python
def _gerar_contexto(repo_res, repo_dir: Path, store: ResourceStore, ctx) -> None:
    """Gera (Opus) e represa o resumo de contexto do projeto num Doc. Degrada em falha."""
    label = repo_res.name
    corpus_max = _spec_int(repo_res, "context_corpus_max", _DEF_CORPUS_MAX)
    corpus, arquivos = _coletar_contexto(repo_dir, corpus_max)
    if not corpus:
        return
    modelo = repo_res.spec.get("context_model") or _DEF_CONTEXT_MODEL
    prompt = (
        f"Crie um RESUMO DE CONTEXTO do projeto '{label}' para servir de base a "
        "futuras revisões de código (entender o que muda e sugerir melhorias). "
        "Seja rico e abrangente — sem limite de tamanho. Cubra: propósito, "
        "arquitetura e módulos principais, fluxos importantes, convenções/estilo, "
        "domínio/termos e pontos de atenção. Responda em PT-BR.\n\n"
        f"Documentação e metadados do projeto:\n{corpus}"
    )
    try:
        resumo = invocar(prompt, modelo=modelo, timeout=180)
    except Exception as exc:  # noqa: BLE001 — degrada (ADR-0006)
        _log.warning("contexto/%s: IA indisponível: %s", label, exc)
        return
    store.apply(
        Resource(
            kind="Doc",
            name=f"repo-{label}-contexto",
            labels={"topic": "repo", "repo": label, "tipo": "contexto"},
            spec={"title": f"{label} · contexto do projeto", "body": resumo},
            status={
                "generated_at": ctx.agora.isoformat(),
                "model": modelo,
                "source_files": arquivos,
            },
        ),
        ctx.agora,
    )
    atual = store.get("Repo", label)
    if atual is not None:
        store.apply(
            Resource(
                kind="Repo",
                name=label,
                labels=atual.labels,
                spec=atual.spec,
                status={**atual.status, "last_context_at": ctx.agora.isoformat()},
            ),
            ctx.agora,
        )


def _contexto_obsoleto(label: str, store: ResourceStore, agora: datetime, ttl_days: int) -> bool:
    """True se o Doc de contexto não existe ou é mais antigo que ttl_days."""
    doc = store.get("Doc", f"repo-{label}-contexto")
    if doc is None:
        return True
    ts = doc.status.get("generated_at") if doc.status else None
    if not ts:
        return True
    try:
        gerado = datetime.fromisoformat(ts)
    except ValueError:
        return True
    return agora - gerado > timedelta(days=ttl_days)


def _contexto_atual(label: str, store: ResourceStore) -> str:
    """Body do Doc de contexto (integral, sem truncar) ou string vazia."""
    doc = store.get("Doc", f"repo-{label}-contexto")
    if doc is None:
        return ""
    return str(doc.spec.get("body", ""))
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_repo_contexto.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atlas/rotinas/repo_sync.py tests/test_repo_contexto.py
git commit -m "feat(repo-sync): gera/represa contexto (Opus) + frescor e leitura"
```

---

### Task 3: Injeção do contexto no insight + budgets no `_reportar`

**Files:**
- Modify: `src/atlas/rotinas/repo_sync.py` (`_analisar`, `_reportar`)
- Test: `tests/test_repo_contexto.py`

- [ ] **Step 1: Escrever os testes**

Adicionar a `tests/test_repo_contexto.py`:
```python
from atlas.rotinas.repo_sync import _analisar


def test_analisar_injeta_contexto_e_diff_no_prompt():
    capturado = {}

    def fake_invocar(prompt, modelo, timeout):
        capturado["prompt"] = prompt
        capturado["modelo"] = modelo
        return "analise"

    with patch("atlas.rotinas.repo_sync.invocar", side_effect=fake_invocar):
        out = _analisar("DIFF_AQUI", "nora", "claude-sonnet-4-6", "CONTEXTO_DO_PROJETO")
    assert out == "analise"
    assert "CONTEXTO_DO_PROJETO" in capturado["prompt"]
    assert "DIFF_AQUI" in capturado["prompt"]
    assert capturado["modelo"] == "claude-sonnet-4-6"


def test_analisar_sem_contexto_ainda_roda():
    with patch("atlas.rotinas.repo_sync.invocar", return_value="ok"):
        out = _analisar("DIFF", "nora", "claude-sonnet-4-6", "")
    assert out == "ok"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_repo_contexto.py::test_analisar_injeta_contexto_e_diff_no_prompt -v`
Expected: FAIL (`_analisar` ainda tem assinatura antiga sem `contexto`)

- [ ] **Step 3: Atualizar `_analisar` (injeta contexto) e `_reportar` (budgets/modelo/contexto)**

Em `src/atlas/rotinas/repo_sync.py`, **substituir** a função `_analisar` por:
```python
def _analisar(diff: str, label: str, modelo: str, contexto: str = "") -> str | None:
    """IA explica o que mudou e sugere — usando o contexto do projeto + o diff."""
    bloco_ctx = (
        f"## Contexto do projeto (resumo represado)\n{contexto}\n\n" if contexto else ""
    )
    prompt = (
        f"Você é um revisor técnico do repositório '{label}'. "
        + bloco_ctx
        + "Analise o diff e responda em PT-BR, em duas seções com bullets:\n\n"
        "## O que mudou\n"
        "- o que mudou e por quê (use o contexto do projeto para inferir)\n"
        "- pontos de atenção ou risco\n\n"
        "## Sugestões\n"
        "- melhorias, testes, refactors, próximos passos acionáveis\n\n"
        f"```diff\n{diff}\n```"
    )
    try:
        return invocar(prompt, modelo=modelo, timeout=90)
    except Exception as exc:  # noqa: BLE001
        _log.warning("IA indisponível para repo-sync/%s: %s", label, exc)
        return f"_(IA indisponível: {exc})_"
```

E **substituir o início** de `_reportar` (as primeiras linhas que definem
`sha7`, `diff_store`, `diff_prompt`, `repo_res`, `modelo`, `explicacao`) por:
```python
    sha7 = sha[:7]
    repo_res = store.get("Repo", label)
    diff_store_max = _spec_int(repo_res, "diff_store_max", _DEF_DIFF_STORE_MAX) if repo_res else _DEF_DIFF_STORE_MAX
    diff_prompt_max = _spec_int(repo_res, "diff_prompt_max", _DEF_DIFF_PROMPT_MAX) if repo_res else _DEF_DIFF_PROMPT_MAX
    diff_store = diff[:diff_store_max]
    diff_prompt = diff[:diff_prompt_max]
    modelo = (repo_res.spec.get("model") if repo_res else None) or _DEF_DIFF_MODEL
    contexto = _contexto_atual(label, store)
    explicacao = _analisar(diff_prompt, label, modelo, contexto)
```
(O restante de `_reportar` — `_salvar_diff`/`_salvar_doc`/`_atualizar_repo_status`
e a montagem das linhas — continua igual, usando `diff_store`.) Remova quaisquer
referências remanescentes a `_MAX_DIFF_STORE`, `_MAX_DIFF_PROMPT` e `_HAIKU`.

- [ ] **Step 4: Verificar que nada referencia as constantes antigas**

Run: `grep -nE "_MAX_DIFF_(STORE|PROMPT)|_HAIKU" src/atlas/rotinas/repo_sync.py`
Expected: nenhuma linha.

- [ ] **Step 5: Rodar e ver passar**

Run: `python -m pytest tests/test_repo_contexto.py -v && python -m pytest tests/test_repo_sync.py -v`
Expected: PASS (inclui a suíte antiga do repo-sync, que continua verde)

- [ ] **Step 6: Commit**

```bash
git add src/atlas/rotinas/repo_sync.py tests/test_repo_contexto.py
git commit -m "feat(repo-sync): injeta contexto+diff no insight (Sonnet) e eleva budgets"
```

---

### Task 4: Gatilhos — gera no clone, regenera por TTL

**Files:**
- Modify: `src/atlas/rotinas/repo_sync.py` (`collect`, `_clonar`)
- Test: `tests/test_repo_contexto.py`

- [ ] **Step 1: Escrever o teste de integração (git fakeado, IA mockada)**

Adicionar a `tests/test_repo_contexto.py`:
```python
import subprocess as _sp

from atlas.executor import ContextoExecucao
from atlas.db import Database
from atlas.routines import Rotina
from atlas.rotinas.repo_sync import collect


def _rotina():
    return Rotina(nome="nora-sync", descricao="x", label="nora", agenda="@daily 09:00",
                  modelo="none", saida="telegram", coletar="repo-sync")


def test_clone_gera_contexto(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "atlas.sqlite"))
    store = ResourceStore(str(tmp_path / "atlas.sqlite"))
    agora = datetime(2026, 6, 21, 9, 0)
    store.apply(Resource(kind="Repo", name="nora", spec={"url": "https://x/y"}), agora)

    # fake git: 'clone' cria o diretório com docs; demais comandos retornam vazio
    real_run = _sp.run

    def fake_run(args, **kw):
        if args[:2] == ["git", "clone"]:
            dest = Path(args[-1])
            _montar_repo(dest)
            return _sp.CompletedProcess(args, 0, "", "")
        if args[1] == "rev-parse":
            return _sp.CompletedProcess(args, 0, "abc1234\n", "")
        return _sp.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(_sp, "run", fake_run)
    ctx = ContextoExecucao(rotina=_rotina(), db=Database(str(tmp_path / "m.db")), agora=agora)
    ctx.store = store
    with patch("atlas.rotinas.repo_sync.invocar", return_value="CTX RICO"):
        collect(ctx)
    doc = store.get("Doc", "repo-nora-contexto")
    assert doc is not None and doc.spec["body"] == "CTX RICO"
```
> Nota: `_montar_repo` já cria o diretório destino (`tmp.mkdir(...)` na Task 1),
> então funciona tanto para `tmp_path` quanto para o destino do `git clone` fake.

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_repo_contexto.py::test_clone_gera_contexto -v`
Expected: FAIL (o `collect`/`_clonar` ainda não gera contexto)

- [ ] **Step 3: Ligar os gatilhos**

Em `src/atlas/rotinas/repo_sync.py`, dentro de `collect`, **substituir** o bloco
`try` que decide clone/sync por:
```python
    repo_dir = _data_dir() / "repos" / label
    try:
        if not repo_dir.exists():
            return _clonar(url, repo_dir, label, store, ctx)
        ttl = _spec_int(repo_res, "context_ttl_days", _DEF_CONTEXT_TTL_DAYS)
        if _contexto_obsoleto(label, store, ctx.agora, ttl):
            _gerar_contexto(repo_res, repo_dir, store, ctx)
        return _sincronizar(url, repo_dir, label, store, ctx)
    except Exception as exc:  # noqa: BLE001
        _log.warning("repo-sync/%s falhou: %s", label, exc)
        return CollectResult(data={"_saida": f"⚠️ repo-sync/{label}: {exc}"})
```
(`repo_res` já está disponível no `collect` — é o `store.get("Repo", label)` feito
antes.) E em `_clonar`, logo após `_atualizar_repo_status(...)` e antes do
`return`, inserir:
```python
    repo_res = store.get("Repo", label)
    if repo_res is not None:
        _gerar_contexto(repo_res, repo_dir, store, ctx)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_repo_contexto.py -v`
Expected: PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add src/atlas/rotinas/repo_sync.py tests/test_repo_contexto.py
git commit -m "feat(repo-sync): gera contexto no clone e regenera por TTL"
```

---

### Task 5: Documentação + nora-sync remodelado

**Files:**
- Modify: `docs/arquitetura/kinds.md` (Repo: campos novos; Doc tipo=contexto)
- Modify: `routines/nora-sync/routine.toml`

- [ ] **Step 1: Atualizar `kinds.md`**

Em `docs/arquitetura/kinds.md`, na seção do kind `Repo`, **substituir** a tabela de
spec por uma que inclua os campos novos:
```markdown
| Campo spec | Tipo | Descrição |
|------------|------|-----------|
| `url` | string | URL (`https://github.com/user/repo`) |
| `model` | string | modelo do insight por diff (default `claude-sonnet-4-6`) |
| `context_model` | string | modelo do resumo de contexto (default `claude-opus-4-8`) |
| `context_ttl_days` | int | frescor do contexto em dias (default 7) |
| `context_corpus_max` | int | teto de chars do corpus do contexto (default 600000) |
| `diff_prompt_max` | int | teto de chars do diff enviado ao insight (default 120000) |
| `diff_store_max` | int | teto de chars do diff guardado no `Diff` (default 200000) |
```
E adicionar, logo após a descrição do `Diff`, uma nota:
```markdown
> **`Doc` especializado `tipo=contexto`:** `Doc/repo-<label>-contexto`
> (`labels: topic=repo, repo=<label>, tipo=contexto`) guarda o **resumo de
> contexto do projeto** (gerado por Opus na criação/TTL). É injetado integral no
> insight de cada diff. Ver [spec](../specs/2026-06-21-repo-contexto-projeto-design.md).
```
Atualizar o cabeçalho (`versao` +0.1) e o histórico de revisão com uma linha:
`| 1.3 | 2026-06-21 | Tech Lead | Repo: contexto de projeto (Doc tipo=contexto) e campos de modelo/budget | PO/PM |`

- [ ] **Step 2: Remodelar `routines/nora-sync/routine.toml`**

Substituir o conteúdo de `routines/nora-sync/routine.toml` por:
```toml
nome      = "nora-sync"
descricao = "Monitora sys0xFF/nora: gera contexto rico do projeto (Opus) e reporta diffs com análise contextual (Sonnet)."
label     = "nora"
coletar   = "repo-sync"
agenda    = "@daily 09:00"
modelo    = "none"
saida     = "telegram"
ativa     = false
# Configure o Repo: /apply Repo nora spec.url=https://github.com/sys0xFF/nora
# (opcional) spec.model, spec.context_model, spec.context_ttl_days, spec.diff_prompt_max …
```

- [ ] **Step 3: Commit**

```bash
git add docs/arquitetura/kinds.md routines/nora-sync/routine.toml
git commit -m "docs: kinds.md (Repo contexto + campos) e remodela nora-sync"
```

---

### Task 6: Verificação final

**Files:** —

- [ ] **Step 1: Suíte + lint**

Run: `python -m pytest -q && ruff check . && ruff format --check .`
Expected: tudo verde.

- [ ] **Step 2: Smoke isolado (sem IA real) — clone gera contexto e insight injeta**

```bash
python - <<'PY'
import datetime, os, subprocess, tempfile
from pathlib import Path
from unittest.mock import patch
tmp = Path(tempfile.mkdtemp())
os.environ["ATLAS_DB_PATH"] = str(tmp / "atlas.sqlite")
from atlas.core.store import ResourceStore
from atlas.core.resource import Resource
from atlas.rotinas import repo_sync as rs

store = ResourceStore(str(tmp / "atlas.sqlite"))
now = datetime.datetime(2026, 6, 21, 9, 0)
store.apply(Resource(kind="Repo", name="demo", spec={"url": "https://x/y"}), now)

def fake_run(args, **kw):
    if args[:2] == ["git", "clone"]:
        d = Path(args[-1]); (d / "docs").mkdir(parents=True, exist_ok=True)
        (d / "README.md").write_text("# Demo"); (d / "docs" / "a.md").write_text("arq")
        return subprocess.CompletedProcess(args, 0, "", "")
    if args[1] == "rev-parse":
        return subprocess.CompletedProcess(args, 0, "abc1234\n", "")
    return subprocess.CompletedProcess(args, 0, "", "")

class C:
    agora = now
    rotina = type("R", (), {"label": "demo", "nome": "demo-sync"})()
    store_ = store

ctx = C(); ctx.store = store
with patch("subprocess.run", fake_run), patch("atlas.rotinas.repo_sync.invocar", return_value="CONTEXTO"):
    rs.collect(ctx)
doc = store.get("Doc", "repo-demo-contexto")
print("contexto gerado:", bool(doc), "· body:", doc.spec["body"] if doc else None)
PY
```
Expected: `contexto gerado: True · body: CONTEXTO`.

> Smoke opcional — o gating real são os testes de `tests/test_repo_contexto.py`.

---

## Notas de verificação para o curador
- **Limites:** contexto guardado e lido **integral**; corpus/diff com tetos altos
  vindos do `Repo.spec` (defaults 600k/120k/200k). Sem os antigos 5k/8k.
- **Modelos:** contexto = Opus; insight por diff = Sonnet (default), ambos
  configuráveis no `Repo`.
- **Resiliência:** falha de IA na geração de contexto não cria o Doc e não quebra
  o sync; `_analisar` sem contexto ainda roda.
- **Economia (P1):** Opus só na criação e por TTL; insight por diff só quando há
  mudança.
- **Próximo (na fila):** melhorar os cards especializados no front embutido da API.
