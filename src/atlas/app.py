"""Wiring do bot Atlas: long-poll → filtro de dono → handler → resposta.

Loop de operação (Camada 0). A análise (IA) entra nas rotinas agendadas; o MVP
foca no registro rápido e em /status.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

import atlas.rotinas.checkin  # noqa: F401 — registra collect de check-in
import atlas.rotinas.checkup_semanal  # noqa: F401 — registra collect de checkup semanal
import atlas.rotinas.coletar_por_label  # noqa: F401 — collect genérico por label de grupo
import atlas.rotinas.estudos  # noqa: F401 — registra collect de estudos
import atlas.rotinas.prompt  # noqa: F401 — registra collect genérico de IA (Kind=Prompt)
import atlas.rotinas.repo_sync  # noqa: F401 — registra collect genérico repo-sync
import atlas.rotinas.resumo_diario  # noqa: F401 — registra collect no registry
import atlas.rotinas.traduzir_pdf  # noqa: F401 — registra collect de tradução de PDF (Kind=Traducao)
import atlas.rotinas.treino  # noqa: F401 — registra collect de treino
from atlas.alarmes import tick_alarmes
from atlas.comandos import para_telegram
from atlas.config import Config
from atlas.controle import aplicar_overrides
from atlas.core.store import ResourceStore
from atlas.db import Database
from atlas.executor import ContextoExecucao, executar
from atlas.handler import responder
from atlas.retomada import recuperar_orfaos_no_boot, retomar_pausados
from atlas.rotinas import obter as obter_collect
from atlas.routines import Rotina, carregar_rotinas
from atlas.scheduler import catch_up, tick
from atlas.sync import sincronizar_store
from atlas.telegram import TelegramAdapter
from atlas.torrent_cmd import responder_conversa as responder_torrent

_log = logging.getLogger("atlas")


@dataclass
class Update:
    """Mensagem normalizada vinda do canal."""

    update_id: int
    chat_id: int
    user_id: int
    texto: str
    documento: dict | None = None  # {file_id, file_name} — anexo (ADR-0049)


class Adapter(Protocol):
    def enviar(self, chat_id: int, texto: str) -> None: ...
    def baixar_arquivo(self, file_id: str) -> bytes: ...


def processar_update(
    upd: Update,
    config: Config,
    db: Database,
    adapter: Adapter,
    agora: datetime | None = None,
    store: ResourceStore | None = None,
) -> None:
    """Atende um update. Só o dono é respondido (seguranca.md)."""
    if upd.user_id != config.allowed_user_id:
        _log.warning("Mensagem ignorada de user_id=%s (não é o dono)", upd.user_id)
        return
    agora = agora or datetime.now()

    # Anexo .torrent (ADR-0049): verifica, cria o Kind Torrent e pergunta.
    if upd.documento is not None and store is not None:
        _atender_torrent_documento(upd, adapter, store, agora)
        return

    if not upd.texto:
        return

    # Conversa stateful do Torrent (sim/não/progresso/cancelar, /torrents) — só
    # intercepta se a mensagem tem a ver com torrent; senão segue o roteador base.
    if store is not None:
        resposta_torrent = responder_torrent(
            upd.texto, store, agora, dispatch=_montar_dispatch_torrent(adapter, store)
        )
        if resposta_torrent is not None:
            adapter.enviar(upd.chat_id, resposta_torrent)
            return

    resposta = responder(upd.texto, db, agora, store=store)
    adapter.enviar(upd.chat_id, resposta)


def _atender_torrent_documento(upd: Update, adapter: Adapter, store: ResourceStore, agora) -> None:
    """Baixa o anexo do Telegram, verifica e cria o Torrent (ADR-0049)."""
    from atlas import torrent_cmd

    doc = upd.documento or {}
    try:
        dados = adapter.baixar_arquivo(doc.get("file_id"))
    except Exception:  # noqa: BLE001
        _log.exception("Falha ao baixar anexo do Telegram")
        adapter.enviar(upd.chat_id, "❌ não consegui baixar esse arquivo do Telegram.")
        return
    msg = torrent_cmd.receber_documento(
        store, dados, doc.get("file_name") or "", upd.chat_id, agora
    )
    adapter.enviar(upd.chat_id, msg)


def _montar_dispatch_torrent(adapter: Adapter, store: ResourceStore):
    """Devolve o ``dispatch(name)`` que sobe o download em background com o
    notificador de progresso/término no Telegram e, ao terminar, libera o slot
    do pool e despacha o próximo da fila (ADR-0049)."""
    from atlas.torrent import servico

    def dispatch(name: str) -> None:
        def _run() -> None:
            try:
                servico.executar_download(
                    store, name, notificar=lambda chat, msg: adapter.enviar(chat, msg)
                )
            finally:
                prox = servico.ao_concluir_slot(store, name)
                if prox is not None:
                    dispatch(prox)

        threading.Thread(target=_run, daemon=True, name=f"torrent-{name[:8]}").start()

    return dispatch


def _normalizar(update_cru: dict) -> Update | None:
    msg = update_cru.get("message") or update_cru.get("edited_message")
    if not msg:
        return None
    documento = None
    doc = msg.get("document")
    if doc:
        documento = {"file_id": doc.get("file_id"), "file_name": doc.get("file_name")}
    if "text" not in msg and documento is None:
        return None
    return Update(
        update_id=update_cru["update_id"],
        chat_id=msg["chat"]["id"],
        user_id=msg["from"]["id"],
        texto=msg.get("text", ""),
        documento=documento,
    )


def montar_disparo(
    db: Database,
    adapter: Adapter,
    chat_id: int,
    store: ResourceStore | None = None,
) -> Callable[[Rotina], object]:
    """Cria o callback que o scheduler usa para disparar uma rotina."""

    def disparar(rotina: Rotina) -> object:
        ctx = ContextoExecucao(
            agora=datetime.now(), rotina=rotina, origem="agenda", db=db, store=store
        )
        collect = obter_collect(rotina.coletar or rotina.nome)
        return executar(ctx, db, lambda msg: adapter.enviar(chat_id, msg), collect=collect)

    return disparar


def montar_disparo_retomada(store: ResourceStore) -> Callable[[str, str, str], object]:
    """Disparador de retomada (ADR-0035): roda o ``collect`` do job pausado numa
    thread daemon (não bloqueia o loop). Reconstrói uma ``Rotina`` mínima com o
    ``label`` = nome do recurso, como faz o disparo de tradução da API."""

    def disparar(kind: str, name: str, collect_nome: str) -> object:
        rot = Rotina(nome=name, descricao="", label=name, coletar=collect_nome)
        collect = obter_collect(collect_nome)

        def _run() -> None:
            ctx = ContextoExecucao(agora=datetime.now(), rotina=rot, origem="retomada", store=store)
            try:
                collect(ctx)
            except Exception:  # noqa: BLE001 — status já é marcado pelo collect (ADR-0006)
                _log.exception("retomada %s/%s falhou", kind, name)

        threading.Thread(target=_run, daemon=True, name=f"retomar-{name}").start()
        return name

    return disparar


def ciclo_scheduler(agora, rotinas, db, disparar, enviar_alarme, store, disparar_retomada) -> None:
    """Um ciclo de agenda + alarmes + retomadas (ADR-0035). Roda a cada volta do
    loop, **independente** do Telegram — extraído p/ ser testável isoladamente e
    p/ garantir que uma falha no long-poll (ex.: token inválido) não impede jobs
    pausados de retomar sozinhos."""
    tick(agora, rotinas, db, disparar)
    tick_alarmes(agora, db, enviar_alarme, store=store)
    retomar_pausados(store, agora, disparar_retomada)


def run(config: Config | None = None) -> None:
    """Inicia o loop de operação do bot (bloqueante)."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = config or Config.from_env()
    db = Database(config.db_path)
    adapter = TelegramAdapter(config.telegram_token, poll_timeout=config.poll_timeout)

    # Carrega rotinas e prepara o agendador.
    carga = carregar_rotinas(Path(config.routines_dir))
    aplicar_overrides(db, carga.rotinas)  # ativação salva no DB sobrepõe o default (E5-02)
    for erro in carga.erros:
        _log.warning("Rotina ignorada (%s): %s", erro.pasta, erro.mensagem)

    store = ResourceStore(config.db_path)
    sincronizar_store(db, store, carga.rotinas)

    # Isolamento multiusuário (ADR-0027 F5): recursos antigos sem dono vão para o
    # owner primário (admin). Idempotente e best-effort — não bloqueia o boot.
    try:
        import os

        from atlas import scoping

        owner_primario = os.environ.get("ATLAS_DEFAULT_OWNER", "admin")
        migrados = scoping.migrate_unowned(store, owner_primario)
        if migrados:
            _log.info(
                "Isolamento: %d recurso(s) sem dono migrado(s) p/ '%s'.", migrados, owner_primario
            )
    except Exception:  # noqa: BLE001 — migração não pode derrubar o boot (ADR-0006)
        _log.exception("Falha ao migrar recursos sem dono; seguindo.")

    # Recupera jobs assíncronos órfãos (ex.: Traducao presa em "traduzindo" por um
    # restart anterior) — sem isso, o usuário fica travado sem conseguir retomar
    # pela UI (ADR-0043). Best-effort — não pode derrubar o boot.
    try:
        recuperados = recuperar_orfaos_no_boot(store, datetime.now())
        if recuperados:
            _log.warning(
                "Boot: %d job(s) órfão(s) recuperado(s): %s", len(recuperados), recuperados
            )
    except Exception:  # noqa: BLE001
        _log.exception("Falha ao recuperar jobs órfãos no boot; seguindo.")

    # Torrents: persistência (ADR-0049). O restart mata o nox, mas o .torrent fica
    # salvo e os dados parciais ficam no destino — retomamos os que estavam
    # baixando/na fila (o nox recontinua do parcial em disco), respeitando o teto
    # do pool. Best-effort — não pode derrubar o boot.
    try:
        from atlas.torrent import servico as _torrent_servico

        n_torrent = _torrent_servico.retomar_no_boot(
            store, datetime.now(), dispatch=_montar_dispatch_torrent(adapter, store)
        )
        if n_torrent:
            _log.warning("Boot: %d torrent(s) retomado(s)/enfileirado(s).", n_torrent)
    except Exception:  # noqa: BLE001
        _log.exception("Falha ao retomar torrents no boot; seguindo.")

    disparar = montar_disparo(db, adapter, config.allowed_user_id, store=store)
    disparar_retomada = montar_disparo_retomada(store)  # ADR-0035: retoma jobs pausados

    # API HTTP + dashboard web (E0-02 / E0-05) — thread daemon.
    # Sobe ANTES do Telegram para não ficar refém da conectividade dele (ADR-0006):
    # se o Telegram estiver fora, a API/dashboard/scheduler seguem no ar.
    from atlas.api import iniciar as iniciar_api

    iniciar_api(store)

    # Setup do Telegram — best-effort; falha de rede não impede a API nem o scheduler.
    try:
        adapter.limpar_webhook()  # remove webhook antes do long-poll (evita HTTP 409)
    except Exception:  # noqa: BLE001 — sem rede não impede operar
        _log.warning("Telegram indisponível no boot (limpar_webhook); seguindo.")
    try:
        adapter.registrar_comandos(para_telegram())
    except Exception:  # noqa: BLE001 — sem rede/erro de API não impede operar
        _log.warning("Não foi possível registrar os comandos no Telegram (segue mesmo assim).")

    # Catch-up dos disparos perdidos enquanto esteve fora do ar (ADR-0006).
    try:
        recuperados = catch_up(datetime.now(), carga.rotinas, db, disparar)
        if recuperados:
            _log.info("Catch-up: %d rotina(s) recuperada(s) no boot.", len(recuperados))
    except Exception:  # noqa: BLE001
        _log.exception("Falha no catch-up de boot; seguindo.")

    _log.info(
        "Atlas no ar. user_id=%s · %d rotina(s) ativa(s). Ctrl+C para sair.",
        config.allowed_user_id,
        len(carga.ativas),
    )
    while True:
        try:
            for update_cru in adapter.receber():
                upd = _normalizar(update_cru)
                if upd is not None:
                    processar_update(upd, config, db, adapter, store=store)
        except KeyboardInterrupt:  # noqa: PERF203
            _log.info("Encerrando.")
            break
        except Exception:  # noqa: BLE001 — Telegram fora do ar não pode travar o scheduler
            _log.exception("Erro no long-poll do Telegram; seguindo.")

        # Agenda, alarmes e retomadas rodam **independente** do Telegram (ADR-0006):
        # um token inválido ou a rede fora não pode impedir jobs pausados (ADR-0035)
        # de retomar sozinhos — por isso é um try/except separado do bloco acima.
        try:
            ciclo_scheduler(
                datetime.now(),
                carga.rotinas,
                db,
                disparar,
                lambda msg: adapter.enviar(config.allowed_user_id, msg),
                store,
                disparar_retomada,
            )
        except Exception:  # noqa: BLE001 — resiliência: um erro não derruba o loop
            _log.exception("Erro no ciclo do scheduler; seguindo.")
