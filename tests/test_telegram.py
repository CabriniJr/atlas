"""Adapter do Telegram — montagem de multipart p/ sendDocument (ADR-0050)."""

from __future__ import annotations

from atlas.telegram import montar_multipart


def test_multipart_tem_boundary_campos_e_arquivo():
    ct, corpo = montar_multipart(
        {"chat_id": "42", "caption": "oi"}, "document", "livro.pdf", b"%PDF-bytes",
        "application/pdf",
    )
    assert ct.startswith("multipart/form-data; boundary=")
    boundary = ct.split("boundary=")[1]
    assert boundary.encode() in corpo
    assert b'name="chat_id"' in corpo and b"42" in corpo
    assert b'name="caption"' in corpo and b"oi" in corpo
    assert b'name="document"; filename="livro.pdf"' in corpo
    assert b"application/pdf" in corpo
    assert b"%PDF-bytes" in corpo
    assert corpo.rstrip().endswith(f"--{boundary}--".encode())
