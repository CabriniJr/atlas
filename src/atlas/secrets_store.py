"""Cofre de segredos cifrados em repouso (ADR-0027, Fase 1).

Cifra valores sensíveis (tokens de GitHub, etc.) com **Fernet** (AES-128-CBC +
HMAC). A chave mestra vem de ``ATLAS_SECRET_KEY`` (env) ou de um arquivo
``secrets/secret.key`` (perms ``0600``, fora do git) — gerado na primeira vez.

Princípios:
- O segredo **nunca** vai para o spec de um recurso nem trafega para o front.
- Blobs cifrados ficam em ``secrets/credentials/<id>.enc`` (``0600``).
- Perder a chave mestra = perder os segredos cifrados (documentado no ADR).

API:
    encrypt(plaintext) -> str            # token Fernet (base64)
    decrypt(token) -> str
    put_secret(cid, plaintext)           # grava cifrado em disco
    get_secret(cid) -> str | None
    delete_secret(cid) -> bool
    has_secret(cid) -> bool
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class SecretsError(RuntimeError):
    """Falha no cofre de segredos."""


def _base_dir() -> Path:
    return Path(os.environ.get("ATLAS_SECRETS_DIR", "secrets"))


def _key_path() -> Path:
    return _base_dir() / "secret.key"


def _creds_dir() -> Path:
    return _base_dir() / "credentials"


_fernet: Fernet | None = None


def _load_or_create_key() -> bytes:
    """Resolve a chave mestra: env ``ATLAS_SECRET_KEY`` ou arquivo (gera se faltar)."""
    env = os.environ.get("ATLAS_SECRET_KEY")
    if env:
        return env.encode() if isinstance(env, str) else env
    kp = _key_path()
    if kp.exists():
        return kp.read_bytes().strip()
    # gera nova chave com permissão restritiva
    kp.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    kp.write_bytes(key)
    try:
        kp.chmod(0o600)
    except OSError:
        pass
    return key


def _f() -> Fernet:
    global _fernet
    if _fernet is None:
        try:
            _fernet = Fernet(_load_or_create_key())
        except Exception as exc:  # noqa: BLE001
            raise SecretsError(f"chave mestra inválida: {exc}") from exc
    return _fernet


def reset_cache() -> None:
    """Esquece a chave em cache (testes / rotação)."""
    global _fernet
    _fernet = None


def encrypt(plaintext: str) -> str:
    return _f().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _f().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise SecretsError("token cifrado inválido (chave errada ou corrompido)") from exc


# ── persistência por id de credencial ────────────────────────────────────────


def _safe_id(cid: str) -> str:
    if not cid or not re.fullmatch(r"[A-Za-z0-9._-]+", cid):
        raise SecretsError(f"id de credencial inválido: {cid!r}")
    return cid


def _path_for(cid: str) -> Path:
    return _creds_dir() / f"{_safe_id(cid)}.enc"


def put_secret(cid: str, plaintext: str) -> None:
    p = _path_for(cid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(encrypt(plaintext), encoding="utf-8")
    try:
        p.chmod(0o600)
    except OSError:
        pass


def get_secret(cid: str) -> str | None:
    p = _path_for(cid)
    if not p.exists():
        return None
    return decrypt(p.read_text(encoding="utf-8").strip())


def has_secret(cid: str) -> bool:
    return _path_for(cid).exists()


def delete_secret(cid: str) -> bool:
    p = _path_for(cid)
    if p.exists():
        p.unlink()
        return True
    return False
