"""Testes do processamento de update (segurança: só o dono é atendido)."""

from __future__ import annotations

from datetime import datetime

from atlas.app import Update, processar_update
from atlas.config import Config
from atlas.db import Database


class _FakeAdapter:
    def __init__(self) -> None:
        self.enviados: list[tuple[int, str]] = []

    def enviar(self, chat_id: int, texto: str) -> None:
        self.enviados.append((chat_id, texto))


_CFG = Config(telegram_token="x", allowed_user_id=42)


def test_dono_e_atendido_e_atividade_registrada():
    db = Database(":memory:")
    adapter = _FakeAdapter()
    upd = Update(update_id=1, chat_id=42, user_id=42, texto="treino de perna")

    processar_update(upd, _CFG, db, adapter, agora=datetime(2026, 6, 16, 21, 0))

    assert len(adapter.enviados) == 1
    assert db.connection.execute("SELECT COUNT(*) AS n FROM activities").fetchone()["n"] == 1


def test_estranho_e_ignorado():
    db = Database(":memory:")
    adapter = _FakeAdapter()
    upd = Update(update_id=1, chat_id=999, user_id=999, texto="oi")

    processar_update(upd, _CFG, db, adapter, agora=datetime(2026, 6, 16, 21, 0))

    assert adapter.enviados == []
    assert db.connection.execute("SELECT COUNT(*) AS n FROM activities").fetchone()["n"] == 0
