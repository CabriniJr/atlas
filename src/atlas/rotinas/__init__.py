"""Registro de funções collect das rotinas-âncora do Atlas.

Cada rotina que tem coleta de dados registra aqui sua função ``coletar``.
O ``app.py`` consulta este registry ao montar o dispatcher.
"""

from __future__ import annotations

from collections.abc import Callable

from atlas.executor import CollectResult, ContextoExecucao

ColetarFn = Callable[[ContextoExecucao], CollectResult]

_REGISTRY: dict[str, ColetarFn] = {}


def registrar(nome: str) -> Callable[[ColetarFn], ColetarFn]:
    """Decorator: @registrar('nome-da-rotina')."""
    def _dec(fn: ColetarFn) -> ColetarFn:
        _REGISTRY[nome] = fn
        return fn
    return _dec


def obter(nome: str) -> ColetarFn | None:
    return _REGISTRY.get(nome)
