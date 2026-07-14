"""Monitor único do client em container (ADR-0051): tick atualiza recursos,
conclui e auto-envia. Sem podman nem imagem."""

from __future__ import annotations

from datetime import datetime

import pytest

from atlas.core.store import ResourceStore
from atlas.torrent import monitor, servico
from atlas.torrent.download import Progresso


@pytest.fixture
def store():
    return ResourceStore(":memory:")


def _criar_baixando(store, *, infohash="abc", nome="pasta", chat=1, destino):
    res = servico.Resource(
        kind=servico.KIND,
        name=infohash,
        labels={"dominio": "geral"},
        spec={
            "infohash": infohash,
            "nome": nome,
            "destino": destino,
            "origem_chat": chat,
            "total_bytes": 0,
        },
        status={"fase": servico.BAIXANDO, "criado_em": "2026-07-14T00:00:00"},
    )
    store.apply(res, datetime.now())
    return res


class ClienteFake:
    def __init__(self, progressos: dict[str, Progresso]):
        self._p = progressos
        self.parados: list[str] = []
        self.removidos: list[str] = []

    def listar(self):
        return [{"hash": h} for h in self._p]

    def progresso_de(self, infohash, arr=None):
        return self._p.get(infohash.lower())

    def parar_p2p(self, infohash):
        self.parados.append(infohash)

    def remover(self, infohash, apagar_dados=False):
        self.removidos.append(infohash)


def test_tick_atualiza_progresso_e_dispara_marco(store, tmp_path):
    _criar_baixando(store, infohash="abc", destino=str(tmp_path))
    cli = ClienteFake({"abc": Progresso(pct=55, velocidade="2.0 MB/s", seeds=4,
                                        estado="downloading")})
    notes: list[tuple[int, str]] = []
    monitor.tick(store, cli, notificar=lambda c, m: notes.append((c, m)))
    s = store.get(servico.KIND, "abc").status
    assert s["progresso_pct"] == 55.0
    assert s["seeds"] == 4 and s["fase"] == servico.BAIXANDO
    # marcos 10 e 50 cruzados → notifica o maior uma vez
    assert notes and "50%" in notes[-1][1]
    assert s["marcos_notificados"] == [10, 50]
    # segundo tick no mesmo % não repete o marco
    notes.clear()
    monitor.tick(store, cli, notificar=lambda c, m: notes.append((c, m)))
    assert notes == []


def test_tick_deriva_fila_de_queueddl(store, tmp_path):
    _criar_baixando(store, infohash="abc", destino=str(tmp_path))
    cli = ClienteFake({"abc": Progresso(pct=0, estado="queuedDL")})
    monitor.tick(store, cli)
    assert store.get(servico.KIND, "abc").status["fase"] == servico.FILA


def test_tick_nao_conclui_em_moving(store, tmp_path):
    _criar_baixando(store, infohash="abc", destino=str(tmp_path))
    cli = ClienteFake({"abc": Progresso(pct=100, estado="moving", concluido=False)})
    monitor.tick(store, cli)
    assert store.get(servico.KIND, "abc").status["fase"] == servico.BAIXANDO
    assert cli.removidos == []


def test_tick_conclui_roda_integridade_envia_e_remove(store, tmp_path):
    destino = tmp_path / "dl"
    destino.mkdir()
    (destino / "pasta").mkdir()
    (destino / "pasta" / "f.bin").write_bytes(b"x" * 10)
    _criar_baixando(store, infohash="abc", nome="pasta", destino=str(destino))
    cli = ClienteFake({"abc": Progresso(pct=100, estado="pausedUP", concluido=True)})
    enviados: list[tuple[int, str, str]] = []
    notes: list[tuple[int, str]] = []
    monitor.tick(
        store, cli,
        notificar=lambda c, m: notes.append((c, m)),
        enviar=lambda c, cam, nome: enviados.append((c, cam, nome)),
    )
    s = store.get(servico.KIND, "abc").status
    assert s["fase"] == servico.CONCLUIDO and s["progresso_pct"] == 100.0
    assert "integridade" in s
    # parou o p2p, removeu do client (dados ficam), auto-enviou o caminho do alvo
    assert cli.parados == ["abc"] and cli.removidos == ["abc"]
    assert enviados and enviados[-1][1] == str(destino / "pasta")
    assert any("baixado" in m for _c, m in notes)


def test_tick_ignora_torrent_ainda_desconhecido_pelo_client(store, tmp_path):
    _criar_baixando(store, infohash="abc", destino=str(tmp_path))
    cli = ClienteFake({})  # client ainda não conhece 'abc'
    monitor.tick(store, cli)  # não levanta, não muda fase
    assert store.get(servico.KIND, "abc").status["fase"] == servico.BAIXANDO
