"""Testes — comando /uso (E1-08)."""
from __future__ import annotations

from datetime import datetime

from atlas.db import Database
from atlas.uso import responder_uso

_AGORA = datetime(2026, 6, 16, 10, 0)


def _inserir_run(db, rotina, status="ok", tokens_in=0, tokens_out=0, custo=0.0):
    db.insert(
        "runs",
        rotina=rotina,
        iniciado_em=_AGORA.isoformat(),
        terminado_em=_AGORA.isoformat(),
        status=status,
        camada="0",
        gate_passou=1,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        custo_usd=custo,
    )


def test_uso_sem_runs(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    resp = responder_uso("/uso", db, _AGORA)
    assert resp is not None
    assert "nenhuma" in resp.lower() or "0" in resp


def test_uso_lista_rotinas(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    _inserir_run(db, "resumo-diario")
    _inserir_run(db, "resumo-diario")
    _inserir_run(db, "treino")
    resp = responder_uso("/uso", db, _AGORA)
    assert "resumo-diario" in resp
    assert "treino" in resp


def test_uso_nao_roteia_outros(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    assert responder_uso("/help", db, _AGORA) is None
    assert responder_uso("/list", db, _AGORA) is None


def test_uso_com_tokens(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    _inserir_run(db, "resumo-diario", tokens_in=1000, tokens_out=500, custo=0.005)
    resp = responder_uso("/uso", db, _AGORA)
    assert resp is not None
    # tokens ou custo aparecem no output
    assert "1000" in resp or "0.005" in resp or "tok" in resp.lower()


def test_uso_ultimas_n(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    for i in range(5):
        _inserir_run(db, f"rotina-{i}")
    resp = responder_uso("/uso 3", db, _AGORA)
    assert resp is not None
