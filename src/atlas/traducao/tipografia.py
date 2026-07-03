"""Motor puro de tipografia do render editorial (ADR-0041): conversão de marcador
de ênfase inline, clustering de nível de heading e taxa de abertura de página —
sem WeasyPrint/IO pesado (mesmo padrão de ``layout.py``). ``extrair_fontes`` é a
única função que precisa do documento aberto (fitz).
"""

from __future__ import annotations

import re
from collections.abc import Callable

_RE_ENFASE = re.compile(r"\*\*(.+?)\*\*|_(.+?)_", re.DOTALL)


def converter_enfase(texto: str, escapar: Callable[[str], str]) -> str:
    """Converte marcador ``**negrito**``/``_itálico_`` em ``<b>``/``<i>``, escapando
    o restante do texto com ``escapar`` (ex.: ``html.escape``). Marcador que não
    fecha (desbalanceado) fica literal — nunca quebra o parse (ADR-0041)."""
    partes: list[str] = []
    pos = 0
    for m in _RE_ENFASE.finditer(texto):
        if m.start() > pos:
            partes.append(escapar(texto[pos : m.start()]))
        if m.group(1) is not None:
            partes.append(f"<b>{escapar(m.group(1))}</b>")
        else:
            partes.append(f"<i>{escapar(m.group(2))}</i>")
        pos = m.end()
    partes.append(escapar(texto[pos:]))
    return "".join(partes)
