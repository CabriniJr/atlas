"""Isola o pool global de torrents entre testes (ADR-0049).

``pool_torrent`` é um singleton de módulo; sem reset, o estado de concorrência/
fila vaza de um teste para o outro."""

from __future__ import annotations

import pytest

from atlas.torrent import pool as _pool


@pytest.fixture(autouse=True)
def _reset_pool_torrent():
    p = _pool.pool_torrent
    p._rodando.clear()
    p._fila.clear()
    p.max_concorrente = 3
    yield
    p._rodando.clear()
    p._fila.clear()
