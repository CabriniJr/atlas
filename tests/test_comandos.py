"""Testes do registro de comandos + /ajuda dinâmico + setMyCommands (E5-01)."""

from __future__ import annotations

from datetime import datetime

from atlas.comandos import COMANDOS, para_telegram, texto_ajuda
from atlas.db import Database
from atlas.handler import responder
from atlas.telegram import TelegramAdapter

_AGORA = datetime(2026, 6, 16, 10, 0, 0)


def test_ajuda_lista_comandos_do_pool():
    db = Database(":memory:")
    resposta = responder("/ajuda", db, _AGORA)
    assert "/ideia" in resposta
    assert "/ideias" in resposta
    assert "/status" in resposta


def test_texto_ajuda_cobre_todo_o_registro():
    texto = texto_ajuda()
    for cmd, _ in COMANDOS:
        assert f"/{cmd}" in texto


def test_para_telegram_sem_barra_e_com_descricao():
    payload = para_telegram()
    assert any(c["command"] == "ideia" for c in payload)
    assert all(not c["command"].startswith("/") and c["description"] for c in payload)


def test_registrar_comandos_chama_set_my_commands():
    chamadas: list[tuple[str, bytes | None]] = []

    def fake_transport(url: str, dados: bytes | None) -> dict:
        chamadas.append((url, dados))
        return {"ok": True, "result": True}

    adapter = TelegramAdapter("TOKEN", transport=fake_transport)
    adapter.registrar_comandos(para_telegram())

    assert chamadas, "deveria ter chamado a API"
    url, dados = chamadas[0]
    assert "setMyCommands" in url
    assert dados is not None and b"ideia" in dados
