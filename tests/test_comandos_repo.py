"""TDD — comando /repo backfill <label> (ADR-0023 §6, E7-06)."""

from __future__ import annotations

import subprocess
from datetime import datetime

import pytest
from tests.repohelpers import init_origin

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.db import Database
from atlas.handler import responder

_AGORA = datetime(2026, 6, 17, 9, 0)


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


def test_repo_sem_args(db, tmp_path):
    store = ResourceStore(str(tmp_path / "t.db"))
    assert "Usage" in responder("/repo", db, _AGORA, store=store)


def test_repo_subcomando_desconhecido(db, tmp_path):
    store = ResourceStore(str(tmp_path / "t.db"))
    out = responder("/repo foo nora", db, _AGORA, store=store)
    assert "foo" in out and "Usage" in out


def test_repo_backfill_executa(db, tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "atlas.sqlite"))
    origin = init_origin(tmp_path / "origin")
    repo_dir = tmp_path / "repos" / "nora"
    repo_dir.parent.mkdir(parents=True)
    subprocess.run(["git", "clone", str(origin), str(repo_dir)], check=True, capture_output=True)

    store = ResourceStore(str(tmp_path / "t.db"))
    store.apply(Resource(kind="Repo", name="nora", spec={"url": str(origin)}, status={}), _AGORA)

    out = responder("/repo backfill nora", db, _AGORA, store=store)
    assert "backfill" in out.lower()
    assert len(store.list("Commit", labels={"repo": "nora"})) == 4
