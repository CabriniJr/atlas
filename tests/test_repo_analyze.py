"""TDD — analyze_policy degradado (ADR-0023 §2/§4): gating + disjuntor de budget."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest
from tests.repohelpers import commit, init_origin

import atlas.rotinas.repo_sync  # noqa: F401
from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.db import Database
from atlas.executor import ContextoExecucao
from atlas.rotinas import obter
from atlas.rotinas.repo_sync import analyze
from atlas.routines import Rotina

_AGORA = datetime(2026, 6, 17, 9, 0)
_ROTINA = Rotina(nome="nora-sync", descricao="", label="nora", coletar="repo-sync", modelo="none")


def _repo(spec):
    return Resource(kind="Repo", name="nora", spec=spec, status={})


# ── gating (função pura) ───────────────────────────────────────────────────────


def test_gating_default_so_na_branch_default():
    r = _repo({})  # default: analyze_branches=default, min_lines=20
    meta = {"is_merge": False, "lines_changed": 50}
    assert analyze.deve_analisar(meta, "main", "main", r) is True
    assert analyze.deve_analisar(meta, "feat/x", "main", r) is False


def test_gating_allowlist():
    r = _repo({"analyze_branches": "feat/x, dev"})
    meta = {"is_merge": False, "lines_changed": 50}
    assert analyze.deve_analisar(meta, "feat/x", "main", r) is True
    assert analyze.deve_analisar(meta, "main", "main", r) is False


def test_gating_pula_merges():
    r = _repo({"analyze_branches": "all"})
    assert analyze.deve_analisar({"is_merge": True, "lines_changed": 99}, "x", "main", r) is False
    assert analyze.deve_analisar({"is_merge": False, "lines_changed": 99}, "x", "main", r) is True


def test_gating_min_lines():
    r = _repo({"analyze_branches": "all", "analyze_min_lines": 20})
    assert analyze.deve_analisar({"is_merge": False, "lines_changed": 5}, "x", "main", r) is False
    assert analyze.deve_analisar({"is_merge": False, "lines_changed": 25}, "x", "main", r) is True


# ── disjuntor de budget (integração, git real) ─────────────────────────────────


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


def _store(tmp_path, spec):
    s = ResourceStore(str(tmp_path / "t.db"))
    s.apply(Resource(kind="Repo", name="nora", labels={}, spec=spec, status={}), _AGORA)
    return s


def _ctx(db, store):
    return ContextoExecucao(agora=_AGORA, rotina=_ROTINA, origem="agenda", db=db, store=store)


def test_disjuntor_limita_analises_por_run(db, tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "atlas.sqlite"))
    origin = init_origin(tmp_path / "origin")
    store = _store(
        tmp_path,
        {
            "url": str(origin),
            "analyze_branches": "main",
            "analyze_min_lines": "1",
            "analyze_max_per_run": "2",
        },
    )
    # clone (analisar=False → não chama IA de análise)
    with patch("atlas.rotinas.repo_sync.invocar", return_value="ctx"):
        obter("repo-sync")(_ctx(db, store))

    # 3 commits novos elegíveis na main
    for i in range(3):
        commit(origin, "big.py", "\n".join(f"l{j}={i}" for j in range(6)) + "\n", f"feat big {i}")

    chamadas = []
    with patch(
        "atlas.rotinas.repo_sync.invocar",
        side_effect=lambda p, **kw: chamadas.append(p) or "analise",
    ):
        obter("repo-sync")(_ctx(db, store))

    # budget=2 → no máximo 2 análises de IA, mesmo com 3 commits elegíveis
    assert len(chamadas) == 2
    assert len(store.list("Diff", labels={"repo": "nora"})) == 2
