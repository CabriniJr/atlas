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

from atlas.conversa import binding
from atlas.conversa.descritores import slugificar
from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.torrent import download, integridade, scan
from atlas.torrent.download import ConfigDownload
from atlas.torrent.pool import TorrentPool, pool_torrent
from atlas.torrent.scan import ResultadoScan

_log = logging.getLogger("atlas.torrent")

KIND = "Torrent"
DIR_TORRENTS = "data/torrents"
DESTINO_DEFAULT = "~/Documents/torrent"

# Fases
VERIFICANDO = "verificando"
AGUARDANDO = "aguardando_confirmacao"
FILA = "fila"
BAIXANDO = "baixando"
CONCLUIDO = "concluido"
ERRO = "erro"
RECUSADO = "recusado"
CANCELADO = "cancelado"
# Concluído cujos arquivos não estão mais no disco (o PO desinstalou o jogo).
ARQUIVADO = "arquivado"

# Marcos de progresso que geram notificação proativa (%). 100% = notificação de
# conclusão ("✅ baixado"), tratada à parte.
MARCOS = (10, 50, 90)


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
        "total_bytes": res_scan.total_bytes,  # p/ checar completude pós-download
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
    # Nasce já participando da camada NL (ADR-0050): sem isto o recurso só
    # entraria no selector após o retro-carimbo do próximo boot.
    labels = binding.labels_com_participacao(KIND, {"dominio": "geral"})
    res = Resource(kind=KIND, name=infohash, labels=labels, spec=spec, status=status)
    store.apply(res, agora)
    return res, res_scan


def pendente_confirmacao(store: ResourceStore) -> Resource | None:
    """O torrent aguardando confirmação mais recente (o alvo de um 'sim'/'não')."""
    return _mais_recente(store, AGUARDANDO)


def pendentes_confirmacao(store: ResourceStore) -> list[Resource]:
    """**Todos** os torrents aguardando confirmação, mais recente primeiro.

    Instalação simultânea: com mais de um pendente, um "sim" solto é ambíguo —
    o chamador desambigua por id (ver ``torrent_cmd``) em vez de confirmar o
    mais recente às cegas.
    """
    pend = [t for t in store.list(KIND) if (t.status or {}).get("fase") == AGUARDANDO]
    return sorted(pend, key=lambda t: (t.status or {}).get("criado_em") or "", reverse=True)


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
    pool: TorrentPool | None = None,
    forte: bool = False,
    container: bool = False,
    nuvem: bool = False,
) -> tuple[bool, str]:
    """Confirma o download.

    - **Container (ADR-0051):** ``container=True`` → adiciona ao client único
      (``dispatch`` faz o ``adicionar``); a **fila é nativa** do qBittorrent, então
      marca ``baixando`` e o monitor corrige para ``fila`` se ficar ``queuedDL``.
    - **Nox (ADR-0049):** senão, se há slot no ``pool`` baixa já, senão entra na
      ``fila`` (o próximo é despachado quando um termina).

    Risco alto (nível 2) exige ``forte=True`` (o usuário digitou 'SIM' maiúsculo),
    espelhando o ``torrent-safe``.
    """
    pool = pool or pool_torrent
    t = store.get(KIND, name)
    if t is None:
        return False, "torrent não encontrado"
    if (t.status or {}).get("fase") not in (AGUARDANDO, FILA):
        return False, "esse torrent não está aguardando confirmação"
    if (t.status or {}).get("risco", 0) >= 2 and not forte:
        return False, "🚨 risco ALTO. Para confirmar mesmo assim, responda: SIM (maiúsculo)"
    nome = t.spec.get("nome") or name
    # `destino_nuvem` mora no status junto com o resto do estado de conversa
    # (`fase`, `cancelar`): é a escolha do PO nesta confirmação, lida pelo
    # monitor ao concluir para subir e liberar o disco (ADR-0056).
    destino = {"destino_nuvem": bool(nuvem)}
    selo = "  ☁️ vai pra nuvem ao terminar" if nuvem else ""
    if container:
        _patch_status(
            store,
            name,
            {"fase": BAIXANDO, "cancelar": False, "mensagem": "", **destino},
            agora,
        )
        dispatch(name)  # adiciona ao container; o monitor único cuida do resto
        return True, f"⬇️ baixando: {nome}{selo}\nAcompanhe com: progresso"
    if not download.motor_disponivel():
        return False, (
            "motor de download indisponível. Instale uma vez:\n"
            "  sudo dnf install -y qbittorrent-nox"
        )
    if pool.tentar_iniciar(name):
        _patch_status(
            store,
            name,
            {"fase": BAIXANDO, "cancelar": False, "mensagem": "", **destino},
            agora,
        )
        dispatch(name)
        return True, f"⬇️ baixando: {nome}{selo}\nAcompanhe com: progresso"
    _patch_status(
        store, name, {"fase": FILA, "cancelar": False, "mensagem": "", **destino}, agora
    )
    pos = pool.posicao_na_fila(name)
    return True, f"🕒 na fila (posição {pos}): {nome}\nComeça quando um slot liberar."


def ao_concluir_slot(
    store: ResourceStore, name: str, *, pool: TorrentPool | None = None
) -> str | None:
    """Chamado quando um download termina: libera o slot e devolve o próximo da
    fila (já marcado ``baixando``), que o chamador deve despachar. ``None`` se a
    fila está vazia."""
    pool = pool or pool_torrent
    prox = pool.liberar(name)
    if prox is not None:
        _patch_status(store, prox, {"fase": BAIXANDO, "cancelar": False})
    return prox


def recusar(store: ResourceStore, name: str, agora: datetime) -> tuple[bool, str]:
    t = store.get(KIND, name)
    if t is None:
        return False, "torrent não encontrado"
    _patch_status(store, name, {"fase": RECUSADO}, agora)
    return True, "👍 ok, não vou baixar."


def cancelar(
    store: ResourceStore,
    name: str,
    agora: datetime,
    *,
    pool: TorrentPool | None = None,
    cliente=None,
) -> tuple[bool, str]:
    """Cancela o download.

    - **Container (ADR-0051):** ``cliente`` dado → para o P2P e remove o torrent do
      client (mantém o parcial em disco); marca ``cancelado``.
    - **Nox (ADR-0049):** se ``fila``, tira da fila; se ``baixando``, sinaliza o
      cancelamento cooperativo (o loop de download lê a flag).
    """
    pool = pool or pool_torrent
    t = store.get(KIND, name)
    if t is None:
        return False, "torrent não encontrado"
    fase = (t.status or {}).get("fase")
    if cliente is not None:
        if fase in (BAIXANDO, FILA, AGUARDANDO):
            infohash = t.spec.get("infohash") or name
            try:
                cliente.parar_p2p(infohash)
                cliente.remover(infohash, apagar_dados=False)
            except Exception:  # noqa: BLE001 — best-effort (ADR-0006)
                _log.exception("cancelar container %s falhou", name)
            _patch_status(store, name, {"cancelar": True, "fase": CANCELADO}, agora)
            return True, "🛑 cancelado."
        return False, f"nada para cancelar (fase: {fase})"
    if fase == FILA:
        pool.cancelar_da_fila(name)
        _patch_status(store, name, {"fase": CANCELADO}, agora)
        return True, "🛑 removido da fila."
    if fase in (BAIXANDO, AGUARDANDO):
        _patch_status(store, name, {"cancelar": True, "fase": CANCELADO}, agora)
        return True, "🛑 cancelado."
    return False, f"nada para cancelar (fase: {fase})"


def alvo_em_disco(spec: dict) -> str:
    """Caminho onde o conteúdo do torrent deveria estar no host."""
    destino = os.path.expanduser(spec.get("destino") or DESTINO_DEFAULT)
    return os.path.join(destino, spec.get("nome") or "")


def _tem_conteudo(alvo: str) -> bool:
    """O conteúdo está realmente no disco?

    Pasta **vazia** não conta: desinstalar um jogo (ou subi-lo pra nuvem)
    costuma deixar o diretório para trás, e tratar isso como "está no disco"
    é o que fazia jogo removido seguir aparecendo como pronto.
    """
    if os.path.isfile(alvo):
        return os.path.getsize(alvo) > 0
    if not os.path.isdir(alvo):
        return False
    return any(arquivos for _r, _d, arquivos in os.walk(alvo))


def arquivar_ausentes(store: ResourceStore, agora: datetime) -> int:
    """``concluido`` cujo alvo não existe mais em disco → ``arquivado``.

    O recurso é histórico permanente, mas o jogo desinstalado não deve seguir
    aparecendo como se estivesse pronto. Checar o disco é o sinal honesto (o
    recurso sozinho não sabe que o PO apagou a pasta). Idempotente.
    """
    n = 0
    for t in store.list(KIND):
        s = t.status or {}
        if s.get("fase") != CONCLUIDO:
            continue
        if _tem_conteudo(alvo_em_disco(t.spec or {})):
            continue
        _patch_status(
            store,
            t.name,
            {"fase": ARQUIVADO, "arquivado_em": agora.isoformat(timespec="seconds")},
            agora,
        )
        n += 1
    return n


def linha_progresso(t: Resource) -> str:
    """Texto de progresso sob demanda para o Telegram.

    Exibe o **id curto como indexador** e o nome em slug (``lower_com_underscore``)
    — é o que o PO referencia em ``/torrent <id>``."""
    s = t.status or {}
    nome = f"{t.name[:8]}  {slugificar(t.spec.get('nome') or t.name)}"
    fase = s.get("fase")
    if fase == BAIXANDO:
        return (
            f"⬇️ {nome}\n"
            f"  {s.get('progresso_pct', 0):.1f}%  ·  {s.get('velocidade') or '—'}"
            f"  ·  seeds: {s.get('seeds', 0)}"
        )
    if fase == FILA:
        return f"🕒 {nome} — na fila"
    if fase == CONCLUIDO:
        selo = _selo_integridade(s)
        return f"✅ {nome} — concluído ({s.get('concluido_em') or ''}){selo}"
    if fase == AGUARDANDO:
        return f"⏸️ {nome} — aguardando você confirmar (sim/não)"
    if fase == ERRO:
        return f"❌ {nome} — erro: {s.get('mensagem') or '?'}"
    if fase == ARQUIVADO:
        return f"🗄️ {nome} — arquivado (arquivos não estão mais no disco)"
    return f"{nome} — {fase}"


def _selo_integridade(s: dict) -> str:
    integ = s.get("integridade")
    if integ == "ok":
        return "  · integridade ✅"
    if integ == "falha":
        return "  · integridade ⚠️ (invalid pfs0)"
    return ""


def _tamanho_esperado(spec: dict) -> int:
    """Tamanho total esperado do download (bytes) p/ checar completude. Usa o
    ``total_bytes`` salvo no spec; se faltar (recurso antigo), relê do ``.torrent``.
    Zero (desconhecido) desliga a checagem de completude — nunca reprova por falta
    de dado."""
    total = spec.get("total_bytes")
    if isinstance(total, int) and total > 0:
        return total
    arquivo = spec.get("arquivo")
    if arquivo and os.path.isfile(arquivo):
        try:
            return scan.analisar_arquivo(arquivo).total_bytes
        except Exception:  # noqa: BLE001 — best-effort (ADR-0006)
            return 0
    return 0


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
    infohash = spec.get("infohash") or name
    if cliente is not None:
        cli = cliente
    else:
        # cada download concorrente: porta WebUI + profile próprios (ADR-0049).
        # O profile por-infohash preserva a sessão p/ retomar após restart.
        porta = download.alocar_porta()
        cfg = ConfigDownload(**{**cfg.__dict__, "porta_webui": porta})
        cli = download.QBittorrentNox(profile=download.profile_para(infohash), porta=porta)
    chat = spec.get("origem_chat")
    nome_t = spec.get("nome") or name
    marcos_pendentes = list(MARCOS)  # notifica ao cruzar cada um, uma vez

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
        # Notificações proativas de marco (10/50/90%): dispara a cada limiar
        # cruzado uma única vez (se pular vários num tick, notifica só o maior).
        cruzados = [m for m in marcos_pendentes if p.pct >= m]
        if cruzados and notificar and chat is not None:
            maior = max(cruzados)
            notificar(int(chat), f"📥 {nome_t}: {maior}%  ·  {p.velocidade or '—'}")
        for m in cruzados:
            marcos_pendentes.remove(m)

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
        # Verificação de integridade (ADR-0049): magic header (conteúdo fake/
        # corrompido na fonte, invalid pfs0) + completude por tamanho (download
        # truncado no meio do move, que passava no magic mas quebrava a instalação).
        alvo = os.path.join(cfg.destino_expandido(), nome)
        esperado = _tamanho_esperado(spec)
        integ = integridade.verificar(alvo, tamanho_esperado=esperado)
        _patch_status(
            store, name,
            {
                "fase": CONCLUIDO,
                "progresso_pct": 100.0,
                "concluido_em": _agora().isoformat(timespec="seconds"),
                "integridade": "ok" if integ.ok else "falha",
                "integridade_detalhe": integ.humano(),
            },
        )
        if notificar and chat is not None:
            if integ.ok:
                notificar(
                    int(chat),
                    f"✅ baixado: {nome}\n📁 em {cfg.destino_expandido()}\n{integ.humano()}",
                )
            else:
                notificar(
                    int(chat),
                    f"⚠️ baixado, MAS integridade falhou: {nome}\n{integ.humano()}\n"
                    f"📁 em {cfg.destino_expandido()} (arquivos mantidos)",
                )
    elif r.motivo == "cancelado":
        _patch_status(store, name, {"fase": CANCELADO})
    else:
        _patch_status(store, name, {"fase": ERRO, "mensagem": r.motivo})
        if notificar and chat is not None:
            notificar(int(chat), f"❌ falhou: {nome}\n{r.motivo}")


def retomar_no_boot(
    store: ResourceStore,
    agora: datetime,
    *,
    dispatch: Callable[[str], None],
    pool: TorrentPool | None = None,
    container: bool = False,
) -> int:
    """Persistência: um restart mata o client, mas o ``.torrent`` fica salvo e os
    dados parciais ficam no destino — então um ``Torrent`` que estava
    ``baixando``/``fila`` **retoma sozinho** (recontinua do parcial em disco).

    - **Container (ADR-0051):** re-adiciona TODOS os pendentes ao client único
      (fila nativa decide quem baixa já vs ``queuedDL``); o monitor dirige.
    - **Nox (ADR-0049):** respeita o teto do pool — até ``max_concorrente`` voltam
      a baixar, o resto reentra na fila.

    Devolve quantos foram re-enfileirados/retomados."""
    pool = pool or pool_torrent
    pendentes = [
        t for t in store.list(KIND) if (t.status or {}).get("fase") in (BAIXANDO, FILA)
    ]
    # ordem estável: retoma primeiro os que já estavam baixando, por criado_em.
    pendentes.sort(
        key=lambda t: (
            0 if (t.status or {}).get("fase") == BAIXANDO else 1,
            (t.status or {}).get("criado_em") or "",
        )
    )
    if container:
        for t in pendentes:
            _patch_status(
                store, t.name,
                {"fase": BAIXANDO, "cancelar": False, "mensagem": "retomado após reinício"},
                agora,
            )
            dispatch(t.name)
        return len(pendentes)
    n = 0
    for t in pendentes:
        if pool.tentar_iniciar(t.name):
            _patch_status(
                store, t.name,
                {"fase": BAIXANDO, "cancelar": False, "mensagem": "retomado após reinício"},
                agora,
            )
            dispatch(t.name)
        else:
            _patch_status(store, t.name, {"fase": FILA, "cancelar": False}, agora)
        n += 1
    return n
