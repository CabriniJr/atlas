"""Sessões de login em memória (ADR-0027, Fase 4).

Login → **sessão** (token opaco aleatório) → identifica o usuário em cada request
(cookie httpOnly, ver ``api``). Em memória (perde no restart, como os runs
agênticos — aceitável; o usuário só refaz login). TTL configurável por
``ATLAS_SESSION_TTL`` (segundos, default 7 dias).

O ``ATLAS_API_TOKEN``/loopback continua válido como **admin** (retrocompat) — isso
é tratado no ``api``, fora daqui.
"""

from __future__ import annotations

import os
import secrets as _secrets
import threading
import time

_DEFAULT_TTL = int(os.environ.get("ATLAS_SESSION_TTL", str(7 * 24 * 3600)))

_sessions: dict[str, dict] = {}
_lock = threading.Lock()


def reset() -> None:
    """Esquece todas as sessões (testes / logout global)."""
    with _lock:
        _sessions.clear()


def create_session(
    user: str, *, role: str = "member", ttl_seconds: int | None = None, now: float | None = None
) -> str:
    """Cria uma sessão e devolve o token opaco."""
    now = time.time() if now is None else now
    ttl = _DEFAULT_TTL if ttl_seconds is None else ttl_seconds
    token = _secrets.token_urlsafe(32)
    with _lock:
        _sessions[token] = {
            "user": user,
            "role": role,
            "created_at": now,
            "expires_at": now + ttl,
        }
    return token


def resolve_session(token: str, *, now: float | None = None) -> dict | None:
    """Devolve a sessão (``user``/``role``) se válida e não expirada; senão ``None``."""
    if not token:
        return None
    now = time.time() if now is None else now
    with _lock:
        sess = _sessions.get(token)
        if sess is None:
            return None
        if now >= sess["expires_at"]:
            del _sessions[token]
            return None
        return dict(sess)


def destroy_session(token: str) -> bool:
    """Invalida um token. ``True`` se existia."""
    with _lock:
        return _sessions.pop(token, None) is not None
