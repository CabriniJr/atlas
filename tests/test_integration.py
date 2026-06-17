"""Integração fim-a-fim: adapter (transport fake) → normalização → handler → DB.

Prova o caminho completo sem rede real: simula uma resposta de getUpdates do
Telegram e verifica que uma resposta é enviada, a atividade é persistida e o
offset avança.
"""

from __future__ import annotations

from datetime import datetime

from atlas.app import _normalizar, processar_update
from atlas.config import Config
from atlas.db import Database
from atlas.telegram import TelegramAdapter


class _FakeTransport:
    """Simula a Bot API: getUpdates devolve um payload; sendMessage é capturado."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.enviados: list[tuple[str, bytes | None]] = []

    def __call__(self, url: str, dados: bytes | None) -> dict:
        if "getUpdates" in url:
            payload, self._payload = self._payload, {"result": []}
            return payload
        self.enviados.append((url, dados))
        return {"ok": True}


def test_loop_atende_o_dono_fim_a_fim():
    payload = {
        "result": [
            {
                "update_id": 5,
                "message": {
                    "chat": {"id": 42},
                    "from": {"id": 42},
                    "text": "/reg treino de perna",
                },
            }
        ]
    }
    fake = _FakeTransport(payload)
    adapter = TelegramAdapter("tok", transport=fake)
    cfg = Config(telegram_token="tok", allowed_user_id=42)
    db = Database(":memory:")

    for update_cru in adapter.receber():
        upd = _normalizar(update_cru)
        assert upd is not None
        processar_update(upd, cfg, db, adapter, agora=datetime(2026, 6, 16, 21, 0))

    # Uma resposta saiu (sendMessage), a atividade foi gravada, o offset avançou.
    assert len(fake.enviados) == 1
    assert b"sendMessage" in fake.enviados[0][0].encode()
    n = db.connection.execute("SELECT COUNT(*) AS n FROM activities").fetchone()["n"]
    assert n == 1
    assert adapter._offset == 6


def test_loop_ignora_estranho_fim_a_fim():
    payload = {
        "result": [
            {
                "update_id": 9,
                "message": {"chat": {"id": 7}, "from": {"id": 7}, "text": "oi"},
            }
        ]
    }
    fake = _FakeTransport(payload)
    adapter = TelegramAdapter("tok", transport=fake)
    cfg = Config(telegram_token="tok", allowed_user_id=42)
    db = Database(":memory:")

    for update_cru in adapter.receber():
        upd = _normalizar(update_cru)
        processar_update(upd, cfg, db, adapter, agora=datetime(2026, 6, 16, 21, 0))

    assert fake.enviados == []  # estranho não recebe resposta
    n = db.connection.execute("SELECT COUNT(*) AS n FROM activities").fetchone()["n"]
    assert n == 0
