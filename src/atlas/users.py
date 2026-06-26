"""Usuários e senha local (ADR-0027, Fase 4).

O Kind ``User`` guarda só **metadados** (``display_name``, ``role``). O segredo de
login — um **verificador PBKDF2** (não a senha) — vai **cifrado no cofre**
(``secrets_store``), chaveado por ``login-<user>``. A senha nunca entra no spec do
recurso nem trafega para o front.

Convenção: ``role`` ∈ {``member``, ``admin``}. O ``admin`` enxerga tudo (Fase 5);
o portador do ``ATLAS_API_TOKEN``/loopback age como admin (retrocompat).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from base64 import b64decode, b64encode
from datetime import datetime

from atlas import secrets_store
from atlas.core.resource import Resource
from atlas.core.store import ResourceStore

_PBKDF2_ITERS = 240_000
_ALGO = "pbkdf2_sha256"


def normalize_name(name: str) -> str:
    """Nome de usuário estável e seguro (slug): minúsculo, ``[a-z0-9._-]``."""
    base = re.sub(r"\s+", "-", (name or "").strip().lower())
    slug = re.sub(r"[^a-z0-9._-]+", "-", base).strip("-")
    if not slug:
        raise ValueError(f"nome de usuário inválido: {name!r}")
    return slug


def _login_key(name: str) -> str:
    return f"login-{name}"


def _hash_password(password: str, *, salt: bytes | None = None, iters: int = _PBKDF2_ITERS) -> str:
    """Verificador ``pbkdf2_sha256$iters$salt_b64$hash_b64`` (salt aleatório)."""
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters)
    return f"{_ALGO}${iters}${b64encode(salt).decode()}${b64encode(dk).decode()}"


def set_password(name: str, password: str) -> None:
    """Calcula o verificador PBKDF2 e o guarda cifrado no cofre."""
    name = normalize_name(name)
    if not password:
        raise ValueError("senha vazia")
    secrets_store.put_secret(_login_key(name), _hash_password(password))


def verify_password(name: str, password: str) -> bool:
    """Confere a senha contra o verificador do cofre (comparação constante)."""
    try:
        name = normalize_name(name)
    except ValueError:
        return False
    stored = secrets_store.get_secret(_login_key(name))
    if not stored:
        return False
    try:
        algo, iters_s, salt_b64, _hash_b64 = stored.split("$")
    except ValueError:
        return False
    if algo != _ALGO:
        return False
    calc = _hash_password(password, salt=b64decode(salt_b64), iters=int(iters_s))
    return hmac.compare_digest(calc, stored)


def create_user(
    store: ResourceStore,
    name: str,
    *,
    display_name: str = "",
    role: str = "member",
    password: str | None = None,
    agora: datetime | None = None,
) -> Resource:
    """Cria/atualiza o ``User`` (metadados). Se ``password``, define a senha no cofre."""
    name = normalize_name(name)
    agora = agora or datetime.now()
    res = Resource(
        kind="User",
        name=name,
        spec={"display_name": display_name or name, "role": role},
        status={"created_at": agora.isoformat()},
    )
    store.apply(res, agora)
    if password:
        set_password(name, password)
    return res
