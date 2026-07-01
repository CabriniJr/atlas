"""Barra de progresso da tradução (ADR-0030).

``barra_texto`` renderiza uma barra ASCII a partir de ``ProgressoTraducao`` — serve
para o terminal (uso local, on-demand) e como base do valor exibido no web shell
(ADR-0029), que também lê ``status.progresso_pct``.

Uso como callback do pipeline::

    traduzir_pdf(src, out, cfg, on_progress=imprimir_barra)
"""

from __future__ import annotations

import sys

_CHEIO = "█"
_VAZIO = "░"


def _pct(prog) -> int:
    if not prog.paginas_total:
        return 0
    return int(prog.paginas_prontas * 100 / prog.paginas_total)


def barra_texto(prog, largura: int = 30) -> str:
    """Retorna a barra como string: ``[████░░░░] 50% (5/10 páginas)``."""
    pct = _pct(prog)
    preenchido = round(pct * largura / 100)
    barra = _CHEIO * preenchido + _VAZIO * (largura - preenchido)
    return f"[{barra}] {pct}% ({prog.paginas_prontas}/{prog.paginas_total} páginas)"


def imprimir_barra(prog) -> None:
    """Callback ``on_progress``: reescreve a barra na mesma linha do terminal."""
    fim = "\n" if prog.paginas_prontas >= prog.paginas_total else ""
    sys.stdout.write("\r" + barra_texto(prog) + fim)
    sys.stdout.flush()
