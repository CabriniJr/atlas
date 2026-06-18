"""TDD — /docs: interface com documentação via Telegram."""

from __future__ import annotations

from datetime import datetime

from atlas.docs_cmd import responder_docs

_AGORA = datetime(2025, 6, 16, 10, 0)


def test_docs_sem_args_retorna_indice():
    resp = responder_docs("/docs", _AGORA)
    assert resp is not None
    assert "kinds" in resp.lower() or "backlog" in resp.lower() or "adr" in resp.lower()


def test_docs_kinds_retorna_conteudo():
    resp = responder_docs("/docs kinds", _AGORA)
    assert resp is not None
    assert "Kind" in resp or "Tracker" in resp or "Alarm" in resp


def test_docs_backlog_retorna_epicos():
    resp = responder_docs("/docs backlog", _AGORA)
    assert resp is not None
    assert "E0" in resp or "E1" in resp or "feito" in resp.lower()


def test_docs_adr_retorna_conteudo():
    resp = responder_docs("/docs adr 15", _AGORA)
    assert resp is not None
    assert "ADR" in resp or "objeto" in resp.lower() or "resource" in resp.lower()


def test_docs_nao_existe_retorna_erro():
    resp = responder_docs("/docs xyzinexistente", _AGORA)
    assert resp is not None
    assert "not found" in resp.lower() or "❓" in resp


def test_docs_retorna_menos_de_4000_chars():
    resp = responder_docs("/docs backlog", _AGORA)
    assert resp is not None
    assert len(resp) < 4000


def test_docs_nao_e_comando_retorna_none():
    assert responder_docs("/help", _AGORA) is None
    assert responder_docs("texto livre", _AGORA) is None


def test_docs_arch_retorna_visao_geral():
    resp = responder_docs("/docs arch", _AGORA)
    assert resp is not None
    # deve mencionar algo de arquitetura
    assert len(resp) > 100
