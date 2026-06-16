"""Wiring do bot Atlas: long-poll → filtro de dono → handler → resposta.

Loop de operação (Camada 0). A análise (IA) entra nas rotinas agendadas; o MVP
foca no registro rápido e em /status.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from atlas.config import Config
from atlas.db import Database
from atlas.handler import responder
from atlas.telegram import TelegramAdapter

_log = logging.getLogger("atlas")


@dataclass
class Update:
    """Mensagem normalizada vinda do canal."""

    update_id: int
    chat_id: int
    user_id: int
    texto: str


class Adapter(Protocol):
    def enviar(self, chat_id: int, texto: str) -> None: ...


def processar_update(
    upd: Update,
    config: Config,
    db: Database,
    adapter: Adapter,
    agora: datetime | None = None,
) -> None:
    """Atende um update. Só o dono é respondido (seguranca.md)."""
    if upd.user_id != config.allowed_user_id:
        _log.warning("Mensagem ignorada de user_id=%s (não é o dono)", upd.user_id)
        return
    if not upd.texto:
        return
    resposta = responder(upd.texto, db, agora or datetime.now())
    adapter.enviar(upd.chat_id, resposta)


def _normalizar(update_cru: dict) -> Update | None:
    msg = update_cru.get("message") or update_cru.get("edited_message")
    if not msg or "text" not in msg:
        return None
    return Update(
        update_id=update_cru["update_id"],
        chat_id=msg["chat"]["id"],
        user_id=msg["from"]["id"],
        texto=msg["text"],
    )


def run(config: Config | None = None) -> None:
    """Inicia o loop de operação do bot (bloqueante)."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = config or Config.from_env()
    db = Database(config.db_path)
    adapter = TelegramAdapter(config.telegram_token, poll_timeout=config.poll_timeout)

    _log.info("Atlas no ar. Atendendo apenas user_id=%s. Ctrl+C para sair.", config.allowed_user_id)
    while True:
        try:
            for update_cru in adapter.receber():
                upd = _normalizar(update_cru)
                if upd is not None:
                    processar_update(upd, config, db, adapter)
        except KeyboardInterrupt:  # noqa: PERF203
            _log.info("Encerrando.")
            break
        except Exception:  # noqa: BLE001 — resiliência: um erro não derruba o loop
            _log.exception("Erro no loop; seguindo.")
