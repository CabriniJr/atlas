"""TDD — snapshot da árvore completa + should_serialize (E7-31)."""

from __future__ import annotations

import subprocess
from datetime import datetime
from types import SimpleNamespace

from tests.repohelpers import init_origin

from atlas.core.store import ResourceStore
from atlas.rotinas.repo_sync import serialize

_AGORA = datetime(2026, 6, 24, 9, 0)


def test_should_serialize_presets():
    assert serialize.should_serialize("README.md", "docs")
    assert not serialize.should_serialize("a.py", "docs")
    assert serialize.should_serialize("a.py", "docs+code")
    assert not serialize.should_serialize("a.py", "off")


def test_should_serialize_glob_extra():
    assert serialize.should_serialize("config.cfg", "off", ["*.cfg"])


def test_snapshot_tree_serializa_arvore_inteira(tmp_path):
    origin = init_origin(tmp_path / "origin")
    repo_dir = tmp_path / "repos" / "p"
    repo_dir.parent.mkdir(parents=True)
    subprocess.run(["git", "clone", str(origin), str(repo_dir)], check=True, capture_output=True)

    store = ResourceStore(str(tmp_path / "t.db"))
    ctx = SimpleNamespace(agora=_AGORA)

    # preset docs → só README.md (a.py é código, fora do preset)
    res = serialize.snapshot_tree(repo_dir, "p", "docs", [], store, ctx)
    assert res["serializados"] == 1
    docs = store.list("Doc", labels={"repo": "p", "tipo": "serial"})
    assert len(docs) == 1
    assert docs[0].labels["path"] == "README.md"


def test_snapshot_tree_docs_code_pega_python(tmp_path):
    origin = init_origin(tmp_path / "origin")
    repo_dir = tmp_path / "repos" / "p"
    repo_dir.parent.mkdir(parents=True)
    subprocess.run(["git", "clone", str(origin), str(repo_dir)], check=True, capture_output=True)

    store = ResourceStore(str(tmp_path / "t.db"))
    ctx = SimpleNamespace(agora=_AGORA)

    res = serialize.snapshot_tree(repo_dir, "p", "docs+code", [], store, ctx)
    # README.md + a.py (na main; b.py está na branch feat/x, não na HEAD)
    assert res["serializados"] >= 2
    paths = {d.labels["path"] for d in store.list("Doc", labels={"repo": "p", "tipo": "serial"})}
    assert "README.md" in paths
    assert "a.py" in paths


def test_snapshot_tree_off_nao_serializa(tmp_path):
    origin = init_origin(tmp_path / "origin")
    repo_dir = tmp_path / "repos" / "p"
    repo_dir.parent.mkdir(parents=True)
    subprocess.run(["git", "clone", str(origin), str(repo_dir)], check=True, capture_output=True)
    store = ResourceStore(str(tmp_path / "t.db"))
    res = serialize.snapshot_tree(repo_dir, "p", "off", [], store, SimpleNamespace(agora=_AGORA))
    assert res["serializados"] == 0
    assert res.get("erro") == "serialize=off"
