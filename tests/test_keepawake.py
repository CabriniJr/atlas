"""Keep-awake — inibidor de suspensão (ADR-0050)."""

from __future__ import annotations

from atlas import keepawake


def test_comando_bloqueia_sleep_idle_e_tampa():
    cmd = keepawake.comando()
    assert cmd[0] == "systemd-inhibit"
    assert "--what=sleep:idle:handle-lid-switch" in cmd
    assert "--mode=block" in cmd
    assert cmd[-2:] == ["sleep", "infinity"]


def test_iniciar_sem_binario_devolve_none(monkeypatch):
    monkeypatch.setattr(keepawake.shutil, "which", lambda _b: None)
    assert keepawake.iniciar() is None


def test_parar_none_nao_quebra():
    keepawake.parar(None)  # não levanta
