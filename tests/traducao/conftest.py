"""Fixtures: gera PDFs mínimos com fitz para testar o motor de tradução."""

from __future__ import annotations

import fitz
import pytest


@pytest.fixture
def pdf_simples(tmp_path):
    """1 página, 1 bloco de texto normal + 1 bloco monospace (código)."""
    path = tmp_path / "simples.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "The deployment scales the pod.", fontname="helv", fontsize=12)
    page.insert_text((72, 200), "kubectl get pods", fontname="cour", fontsize=12)  # monospace
    doc.save(path)
    doc.close()
    return str(path)
