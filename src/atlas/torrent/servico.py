"""Serviço do Kind ``Torrent`` (ADR-0049): máquina de estados sobre o
``ResourceStore``, ligando scan → confirmação → download headless → notificação.

Estado mora **no recurso** (não em memória de processo): sobrevive a restart e
aparece no dashboard. Zero IA.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.torrent import download, scan
from atlas.torrent.download import ConfigDownload
from atlas.torrent.scan import ResultadoScan

_log = logging.getLogger("atlas.torrent")

KIND = "Torrent"
DIR_TORRENTS = "data/torrents"
DESTINO_DEFAULT = "~/Documents/torrent"

# Fases
VERIFICANDO = "verificando"
AGUARDANDO = "aguardando_confirmacao"
BAIXANDO = "baixando"
CONCLUIDO = "concluido"
ERRO = "erro"
RECUSADO = "recusado"
CANCELADO = "cancelado"


def _agora() -> datetime:
    return datetime.now()


def criar_do_bytes(
    store: ResourceStore,
    dados: bytes,
    nome_arquivo: str,
    chat_id: int | None,
    agora: datetime,
    *,
    dir_torrents: str = DIR_TORRENTS,
    destino: str = DESTINO_DEFAULT,
    permitir_sem_vpn: bool = True,
    vpn: str = "",
) -> tuple[Resource | None, ResultadoScan]:
    """Verifica o ``.torrent`` e, se válido, cria o recurso em
    ``aguardando_confirmacao``. Devolve ``(recurso|None, resultado_scan)`` — em
    scan inválido, ``recurso`` é ``None`` e o chamador responde o erro."""
    res_scan = scan.analisar_bytes(dados)
    if not res_scan.ok:
        return None, res_scan

    infohash = res_scan.infohash
    Path(dir_torrents).mkdir(parents=True, exist_ok=True)
    caminho = os.path.join(dir_torrents, f"{infohash}.torrent")
    with open(caminho, "wb") as f:
        f.write(dados)

    spec = {
        "arquivo": caminho,
        "nome": res_scan.nome,
        "infohash": infohash,
        "destino": destino,
        "vpn": vpn,
        "permitir_sem_vpn": permitir_sem_vpn,
        "semear": False,
        "origem_chat": chat_id,
        "nome_arquivo": nome_arquivo,
    }
    status = {
        "fase": AGUARDANDO,
        "risco": res_scan.risco,
        "resumo": res_scan.humano(),
        "progresso_pct": 0.0,
        "velocidade": "",
        "seeds": 0,
        "mensagem": "",
        "cancelar": False,
        "criado_em": agora.isoformat(timespec="seconds"),
        "concluido_em": None,
    }
    res = Resource(kind=KIND, name=infohash, labels={"dominio": "geral"}, spec=spec, status=status)
    store.apply(res, agora)
    return res, res_scan


def pendente_confirmacao(store: ResourceStore) -> Resource | None:
    """O torrent aguardando confirmação mais recente (o alvo de um 'sim'/'não')."""
    return _mais_recente(store, AGUARDANDO)


def em_andamento(store: ResourceStore) -> Resource | None:
    """O torrent baixando mais recente (alvo de 'progresso'/'cancelar')."""
    return _mais_recente(store, BAIXANDO)


def _mais_recente(store: ResourceStore, fase: str) -> Resource | None:
    candidatos = [t for t in store.list(KIND) if (t.status or {}).get("fase") == fase]
    if not candidatos:
        return None
    return max(candidatos, key=lambda t: (t.status or {}).get("criado_em") or "")


def _patch_status(
    store: ResourceStore, name: str, patch: dict, agora: datetime | None = None
) -> None:
    t = store.get(KIND, name)
    if t is None:
        return
    store.set_status(KIND, name, {**(t.status or {}), **patch}, agora or _agora())


def confirmar(
    store: ResourceStore,
    name: str,
    agora: datetime,
    *,
    dispatch: Callable[[str], None],
    forte: bool = False,
) -> tuple[bool, str]:
    """Move ``aguardando_confirmacao`` → ``baixando`` e dispara o download.

    Risco alto (nível 2) exige ``forte=True`` (o usuário digitou 'SIM' maiúsculo),
    espelhando o ``torrent-safe``.
    """
    t = store.get(KIND, name)
    if t is None:
        return False, "torrent não encontrado"
    if (t.status or {}).get("fase") != AGUARDANDO:
        return False, "esse torrent não está aguardando confirmação"
    if (t.status or {}).get("risco", 0) >= 2 and not forte:
        return False, "🚨 risco ALTO. Para confirmar mesmo assim, responda: SIM (maiúsculo)"
    if not download.motor_disponivel():
        return False, (
            "motor de download indisponível. Instale uma vez:\n"
            "  sudo dnf install -y qbittorrent-nox"
        )
    _patch_status(store, name, {"fase": BAIXANDO, "cancelar": False, "mensagem": ""}, agora)
    dispatch(name)
    nome = t.spec.get("nome") or name
    return True, f"⬇️ baixando: {nome}\nAcompanhe com: progresso"


def recusar(store: ResourceStore, name: str, agora: datetime) -> tuple[bool, str]:
    t = store.get(KIND, name)
    if t is None:
        return False, "torrent não encontrado"
    _patch_status(store, name, {"fase": RECUSADO}, agora)
    return True, "👍 ok, não vou baixar."


def cancelar(store: ResourceStore, name: str, agora: datetime) -> tuple[bool, str]:
    """Sinaliza cancelamento cooperativo (o loop de download lê a flag)."""
    t = store.get(KIND, name)
    if t is None:
        return False, "torrent não encontrado"
    fase = (t.status or {}).get("fase")
    if fase not in (BAIXANDO, AGUARDANDO):
        return False, f"nada para cancelar (fase: {fase})"
    _patch_status(store, name, {"cancelar": True, "fase": CANCELADO}, agora)
    return True, "🛑 cancelado."


def linha_progresso(t: Resource) -> str:
    """Texto de progresso sob demanda para o Telegram."""
    s = t.status or {}
    nome = t.spec.get("nome") or t.name
    fase = s.get("fase")
    if fase == BAIXANDO:
        return (
            f"⬇️ {nome}\n"
            f"  {s.get('progresso_pct', 0):.1f}%  ·  {s.get('velocidade') or '—'}"
            f"  ·  seeds: {s.get('seeds', 0)}"
        )
    if fase == CONCLUIDO:
        return f"✅ {nome} — concluído ({s.get('concluido_em') or ''})"
    if fase == AGUARDANDO:
        return f"⏸️ {nome} — aguardando você confirmar (sim/não)"
    if fase == ERRO:
        return f"❌ {nome} — erro: {s.get('mensagem') or '?'}"
    return f"{nome} — {fase}"


def executar_download(
    store: ResourceStore,
    name: str,
    *,
    notificar: Callable[[int, str], None] | None = None,
    cliente: download.ClienteTorrent | None = None,
    baixar_fn: Callable = download.baixar,
    intervalo_s: float = 2.0,
) -> None:
    """Corpo do job em background: roda o download atualizando o ``status`` e
    notifica o dono ao concluir/errar. Nunca levanta (ADR-0006)."""
    t = store.get(KIND, name)
    if t is None:
        return
    spec = t.spec
    cfg = ConfigDownload(
        destino=spec.get("destino") or DESTINO_DEFAULT,
        vpn=spec.get("vpn") or "",
        permitir_sem_vpn=bool(spec.get("permitir_sem_vpn", True)),
        semear=bool(spec.get("semear", False)),
    )
    cli = cliente if cliente is not None else download.QBittorrentNox()
    chat = spec.get("origem_chat")

    def _on_progress(p: download.Progresso) -> None:
        _patch_status(
            store,
            name,
            {
                "progresso_pct": round(p.pct, 1),
                "velocidade": p.velocidade,
                "seeds": p.seeds,
                "estado_motor": p.estado,
            },
        )

    def _cancelado() -> bool:
        cur = store.get(KIND, name)
        return bool(cur and (cur.status or {}).get("cancelar"))

    try:
        r = baixar_fn(
            spec.get("arquivo"),
            spec.get("infohash") or name,
            cfg,
            cli,
            on_progress=_on_progress,
            checar_cancel=_cancelado,
            intervalo_s=intervalo_s,
        )
    except Exception as exc:  # noqa: BLE001
        _log.exception("torrent %s: download falhou", name)
        _patch_status(store, name, {"fase": ERRO, "mensagem": str(exc)})
        if notificar and chat is not None:
            notificar(int(chat), f"❌ falhou: {spec.get('nome') or name}\n{exc}")
        return

    nome = spec.get("nome") or name
    if r.ok and r.concluido:
        _patch_status(
            store, name,
            {
                "fase": CONCLUIDO,
                "progresso_pct": 100.0,
                "concluido_em": _agora().isoformat(timespec="seconds"),
            },
        )
        if notificar and chat is not None:
            notificar(int(chat), f"✅ baixado: {nome}\n📁 em {cfg.destino_expandido()}")
    elif r.motivo == "cancelado":
        _patch_status(store, name, {"fase": CANCELADO})
    else:
        _patch_status(store, name, {"fase": ERRO, "mensagem": r.motivo})
        if notificar and chat is not None:
            notificar(int(chat), f"❌ falhou: {nome}\n{r.motivo}")


def recuperar_orfaos_no_boot(store: ResourceStore, agora: datetime) -> int:
    """Um restart mata o P2P; um ``Torrent`` preso em ``baixando`` volta para
    ``aguardando_confirmacao`` (o dono reconfirma). Devolve quantos recuperou."""
    n = 0
    for t in store.list(KIND):
        if (t.status or {}).get("fase") == BAIXANDO:
            _patch_status(
                store, t.name,
                {
                    "fase": AGUARDANDO,
                    "mensagem": "reiniciado — confirme para retomar",
                    "cancelar": False,
                },
                agora,
            )
            n += 1
    return n
