"""Adapter do Telegram via long-poll (stdlib urllib, zero dependências).

Implementa só ``enviar`` e ``receber`` — o canal é plugável (P6). Não precisa de
domínio, IP público nem webhook: o notebook puxa as mensagens de dentro pra fora.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Callable

_API = "https://api.telegram.org/bot{token}/{metodo}"

# Transport injetável (para teste). Recebe (url, dados_post|None) e devolve dict.
Transport = Callable[[str, bytes | None], dict]


def _http(url: str, dados: bytes | None) -> dict:
    req = urllib.request.Request(url, data=dados)
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (URL fixa da API)
        return json.loads(resp.read().decode("utf-8"))


class TelegramAdapter:
    """Cliente mínimo da Bot API do Telegram."""

    def __init__(self, token: str, poll_timeout: int = 30, transport: Transport = _http) -> None:
        self._token = token
        self._poll_timeout = poll_timeout
        self._transport = transport
        self._offset = 0

    def _url(self, metodo: str) -> str:
        return _API.format(token=self._token, metodo=metodo)

    def enviar(self, chat_id: int, texto: str) -> None:
        """Envia uma mensagem (Markdown)."""
        dados = urllib.parse.urlencode(
            {"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"}
        ).encode("utf-8")
        self._transport(self._url("sendMessage"), dados)

    def receber(self) -> list[dict]:
        """Long-poll de novas mensagens. Devolve a lista crua de updates."""
        url = (
            self._url("getUpdates")
            + "?"
            + urllib.parse.urlencode({"timeout": self._poll_timeout, "offset": self._offset})
        )
        resposta = self._transport(url, None)
        updates = resposta.get("result", [])
        if updates:
            self._offset = updates[-1]["update_id"] + 1
        return updates
