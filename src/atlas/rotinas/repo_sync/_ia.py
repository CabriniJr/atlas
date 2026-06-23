"""Seam de IA do repo-sync.

Toda chamada de IA das submódulos passa por aqui e resolve ``invocar`` no
namespace do pacote **em tempo de chamada**. Assim os testes podem patchar
``atlas.rotinas.repo_sync.invocar`` e atingir qualquer submódulo, e o ponto de
chamada fica isolado para virar o Kind ``Agente`` (ADR-0024) sem tocar no resto.
"""

from __future__ import annotations

from typing import Any


def invocar(*args: Any, **kwargs: Any) -> Any:
    from atlas.rotinas import repo_sync

    return repo_sync.invocar(*args, **kwargs)
