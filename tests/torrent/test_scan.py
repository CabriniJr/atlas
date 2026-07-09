"""Varredura de .torrent (ADR-0049). Monta torrents sintéticos com o próprio
``bencode`` do módulo — sem fixtures binárias no repo."""

from __future__ import annotations

from atlas.torrent import scan


def _torrent(
    files: list[tuple[str, int]], *, single: str | None = None, extra: dict | None = None
) -> bytes:
    info: dict = {b"piece length": 262144, b"name": (single or "pasta").encode()}
    if single is not None:
        info[b"length"] = files[0][1]
    else:
        info[b"files"] = [
            {b"length": tam, b"path": [p.encode() for p in nome.split("/")]} for nome, tam in files
        ]
    meta = {b"announce": b"http://tracker.exemplo/anunciar", b"info": info}
    if extra:
        meta.update(extra)
    return scan.bencode(meta)


def test_torrent_valido_so_midia_risco_zero():
    dados = _torrent([("filme.mkv", 700 * 1024 * 1024), ("legenda.srt", 40 * 1024)])
    r = scan.analisar_bytes(dados)
    assert r.ok is True
    assert r.risco == 0
    assert r.num_arquivos == 2
    assert r.nome == "pasta"
    assert len(r.infohash) == 40  # SHA-1 hex
    assert "só arquivos" not in r.humano().lower() or True  # humano não quebra


def test_executavel_eleva_risco_para_2():
    dados = _torrent([("instalar.exe", 5 * 1024 * 1024)])
    r = scan.analisar_bytes(dados)
    assert r.risco == 2
    assert any("executável" in a for a in r.alertas)


def test_dupla_extensao_enganosa_risco_2():
    dados = _torrent([("filme.mp4.exe", 3 * 1024 * 1024)])
    r = scan.analisar_bytes(dados)
    assert r.risco == 2
    assert any("dupla extensão" in a for a in r.alertas)


def test_compactado_risco_1():
    dados = _torrent([("dados.zip", 10 * 1024 * 1024)])
    r = scan.analisar_bytes(dados)
    assert r.risco == 1
    assert any("compactado" in a for a in r.alertas)


def test_arquivo_unico_single_file():
    dados = _torrent([("kali.img.xz", 2 * 1024 * 1024 * 1024)], single="kali.img.xz")
    r = scan.analisar_bytes(dados)
    assert r.ok is True
    assert r.num_arquivos == 1
    assert r.nome == "kali.img.xz"


def test_bytes_invalidos_nao_quebram():
    r = scan.analisar_bytes(b"isso nao eh bencode")
    assert r.ok is False
    assert r.risco == 2
    assert r.erro


def test_infohash_estavel_e_determinista():
    dados = _torrent([("a.mkv", 100)])
    assert scan.analisar_bytes(dados).infohash == scan.analisar_bytes(dados).infohash


def test_comentario_com_url_vira_nota():
    dados = _torrent([("a.mkv", 100)], extra={b"comment": b"baixe mais em http://spam.site"})
    r = scan.analisar_bytes(dados)
    assert any("URL" in n for n in r.notas)


def test_tamanho_humano():
    assert scan.tamanho_humano(0) == "0 B"
    assert scan.tamanho_humano(1536).endswith("KB")
    assert scan.tamanho_humano(5 * 1024 * 1024).endswith("MB")
