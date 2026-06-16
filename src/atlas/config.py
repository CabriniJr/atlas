"""Configuração do Atlas por variáveis de ambiente.

Segredos (token) e identidade ficam fora do versionamento (seguranca.md).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass
class Config:
    """Configuração de execução do bot."""

    telegram_token: str
    allowed_user_id: int
    db_path: str = "atlas.sqlite"
    routines_dir: str = "routines"
    poll_timeout: int = 30

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        """Lê a config do ambiente. Levanta ValueError se faltar algo essencial."""
        env = os.environ if env is None else env

        token = env.get("TELEGRAM_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_TOKEN não definido no ambiente")

        user_raw = env.get("ATLAS_ALLOWED_USER_ID")
        if not user_raw:
            raise ValueError("ATLAS_ALLOWED_USER_ID não definido no ambiente")
        try:
            allowed_user_id = int(user_raw)
        except ValueError as exc:
            raise ValueError(
                "ATLAS_ALLOWED_USER_ID deve ser um número (seu ID do Telegram)"
            ) from exc

        return cls(
            telegram_token=token,
            allowed_user_id=allowed_user_id,
            db_path=env.get("ATLAS_DB_PATH", "atlas.sqlite"),
            routines_dir=env.get("ATLAS_ROUTINES_DIR", "routines"),
            poll_timeout=int(env.get("ATLAS_POLL_TIMEOUT", "30")),
        )
