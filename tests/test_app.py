"""Testes do processamento de update (segurança: só o dono é atendido)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from atlas.app import Update, ciclo_scheduler, montar_disparo, processar_update
from atlas.config import Config
from atlas.db import Database
from atlas.routines import Rotina
from atlas.scheduler import tick


class _FakeAdapter:
    def __init__(self) -> None:
        self.enviados: list[tuple[int, str]] = []

    def enviar(self, chat_id: int, texto: str) -> None:
        self.enviados.append((chat_id, texto))


_CFG = Config(telegram_token="x", allowed_user_id=42)


def test_disparo_agendado_executa_e_notifica_o_dono():
    db = Database(":memory:")
    adapter = _FakeAdapter()
    agora = datetime(2026, 6, 16, 21, 0)
    rotina = Rotina(nome="ping", descricao="d", agenda="@every 1m", modelo="none")
    # último run 70s atrás → vencido
    db.connection.execute(
        "INSERT INTO routine_state (rotina, chave, valor, atualizado_em) VALUES (?,?,?,?)",
        ("ping", "ultimo_run", (agora - timedelta(seconds=70)).isoformat(), agora.isoformat()),
    )
    db.connection.commit()

    disparar = montar_disparo(db, adapter, chat_id=42)
    resultados = tick(agora, [rotina], db, disparar)

    assert len(resultados) == 1
    assert adapter.enviados and adapter.enviados[0][0] == 42  # notificou o dono
    assert db.connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1


def test_dono_e_atendido_com_reg():
    """Dono envia /reg → respondido e atividade gravada (barreira E1-11)."""
    db = Database(":memory:")
    adapter = _FakeAdapter()
    upd = Update(update_id=1, chat_id=42, user_id=42, texto="/reg treino de perna")

    processar_update(upd, _CFG, db, adapter, agora=datetime(2026, 6, 16, 21, 0))

    assert len(adapter.enviados) == 1
    assert db.connection.execute("SELECT COUNT(*) AS n FROM activities").fetchone()["n"] == 1


def test_estranho_e_ignorado():
    db = Database(":memory:")
    adapter = _FakeAdapter()
    upd = Update(update_id=1, chat_id=999, user_id=999, texto="oi")

    processar_update(upd, _CFG, db, adapter, agora=datetime(2026, 6, 16, 21, 0))

    assert adapter.enviados == []
    assert db.connection.execute("SELECT COUNT(*) AS n FROM activities").fetchone()["n"] == 0


# ── ciclo_scheduler roda independente do Telegram (regressão) ───────────────
# Um token/rede do Telegram inválido não pode travar retomada de jobs pausados
# (ADR-0035) — por isso ciclo_scheduler não recebe o adapter, só o necessário
# pro agendador/retomada. Ver app.run(): o long-poll e o ciclo_scheduler agora
# são try/except separados, exatamente pra essa falha não se propagar.


@dataclass
class _FakeRes:
    name: str
    status: dict = field(default_factory=dict)


class _FakeStoreRetomada:
    def __init__(self, por_kind: dict[str, list[_FakeRes]]):
        self._por_kind = por_kind

    def kinds(self):
        return list(self._por_kind)

    def list(self, kind):
        return list(self._por_kind.get(kind, []))

    def set_status(self, kind, name, status, agora):
        for r in self._por_kind.get(kind, []):
            if r.name == name:
                r.status = status


def test_ciclo_scheduler_dispara_retomada_sem_depender_do_telegram():
    """Regressão: ciclo_scheduler não recebe adapter — é impossível que uma
    falha no Telegram (ex.: token inválido) impeça um job pausado de retomar."""
    db = Database(":memory:")
    agora = datetime(2026, 7, 2, 13, 46, 0)
    passado = agora - timedelta(minutes=1)
    store = _FakeStoreRetomada({
        "Traducao": [
            _FakeRes(name="livro", status={"fase": "pausado", "retoma_em": passado.isoformat(),
                                            "retoma_collect": "traduzir-pdf"}),
        ]
    })
    chamados = []

    def disparar_retomada(kind, name, collect):
        chamados.append((kind, name, collect))

    ciclo_scheduler(agora, [], db, lambda r: None, lambda msg: None, store, disparar_retomada)

    assert chamados == [("Traducao", "livro", "traduzir-pdf")]
