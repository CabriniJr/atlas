"""Recebimento de PDF pelo Telegram → Kind Traducao (ADR-0050)."""

from __future__ import annotations

from datetime import datetime

from atlas import traducao_cmd
from atlas.core.store import ResourceStore


def _store():
    return ResourceStore(":memory:")


def test_e_pdf_por_extensao_ou_magic():
    assert traducao_cmd.e_pdf("livro.pdf", b"qualquer")
    assert traducao_cmd.e_pdf("semext", b"%PDF-1.7")
    assert not traducao_cmd.e_pdf("jogo.torrent", b"d8:announce")


def test_receber_pdf_cria_traducao(tmp_path):
    store = _store()
    res, msg = traducao_cmd.receber_pdf(
        store, b"%PDF-1.7 conteudo", "Meu Livro.pdf", 42, datetime.now(),
        dir_pdfs=str(tmp_path),
    )
    assert res is not None
    assert res.name == "Meu_Livro"
    assert res.spec["origem"].endswith("Meu_Livro.pdf")
    assert res.labels["interface"] == "telegram"
    assert res.status["origem_chat"] == 42
    assert "recebido" in msg
    assert store.get("Traducao", "Meu_Livro") is not None


def test_receber_pdf_rejeita_nao_pdf(tmp_path):
    store = _store()
    res, msg = traducao_cmd.receber_pdf(
        store, b"NAODEPDF", "x.pdf", 1, datetime.now(), dir_pdfs=str(tmp_path)
    )
    assert res is None and "não parece um PDF" in msg


def test_reenvio_preserva_spec_e_reusa(tmp_path):
    store = _store()
    traducao_cmd.receber_pdf(
        store, b"%PDF-1 a", "Livro.pdf", 1, datetime.now(), dir_pdfs=str(tmp_path)
    )
    store.patch("Traducao", "Livro", {"assunto": "Kubernetes"}, datetime.now())
    res, _ = traducao_cmd.receber_pdf(
        store, b"%PDF-1 b", "Livro.pdf", 1, datetime.now(), dir_pdfs=str(tmp_path)
    )
    assert res.spec.get("assunto") == "Kubernetes"  # preservou o spec anterior
