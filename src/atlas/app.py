"""Wiring do bot Atlas: long-poll → filtro de dono → handler → resposta.

Loop de operação (Camada 0). A análise (IA) entra nas rotinas agendadas; o MVP
foca no registro rápido e em /status.
"""

from __future__ import annotations

import logging
import threading
import time
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
    def enviar_documento(self, chat_id: int, caminho: str, legenda: str = "") -> None: ...


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

    # Anexo: .pdf → tradução (ADR-0050); .torrent (ou resto) → torrent (ADR-0049).
    if upd.documento is not None and store is not None:
        _atender_documento(upd, adapter, store, agora)
        return

    if not upd.texto:
        return

    # Camada NL global (ADR-0050): progresso agregado, busca cross-kind, enviar
    # traduzido, sync. Data-driven (Binding). Roda ANTES da conversa do torrent
    # para o "progresso" ser global; sim/não/cancelar não casam verbo/nome e caem
    # adiante. None → segue para a conversa do torrent / roteador base.
    if store is not None:
        from atlas.conversa import responder as responder_conversa
        from atlas.conversa.router import Contexto as _CtxConversa

        ctx_conv = _CtxConversa(
            agora=agora,
            chat_id=upd.chat_id,
            enviar_documento=getattr(adapter, "enviar_documento", None),
            notificar=adapter.enviar,
        )
        resposta_conv = responder_conversa(upd.texto, store, ctx_conv)
        if resposta_conv is not None:
            adapter.enviar(upd.chat_id, resposta_conv)
            return

    # Conversa stateful do Torrent (sim/não/cancelar, /torrents) — só intercepta se
    # a mensagem tem a ver com torrent; senão segue o roteador base.
    if store is not None:
        resposta_torrent = responder_torrent(
            upd.texto, store, agora,
            dispatch=_montar_dispatch_torrent(adapter, store),
            cliente=_obter_cliente_torrent(),
        )
        if resposta_torrent is not None:
            adapter.enviar(upd.chat_id, resposta_torrent)
            return

    resposta = responder(upd.texto, db, agora, store=store)
    adapter.enviar(upd.chat_id, resposta)


def _atender_documento(upd: Update, adapter: Adapter, store: ResourceStore, agora) -> None:
    """Baixa o anexo e roteia por tipo: PDF → tradução (ADR-0050); resto → torrent."""
    from atlas import traducao_cmd

    doc = upd.documento or {}
    nome = doc.get("file_name") or ""
    try:
        dados = adapter.baixar_arquivo(doc.get("file_id"))
    except Exception:  # noqa: BLE001
        _log.exception("Falha ao baixar anexo do Telegram")
        adapter.enviar(upd.chat_id, "❌ não consegui baixar esse arquivo do Telegram.")
        return
    if traducao_cmd.e_pdf(nome, dados):
        _atender_traducao_documento(upd, adapter, store, agora, dados, nome)
    else:
        _atender_torrent_documento(upd, adapter, store, agora, dados, nome)


def _atender_torrent_documento(
    upd: Update, adapter: Adapter, store: ResourceStore, agora, dados: bytes, nome: str
) -> None:
    """Verifica e cria o Torrent a partir dos bytes já baixados (ADR-0049)."""
    from atlas import torrent_cmd

    msg = torrent_cmd.receber_documento(store, dados, nome, upd.chat_id, agora)
    adapter.enviar(upd.chat_id, msg)


def _atender_traducao_documento(
    upd: Update, adapter: Adapter, store: ResourceStore, agora, dados: bytes, nome: str
) -> None:
    """Salva o PDF, cria o Traducao e dispara a tradução (auto-envio ao concluir)."""
    from atlas import traducao_cmd

    res, msg = traducao_cmd.receber_pdf(store, dados, nome, upd.chat_id, agora)
    adapter.enviar(upd.chat_id, msg)
    if res is not None:
        _montar_dispatch_traducao(adapter, store)(res.name, upd.chat_id)


def _montar_dispatch_traducao(adapter: Adapter, store: ResourceStore):
    """Dispatch da tradução vinda do Telegram (ADR-0050): roda o collect
    ``traduzir-pdf`` em thread e, ao concluir, ENVIA o PDF traduzido (ou o caminho
    local se passar do limite do bot); avisa se pausou/errou."""
    from atlas.conversa.acoes import preparar_envio

    def dispatch(label: str, chat_id: int | None) -> None:
        def _run() -> None:
            from atlas.executor import ContextoExecucao
            from atlas.rotinas import obter
            from atlas.routines import Rotina

            try:
                collect = obter("traduzir-pdf")
                rot = Rotina(nome=label, descricao="", label=label, coletar="traduzir-pdf")
                ctx = ContextoExecucao(
                    agora=datetime.now(), rotina=rot, origem="telegram", store=store
                )
                collect(ctx)
            except Exception:  # noqa: BLE001 — status já é marcado pelo collect
                _log.exception("tradução %s (telegram) falhou", label)
            finally:
                if chat_id is not None:
                    _entregar_traducao(adapter, store, label, chat_id, preparar_envio)

        threading.Thread(target=_run, daemon=True, name=f"traduzir-tg-{label}").start()

    return dispatch


def _entregar_traducao(adapter: Adapter, store: ResourceStore, label, chat_id, preparar_envio):
    t = store.get("Traducao", label)
    s = (t.status or {}) if t else {}
    fase = s.get("fase")
    if fase == "pronto" and not s.get("parcial"):
        modo, detalhe = preparar_envio(s.get("saida") or "")
        if modo == "arquivo":
            adapter.enviar_documento(chat_id, detalhe, f"✅ traduzido: {label}")
        elif modo == "grande":
            adapter.enviar(
                chat_id,
                f"✅ traduzido: {label}\n📦 passou do limite do Telegram.\n📁 {detalhe}",
            )
        else:
            adapter.enviar(chat_id, f"✅ traduzido: {label}, mas o arquivo sumiu do disco.")
    elif fase == "pausado" or s.get("parcial"):
        adapter.enviar(chat_id, f"⏸ {label}: pausei (tokens/timeout) — retomo sozinho e te aviso.")
    else:
        adapter.enviar(chat_id, f"❌ {label}: {s.get('erro') or 'falhou na tradução'}")


# Client de torrent em container (ADR-0051): singleton compartilhado. Sentinela
# distingue "ainda não decidi" de "decidi que é None (sem podman → fallback nox)".
_NAO_DECIDIDO = object()
_cliente_torrent = _NAO_DECIDIDO
_monitor_torrent_iniciado = False

# Loja Ownfoil em container (ADR-0052): singleton + flag do supervisor.
_cliente_ownfoil = _NAO_DECIDIDO
_supervisor_ownfoil_iniciado = False
# Intervalo do tick do supervisor (mantém o container no ar e o status fresco).
_OWNFOIL_TICK_S = 300


def _obter_cliente_torrent():
    """``ClienteContainer`` compartilhado quando ``podman`` existe; ``None`` cai no
    fallback ``qbittorrent-nox`` (ADR-0051). Decidido uma vez por processo."""
    global _cliente_torrent
    if _cliente_torrent is _NAO_DECIDIDO:
        import os

        from atlas.torrent import container
        from atlas.torrent.servico import DESTINO_DEFAULT

        if container.disponivel():
            _cliente_torrent = container.ClienteContainer(
                dir_downloads=os.path.expanduser(DESTINO_DEFAULT),
                max_ativos=int(os.environ.get("ATLAS_TORRENT_MAX_CONCURRENT", "3")),
            )
            _log.info("Torrent: usando client em container (podman).")
        else:
            _cliente_torrent = None
    return _cliente_torrent


def _montar_dispatch_torrent(adapter: Adapter, store: ResourceStore):
    """``dispatch(name)`` que inicia um download. No modo **container** (ADR-0051)
    apenas adiciona o ``.torrent`` ao client único (a fila é nativa e o monitor
    único dirige o resto). No fallback **nox** (ADR-0049), sobe o loop por-download
    e, ao terminar, libera o slot do pool e despacha o próximo da fila."""
    from atlas.torrent import servico

    cliente = _obter_cliente_torrent()
    if cliente is not None:
        return _montar_dispatch_torrent_container(adapter, store, cliente)

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


def _montar_dispatch_torrent_container(adapter: Adapter, store: ResourceStore, cliente):
    """``dispatch`` do modo container: garante o container no ar, faz o gate de VPN
    no host (a rede do container não enxerga a iface) e adiciona o ``.torrent`` ao
    client. O monitor único cuida de progresso/conclusão/auto-envio."""
    import os

    from atlas.torrent import download, servico

    def dispatch(name: str) -> None:
        def _run() -> None:
            t = store.get(servico.KIND, name)
            if t is None:
                return
            arquivo = t.spec.get("arquivo")
            vpn = t.spec.get("vpn") or ""
            if vpn and not download.iface_ativa(vpn):
                _falha_torrent(adapter, store, name, f"VPN '{vpn}' não está ativa")
                return
            if not cliente.garantir_no_ar():
                _falha_torrent(adapter, store, name, "container do torrent não subiu")
                return
            try:
                with open(arquivo, "rb") as f:
                    dados = f.read()
            except OSError as exc:
                _falha_torrent(adapter, store, name, str(exc))
                return
            if not cliente.adicionar(dados, os.path.basename(arquivo or name)):
                _falha_torrent(adapter, store, name, "falha ao adicionar no client")

        threading.Thread(target=_run, daemon=True, name=f"torrent-add-{name[:8]}").start()

    return dispatch


def _falha_torrent(adapter: Adapter, store: ResourceStore, name: str, motivo: str) -> None:
    from atlas.torrent import servico

    servico._patch_status(store, name, {"fase": servico.ERRO, "mensagem": motivo})
    t = store.get(servico.KIND, name)
    chat = (t.spec.get("origem_chat") if t else None)
    nome = (t.spec.get("nome") if t else None) or name
    if chat is not None:
        adapter.enviar(int(chat), f"❌ falhou: {nome}\n{motivo}")


def _iniciar_monitor_torrent(adapter: Adapter, store: ResourceStore) -> None:
    """Sobe a thread única do monitor de torrents em container (ADR-0051): poll do
    client → atualiza recursos → auto-envia ao concluir. No-op sem podman (o modo
    nox tem um loop por-download). Uma vez por processo."""
    global _monitor_torrent_iniciado
    if _monitor_torrent_iniciado:
        return
    cliente = _obter_cliente_torrent()
    if cliente is None:
        return
    from atlas.torrent import monitor

    def _enviar(chat_id: int, caminho: str, nome: str) -> None:
        _auto_enviar_torrent(adapter, chat_id, caminho, nome)

    monitor.monitorar(store, cliente, notificar=adapter.enviar, enviar=_enviar)
    _monitor_torrent_iniciado = True


def _obter_cliente_ownfoil():
    """``ClienteOwnfoil`` compartilhado quando ``podman`` existe; ``None`` sem podman
    (a loja simplesmente não sobe). Decidido uma vez por processo (ADR-0052)."""
    global _cliente_ownfoil
    if _cliente_ownfoil is _NAO_DECIDIDO:
        from atlas.ownfoil import container

        _cliente_ownfoil = container.ClienteOwnfoil() if container.disponivel() else None
        if _cliente_ownfoil is not None:
            _log.info("Ownfoil: usando loja em container (podman).")
    return _cliente_ownfoil


def _iniciar_supervisor_ownfoil(store: ResourceStore) -> None:
    """Sobe a thread única que garante a loja Ownfoil no ar (ADR-0052) e mantém o
    recurso ``Ownfoil/loja`` fresco (rodando, nº de jogos). No-op sem podman. Uma
    vez por processo. Best-effort — nunca derruba o boot."""
    global _supervisor_ownfoil_iniciado
    if _supervisor_ownfoil_iniciado:
        return
    cliente = _obter_cliente_ownfoil()
    if cliente is None:
        return
    from atlas.ownfoil import servico

    def _loop() -> None:
        # 1º tick garante o container; ticks seguintes só ressincronizam o status
        # (o próprio Ownfoil re-escaneia o acervo no scheduler dele).
        servico.garantir(store, cliente, datetime.now())
        while True:
            time.sleep(_OWNFOIL_TICK_S)
            try:
                servico.garantir(store, cliente, datetime.now())
            except Exception:  # noqa: BLE001
                _log.exception("Ownfoil: falha no tick do supervisor; seguindo.")

    threading.Thread(target=_loop, daemon=True, name="ownfoil-supervisor").start()
    _supervisor_ownfoil_iniciado = True


def _auto_enviar_torrent(adapter: Adapter, chat_id: int, caminho: str, nome: str) -> None:
    """Auto-envio ao concluir (ADR-0051): arquivo único que cabe no Telegram vai
    como documento; pasta/arquivo grande já foi anunciado por caminho na
    notificação de conclusão — aqui fica em silêncio para não duplicar."""
    import os

    from atlas.conversa.acoes import preparar_envio

    if os.path.isdir(caminho):
        return  # pasta (jogo/ISO): a notificação de conclusão já deu o caminho
    enviar_doc = getattr(adapter, "enviar_documento", None)
    modo, detalhe = preparar_envio(caminho)
    if modo == "arquivo" and enviar_doc is not None:
        enviar_doc(chat_id, detalhe, f"📎 {nome}")


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

    # Keep-awake (ADR-0050): a máquina não suspende enquanto o Atlas roda.
    from atlas import keepawake

    _inibidor = keepawake.iniciar()
    import atexit

    atexit.register(keepawake.parar, _inibidor)

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

        _cli_torrent = _obter_cliente_torrent()
        _iniciar_monitor_torrent(adapter, store)  # ADR-0051: monitor único (container)
        n_torrent = _torrent_servico.retomar_no_boot(
            store,
            datetime.now(),
            dispatch=_montar_dispatch_torrent(adapter, store),
            container=_cli_torrent is not None,
        )
        if n_torrent:
            _log.warning("Boot: %d torrent(s) retomado(s)/enfileirado(s).", n_torrent)
    except Exception:  # noqa: BLE001
        _log.exception("Falha ao retomar torrents no boot; seguindo.")

    # Loja Ownfoil (ADR-0052): sobe o container e mantém o recurso Ownfoil/loja
    # fresco. Best-effort — não pode derrubar o boot.
    try:
        _iniciar_supervisor_ownfoil(store)
    except Exception:  # noqa: BLE001
        _log.exception("Falha ao iniciar supervisor do Ownfoil no boot; seguindo.")

    # Camada NL global (ADR-0050): semeia os Binding default e carimba
    # interface=telegram nos recursos participantes. Idempotente, best-effort.
    try:
        from atlas.conversa import binding as _binding

        _binding.aplicar_seeds(store, datetime.now())
        _binding.carimbar_participacao(store, datetime.now())
    except Exception:  # noqa: BLE001
        _log.exception("Falha ao semear a camada NL (Binding); seguindo.")

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
