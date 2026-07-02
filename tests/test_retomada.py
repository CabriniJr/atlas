"""Job pausável/reagendável por escassez — capacidade genérica do núcleo (ADR-0035)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from atlas.retomada import campos_pausa, retomar_pausados

AGORA = datetime(2026, 7, 1, 12, 0, 0)


@dataclass
class FakeRes:
    name: str
    status: dict = field(default_factory=dict)


class FakeStore:
    """Store mínimo Kind-agnóstico para exercitar o scanner de retomada."""

    def __init__(self, por_kind: dict[str, list[FakeRes]]):
        self._por_kind = por_kind

    def kinds(self):
        return list(self._por_kind)

    def list(self, kind):
        return list(self._por_kind.get(kind, []))

    def set_status(self, kind, name, status, agora):
        for r in self._por_kind.get(kind, []):
            if r.name == name:
                r.status = status


def test_campos_pausa_marca_fase_e_agenda_futuro():
    campos = campos_pausa(AGORA, 18000, "traduzir-pdf")
    assert campos["fase"] == "pausado"
    assert campos["retoma_collect"] == "traduzir-pdf"
    assert datetime.fromisoformat(campos["retoma_em"]) == AGORA + timedelta(seconds=18000)


def test_retoma_apenas_os_vencidos():
    vencido = FakeRes("obs", {
        "fase": "pausado",
        "retoma_em": (AGORA - timedelta(minutes=1)).isoformat(),
        "retoma_collect": "traduzir-pdf",
    })
    futuro = FakeRes("livro2", {
        "fase": "pausado",
        "retoma_em": (AGORA + timedelta(hours=3)).isoformat(),
        "retoma_collect": "traduzir-pdf",
    })
    rodando = FakeRes("livro3", {"fase": "traduzindo"})
    store = FakeStore({"Traducao": [vencido, futuro, rodando]})

    chamados = []
    retomados = retomar_pausados(store, AGORA, lambda k, n, c: chamados.append((k, n, c)))

    assert retomados == ["obs"]
    assert chamados == [("Traducao", "obs", "traduzir-pdf")]
    # marcador limpo p/ não redisparar no próximo tick
    assert vencido.status["fase"] == "retomando"
    assert vencido.status["retoma_em"] is None
    # os demais intactos
    assert futuro.status["fase"] == "pausado"


def test_pausado_sem_collect_e_ignorado():
    ruim = FakeRes("x", {"fase": "pausado",
                         "retoma_em": (AGORA - timedelta(minutes=1)).isoformat()})
    store = FakeStore({"K": [ruim]})
    chamados = []
    retomados = retomar_pausados(store, AGORA, lambda k, n, c: chamados.append(n))
    assert retomados == [] and chamados == []


def test_erro_de_disparo_nao_trava_os_demais():
    a = FakeRes("a", {"fase": "pausado", "retoma_em": (AGORA - timedelta(minutes=1)).isoformat(),
                      "retoma_collect": "c"})
    b = FakeRes("b", {"fase": "pausado", "retoma_em": (AGORA - timedelta(minutes=1)).isoformat(),
                      "retoma_collect": "c"})
    store = FakeStore({"K": [a, b]})

    def disparar(k, n, c):
        if n == "a":
            raise RuntimeError("boom")

    retomados = retomar_pausados(store, AGORA, disparar)
    assert "b" in retomados  # 'a' falhou, 'b' seguiu
