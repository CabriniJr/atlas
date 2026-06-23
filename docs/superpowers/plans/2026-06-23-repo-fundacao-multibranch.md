# Repo — Fundação de dados multi-branch (Branch/Commit) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Materializar, a cada sync do `repo-sync`, os Kinds ocultos `Branch` e `Commit` (resumo leve) no store, ligados por label `repo=<label>`, formando a base do git-graph e do progresso (ADR-0023 §1–§3).

**Architecture:** Funções puras em [repo_sync.py](../../../src/atlas/rotinas/repo_sync.py) que leem o clone via o wrapper `_git` (mockável) e gravam `Resource`s via o `ResourceStore`. Esta fatia cobre a **branch default** (não-quebrante: `Diff`/`Doc` atuais continuam iguais). O loop sobre **todas** as branches remotas é o próximo plano (E7-02).

**Tech Stack:** Python 3, pytest, `unittest.mock`, git (via subprocess wrapper `_git`).

**Contexto:** Leia antes o [dossiê de contexto E7](2026-06-23-repo-e7-dossie-contexto.md) — agrega ADRs, código e padrões de teste.

**Escopo (backlog):** E7-01 (Kinds Branch/Commit) + a base de E7-02. Fora desta fatia: fetch de todas as remotas, serialização, `analyze_policy`, backfill, front, Telegram (planos seguintes).

---

### Task 1: Slug de nome de branch

Nomes de branch contêm `/` (ex.: `feat/x`), inválido para compor `name` de Resource limpo. Criar um slug determinístico.

**Files:**
- Modify: `src/atlas/rotinas/repo_sync.py` (adicionar função perto dos helpers, após `_git`)
- Test: `tests/test_repo_branch_commit.py` (novo arquivo)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_repo_branch_commit.py
"""TDD — materialização de Branch/Commit no repo-sync (ADR-0023)."""

from __future__ import annotations

from atlas.rotinas import repo_sync


def test_branch_slug_troca_barra_por_hifen():
    assert repo_sync._branch_slug("feat/x") == "feat-x"
    assert repo_sync._branch_slug("main") == "main"
    assert repo_sync._branch_slug("feature/a/b") == "feature-a-b"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_repo_branch_commit.py::test_branch_slug_troca_barra_por_hifen -v`
Expected: FAIL com `AttributeError: module 'atlas.rotinas.repo_sync' has no attribute '_branch_slug'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/atlas/rotinas/repo_sync.py  (após a função _git)
def _branch_slug(branch: str) -> str:
    """Slug determinístico para compor names de Resource (troca '/' e espaço por '-')."""
    return re.sub(r"[/\s]+", "-", branch.strip())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_repo_branch_commit.py::test_branch_slug_troca_barra_por_hifen -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atlas/rotinas/repo_sync.py tests/test_repo_branch_commit.py
git commit -m "feat(repo-sync): slug de nome de branch para Resources"
```

---

### Task 2: Listar branches remotas

Descobrir as branches remotas do clone, sem `origin/HEAD`, com o prefixo `origin/` removido.

**Files:**
- Modify: `src/atlas/rotinas/repo_sync.py`
- Test: `tests/test_repo_branch_commit.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_repo_branch_commit.py  (adicionar)
from pathlib import Path


def test_listar_branches_remotas_ignora_head(monkeypatch):
    saida = "origin/HEAD\norigin/main\norigin/feat/x\n"
    monkeypatch.setattr(repo_sync, "_git", lambda args, cwd=None: saida)
    branches = repo_sync._listar_branches_remotas(Path("/tmp/repo"))
    assert branches == ["main", "feat/x"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_repo_branch_commit.py::test_listar_branches_remotas_ignora_head -v`
Expected: FAIL com `AttributeError: ... '_listar_branches_remotas'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/atlas/rotinas/repo_sync.py
def _listar_branches_remotas(repo_dir: Path) -> list[str]:
    """Branches remotas de origin, sem 'origin/HEAD', com o prefixo 'origin/' removido."""
    out = _git(
        ["for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"],
        cwd=repo_dir,
    )
    nomes: list[str] = []
    for linha in out.splitlines():
        ref = linha.strip()
        if not ref or ref == "origin/HEAD":
            continue
        nomes.append(ref[len("origin/"):] if ref.startswith("origin/") else ref)
    return nomes
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_repo_branch_commit.py::test_listar_branches_remotas_ignora_head -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atlas/rotinas/repo_sync.py tests/test_repo_branch_commit.py
git commit -m "feat(repo-sync): listar branches remotas do clone"
```

---

### Task 3: Métricas de uma branch (ahead/behind/commits/atividade)

Calcular as métricas de uma branch relativas à default, via git.

**Files:**
- Modify: `src/atlas/rotinas/repo_sync.py`
- Test: `tests/test_repo_branch_commit.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_repo_branch_commit.py  (adicionar)
def test_metricas_branch_calcula_ahead_behind(monkeypatch):
    def fake_git(args, cwd=None):
        cmd = " ".join(args)
        if "rev-parse" in cmd:
            return "1a2b3c4d5e6f\n"
        if "--count" in cmd and "..." in cmd:
            return "3\t5\n"          # behind=3, ahead=5 (left-right)
        if "--count" in cmd:
            return "42\n"            # total de commits na branch
        if "log" in cmd:
            return "2026-06-20T10:00:00-03:00\n"
        return ""

    monkeypatch.setattr(repo_sync, "_git", fake_git)
    m = repo_sync._metricas_branch(Path("/tmp/repo"), "feat/x", "main")
    assert m["head"] == "1a2b3c4"
    assert m["ahead"] == 5
    assert m["behind"] == 3
    assert m["commits"] == 42
    assert m["last_activity"] == "2026-06-20T10:00:00-03:00"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_repo_branch_commit.py::test_metricas_branch_calcula_ahead_behind -v`
Expected: FAIL com `AttributeError: ... '_metricas_branch'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/atlas/rotinas/repo_sync.py
def _metricas_branch(repo_dir: Path, branch: str, default_branch: str) -> dict:
    """Métricas de 'branch' relativas a 'default_branch' (best-effort; campos zerados em falha)."""
    def g(args: list[str]) -> str:
        try:
            return _git(args, cwd=repo_dir).strip()
        except Exception as exc:  # noqa: BLE001 — degrada (ADR-0006)
            _log.debug("git %s falhou: %s", args[:2], exc)
            return ""

    head = g(["rev-parse", f"origin/{branch}"])[:7]
    ahead = behind = 0
    lr = g(["rev-list", "--left-right", "--count",
            f"origin/{default_branch}...origin/{branch}"])
    if "\t" in lr:
        b_str, a_str = lr.split("\t")[:2]
        behind = int(b_str) if b_str.isdigit() else 0
        ahead = int(a_str) if a_str.isdigit() else 0
    commits_str = g(["rev-list", "--count", f"origin/{branch}"])
    commits = int(commits_str) if commits_str.isdigit() else 0
    last_activity = g(["log", "-1", "--format=%cI", f"origin/{branch}"])
    return {
        "head": head,
        "ahead": ahead,
        "behind": behind,
        "commits": commits,
        "last_activity": last_activity,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_repo_branch_commit.py::test_metricas_branch_calcula_ahead_behind -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atlas/rotinas/repo_sync.py tests/test_repo_branch_commit.py
git commit -m "feat(repo-sync): métricas de branch (ahead/behind/commits/atividade)"
```

---

### Task 4: Materializar o Resource Branch

Gravar/atualizar um `Resource` Kind=`Branch`, oculto, rotulado ao repo.

**Files:**
- Modify: `src/atlas/rotinas/repo_sync.py`
- Test: `tests/test_repo_branch_commit.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_repo_branch_commit.py  (adicionar)
from datetime import datetime

from atlas.core.store import ResourceStore

_AGORA = datetime(2026, 6, 23, 9, 0)


class _Ctx:
    def __init__(self, store):
        self.agora = _AGORA
        self.store = store


def _store(tmp_path):
    return ResourceStore(str(tmp_path / "t.db"))


def test_materializar_branch_cria_resource_oculto(tmp_path):
    store = _store(tmp_path)
    metrics = {"head": "1a2b3c4", "ahead": 5, "behind": 3,
               "commits": 42, "last_activity": "2026-06-20T10:00:00-03:00"}
    repo_sync._materializar_branch("nora", "feat/x", "main", metrics, store, _Ctx(store))

    branches = store.list("Branch", labels={"repo": "nora"})
    assert len(branches) == 1
    b = branches[0]
    assert b.name == "nora-feat-x"
    assert b.labels == {"repo": "nora", "branch": "feat/x"}
    assert b.status["head"] == "1a2b3c4"
    assert b.status["ahead"] == 5
    assert b.status["behind"] == 3
    assert b.status["stale"] is False  # default branch alvo => não stale
    assert b.spec["name"] == "feat/x"
    assert b.spec["base"] == "main"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_repo_branch_commit.py::test_materializar_branch_cria_resource_oculto -v`
Expected: FAIL com `AttributeError: ... '_materializar_branch'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/atlas/rotinas/repo_sync.py
_STALE_DIAS = 30


def _materializar_branch(
    label: str, branch: str, default_branch: str, metrics: dict,
    store: ResourceStore, ctx: ContextoExecucao,
) -> None:
    """Cria/atualiza o Resource Branch (oculto), rotulado ao repo."""
    stale = _branch_stale(metrics.get("last_activity"), ctx.agora)
    res = Resource(
        kind="Branch",
        name=f"{label}-{_branch_slug(branch)}",
        labels={"repo": label, "branch": branch},
        spec={"name": branch, "base": default_branch},
        status={
            "head": metrics.get("head", ""),
            "ahead": metrics.get("ahead", 0),
            "behind": metrics.get("behind", 0),
            "commits": metrics.get("commits", 0),
            "last_activity": metrics.get("last_activity", ""),
            "stale": stale,
            "synced_at": ctx.agora.isoformat(),
        },
    )
    store.apply(res, ctx.agora)


def _branch_stale(last_activity: str | None, agora: datetime) -> bool:
    """True se a última atividade é mais antiga que _STALE_DIAS (ou desconhecida=False)."""
    if not last_activity:
        return False
    try:
        ts = datetime.fromisoformat(last_activity)
    except (ValueError, TypeError):
        return False
    return (agora - ts.replace(tzinfo=None)) > timedelta(days=_STALE_DIAS)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_repo_branch_commit.py::test_materializar_branch_cria_resource_oculto -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atlas/rotinas/repo_sync.py tests/test_repo_branch_commit.py
git commit -m "feat(repo-sync): materializar Resource Branch (oculto)"
```

---

### Task 5: Parents de um commit

Para o git-graph, o `Commit` guarda os SHAs pais.

**Files:**
- Modify: `src/atlas/rotinas/repo_sync.py`
- Test: `tests/test_repo_branch_commit.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_repo_branch_commit.py  (adicionar)
def test_commit_parents_divide_shas(monkeypatch):
    monkeypatch.setattr(repo_sync, "_git", lambda args, cwd=None: "9f8e7d6 1122334\n")
    parents = repo_sync._commit_parents(Path("/tmp/repo"), "1a2b3c4")
    assert parents == ["9f8e7d6", "1122334"]


def test_commit_parents_vazio_para_root(monkeypatch):
    monkeypatch.setattr(repo_sync, "_git", lambda args, cwd=None: "\n")
    assert repo_sync._commit_parents(Path("/tmp/repo"), "root") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_repo_branch_commit.py -k commit_parents -v`
Expected: FAIL com `AttributeError: ... '_commit_parents'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/atlas/rotinas/repo_sync.py
def _commit_parents(repo_dir: Path, sha: str) -> list[str]:
    """SHAs pais (abreviados) do commit; lista vazia para o root ou em falha."""
    try:
        out = _git(["log", "-1", "--format=%p", sha], cwd=repo_dir)
    except Exception as exc:  # noqa: BLE001
        _log.debug("git parents falhou para %s: %s", sha, exc)
        return []
    return out.split()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_repo_branch_commit.py -k commit_parents -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atlas/rotinas/repo_sync.py tests/test_repo_branch_commit.py
git commit -m "feat(repo-sync): extrair parents de commit para o git-graph"
```

---

### Task 6: Materializar o Resource Commit (resumo leve)

Gravar um `Resource` Kind=`Commit` leve (sem `diff_raw`), rotulado a repo+branch+commit.

**Files:**
- Modify: `src/atlas/rotinas/repo_sync.py`
- Test: `tests/test_repo_branch_commit.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_repo_branch_commit.py  (adicionar)
def test_materializar_commit_leve_sem_diff(tmp_path):
    store = _store(tmp_path)
    meta = {"subject": "refactor store", "author": "Luigi",
            "author_email": "l@x.com", "date": "2026-06-22T08:00:00-03:00",
            "date_rel": "há 1 dia"}
    stat = {"files": 5, "insertions": 120, "deletions": 40, "files_list": ["a.py"]}
    repo_sync._materializar_commit(
        "nora", "feat/x", "1a2b3c4", meta, stat, ["9f8e7d6"], store, _Ctx(store)
    )

    commits = store.list("Commit", labels={"repo": "nora"})
    assert len(commits) == 1
    c = commits[0]
    assert c.name == "nora-1a2b3c4"
    assert c.labels == {"repo": "nora", "branch": "feat/x", "commit": "1a2b3c4"}
    assert c.spec["sha"] == "1a2b3c4"
    assert c.spec["subject"] == "refactor store"
    assert c.spec["parents"] == ["9f8e7d6"]
    assert c.spec["stat"] == {"files": 5, "insertions": 120, "deletions": 40}
    assert "diff_raw" not in c.spec  # leve: sem diff pesado
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_repo_branch_commit.py::test_materializar_commit_leve_sem_diff -v`
Expected: FAIL com `AttributeError: ... '_materializar_commit'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/atlas/rotinas/repo_sync.py
def _materializar_commit(
    label: str, branch: str, sha7: str, meta: dict, stat: dict,
    parents: list[str], store: ResourceStore, ctx: ContextoExecucao,
) -> None:
    """Cria o Resource Commit (resumo leve, sem diff_raw), rotulado repo+branch+commit."""
    res = Resource(
        kind="Commit",
        name=f"{label}-{sha7}",
        labels={"repo": label, "branch": branch, "commit": sha7},
        spec={
            "sha": sha7,
            "subject": meta.get("subject", ""),
            "author": meta.get("author", ""),
            "date": meta.get("date", ""),
            "parents": parents,
            "stat": {
                "files": stat.get("files", 0),
                "insertions": stat.get("insertions", 0),
                "deletions": stat.get("deletions", 0),
            },
        },
        status={"synced_at": ctx.agora.isoformat()},
    )
    store.apply(res, ctx.agora)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_repo_branch_commit.py::test_materializar_commit_leve_sem_diff -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atlas/rotinas/repo_sync.py tests/test_repo_branch_commit.py
git commit -m "feat(repo-sync): materializar Resource Commit leve (git-graph)"
```

---

### Task 7: Wiring — sync da default branch materializa Branch + Commit

Integrar as primitivas no fluxo existente: ao reportar uma atualização, materializar também o `Branch` (default) e o `Commit` do novo HEAD. Não-quebrante: `Diff`/`Doc`/status atuais seguem iguais.

**Files:**
- Modify: `src/atlas/rotinas/repo_sync.py` (função `_reportar`, ao final, antes do `return`)
- Test: `tests/test_repo_branch_commit.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_repo_branch_commit.py  (adicionar)
import subprocess
from unittest.mock import MagicMock, patch

from atlas.db import Database
from atlas.executor import ContextoExecucao
from atlas.rotinas import obter
from atlas.routines import Rotina
from atlas.core.resource import Resource

_ROTINA = Rotina(nome="nora-sync", descricao="x", label="nora",
                 coletar="repo-sync", modelo="none")


def _store_com_repo(tmp_path):
    s = ResourceStore(str(tmp_path / "t.db"))
    s.apply(Resource(kind="Repo", name="nora", labels={},
                     spec={"url": "https://github.com/x/nora"}, status={}), _AGORA)
    return s


def test_sync_materializa_branch_e_commit_default(tmp_path, monkeypatch):
    import atlas.rotinas.repo_sync  # noqa: F401
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "atlas.sqlite"))
    store = _store_com_repo(tmp_path)
    db = Database(str(tmp_path / "t.db"))
    repo_dir = tmp_path / "repos" / "nora"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()

    def fake_run(args, **kw):
        cmd = " ".join(args)
        if "log" in cmd and "--format=%p" in cmd:
            return MagicMock(stdout="9f8e7d6\n", returncode=0, stderr="")
        if "log" in cmd:
            return MagicMock(stdout="feat: nova\nLuigi\nl@x.com\n2026-06-23T09:00:00-03:00\nhá 1h\n",
                             returncode=0, stderr="")
        if "symbolic-ref" in cmd:
            return MagicMock(stdout="main\n", returncode=0, stderr="")
        if "diff" in cmd:
            return MagicMock(stdout="+x\n 1 file changed, 1 insertion(+)\n", returncode=0, stderr="")
        if "rev-parse" in cmd:
            return MagicMock(stdout="abc1234\n", returncode=0, stderr="")
        return MagicMock(stdout="", returncode=0, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ctx = ContextoExecucao(agora=_AGORA, rotina=_ROTINA, origem="agenda", db=db, store=store)
    with patch("atlas.rotinas.repo_sync.invocar", return_value="ok"):
        obter("repo-sync")(ctx)

    assert store.list("Branch", labels={"repo": "nora"}), "deve materializar Branch"
    commits = store.list("Commit", labels={"repo": "nora"})
    assert commits and commits[0].spec["sha"] == "abc1234"
    # não-quebrante: Diff ainda existe
    assert store.list("Diff", labels={"repo": "nora"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_repo_branch_commit.py::test_sync_materializa_branch_e_commit_default -v`
Expected: FAIL (nenhum Branch/Commit materializado ainda)

- [ ] **Step 3: Add a helper to read the default branch, then wire into `_reportar`**

```python
# src/atlas/rotinas/repo_sync.py
def _default_branch(repo_dir: Path) -> str:
    """Nome da branch default de origin (best-effort; 'HEAD' como fallback)."""
    try:
        out = _git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=repo_dir)
    except Exception:  # noqa: BLE001
        return "HEAD"
    ref = out.strip()
    return ref[len("origin/"):] if ref.startswith("origin/") else (ref or "HEAD")
```

No fim de `_reportar`, logo antes de montar `data_str`/`return`, inserir:

```python
    # materializa grafo leve (ADR-0023): Branch default + Commit do novo HEAD
    repo_dir = _data_dir() / "repos" / label
    default = _default_branch(repo_dir)
    metrics = _metricas_branch(repo_dir, default, default)
    if not metrics.get("head"):
        metrics["head"] = sha7
    _materializar_branch(label, default, default, metrics, store, ctx)
    _materializar_commit(
        label, default, sha7, meta, stat, _commit_parents(repo_dir, sha), store, ctx
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_repo_branch_commit.py::test_sync_materializa_branch_e_commit_default -v`
Expected: PASS

- [ ] **Step 5: Run the full repo-sync suite to confirm non-regression**

Run: `python -m pytest tests/test_repo_sync.py tests/test_repo_contexto.py tests/test_repo_branch_commit.py -v`
Expected: todos PASS (comportamento de Diff/Doc/status inalterado)

- [ ] **Step 6: Commit**

```bash
git add src/atlas/rotinas/repo_sync.py tests/test_repo_branch_commit.py
git commit -m "feat(repo-sync): materializar Branch+Commit da default no sync (ADR-0023)"
```

---

## Self-Review

**1. Spec coverage (ADR-0023 §1–§3, fatia E7-01):**
- Kind `Branch` (oculto, labels repo+branch, métricas) → Tasks 3, 4, 7 ✓
- Kind `Commit` (leve, sem diff_raw, parents) → Tasks 5, 6, 7 ✓
- Agregação por label `repo=<label>` → labels em todas as materializações ✓
- Híbrido (commit leve; diff pesado fora) → `Commit` sem `diff_raw` (Task 6) ✓
- Fora de escopo desta fatia (próximos planos): fetch de **todas** as remotas e loop por branch (E7-02), serialização (E7-04), `analyze_policy` (E7-05), backfill (E7-06), schema `hidden` + render (E7-07/E7-08), Telegram (E7-11). Registrado em "Escopo".

**2. Placeholder scan:** sem TBD/TODO; todo step com código real e comando com saída esperada. ✓

**3. Type consistency:** assinaturas conferem entre tasks — `_metricas_branch` retorna dict consumido por `_materializar_branch` (Task 3→4); `_commit_parents` (lista) consumido por `_materializar_commit` (Task 5→6); `_branch_slug` usado em Task 4 e 6; `_default_branch` em Task 7. Campos `head/ahead/behind/commits/last_activity` idênticos onde usados. ✓

**Pré-requisitos do código:** o módulo já importa `re`, `logging` (`_log`), `timedelta`, `datetime`, `Path`, `Resource`, `ResourceStore`, `ContextoExecucao` — confirmado em repo_sync.py. Nenhum import novo necessário.
