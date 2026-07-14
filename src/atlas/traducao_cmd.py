"""Camada de recebimento de PDF pelo Telegram → Kind ``Traducao`` (ADR-0050).

Espelha ``torrent_cmd.receber_documento``: valida o PDF, salva em ``data/pdfs/`` e
cria/atualiza o ``Traducao/<label>`` pronto para o collect ``traduzir-pdf`` (motor
default do spec: ollama + refino). O dispatch/auto-envio do resultado vive no
``app.py`` (mesmo padrão do torrent).
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore

DIR_PDFS = "data/pdfs"


def _safe_pdf_name(nome: str) -> str:
    """Basename saneado terminando em .pdf (evita path traversal)."""
    base = os.path.basename((nome or "").strip()) or "upload.pdf"
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    return base


def e_pdf(nome_arquivo: str, dados: bytes) -> bool:
    """``True`` se o anexo é um PDF (por extensão OU magic ``%PDF-``)."""
    return nome_arquivo.lower().endswith(".pdf") or dados[:5] == b"%PDF-"


def receber_pdf(
    store: ResourceStore,
    dados: bytes,
    nome_arquivo: str,
    chat_id: int | None,
    agora: datetime,
    *,
    dir_pdfs: str = DIR_PDFS,
    idioma_destino: str = "pt-BR",
) -> tuple[Resource | None, str]:
    """Salva o PDF e cria/atualiza o ``Traducao``. Devolve ``(recurso|None, msg)``.

    Reenvio do mesmo PDF reusa o cache (o collect re-renderiza barato) — não
    repaga a tradução (ADR-0030/0031)."""
    if dados[:5] != b"%PDF-":
        return None, "❌ isso não parece um PDF (%PDF- ausente)."
    nome = _safe_pdf_name(nome_arquivo)
    Path(dir_pdfs).mkdir(parents=True, exist_ok=True)
    caminho = os.path.join(dir_pdfs, nome)
    with open(caminho, "wb") as f:
        f.write(dados)

    label = os.path.splitext(nome)[0]
    existente = store.get("Traducao", label)
    spec = {
        **(existente.spec if existente else {}),
        "origem": caminho,
        "idioma_destino": idioma_destino,
    }
    labels = {
        **((existente.labels if existente else {}) or {}),
        "interface": "telegram",
        "dominio": "geral",
    }
    status = {
        "fase": "fila",
        "origem_chat": chat_id,
        "recebido_em": agora.isoformat(timespec="seconds"),
        "progresso_pct": 0,
    }
    res = Resource(kind="Traducao", name=label, labels=labels, spec=spec, status=status)
    store.apply(res, agora)
    return res, f"📥 recebido: {nome}\n📖 traduzindo… te mando o PDF quando terminar."
