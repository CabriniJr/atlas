"""Deletar uma Traducao apaga os artefatos gerados (efêmero), preserva a origem."""

from __future__ import annotations

from atlas.api import _limpar_artefatos
from atlas.core.resource import Resource
from atlas.rotinas.traduzir_pdf import _cache_para


def test_limpar_artefatos_remove_saida_e_cache_preserva_origem(tmp_path):
    origem = tmp_path / "doc.pdf"
    origem.write_bytes(b"%PDF-1.4 origem")
    saida = tmp_path / "doc.pt-BR.pdf"
    saida.write_bytes(b"%PDF-1.4 saida")
    cache = tmp_path / _cache_para("doc.pdf", "pt-BR")  # doc.pt-BR.cache.json
    cache = tmp_path / cache.name
    cache.write_text("{}")

    res = Resource(
        kind="Traducao",
        name="doc",
        spec={"origem": str(origem), "idioma_destino": "pt-BR"},
        status={"saida": str(saida)},
    )

    _limpar_artefatos(res)

    assert not saida.exists(), "PDF de saída deveria ter sido removido"
    assert not cache.exists(), "cache de tradução deveria ter sido removido"
    assert origem.exists(), "PDF de origem (do usuário) deve ser preservado"


def test_limpar_artefatos_ignora_kind_nao_traducao(tmp_path):
    f = tmp_path / "x.pdf"
    f.write_bytes(b"%PDF-")
    res = Resource(kind="Job", name="j", status={"saida": str(f)})
    _limpar_artefatos(res)
    assert f.exists(), "só Traducao limpa artefatos"
