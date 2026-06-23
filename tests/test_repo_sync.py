"""TDD — repo-sync multi-branch (ADR-0023): materialização Branch/Commit, grafo,
sync incremental e notificação. Usa repositórios git reais (mais fiel que mockar
saída de git); a IA é sempre mockada."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest
from tests.repohelpers import commit, init_origin

import atlas.rotinas.repo_sync  # noqa: F401 — registra a rotina
from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.db import Database
from atlas.executor import ContextoExecucao
from atlas.rotinas import obter
from atlas.routines import Rotina

_AGORA = datetime(2026, 6, 17, 9, 0)
_ROTINA = Rotina(
    nome="nora-sync", descricao="Monitor nora", label="nora", coletar="repo-sync", modelo="none"
)


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


def _store(tmp_path, spec=None):
    s = ResourceStore(str(tmp_path / "t.db"))
    s.apply(
        Resource(kind="Repo", name="nora", labels={"grupo": "repos"}, spec=spec or {}, status={}),
        _AGORA,
    )
    return s


def _ctx(db, store):
    return ContextoExecucao(agora=_AGORA, rotina=_ROTINA, origem="agenda", db=db, store=store)


def _rodar(db, store, monkeypatch, tmp_path, retorno="ctx"):
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "atlas.sqlite"))
    with patch("atlas.rotinas.repo_sync.invocar", return_value=retorno):
        return obter("repo-sync")(_ctx(db, store)).data["_saida"]


# ── guards ─────────────────────────────────────────────────────────────────────


def test_repo_sync_registrado(db):
    assert obter("repo-sync") is not None


def test_repo_sync_sem_repo_resource(db, tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "atlas.sqlite"))
    store = ResourceStore(str(tmp_path / "t.db"))
    saida = obter("repo-sync")(_ctx(db, store)).data["_saida"]
    assert "não configurado" in saida.lower()
    assert "nora" in saida


def test_repo_sync_sem_store_retorna_aviso(db):
    ctx = ContextoExecucao(agora=_AGORA, rotina=_ROTINA, origem="agenda", db=db)
    assert obter("repo-sync")(ctx).data["_saida"]


def test_repo_sync_url_ausente(db, tmp_path, monkeypatch):
    store = _store(tmp_path, {"url": ""})
    saida = _rodar(db, store, monkeypatch, tmp_path)
    assert "url" in saida.lower()


# ── clone + materialização multi-branch ────────────────────────────────────────


def test_collect_clona_e_materializa_branches(db, tmp_path, monkeypatch):
    origin = init_origin(tmp_path / "origin")
    store = _store(tmp_path, {"url": str(origin)})
    saida = _rodar(db, store, monkeypatch, tmp_path)

    assert "clonado" in saida.lower()
    branches = store.list("Branch", labels={"repo": "nora"})
    assert {b.spec["branch"] for b in branches} == {"main", "feat/x"}
    commits = store.list("Commit", labels={"repo": "nora"})
    assert len(commits) == 4  # init, a, b, mais-b (distintos)


def test_repo_status_agregado(db, tmp_path, monkeypatch):
    origin = init_origin(tmp_path / "origin")
    store = _store(tmp_path, {"url": str(origin)})
    _rodar(db, store, monkeypatch, tmp_path)

    st = store.get("Repo", "nora").status
    assert st["default_branch"] == "main"
    assert st["branches_total"] == 2
    assert st["commits_total"] == 4


def test_commit_parents_reconstroi_grafo(db, tmp_path, monkeypatch):
    origin = init_origin(tmp_path / "origin")
    store = _store(tmp_path, {"url": str(origin)})
    _rodar(db, store, monkeypatch, tmp_path)

    commits = {c.spec["subject"]: c for c in store.list("Commit", labels={"repo": "nora"})}
    # "feat: mais b" tem exatamente 1 pai (o commit "feat: b na branch")
    mais_b = commits["feat: mais b"]
    assert len(mais_b.spec["parents"]) == 1
    assert mais_b.spec["is_merge"] is False
    # o pai materializado existe → grafo reconstruível
    pai_sha7 = mais_b.spec["parents"][0]
    assert any(c.spec["sha"].startswith(pai_sha7) for c in commits.values())


def test_branch_ahead_behind(db, tmp_path, monkeypatch):
    origin = init_origin(tmp_path / "origin")
    store = _store(tmp_path, {"url": str(origin)})
    _rodar(db, store, monkeypatch, tmp_path)

    feat = store.get("Branch", "nora-feat-x")
    assert feat.status["ahead"] == 2
    assert feat.status["behind"] == 0
    assert feat.status["is_default"] is False
    main = store.get("Branch", "nora-main")
    assert main.status["is_default"] is True


# ── sync incremental ───────────────────────────────────────────────────────────


def test_collect_sem_mudancas(db, tmp_path, monkeypatch):
    origin = init_origin(tmp_path / "origin")
    store = _store(tmp_path, {"url": str(origin)})
    _rodar(db, store, monkeypatch, tmp_path)  # clone
    saida = _rodar(db, store, monkeypatch, tmp_path)  # 2º run, nada novo
    assert "sem mudanças" in saida.lower()


def test_collect_incremental_so_novos(db, tmp_path, monkeypatch):
    origin = init_origin(tmp_path / "origin")
    store = _store(tmp_path, {"url": str(origin)})
    _rodar(db, store, monkeypatch, tmp_path)  # clone materializa tudo
    antes = len(store.list("Commit", labels={"repo": "nora"}))

    commit(origin, "c.py", "novo = 1\n", "feat: c novo")
    saida = _rodar(db, store, monkeypatch, tmp_path)

    assert "+1" in saida
    assert "main" in saida
    depois = len(store.list("Commit", labels={"repo": "nora"}))
    assert depois == antes + 1


# ── serialização ───────────────────────────────────────────────────────────────


def test_serializa_arquivos_de_doc(db, tmp_path, monkeypatch):
    origin = init_origin(tmp_path / "origin")
    store = _store(tmp_path, {"url": str(origin), "serialize": "docs"})
    _rodar(db, store, monkeypatch, tmp_path)

    seriais = store.list("Doc", labels={"repo": "nora", "tipo": "serial"})
    paths = {d.labels["path"] for d in seriais}
    assert "README.md" in paths
    readme = next(d for d in seriais if d.labels["path"] == "README.md")
    assert "proj" in readme.spec["body"]
    # código não entra no preset "docs"
    assert "a.py" not in paths


def test_serialize_off_nao_gera_doc(db, tmp_path, monkeypatch):
    origin = init_origin(tmp_path / "origin")
    store = _store(tmp_path, {"url": str(origin), "serialize": "off"})
    _rodar(db, store, monkeypatch, tmp_path)
    assert store.list("Doc", labels={"repo": "nora", "tipo": "serial"}) == []
