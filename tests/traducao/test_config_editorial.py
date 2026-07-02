"""Configs editoriais do Traducao (ADR-0033): min_fonte_pct e notas_rodape."""

from __future__ import annotations

from atlas.traducao.traducao_ia import ConfigTraducao


def test_config_tem_defaults_editoriais():
    c = ConfigTraducao()
    assert c.min_fonte_pct == 90
    assert c.notas_rodape is False


def test_config_aceita_override():
    c = ConfigTraducao(min_fonte_pct=80, notas_rodape=True)
    assert c.min_fonte_pct == 80
    assert c.notas_rodape is True
