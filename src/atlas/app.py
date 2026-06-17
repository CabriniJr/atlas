"""Wiring do bot Atlas: long-poll → filtro de dono → handler → resposta.

Loop de operação (Camada 0). A análise (IA) entra nas rotinas agendadas; o MVP
foca no registro rápido e em /status.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

import atlas.rotinas.resumo_diario  # noqa: F401 — registra collect no registry
import atlas.rotinas.treino  # noqa: F401 — registra collect de treino
from atlas.alarmes import tick_alarmes
from atlas.comandos import para_telegram
from atlas.config import Config
from atlas.controle import aplicar_overrides
from atlas.core.store import ResourceStore
from atlas.db import Database
from atlas.executor import ContextoExecucao, executar
from atlas.handler import responder
from atlas.rotinas import obter as obter_collect
from atlas.routines import Rotina, carregar_rotinas
from atlas.scheduler import catch_up, tick
from atlas.sync import sincronizar_store
from atlas.telegram import TelegramAdapter

_log = logging.getLogger("atlas")


@dataclass
class Update:
    """Mensagem normalizada vinda do canal."""

    update_id: int
    chat_id: int
    user_id: int
    texto: str


class Adapter(Protocol):
    def enviar(self, chat_id: int, texto: str) -> None: ...


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
    if not upd.texto:
        return
    resposta = responder(upd.texto, db, agora or datetime.now(), store=store)
    adapter.enviar(upd.chat_id, resposta)


def _normalizar(update_cru: dict) -> Update | None:
    msg = update_cru.get("message") or update_cru.get("edited_message")
    if not msg or "text" not in msg:
        return None
    return Update(
        update_id=update_cru["update_id"],
        chat_id=msg["chat"]["id"],
        user_id=msg["from"]["id"],
        texto=msg["text"],
    )


def montar_disparo(db: Database, adapter: Adapter, chat_id: int) -> Callable[[Rotina], object]:
    """Cria o callback que o scheduler usa para disparar uma rotina.

    Embrulha o [executor](executor-e-notificacao): roda o ciclo de vida com
    origem ``agenda`` e notifica o dono pelo Telegram. (Sem invocador de IA por
    enquanto — rotinas com modelo só confirmam; análise real vem com E1-05.)
    """

    def disparar(rotina: Rotina) -> object:
        ctx = ContextoExecucao(agora=datetime.now(), rotina=rotina, origem="agenda", db=db)
        collect = obter_collect(rotina.nome)
        return executar(ctx, db, lambda msg: adapter.enviar(chat_id, msg), collect=collect)

    return disparar


def run(config: Config | None = None) -> None:
    """Inicia o loop de operação do bot (bloqueante)."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = config or Config.from_env()
    db = Database(config.db_path)
    adapter = TelegramAdapter(config.telegram_token, poll_timeout=config.poll_timeout)

    # Registra o menu de comandos do Telegram (best-effort; não derruba o boot).
    try:
        adapter.registrar_comandos(para_telegram())
    except Exception:  # noqa: BLE001 — sem rede/erro de API não impede operar
        _log.warning("Não foi possível registrar os comandos no Telegram (segue mesmo assim).")

    # Carrega rotinas e prepara o agendador.
    carga = carregar_rotinas(Path(config.routines_dir))
    aplicar_overrides(db, carga.rotinas)  # ativação salva no DB sobrepõe o default (E5-02)
    for erro in carga.erros:
        _log.warning("Rotina ignorada (%s): %s", erro.pasta, erro.mensagem)
    disparar = montar_disparo(db, adapter, config.allowed_user_id)

    # Catch-up dos disparos perdidos enquanto esteve fora do ar (ADR-0006).
    try:
        recuperados = catch_up(datetime.now(), carga.rotinas, db, disparar)
        if recuperados:
            _log.info("Catch-up: %d rotina(s) recuperada(s) no boot.", len(recuperados))
    except Exception:  # noqa: BLE001
        _log.exception("Falha no catch-up de boot; seguindo.")

    store = ResourceStore(config.db_path)
    sincronizar_store(db, store, carga.rotinas)

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
            # Após cada janela de long-poll, verifica agenda e alarmes.
            agora = datetime.now()
            tick(agora, carga.rotinas, db, disparar)
            tick_alarmes(
                agora, db, lambda msg: adapter.enviar(config.allowed_user_id, msg), store=store
            )
        except KeyboardInterrupt:  # noqa: PERF203
            _log.info("Encerrando.")
            break
        except Exception:  # noqa: BLE001 — resiliência: um erro não derruba o loop
            _log.exception("Erro no loop; seguindo.")
