"""Adapter do Telegram via long-poll (stdlib urllib, zero dependências).

Implementa só ``enviar`` e ``receber`` — o canal é plugável (P6). Não precisa de
domínio, IP público nem webhook: o notebook puxa as mensagens de dentro pra fora.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable

_log = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/{metodo}"


def montar_multipart(
    campos: dict[str, str], campo_arquivo: str, nome: str, conteudo: bytes, mime: str
) -> tuple[str, bytes]:
    """Monta um corpo ``multipart/form-data`` (para ``sendDocument``). Devolve
    ``(content_type, corpo)``. Função pura — testável sem rede."""
    boundary = "----atlas" + uuid.uuid4().hex
    linhas: list[bytes] = []
    for k, v in campos.items():
        linhas += [
            f"--{boundary}".encode(),
            f'Content-Disposition: form-data; name="{k}"'.encode(),
            b"",
            str(v).encode("utf-8"),
        ]
    linhas += [
        f"--{boundary}".encode(),
        (
            f'Content-Disposition: form-data; name="{campo_arquivo}"; filename="{nome}"'
        ).encode(),
        f"Content-Type: {mime}".encode(),
        b"",
    ]
    corpo = b"\r\n".join(linhas) + b"\r\n" + conteudo + f"\r\n--{boundary}--\r\n".encode()
    return f"multipart/form-data; boundary={boundary}", corpo


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
        """Envia uma mensagem em **texto puro**.

        Sem ``parse_mode``: assim caracteres como ``_``, ``*`` e ``<id>`` (comuns
        nas nossas respostas e nomes de comando) não quebram a formatação e a
        mensagem nunca é rejeitada (HTTP 400) pela API.
        """
        dados = urllib.parse.urlencode({"chat_id": chat_id, "text": texto}).encode("utf-8")
        resposta = self._transport(self._url("sendMessage"), dados)
        if isinstance(resposta, dict) and resposta.get("ok") is False:
            _log.warning("Telegram recusou sendMessage: %s", resposta.get("description"))

    def enviar_documento(self, chat_id: int, caminho: str, legenda: str = "") -> None:
        """Envia um arquivo (``sendDocument``) via multipart. Best-effort — loga e
        segue se a API recusar/o arquivo sumir (ADR-0006). Usa ``urllib`` direto
        (o ``transport`` injetável só serve p/ url-encoded/JSON, não multipart)."""
        try:
            with open(caminho, "rb") as fh:
                conteudo = fh.read()
        except OSError as exc:
            _log.warning("enviar_documento: não li %s: %s", caminho, exc)
            return
        nome = os.path.basename(caminho)
        mime = "application/pdf" if nome.lower().endswith(".pdf") else "application/octet-stream"
        campos = {"chat_id": str(chat_id)}
        if legenda:
            campos["caption"] = legenda[:1024]
        ct, corpo = montar_multipart(campos, "document", nome, conteudo, mime)
        try:
            req = urllib.request.Request(
                self._url("sendDocument"), data=corpo, headers={"Content-Type": ct}
            )
            urllib.request.urlopen(req, timeout=300).read()  # noqa: S310 (host fixo da API)
        except Exception as exc:  # noqa: BLE001 — best-effort
            _log.warning("Telegram recusou sendDocument (%s): %s", nome, exc)

    def limpar_webhook(self) -> None:
        """Remove qualquer webhook registrado para liberar o long-poll (evita HTTP 409)."""
        try:
            self._transport(self._url("deleteWebhook"), b"drop_pending_updates=true")
            _log.info("Webhook removido; long-poll liberado.")
        except Exception:  # noqa: BLE001
            _log.warning("Não foi possível remover o webhook (segue mesmo assim).")

    def baixar_arquivo(self, file_id: str) -> bytes:
        """Baixa os bytes de um anexo (``document``) do Telegram (ADR-0049).

        Dois passos: ``getFile`` devolve o ``file_path``; o conteúdo vem de
        ``/file/bot<token>/<file_path>`` como bytes crus (não JSON). Usa
        ``urllib`` direto — o ``transport`` injetável do adapter devolve dict e
        não serve para binário.
        """
        meta = self._transport(self._url("getFile") + f"?file_id={file_id}", None)
        if not isinstance(meta, dict) or not meta.get("ok"):
            raise RuntimeError(f"getFile falhou: {meta}")
        file_path = meta["result"]["file_path"]
        url = f"https://api.telegram.org/file/bot{self._token}/{file_path}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 (host fixo da API)
            return resp.read()

    def registrar_comandos(self, comandos: list[dict[str, str]]) -> None:
        """Registra o menu de comandos do bot (``setMyCommands``)."""
        dados = urllib.parse.urlencode({"commands": json.dumps(comandos)}).encode("utf-8")
        self._transport(self._url("setMyCommands"), dados)

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
