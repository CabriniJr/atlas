"""TDD — sessões em memória (ADR-0027, Fase 4).

Token opaco aleatório → identidade do usuário, com TTL. Em memória (perde no
restart, como os runs agênticos); ``now`` é injetável para testar expiração.
"""

from __future__ import annotations

import pytest

from atlas import sessions


@pytest.fixture(autouse=True)
def _limpa():
    sessions.reset()
    yield
    sessions.reset()


def test_create_devolve_token_opaco():
    t1 = sessions.create_session("luigi", role="admin")
    t2 = sessions.create_session("luigi", role="admin")
    assert t1 and t2 and t1 != t2
    assert len(t1) >= 20


def test_resolve_recupera_usuario():
    t = sessions.create_session("ana", role="member")
    s = sessions.resolve_session(t)
    assert s is not None
    assert s["user"] == "ana"
    assert s["role"] == "member"


def test_resolve_token_invalido_eh_none():
    assert sessions.resolve_session("nope") is None
    assert sessions.resolve_session("") is None


def test_destroy_invalida_token():
    t = sessions.create_session("ana")
    assert sessions.destroy_session(t) is True
    assert sessions.resolve_session(t) is None
    assert sessions.destroy_session(t) is False


def test_sessao_expira_apos_ttl():
    t = sessions.create_session("ana", ttl_seconds=100, now=1000.0)
    assert sessions.resolve_session(t, now=1099.0) is not None
    assert sessions.resolve_session(t, now=1101.0) is None
