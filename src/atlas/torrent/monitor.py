"""Monitor único do client de torrent em container (ADR-0051).

Uma thread poll-a o ``ClienteContainer`` e dirige **todos** os recursos ``Torrent``
ativos: atualiza progresso/estado/fase, dispara marcos (10/50/90%) e, ao concluir,
roda integridade (magic + tamanho) e **auto-envia** o resultado ao dono no Telegram
(a feature pedida). Substitui o loop ``baixar`` por-download (ADR-0049); a fila é
nativa do qBittorrent, então "baixando vs fila" deriva do estado do client.

``tick`` é uma varredura testável com fakes; ``monitorar`` é o laço em background.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from datetime import datetime

from atlas.torrent import integridade
from atlas.torrent.container import ClienteContainer
from atlas.torrent.download import Progresso
from atlas.torrent.servico import (
    BAIXANDO,
    CONCLUIDO,
    DESTINO_DEFAULT,
    FILA,
    KIND,
    MARCOS,
    _agora,
    _patch_status,
    _tamanho_esperado,
)

_log = logging.getLogger("atlas.torrent")

# Estados do qBittorrent que significam "ainda na fila nativa" (não começou).
_ESTADOS_FILA = frozenset({"queueddl", "queuedforcedl"})


def _fase_do_estado(estado: str) -> str:
    """Deriva a fase do recurso a partir do estado do qBittorrent (fila nativa)."""
    return FILA if estado.strip().lower() in _ESTADOS_FILA else BAIXANDO


def _aplicar_progresso(store, t, p: Progresso, notificar) -> None:
    s = t.status or {}
    chat = t.spec.get("origem_chat")
    nome = t.spec.get("nome") or t.name
    ja = list(s.get("marcos_notificados") or [])
    cruzados = [m for m in MARCOS if p.pct >= m and m not in ja]
    if cruzados and notificar and chat is not None:
        notificar(int(chat), f"📥 {nome}: {max(cruzados)}%  ·  {p.velocidade or '—'}")
    _patch_status(
        store,
        t.name,
        {
            "progresso_pct": round(p.pct, 1),
            "velocidade": p.velocidade,
            "seeds": p.seeds,
            "estado_motor": p.estado,
            "fase": _fase_do_estado(p.estado),
            "marcos_notificados": sorted(set(ja) | set(cruzados)),
        },
    )


def _concluir(store, t, cliente: ClienteContainer, notificar, enviar, agora_fn) -> None:
    spec = t.spec
    infohash = spec.get("infohash") or t.name
    nome = spec.get("nome") or t.name
    chat = spec.get("origem_chat")
    destino = os.path.expanduser(spec.get("destino") or DESTINO_DEFAULT)
    alvo = os.path.join(destino, nome)
    integ = integridade.verificar(alvo, tamanho_esperado=_tamanho_esperado(spec))
    _patch_status(
        store,
        t.name,
        {
            "fase": CONCLUIDO,
            "progresso_pct": 100.0,
            "concluido_em": agora_fn().isoformat(timespec="seconds"),
            "integridade": "ok" if integ.ok else "falha",
            "integridade_detalhe": integ.humano(),
        },
    )
    # Para o P2P e tira do client (mantém os dados no host — só some da lista).
    cliente.parar_p2p(infohash)
    cliente.remover(infohash, apagar_dados=False)
    if notificar and chat is not None:
        if integ.ok:
            notificar(int(chat), f"✅ baixado: {nome}\n📁 {destino}\n{integ.humano()}")
        else:
            notificar(
                int(chat),
                f"⚠️ baixado, MAS integridade falhou: {nome}\n{integ.humano()}\n"
                f"📁 {destino} (arquivos mantidos)",
            )
    # Auto-envio (ADR-0051): arquivo pequeno vai como documento; pasta/grande vai
    # como caminho — decisão no callback do app (reusa preparar_envio).
    if enviar and chat is not None:
        try:
            enviar(int(chat), alvo, nome)
        except Exception:  # noqa: BLE001 — best-effort (ADR-0006)
            _log.exception("auto-envio de %s falhou", nome)


def tick(
    store,
    cliente: ClienteContainer,
    *,
    notificar: Callable[[int, str], None] | None = None,
    enviar: Callable[[int, str, str], None] | None = None,
    agora_fn: Callable[[], datetime] = _agora,
) -> None:
    """Uma varredura: atualiza cada ``Torrent`` ativo pela listagem do client e
    conclui os que terminaram. Nunca levanta (ADR-0006)."""
    ativos = [
        t for t in store.list(KIND) if (t.status or {}).get("fase") in (BAIXANDO, FILA)
    ]
    if not ativos:
        return
    try:
        arr = cliente.listar()
    except Exception:  # noqa: BLE001
        _log.exception("monitor: falha ao listar torrents")
        return
    for t in ativos:
        infohash = t.spec.get("infohash") or t.name
        p = cliente.progresso_de(infohash, arr)
        if p is None:
            continue  # client ainda não conhece (recém-adicionado / já removido)
        _aplicar_progresso(store, t, p, notificar)
        if p.concluido:
            _concluir(store, t, cliente, notificar, enviar, agora_fn)


def monitorar(
    store,
    cliente: ClienteContainer,
    *,
    notificar: Callable[[int, str], None] | None = None,
    enviar: Callable[[int, str, str], None] | None = None,
    intervalo_s: float = 3.0,
    parar: Callable[[], bool] | None = None,
) -> threading.Thread:
    """Sobe a thread daemon do monitor (uma por processo). ``parar`` opcional
    encerra o laço (testes/shutdown)."""

    def _loop() -> None:
        while not (parar and parar()):
            tick(store, cliente, notificar=notificar, enviar=enviar)
            time.sleep(intervalo_s)

    th = threading.Thread(target=_loop, daemon=True, name="torrent-monitor")
    th.start()
    return th
