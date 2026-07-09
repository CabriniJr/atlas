"""Pool de execução de torrents (ADR-0049, padrão do ADR-0038): teto de
concorrência escalável em runtime + fila FIFO.

Você manda vários `.torrent`; até ``max_concorrente`` baixam **juntos**, o resto
**enfileira** (fase ``fila``) e é despachado sozinho quando um slot libera.
Estado só em memória — reflete a instância viva; cada torrent persiste a própria
``fase`` no recurso.
"""

from __future__ import annotations

import os
import threading


class TorrentPool:
    """Decide, na hora de confirmar, se um torrent baixa agora ou entra na fila.

    ``tentar_iniciar`` reserva o slot atomicamente (sem isso, duas confirmações
    concorrentes poderiam ambas ver espaço e estourar o teto).
    """

    def __init__(self, max_concorrente: int = 3) -> None:
        self._lock = threading.Lock()
        self.max_concorrente = max(1, max_concorrente)
        self._rodando: set[str] = set()
        self._fila: list[str] = []

    def tentar_iniciar(self, label: str) -> bool:
        """``True``: reservou slot, baixa agora. ``False``: entrou na fila."""
        with self._lock:
            if label in self._rodando:
                return True
            if len(self._rodando) < self.max_concorrente:
                self._rodando.add(label)
                return True
            if label not in self._fila:
                self._fila.append(label)
            return False

    def liberar(self, label: str) -> str | None:
        """Chamado quando um torrent termina (sucesso/erro/cancelado). Libera o
        slot e despacha o próximo da fila, se houver. Devolve o label despachado
        (o chamador deve disparar a thread dele) ou ``None``."""
        with self._lock:
            self._rodando.discard(label)
            return self._despachar_proximo()

    def escalar(self, novo_max: int) -> list[str]:
        """Muda o teto (mín. 1). Se subiu, drena a fila. Devolve os despachados."""
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
        """Remove um label da fila antes de rodar. ``True`` se estava na fila."""
        with self._lock:
            if label in self._fila:
                self._fila.remove(label)
                return True
            return False

    def posicao_na_fila(self, label: str) -> int | None:
        """Posição 1-based na fila, ou ``None`` se não está enfileirado."""
        with self._lock:
            return self._fila.index(label) + 1 if label in self._fila else None

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


# Instância compartilhada (default 3 baixando juntos; escalável em runtime).
_max_default = int(os.environ.get("ATLAS_TORRENT_MAX_CONCURRENT", "3"))
pool_torrent = TorrentPool(max_concorrente=_max_default)
