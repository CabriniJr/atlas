"""Pool de execução de traduções (ADR-0038): teto de concorrência escalável em
runtime + fila FIFO. Generaliza para ``Traducao`` o padrão de concorrência e
registro do Agente modo ``code`` (ADR-0028 §3/§5).

Estado só em memória — reflete a instância viva; cada tradução persiste o
próprio ``status.fase`` no recurso (E9-10).
"""

from __future__ import annotations

import os
import threading


class TraducaoPool:
    """Decide, na hora de iniciar, se uma tradução roda agora ou entra na fila.

    ``tentar_iniciar`` reserva o slot atomicamente (sem essa garantia, duas
    chamadas concorrentes poderiam ambas ver espaço livre e estourar o teto).
    """

    def __init__(self, max_concorrente: int = 2) -> None:
        self._lock = threading.Lock()
        self.max_concorrente = max(1, max_concorrente)
        self._rodando: set[str] = set()
        self._fila: list[str] = []

    def tentar_iniciar(self, label: str) -> bool:
        """``True``: reservou slot, o chamador deve rodar agora. ``False``: foi
        pra fila (o chamador não deve disparar a thread)."""
        with self._lock:
            if len(self._rodando) < self.max_concorrente:
                self._rodando.add(label)
                return True
            if label not in self._fila:
                self._fila.append(label)
            return False

    def liberar(self, label: str) -> str | None:
        """Chamado quando uma tradução termina (sucesso/erro/pausa). Libera o
        slot e despacha o próximo da fila, se houver. Devolve o label
        despachado (o chamador deve disparar a thread dele) ou ``None``."""
        with self._lock:
            self._rodando.discard(label)
            return self._despachar_proximo()

    def escalar(self, novo_max: int) -> list[str]:
        """Muda o teto (mín. 1). Se subiu, drena a fila imediatamente. Devolve
        os labels despachados — o chamador deve disparar a thread de cada um."""
        despachados: list[str] = []
        with self._lock:
            self.max_concorrente = max(1, novo_max)
            while True:
                prox = self._despachar_proximo()
                if prox is None:
                    break
                despachados.append(prox)
        return despachados

    def cancelar_da_fila(self, label: str) -> bool:
        """Remove um label da fila (antes de rodar; sem custo de IA)."""
        with self._lock:
            if label in self._fila:
                self._fila.remove(label)
                return True
            return False

    def estado(self) -> dict:
        with self._lock:
            return {
                "max_concorrente": self.max_concorrente,
                "rodando": sorted(self._rodando),
                "fila": list(self._fila),
            }

    def _despachar_proximo(self) -> str | None:
        """Chamado com o lock já adquirido."""
        if self._fila and len(self._rodando) < self.max_concorrente:
            prox = self._fila.pop(0)
            self._rodando.add(prox)
            return prox
        return None


# Instância compartilhada (ADR-0038/0039): a API usa pra distribuir jobs entre
# réplicas; a rotina traduzir-pdf lê ``max_concorrente`` do mesmo objeto pra
# saber com quantos workers paralelizar as páginas de UM job — "réplicas" é um
# dial só, vale pros dois eixos.
_max_default = int(os.environ.get("ATLAS_TRADUCAO_MAX_CONCURRENT", "2"))
pool_global = TraducaoPool(max_concorrente=_max_default)
