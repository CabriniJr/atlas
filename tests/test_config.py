"""Testes da configuração por ambiente."""

from __future__ import annotations

import pytest

from atlas.config import Config


def test_from_env_le_valores():
    cfg = Config.from_env({"TELEGRAM_TOKEN": "abc:123", "ATLAS_ALLOWED_USER_ID": "42"})
    assert cfg.telegram_token == "abc:123"
    assert cfg.allowed_user_id == 42
    assert cfg.db_path == "atlas.sqlite"  # default


def test_from_env_sem_token_falha():
    with pytest.raises(ValueError, match="TELEGRAM_TOKEN"):
        Config.from_env({"ATLAS_ALLOWED_USER_ID": "42"})


def test_from_env_sem_user_id_falha():
    with pytest.raises(ValueError, match="ATLAS_ALLOWED_USER_ID"):
        Config.from_env({"TELEGRAM_TOKEN": "abc:123"})
