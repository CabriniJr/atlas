"""Verificação de integridade por magic header (ADR-0049)."""

from __future__ import annotations

from atlas.torrent import integridade


def _escreve(p, nome, dados: bytes):
    f = p / nome
    f.write_bytes(dados)
    return str(f)


def test_nsz_valido_pfs0_ok(tmp_path):
    c = _escreve(tmp_path, "jogo.nsz", b"PFS0" + b"\x00" * 100)
    ok, _ = integridade.verificar_arquivo(c)
    assert ok is True


def test_nsz_corrompido_sem_pfs0_falha(tmp_path):
    c = _escreve(tmp_path, "jogo.nsz", b"LIXO" + b"\x00" * 100)
    ok, det = integridade.verificar_arquivo(c)
    assert ok is False
    assert "PFS0" in det


def test_nsp_valido(tmp_path):
    c = _escreve(tmp_path, "app.nsp", b"PFS0rest")
    assert integridade.verificar_arquivo(c)[0] is True


def test_xci_head_no_offset(tmp_path):
    dados = bytearray(0x200)
    dados[0x100:0x104] = b"HEAD"
    c = _escreve(tmp_path, "cart.xci", bytes(dados))
    assert integridade.verificar_arquivo(c)[0] is True


def test_tipo_desconhecido_pulado(tmp_path):
    c = _escreve(tmp_path, "leiame.qualquer", b"seja o que for")
    ok, _ = integridade.verificar_arquivo(c)
    assert ok is None


def test_pdf_e_zip(tmp_path):
    assert integridade.verificar_arquivo(_escreve(tmp_path, "a.pdf", b"%PDF-1.7"))[0] is True
    assert integridade.verificar_arquivo(_escreve(tmp_path, "a.zip", b"PK\x03\x04xx"))[0] is True


def test_verificar_pasta_mistura(tmp_path):
    _escreve(tmp_path, "bom.nsz", b"PFS0aaa")
    _escreve(tmp_path, "ruim.nsz", b"XXXXaaa")
    _escreve(tmp_path, "nota.txt.desconhecido", b"oi")  # pulado
    r = integridade.verificar(str(tmp_path))
    assert r.ok is False
    assert r.verificados == 2  # os dois .nsz
    assert any("ruim.nsz" in f for f in r.falhas)
    assert "invalid pfs0" in r.humano().lower()


def test_verificar_pasta_tudo_ok(tmp_path):
    _escreve(tmp_path, "a.nsz", b"PFS0")
    _escreve(tmp_path, "b.nsp", b"PFS0")
    r = integridade.verificar(str(tmp_path))
    assert r.ok is True and r.verificados == 2
    assert "ok" in r.humano().lower()


def test_ignora_parciais_qb(tmp_path):
    _escreve(tmp_path, "grande.nsz.!qB", b"XXXX")  # parcial → ignorado
    _escreve(tmp_path, "pronto.nsz", b"PFS0")
    r = integridade.verificar(str(tmp_path))
    assert r.ok is True and r.verificados == 1
