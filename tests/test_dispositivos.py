"""TDD — auth por dispositivo (tailnet) com pareamento via Telegram (ADR-0054)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from atlas import dispositivos as dv
from atlas.core.store import ResourceStore


@pytest.fixture
def store():
    return ResourceStore(":memory:")


@pytest.fixture
def reg(store):
    return dv.RegistroDispositivos(store, ttl_pareamento_s=300, max_dispositivos=3)


# ── range da tailnet ─────────────────────────────────────────────────────────


def test_ip_tailnet_reconhece_v4_v6_e_rejeita_lan_e_loopback():
    assert dv.ip_tailnet("100.79.40.56") is True          # CGNAT tailscale
    assert dv.ip_tailnet("fd7a:115c:a1e0::af01:ada1") is True  # ULA tailscale
    assert dv.ip_tailnet("192.168.0.10") is False         # LAN
    assert dv.ip_tailnet("127.0.0.1") is False            # loopback
    assert dv.ip_tailnet("8.8.8.8") is False              # internet
    assert dv.ip_tailnet("::ffff:100.79.40.56") is True   # v4-mapped normaliza
    assert dv.ip_tailnet("lixo") is False


# ── pareamento ───────────────────────────────────────────────────────────────


def test_gerar_codigo_e_confirmar_registra_o_ip(reg, store):
    agora = datetime(2026, 7, 14, 12, 0, 0)
    cod = reg.gerar_codigo("100.90.5.104", agora)
    assert cod.isdigit() and len(cod) == 6
    assert reg.autorizado("100.90.5.104") is False  # ainda não confirmado
    d = reg.confirmar(cod, agora, nome="Celular")
    assert d is not None and d.kind == dv.KIND
    assert reg.autorizado("100.90.5.104") is True
    assert store.get(dv.KIND, d.name).spec["nome"] == "Celular"


def test_codigo_invalido_ou_expirado_nao_registra(reg):
    agora = datetime(2026, 7, 14, 12, 0, 0)
    assert reg.confirmar("000000", agora) is None  # nunca gerado
    cod = reg.gerar_codigo("100.0.0.9", agora)
    tarde = agora + timedelta(seconds=301)  # passou o TTL
    assert reg.confirmar(cod, tarde) is None
    assert reg.autorizado("100.0.0.9") is False


def test_codigo_e_de_uso_unico(reg):
    agora = datetime(2026, 7, 14, 12, 0, 0)
    cod = reg.gerar_codigo("100.0.0.9", agora)
    assert reg.confirmar(cod, agora) is not None
    assert reg.confirmar(cod, agora) is None  # não dá pra reusar


def test_limite_de_tres_dispositivos(reg):
    agora = datetime(2026, 7, 14, 12, 0, 0)
    for i in range(3):
        cod = reg.gerar_codigo(f"100.0.0.{i}", agora)
        assert reg.confirmar(cod, agora) is not None
    cod4 = reg.gerar_codigo("100.0.0.99", agora)
    with pytest.raises(dv.LimiteDispositivos):
        reg.confirmar(cod4, agora)
    assert reg.autorizado("100.0.0.99") is False


def test_reparear_ip_ja_registrado_e_idempotente_nao_conta_no_limite(reg):
    agora = datetime(2026, 7, 14, 12, 0, 0)
    for i in range(3):
        reg.confirmar(reg.gerar_codigo(f"100.0.0.{i}", agora), agora)
    # re-parear um IP JÁ registrado não estoura o limite (atualiza)
    cod = reg.gerar_codigo("100.0.0.0", agora)
    d = reg.confirmar(cod, agora, nome="Renomeado")
    assert d is not None
    assert len(reg.listar()) == 3
    assert reg.autorizado("100.0.0.0") is True


def test_revogar_remove_o_dispositivo(reg):
    agora = datetime(2026, 7, 14, 12, 0, 0)
    reg.confirmar(reg.gerar_codigo("100.0.0.1", agora), agora, nome="PC")
    assert reg.revogar("100.0.0.1", agora) is True
    assert reg.autorizado("100.0.0.1") is False
    assert reg.revogar("100.0.0.1", agora) is False  # já não existe


def test_autorizado_normaliza_v4_mapeada(reg):
    agora = datetime(2026, 7, 14, 12, 0, 0)
    reg.confirmar(reg.gerar_codigo("100.90.5.104", agora), agora)
    assert reg.autorizado("::ffff:100.90.5.104") is True


# ── comandos do Telegram ─────────────────────────────────────────────────────


@pytest.fixture
def com_registro(store, monkeypatch):
    r = dv.init_registro(store)
    yield r
    monkeypatch.setattr(dv, "_REGISTRO", None, raising=False)


def test_comando_autorizar_confirma_pareamento(com_registro):
    agora = datetime(2026, 7, 14, 12, 0, 0)
    cod = com_registro.gerar_codigo("100.90.5.104", agora)
    out = dv.responder_comando(f"/autorizar {cod} Celular", agora)
    assert out is not None and "autorizado" in out.lower()
    assert com_registro.autorizado("100.90.5.104") is True


def test_comando_autorizar_codigo_ruim(com_registro):
    agora = datetime(2026, 7, 14, 12, 0, 0)
    out = dv.responder_comando("/autorizar 000000", agora)
    assert out is not None and ("inválido" in out.lower() or "expirou" in out.lower())


def test_comando_autorizar_no_limite_avisa(com_registro):
    agora = datetime(2026, 7, 14, 12, 0, 0)
    for i in range(3):
        com_registro.confirmar(com_registro.gerar_codigo(f"100.0.0.{i}", agora), agora)
    cod = com_registro.gerar_codigo("100.0.0.9", agora)
    out = dv.responder_comando(f"/autorizar {cod}", agora)
    assert out is not None and "limite" in out.lower()


def test_comando_lista_e_revoga(com_registro):
    agora = datetime(2026, 7, 14, 12, 0, 0)
    com_registro.confirmar(com_registro.gerar_codigo("100.0.0.1", agora), agora, nome="PC")
    lista = dv.responder_comando("/dispositivos", agora)
    assert "PC" in lista and "100.0.0.1" in lista
    rev = dv.responder_comando("/revogar 100.0.0.1", agora)
    assert "revogado" in rev.lower()
    assert com_registro.autorizado("100.0.0.1") is False


def test_comando_ignora_texto_alheio(com_registro):
    assert dv.responder_comando("/help", datetime.now()) is None
    assert dv.responder_comando("oi tudo bem", datetime.now()) is None
