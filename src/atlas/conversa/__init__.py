"""Camada de linguagem natural global do Atlas (ADR-0050).

Data-driven: os comportamentos são recursos ``Binding`` (mensagem → ação sobre um
selector de labels), não código no roteador. ``responder`` casa o gatilho de um
Binding e roda a ação; ``None`` cai no roteador base.
"""

from atlas.conversa.router import responder

__all__ = ["responder"]
