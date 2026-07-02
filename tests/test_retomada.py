"""Job pausável/reagendável por escassez — capacidade genérica do núcleo (ADR-0035)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from atlas.retomada import campos_pausa, recuperar_orfaos_no_boot, retomar_pausados

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
    vencido = FakeRes(
        "obs",
        {
            "fase": "pausado",
            "retoma_em": (AGORA - timedelta(minutes=1)).isoformat(),
            "retoma_collect": "traduzir-pdf",
        },
    )
    futuro = FakeRes(
        "livro2",
        {
            "fase": "pausado",
            "retoma_em": (AGORA + timedelta(hours=3)).isoformat(),
            "retoma_collect": "traduzir-pdf",
        },
    )
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
    ruim = FakeRes(
        "x", {"fase": "pausado", "retoma_em": (AGORA - timedelta(minutes=1)).isoformat()}
    )
    store = FakeStore({"K": [ruim]})
    chamados = []
    retomados = retomar_pausados(store, AGORA, lambda k, n, c: chamados.append(n))
    assert retomados == [] and chamados == []


# ── Recuperação de órfãos no boot (ADR-0043) ─────────────────────────────────


def test_recuperar_orfaos_reseta_traduzindo_para_pausado_com_retomada_imediata():
    orfao = FakeRes("obs", {"fase": "traduzindo", "progresso_pct": 45})
    store = FakeStore({"Traducao": [orfao]})

    recuperados = recuperar_orfaos_no_boot(store, AGORA)

    assert recuperados == ["Traducao/obs"]
    assert orfao.status["fase"] == "pausado"
    assert orfao.status["retoma_collect"] == "traduzir-pdf"
    assert datetime.fromisoformat(orfao.status["retoma_em"]) <= AGORA + timedelta(seconds=2)
    assert orfao.status["progresso_pct"] == 45  # preserva o resto do status


def test_recuperar_orfaos_pega_fila_e_retomando_tambem():
    fila = FakeRes("a", {"fase": "fila"})
    retomando = FakeRes("b", {"fase": "retomando"})
    store = FakeStore({"Traducao": [fila, retomando]})

    recuperados = recuperar_orfaos_no_boot(store, AGORA)

    assert set(recuperados) == {"Traducao/a", "Traducao/b"}
    assert fila.status["fase"] == "pausado"
    assert retomando.status["fase"] == "pausado"


def test_recuperar_orfaos_nao_mexe_em_pronto_ou_ja_pausado():
    pronto = FakeRes("p", {"fase": "pronto"})
    pausado = FakeRes(
        "q",
        {"fase": "pausado", "retoma_em": "2026-08-01T00:00:00", "retoma_collect": "traduzir-pdf"},
    )
    store = FakeStore({"Traducao": [pronto, pausado]})

    recuperados = recuperar_orfaos_no_boot(store, AGORA)

    assert recuperados == []
    assert pronto.status["fase"] == "pronto"
    assert pausado.status["retoma_em"] == "2026-08-01T00:00:00"  # não antecipa um pausado legítimo


def test_recuperar_orfaos_ignora_outros_kinds():
    store = FakeStore({"Job": [FakeRes("j", {"fase": "traduzindo"})]})
    assert recuperar_orfaos_no_boot(store, AGORA) == []


def test_erro_de_disparo_nao_trava_os_demais():
    a = FakeRes(
        "a",
        {
            "fase": "pausado",
            "retoma_em": (AGORA - timedelta(minutes=1)).isoformat(),
            "retoma_collect": "c",
        },
    )
    b = FakeRes(
        "b",
        {
            "fase": "pausado",
            "retoma_em": (AGORA - timedelta(minutes=1)).isoformat(),
            "retoma_collect": "c",
        },
    )
    store = FakeStore({"K": [a, b]})

    def disparar(k, n, c):
        if n == "a":
            raise RuntimeError("boom")

    retomados = retomar_pausados(store, AGORA, disparar)
    assert "b" in retomados  # 'a' falhou, 'b' seguiu
