"""Sessões de login persistidas em disco (ADR-0027 Fase 4 + item 1.2 do hardening).

Login → **sessão** (token opaco aleatório) → identifica o usuário em cada request
(cookie httpOnly, ver ``api``). A sessão **sobrevive a restart**: o mapa é gravado
em JSON (``ATLAS_SESSIONS_PATH`` ou ``<dir do DB>/sessions.json``). O arquivo guarda
apenas o **hash** do token (sha256), nunca o token em claro — vazar o arquivo não
entrega sessões usáveis. TTL por ``ATLAS_SESSION_TTL`` (segundos, default 7 dias).

O ``ATLAS_API_TOKEN``/loopback continua válido como **admin** (retrocompat) — isso
é tratado no ``api``, fora daqui.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets as _secrets
import threading
import time
from pathlib import Path

_log = logging.getLogger("atlas.sessions")
_DEFAULT_TTL = int(os.environ.get("ATLAS_SESSION_TTL", str(7 * 24 * 3600)))

# Chave do mapa = sha256(token); valor = {user, role, created_at, expires_at}.
_sessions: dict[str, dict] = {}
_loaded = False
_lock = threading.RLock()


def _path() -> Path:
    """Arquivo de persistência (resolvido a cada chamada — env injetável em teste)."""
    p = os.environ.get("ATLAS_SESSIONS_PATH")
    if p:
        return Path(p)
    db = os.environ.get("ATLAS_DB_PATH", "atlas.sqlite")
    return Path(db).resolve().parent / "sessions.json"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _load_locked() -> None:
    """Carrega o mapa do disco para a memória. Degrade: arquivo ausente/corrompido = vazio."""
    _sessions.clear()
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, dict) and "user" in v and "expires_at" in v:
                    _sessions[k] = v
    except FileNotFoundError:
        pass
    except (ValueError, OSError) as exc:
        _log.warning("sessions.json ilegível (%s) — começando vazio", exc)


def _ensure_loaded_locked() -> None:
    global _loaded
    if not _loaded:
        _load_locked()
        _loaded = True


def _save_locked() -> None:
    """Grava o mapa no disco de forma atômica. Degrade: erro de IO não derruba o login."""
    try:
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(_sessions), encoding="utf-8")
        os.replace(tmp, p)
    except OSError as exc:
        _log.warning("falha ao gravar sessions.json (%s)", exc)


def reset() -> None:
    """Esquece todas as sessões (testes / logout global) — também limpa o arquivo."""
    global _loaded
    with _lock:
        _sessions.clear()
        _loaded = True  # estado autoritativo vazio; não recarrega lixo antigo
        _save_locked()


def reload() -> None:
    """Recarrega as sessões do disco (simula restart / re-leitura do arquivo)."""
    global _loaded
    with _lock:
        _loaded = False
        _ensure_loaded_locked()


def create_session(
    user: str, *, role: str = "member", ttl_seconds: int | None = None, now: float | None = None
) -> str:
    """Cria uma sessão, persiste e devolve o token opaco (só o hash vai pro disco)."""
    now = time.time() if now is None else now
    ttl = _DEFAULT_TTL if ttl_seconds is None else ttl_seconds
    token = _secrets.token_urlsafe(32)
    with _lock:
        _ensure_loaded_locked()
        _sessions[_hash(token)] = {
            "user": user,
            "role": role,
            "created_at": now,
            "expires_at": now + ttl,
        }
        _save_locked()
    return token


def resolve_session(token: str, *, now: float | None = None) -> dict | None:
    """Devolve a sessão (``user``/``role``) se válida e não expirada; senão ``None``."""
    if not token:
        return None
    now = time.time() if now is None else now
    with _lock:
        _ensure_loaded_locked()
        key = _hash(token)
        sess = _sessions.get(key)
        if sess is None:
            return None
        if now >= sess["expires_at"]:
            del _sessions[key]
            _save_locked()
            return None
        return dict(sess)


def destroy_session(token: str) -> bool:
    """Invalida um token e persiste. ``True`` se existia."""
    if not token:
        return False
    with _lock:
        _ensure_loaded_locked()
        existed = _sessions.pop(_hash(token), None) is not None
        if existed:
            _save_locked()
        return existed
