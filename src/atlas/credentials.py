"""Credenciais por usuário (ADR-0027, Fase 2) — metadados no store + segredo no cofre.

O Kind ``Credential`` guarda só **metadados** (provider, conta, escopos, status,
``labels.owner``). O **valor secreto** (token) é cifrado em repouso pelo
``secrets_store``, chaveado pelo nome da credencial. O segredo nunca entra no spec
do recurso nem trafega para o front.

Convenção de id/nome da credencial: ``<provider>-<owner>`` (ex.: ``github-luigi``).
"""

from __future__ import annotations

import re
from datetime import datetime

from atlas import secrets_store
from atlas.core.resource import Resource
from atlas.core.store import ResourceStore


def credential_id(provider: str, owner: str) -> str:
    """Id estável e seguro da credencial (também o nome do recurso e a chave do cofre)."""
    base = f"{provider}-{owner}".lower()
    cid = re.sub(r"[^a-z0-9._-]+", "-", base).strip("-")
    if not cid:
        raise ValueError(f"provider/owner inválidos: {provider!r}/{owner!r}")
    return cid


def save_credential(
    store: ResourceStore,
    *,
    owner: str,
    provider: str,
    secret: str,
    account: str = "",
    scopes: str = "",
    agora: datetime | None = None,
) -> str:
    """Cifra o segredo no cofre e persiste o ``Credential`` (metadados). Devolve o id."""
    agora = agora or datetime.now()
    cid = credential_id(provider, owner)
    secrets_store.put_secret(cid, secret)
    store.apply(
        Resource(
            kind="Credential",
            name=cid,
            labels={"owner": owner, "provider": provider},
            spec={
                "provider": provider,
                "account": account,
                "scopes": scopes,
                "status": "conectado",
            },
            status={"connected_at": agora.isoformat()},
        ),
        agora,
    )
    return cid


def get_secret(cid: str) -> str | None:
    """Descifra o segredo da credencial (uso interno; nunca expor ao front)."""
    return secrets_store.get_secret(cid)


def delete_credential(store: ResourceStore, cid: str) -> bool:
    """Remove o segredo do cofre e o recurso Credential. True se algo foi removido."""
    removed = secrets_store.delete_secret(cid)
    if store.delete("Credential", cid):
        removed = True
    return removed


def list_credentials(store: ResourceStore, owner: str | None = None) -> list[Resource]:
    """Lista Credentials (todas ou de um dono). Só metadados — sem segredos."""
    labels = {"owner": owner} if owner else None
    return store.list("Credential", labels=labels)
