"""Testes do modelo de objeto Resource (E0-01, ADR-0015).

TDD: a forma do objeto espelha o Kubernetes (apiVersion/kind/metadata/spec/status).
"""

from __future__ import annotations

from atlas.core.resource import Resource


def test_defaults_minimos():
    r = Resource(kind="Tracker", name="peso")
    assert r.kind == "Tracker"
    assert r.name == "peso"
    assert r.api_version == "atlas/v1"
    assert r.labels == {}
    assert r.spec == {}
    assert r.status == {}


def test_to_dict_forma_k8s():
    r = Resource(
        kind="Tracker",
        name="peso",
        labels={"dominio": "saude"},
        spec={"unidade": "kg"},
        status={"ultimo": 82.3},
        criado_em="2026-06-16T10:00:00",
        atualizado_em="2026-06-16T11:00:00",
    )
    d = r.to_dict()
    assert d["apiVersion"] == "atlas/v1"
    assert d["kind"] == "Tracker"
    assert d["metadata"]["name"] == "peso"
    assert d["metadata"]["labels"] == {"dominio": "saude"}
    assert d["metadata"]["criado_em"] == "2026-06-16T10:00:00"
    assert d["spec"] == {"unidade": "kg"}
    assert d["status"] == {"ultimo": 82.3}


def test_from_dict_ida_e_volta():
    original = Resource(
        kind="Idea",
        name="ui-web",
        labels={"prioridade": "alta"},
        spec={"corpo": "fazer UI web"},
        status={"estado": "capturada"},
        criado_em="2026-06-16T10:00:00",
        atualizado_em="2026-06-16T10:00:00",
    )
    reconstruido = Resource.from_dict(original.to_dict())
    assert reconstruido == original


def test_from_dict_aceita_campos_ausentes():
    r = Resource.from_dict({"kind": "Routine", "metadata": {"name": "resumo"}})
    assert r.kind == "Routine"
    assert r.name == "resumo"
    assert r.spec == {}
    assert r.status == {}
    assert r.labels == {}
