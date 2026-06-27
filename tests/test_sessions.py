"""TDD — sessões em memória (ADR-0027, Fase 4).

Token opaco aleatório → identidade do usuário, com TTL. Em memória (perde no
restart, como os runs agênticos); ``now`` é injetável para testar expiração.
"""

from __future__ import annotations

import pytest

from atlas import sessions


@pytest.fixture(autouse=True)
def _limpa(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_SESSIONS_PATH", str(tmp_path / "sessions.json"))
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


# ── persistência (item 1.2 do hardening / ADR-0027 §Pendências) ────────────────


def test_sessao_sobrevive_a_restart():
    t = sessions.create_session("ana", role="member")
    sessions.reload()  # simula reinício do processo (recarrega do disco)
    s = sessions.resolve_session(t)
    assert s is not None
    assert s["user"] == "ana"
    assert s["role"] == "member"


def test_destroy_persiste_apos_restart():
    t = sessions.create_session("ana")
    sessions.destroy_session(t)
    sessions.reload()
    assert sessions.resolve_session(t) is None


def test_arquivo_nao_guarda_token_em_claro(tmp_path):
    t = sessions.create_session("ana")
    conteudo = (tmp_path / "sessions.json").read_text()
    assert t not in conteudo  # só o hash do token vai pro disco


def test_arquivo_corrompido_degrada(tmp_path):
    (tmp_path / "sessions.json").write_text("{lixo não-json}")
    sessions.reload()  # não deve quebrar
    assert sessions.resolve_session("qualquer") is None
    # e ainda dá pra criar/resolver normalmente
    t = sessions.create_session("ana")
    assert sessions.resolve_session(t)["user"] == "ana"


def test_expiracao_persistida_sobrevive_restart():
    t = sessions.create_session("ana", ttl_seconds=100, now=1000.0)
    sessions.reload()
    assert sessions.resolve_session(t, now=1099.0) is not None
    assert sessions.resolve_session(t, now=1101.0) is None


def test_reset_limpa_o_arquivo():
    sessions.create_session("ana")
    sessions.reset()
    sessions.reload()
    assert sessions.resolve_session("ana") is None
