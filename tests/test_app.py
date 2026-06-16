"""Testes do processamento de update (segurança: só o dono é atendido)."""

from __future__ import annotations

from datetime import datetime, timedelta

from atlas.app import Update, montar_disparo, processar_update
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


def test_dono_e_atendido_e_atividade_registrada():
    db = Database(":memory:")
    adapter = _FakeAdapter()
    upd = Update(update_id=1, chat_id=42, user_id=42, texto="treino de perna")

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
