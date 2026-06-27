"""Fixtures compartilhadas dos testes.

Define ``free_tcp_port`` localmente para que a suíte rode com **qualquer** Python
(não só o do sistema): antes o fixture vinha do plugin do ``anyio``, instalado só
no Python do sistema — daí o gotcha "rode com `python -m pytest`". Definindo aqui,
o `pytest` puro do CI (e o do venv) também acham o fixture.
"""

from __future__ import annotations

import socket

import pytest


@pytest.fixture
def free_tcp_port() -> int:
    """Devolve uma porta TCP livre (bind em :0, lê a porta, libera)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
