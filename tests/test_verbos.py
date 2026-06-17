"""E0-03 — Verbos kubectl-like no chat (TDD)."""

from __future__ import annotations

from datetime import datetime

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.verbos import responder_verbos

T0 = datetime(2026, 6, 16, 10, 0)


def _store(*recursos: Resource) -> ResourceStore:
    s = ResourceStore(":memory:")
    for r in recursos:
        s.apply(r, T0)
    return s


# --- /list -------------------------------------------------------------------


def test_list_kind_vazio():
    resposta = responder_verbos("/list Idea", _store(), T0)
    assert resposta is not None
    assert (
        "0" in resposta
        or "empty" in resposta.lower()
        or "vazio" in resposta.lower()
        or "not found" in resposta.lower()
        or "no " in resposta.lower()
    )


def test_list_retorna_recursos():
    s = _store(
        Resource(kind="Idea", name="ui-web", spec={"body": "fazer frontend"}),
        Resource(kind="Idea", name="dark-mode"),
    )
    resposta = responder_verbos("/list Idea", s, T0)
    assert "ui-web" in resposta
    assert "dark-mode" in resposta


def test_list_sem_kind_retorna_ajuda():
    resposta = responder_verbos("/list", _store(), T0)
    assert resposta is not None
    assert "usage" in resposta.lower() or "/list" in resposta


# --- /get --------------------------------------------------------------------


def test_get_existente():
    s = _store(Resource(kind="Tracker", name="weight", spec={"unit": "kg"}))
    resposta = responder_verbos("/get Tracker weight", s, T0)
    assert "weight" in resposta
    assert "kg" in resposta


def test_get_inexistente():
    resposta = responder_verbos("/get Tracker nao-existe", _store(), T0)
    assert "not found" in resposta.lower() or "não encontrado" in resposta.lower()


def test_get_args_insuficientes():
    resposta = responder_verbos("/get Tracker", _store(), T0)
    assert "usage" in resposta.lower() or "/get" in resposta


# --- /describe ---------------------------------------------------------------


def test_describe_mostra_spec_e_status():
    r = Resource(
        kind="Idea",
        name="meta-loop",
        spec={"body": "implementar meta-loop"},
        status={"state": "capturada"},
    )
    resposta = responder_verbos("/describe Idea meta-loop", _store(r), T0)
    assert "meta-loop" in resposta
    assert "spec" in resposta.lower() or "body" in resposta
    assert "status" in resposta.lower() or "capturada" in resposta


# --- /delete -----------------------------------------------------------------


def test_delete_existente():
    s = _store(Resource(kind="Idea", name="obsoleta"))
    resposta = responder_verbos("/delete Idea obsoleta", s, T0)
    assert "deleted" in resposta.lower() or "removido" in resposta.lower()
    assert s.get("Idea", "obsoleta") is None


def test_delete_inexistente():
    resposta = responder_verbos("/delete Idea nao-existe", _store(), T0)
    assert "not found" in resposta.lower() or "não encontrado" in resposta.lower()


# --- /apply ------------------------------------------------------------------


def test_apply_cria_recurso():
    s = ResourceStore(":memory:")
    resposta = responder_verbos("/apply Idea nova body=testar", s, T0)
    assert "applied" in resposta.lower() or "ok" in resposta.lower() or "✅" in resposta
    assert s.get("Idea", "nova") is not None


def test_apply_atualiza_recurso():
    s = _store(Resource(kind="Idea", name="existente", spec={"body": "original"}))
    responder_verbos("/apply Idea existente body=atualizado", s, T0)
    r = s.get("Idea", "existente")
    assert r is not None
    assert r.spec.get("body") == "atualizado"


# --- comandos não-verbos retornam None ---------------------------------------


def test_nao_verbo_retorna_none():
    assert responder_verbos("/help", _store(), T0) is None
    assert responder_verbos("/track", _store(), T0) is None
    assert responder_verbos("texto livre", _store(), T0) is None
