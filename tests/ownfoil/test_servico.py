"""Serviço/supervisor do Kind ``Ownfoil`` (ADR-0052) — estado no recurso."""

from __future__ import annotations

from datetime import datetime

from atlas.core.store import ResourceStore
from atlas.ownfoil import servico


class ClienteFake:
    def __init__(self, no_ar=True, jogos=3, rodando=True):
        self._no_ar = no_ar
        self._jogos = jogos
        self._rodando = rodando
        self.garantiu = 0

    def garantir_no_ar(self):
        self.garantiu += 1
        return self._no_ar

    def status(self):
        return {
            "rodando": self._rodando,
            "porta": 8465,
            "jogos": self._jogos,
            "acervo": "/games",
            "imagem": "img",
        }


def _store():
    return ResourceStore(":memory:")


def test_sincronizar_cria_recurso_singleton_com_status():
    store = _store()
    cli = ClienteFake(jogos=5)
    res = servico.sincronizar(store, cli, datetime(2026, 7, 14, 12, 0, 0))
    assert res.kind == servico.KIND and res.name == servico.NOME
    assert res.status["rodando"] is True
    assert res.status["jogos"] == 5
    assert res.status["ultimo_check"] == "2026-07-14T12:00:00"
    # persistiu no store
    lido = store.get(servico.KIND, servico.NOME)
    assert lido is not None and lido.status["jogos"] == 5


def test_sincronizar_idempotente_atualiza_o_mesmo_recurso():
    store = _store()
    cli = ClienteFake(jogos=1)
    servico.sincronizar(store, cli, datetime(2026, 7, 14, 12, 0, 0))
    cli._jogos = 9
    servico.sincronizar(store, cli, datetime(2026, 7, 14, 13, 0, 0))
    assert len(store.list(servico.KIND)) == 1
    assert store.get(servico.KIND, servico.NOME).status["jogos"] == 9


def test_garantir_sobe_o_container_e_reflete_no_status():
    store = _store()
    cli = ClienteFake(no_ar=True, rodando=True, jogos=2)
    res = servico.garantir(store, cli, datetime(2026, 7, 14, 12, 0, 0))
    assert cli.garantiu == 1
    assert res.status["rodando"] is True
    assert res.status["jogos"] == 2


def test_garantir_marca_erro_quando_container_nao_sobe():
    store = _store()
    cli = ClienteFake(no_ar=False, rodando=False)
    res = servico.garantir(store, cli, datetime(2026, 7, 14, 12, 0, 0))
    assert res.status["rodando"] is False
    assert res.status.get("erro") is not None


def test_resumo_humano_para_status_e_telegram():
    store = _store()
    cli = ClienteFake(jogos=7)
    servico.sincronizar(store, cli, datetime(2026, 7, 14, 12, 0, 0))
    txt = servico.resumo(store)
    assert "7" in txt
    assert "no ar" in txt.lower() or "🟢" in txt


def test_resumo_sem_recurso_ainda():
    txt = servico.resumo(_store())
    assert isinstance(txt, str) and len(txt) > 0
