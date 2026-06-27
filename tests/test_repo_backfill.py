"""TDD — backfill (ADR-0023 §4, E7-06): varredura idempotente do histórico, 0 IA."""

from __future__ import annotations

import subprocess
from datetime import datetime

import pytest
from tests.repohelpers import init_origin

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.db import Database
from atlas.executor import ContextoExecucao
from atlas.rotinas.repo_sync.backfill import backfill
from atlas.routines import Rotina

_AGORA = datetime(2026, 6, 17, 9, 0)
_ROTINA = Rotina(nome="nora-sync", descricao="", label="nora", coletar="repo-sync", modelo="none")


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


def _store(tmp_path, spec):
    s = ResourceStore(str(tmp_path / "t.db"))
    s.apply(Resource(kind="Repo", name="nora", labels={}, spec=spec, status={}), _AGORA)
    return s


def _ctx(db, store):
    return ContextoExecucao(agora=_AGORA, rotina=_ROTINA, origem="agenda", db=db, store=store)


def test_backfill_sem_repo(db, tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "atlas.sqlite"))
    store = ResourceStore(str(tmp_path / "t.db"))
    out = backfill("nora", store, _ctx(db, store))
    assert "não configurado" in out.lower()


def test_backfill_materializa_e_idempotente(db, tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "atlas.sqlite"))
    origin = init_origin(tmp_path / "origin")
    repo_dir = tmp_path / "repos" / "nora"
    repo_dir.parent.mkdir(parents=True)
    subprocess.run(["git", "clone", str(origin), str(repo_dir)], check=True, capture_output=True)
    store = _store(tmp_path, {"url": str(origin)})

    out1 = backfill("nora", store, _ctx(db, store))
    assert "2 branch" in out1
    assert len(store.list("Commit", labels={"repo": "nora"})) == 4
    assert len(store.list("Branch", labels={"repo": "nora"})) == 2
    # 0 IA: nenhum Diff materializado no backfill
    assert store.list("Diff", labels={"repo": "nora"}) == []

    out2 = backfill("nora", store, _ctx(db, store))
    assert "0 commit" in out2
    assert len(store.list("Commit", labels={"repo": "nora"})) == 4  # não duplica
