"""TDD — resolução de engine via LLMProvider (ADR-0026) e Job de sync por label (P11)."""

from __future__ import annotations

from datetime import datetime

import pytest

import atlas.api as api_mod
from atlas.api import _resolve_engine, _resolve_repo_sync_job, _rotina_from_job
from atlas.core.resource import Resource
from atlas.core.store import ResourceStore

_AGORA = datetime(2026, 6, 24, 9, 0)


@pytest.fixture
def store(tmp_path):
    s = ResourceStore(str(tmp_path / "t.db"))
    s.apply(
        Resource(
            kind="LLMProvider",
            name="claude-default",
            spec={"motor": "claude", "modelo": "claude-sonnet-4-6", "timeout": 90},
        ),
        _AGORA,
    )
    s.apply(
        Resource(
            kind="LLMProvider",
            name="ollama-local",
            spec={
                "motor": "ollama",
                "modelo": "gemma4",
                "endpoint": "http://x:11434",
                "timeout": 30,
            },
        ),
        _AGORA,
    )
    return s


# ── _resolve_engine ─────────────────────────────────────────────────────────────


def test_provider_dita_motor_e_modelo(store):
    eng = _resolve_engine({"provider": "claude-default"}, store)
    assert eng["motor"] == "claude"
    assert eng["modelo"] == "claude-sonnet-4-6"
    assert eng["timeout"] == 90
    assert eng["provider"] == "claude-default"


def test_modelo_do_agente_sobrepoe_provider(store):
    eng = _resolve_engine(
        {"provider": "claude-default", "modelo": "claude-haiku-4-5-20251001"}, store
    )
    assert eng["modelo"] == "claude-haiku-4-5-20251001"
    assert eng["motor"] == "claude"  # motor continua do provider


def test_provider_ollama_traz_endpoint(store):
    eng = _resolve_engine({"provider": "ollama-local"}, store)
    assert eng["motor"] == "ollama"
    assert eng["endpoint"] == "http://x:11434"


def test_sem_provider_usa_campos_proprios(store):
    eng = _resolve_engine({"motor": "claude", "modelo": "claude-haiku-4-5-20251001"}, store)
    assert eng["motor"] == "claude"
    assert eng["modelo"] == "claude-haiku-4-5-20251001"
    assert eng["provider"] is None


def test_provider_inexistente_cai_em_fallback(store):
    eng = _resolve_engine({"provider": "nao-existe", "motor": "ollama"}, store)
    assert eng["motor"] == "ollama"  # usou campo próprio
    # modelo default por motor (sem modelo próprio nem provider)
    assert eng["modelo"] == "gemma4"


def test_defaults_quando_vazio(store):
    eng = _resolve_engine({}, store)
    assert eng["motor"] == "claude"
    assert eng["modelo"] == "claude-haiku-4-5-20251001"


# ── _resolve_repo_sync_job (match por LABEL, não por nome) ───────────────────────


def test_resolve_sync_job_por_label(store, monkeypatch):
    # Job com nome NÃO-convencional, vínculo só pelo label
    store.apply(
        Resource(
            kind="Job",
            name="sync-do-meu-repo",
            spec={"coletar": "repo-sync", "label": "meurepo", "active": True},
        ),
        _AGORA,
    )
    monkeypatch.setattr(api_mod, "_store", store)
    assert _resolve_repo_sync_job("meurepo") == "sync-do-meu-repo"


def test_resolve_sync_job_inexistente(store, monkeypatch):
    monkeypatch.setattr(api_mod, "_store", store)
    assert _resolve_repo_sync_job("nao-tem") is None


def test_resolve_ignora_job_sem_coletar_repo_sync(store, monkeypatch):
    store.apply(
        Resource(
            kind="Job",
            name="outro",
            spec={"coletar": "treino", "label": "meurepo"},
        ),
        _AGORA,
    )
    monkeypatch.setattr(api_mod, "_store", store)
    assert _resolve_repo_sync_job("meurepo") is None


# ── _rotina_from_job ─────────────────────────────────────────────────────────────


def test_rotina_from_job_mapeia_spec(store):
    job = Resource(
        kind="Job",
        name="meu-job",
        spec={
            "coletar": "repo-sync",
            "label": "r1",
            "schedule": "@daily 09:00",
            "model": "none",
            "active": True,
            "description": "desc",
        },
    )
    rot = _rotina_from_job(job)
    assert rot.nome == "meu-job"
    assert rot.coletar == "repo-sync"
    assert rot.label == "r1"
    assert rot.agenda == "@daily 09:00"
    assert rot.ativa is True
