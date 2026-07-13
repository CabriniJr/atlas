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


def test_incompleto_por_tamanho_falha(tmp_path):
    """Bug real (ADR-0049): um download interrompido no meio do move tem o header
    PFS0 certo (passa no magic) mas está TRUNCADO — o magic sozinho dava ✅. Compara
    o tamanho em disco com o esperado do .torrent: menor = incompleto/corrompido."""
    _escreve(tmp_path, "jogo.nsp", b"PFS0" + b"\x00" * 100)  # 104 bytes
    r = integridade.verificar(str(tmp_path), tamanho_esperado=1000)
    assert r.ok is False
    assert r.incompleto is True
    assert "incompleto" in r.humano().lower()


def test_completo_por_tamanho_ok(tmp_path):
    _escreve(tmp_path, "jogo.nsp", b"PFS0" + b"\x00" * 996)  # 1000 bytes
    r = integridade.verificar(str(tmp_path), tamanho_esperado=1000)
    assert r.ok is True


def test_pasta_vazia_com_esperado_falha(tmp_path):
    """Pasta final vazia (move nunca aconteceu) com tamanho esperado > 0: não pode
    passar como ✅ (o código antigo dava ok=True pra 0 arquivos)."""
    r = integridade.verificar(str(tmp_path), tamanho_esperado=500)
    assert r.ok is False and r.incompleto is True


def test_padding_nao_conta_como_tamanho(tmp_path):
    """Arquivos de padding do libtorrent não entram no total esperado (scan os
    exclui) — nem devem entrar no total em disco."""
    _escreve(tmp_path, "jogo.nsp", b"PFS0" + b"\x00" * 996)  # 1000 bytes reais
    _escreve(tmp_path, "_____padding_file_0", b"\x00" * 500)  # padding: ignorado
    r = integridade.verificar(str(tmp_path), tamanho_esperado=1000)
    assert r.ok is True
