"""TDD — label selectors: /list <Kind> -l key=val, /apply <Kind> <name> labels.key=val."""

from __future__ import annotations

from datetime import datetime

import pytest

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.verbos import responder_verbos

_AGORA = datetime(2025, 6, 16, 10, 0)


@pytest.fixture
def store(tmp_path):
    s = ResourceStore(str(tmp_path / "test.db"))
    s.apply(
        Resource(kind="Tracker", name="peso", labels={"domain": "fisico", "routine": "treino"}),
        _AGORA,
    )
    s.apply(Resource(kind="Tracker", name="sono", labels={"domain": "sono"}), _AGORA)
    s.apply(
        Resource(
            kind="Tracker", name="estudo", labels={"domain": "estudo", "routine": "resumo-diario"}
        ),
        _AGORA,
    )
    return s


# ---------------------------------------------------------------------------
# /list <Kind> -l key=val
# ---------------------------------------------------------------------------


def test_list_com_label_selector_filtra(store):
    resp = responder_verbos("/list Tracker -l domain=fisico", store, _AGORA)
    assert resp is not None
    assert "peso" in resp
    assert "sono" not in resp


def test_list_com_label_selector_sem_match_vazio(store):
    resp = responder_verbos("/list Tracker -l domain=nao-existe", store, _AGORA)
    assert resp is not None
    assert "peso" not in resp
    assert "sono" not in resp


def test_list_com_dois_labels_and(store):
    resp = responder_verbos("/list Tracker -l domain=fisico,routine=treino", store, _AGORA)
    assert resp is not None
    assert "peso" in resp
    assert "estudo" not in resp


def test_list_sem_selector_lista_todos(store):
    resp = responder_verbos("/list Tracker", store, _AGORA)
    assert resp is not None
    assert "peso" in resp
    assert "sono" in resp
    assert "estudo" in resp


# ---------------------------------------------------------------------------
# /apply com labels.key=val
# ---------------------------------------------------------------------------


def test_apply_adiciona_label(store):
    resp = responder_verbos("/apply Tracker peso labels.routine=treino", store, _AGORA)
    assert resp is not None
    r = store.get("Tracker", "peso")
    assert r.labels.get("routine") == "treino"


def test_apply_label_nao_sobrescreve_spec(store):
    resp = responder_verbos("/apply Tracker peso labels.nova=sim spec.unit=kg", store, _AGORA)
    assert resp is not None
    r = store.get("Tracker", "peso")
    assert r.labels.get("nova") == "sim"
    assert r.spec.get("unit") == "kg"


# ---------------------------------------------------------------------------
# store.list com selector
# ---------------------------------------------------------------------------


def test_store_list_com_selector(tmp_path):
    from atlas.core.store import ResourceStore
    s = ResourceStore(str(tmp_path / "s.db"))
    s.apply(Resource(kind="Tracker", name="a", labels={"t": "x"}), _AGORA)
    s.apply(Resource(kind="Tracker", name="b", labels={"t": "y"}), _AGORA)
    resultado = s.list("Tracker", labels={"t": "x"})
    assert len(resultado) == 1
    assert resultado[0].name == "a"
