"""Job de vida-longa pausável e reagendável por escassez (ADR-0035).

Capacidade **genérica do núcleo** (Kind-agnóstica): um ``collect`` que pare por
escassez de token marca no ``status`` do recurso que quer ser retomado mais tarde;
o loop do app varre os pausados vencidos e re-dispara o ``collect`` em background,
continuando do checkpoint (a resumibilidade é responsabilidade do próprio job).

Contrato de pausa (campos gravados no ``status`` do recurso):
- ``fase = "pausado"``
- ``retoma_em``      — timestamp ISO de quando retomar
- ``retoma_collect`` — nome do ``collect`` que retoma o job
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

_log = logging.getLogger(__name__)

# Disparador injetado: (kind, name, collect) -> None. Deve rodar o collect em
# background (thread daemon) para não bloquear o loop do app.
Disparar = Callable[[str, str, str], object]


def campos_pausa(agora: datetime, segundos: int, collect: str) -> dict:
    """Campos de status que pausam o job e agendam a retomada (ADR-0035).

    O ``collect`` mescla o retorno no seu patch de ``status``. ``segundos`` é a
    janela até a retomada (ex.: 18000 = 5 h, quando a quota costuma resetar).
    """
    quando = agora + timedelta(seconds=max(1, int(segundos)))
    return {
        "fase": "pausado",
        "retoma_em": quando.isoformat(),
        "retoma_collect": collect,
    }


def _vencido(status: dict, agora: datetime) -> bool:
    if (status or {}).get("fase") != "pausado":
        return False
    quando = (status or {}).get("retoma_em")
    if not quando:
        return False
    try:
        return datetime.fromisoformat(quando) <= agora
    except (TypeError, ValueError):
        return False


def retomar_pausados(store, agora: datetime, disparar: Disparar) -> list[str]:
    """Varre os recursos pausados vencidos e re-dispara cada um em background.

    Limpa o marcador (``fase="retomando"``) **antes** de disparar para não repetir o
    disparo no próximo tick. Devolve os nomes retomados (observabilidade). Nunca
    propaga exceção (resiliência, ADR-0006).
    """
    retomados: list[str] = []
    try:
        kinds = store.kinds()
    except Exception:  # noqa: BLE001
        _log.exception("retomar_pausados: falha ao listar kinds")
        return retomados
    for kind in kinds:
        try:
            recursos = store.list(kind)
        except Exception:  # noqa: BLE001
            continue
        for res in recursos:
            status = getattr(res, "status", None) or {}
            if not _vencido(status, agora):
                continue
            collect = status.get("retoma_collect")
            if not collect:
                continue
            name = res.name
            # marca "retomando" antes do disparo → o próximo tick não re-seleciona.
            novo = {**status, "fase": "retomando", "retoma_em": None}
            try:
                store.set_status(kind, name, novo, agora)
                disparar(kind, name, collect)
                retomados.append(name)
            except Exception:  # noqa: BLE001 — um recurso ruim não trava os demais
                _log.exception("retomar_pausados: falha ao retomar %s/%s", kind, name)
    return retomados
