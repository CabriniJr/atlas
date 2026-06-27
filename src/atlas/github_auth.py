"""GitHub device flow + PAT fallback + git helper escopado (ADR-0027, Fase 3).

"Conectar GitHub" sem callback público (funciona na Tailnet): o backend pede um
``device_code``/``user_code`` ao GitHub, o usuário cola o código em
``github.com/login/device`` e o backend faz *polling* até obter o ``access_token``,
que é **cifrado e guardado** como ``Credential`` daquele dono ([credentials.py]).

Tudo stdlib (``urllib``), zero deps. A função de HTTP (``post``) é injetável para
testes — nunca toca a rede em teste.

Requer um **GitHub OAuth App** com ``client_id`` público em
``ATLAS_GITHUB_CLIENT_ID``. **Fallback:** colar um PAT (``connect_via_pat``).
"""

from __future__ import annotations

import base64
import json
import os
import urllib.parse
import urllib.request

from atlas import credentials as cred
from atlas.core.store import ResourceStore

DEVICE_CODE_URL = "https://github.com/login/device/code"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
API_USER_URL = "https://api.github.com/user"
DEFAULT_SCOPE = "repo read:user"

# erros do device flow que ainda podem virar sucesso (continuar polling)
_PENDING_ERRORS = {"authorization_pending", "slow_down"}


class GitHubAuthError(RuntimeError):
    """Falha na autenticação GitHub (config ausente, token inválido, etc.)."""


def client_id() -> str:
    """``client_id`` público do OAuth App (env ``ATLAS_GITHUB_CLIENT_ID``)."""
    return os.environ.get("ATLAS_GITHUB_CLIENT_ID", "").strip()


def _post_form(url: str, data: dict) -> dict:
    """POST ``application/x-www-form-urlencoded`` → JSON (Accept: application/json)."""
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Accept": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (URL fixa do GitHub)
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str, token: str) -> dict:
    """GET autenticado → JSON (para a API REST do GitHub)."""
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (URL fixa do GitHub)
        return json.loads(resp.read().decode("utf-8"))


def fetch_github_login(token: str, *, get=_get_json) -> str:
    """Resolve o ``login`` (username) do dono do token via API do GitHub."""
    data = get(API_USER_URL, token)
    login = (data or {}).get("login")
    if not login:
        raise GitHubAuthError("não foi possível resolver o usuário GitHub do token")
    return login


# ── device flow ──────────────────────────────────────────────────────────────


def start_device_flow(
    *, cid: str | None = None, scope: str = DEFAULT_SCOPE, post=_post_form
) -> dict:
    """Inicia o device flow: devolve ``device_code``/``user_code``/``verification_uri``."""
    cid = (cid if cid is not None else client_id()).strip()
    if not cid:
        raise GitHubAuthError("ATLAS_GITHUB_CLIENT_ID não configurado — use o fallback de PAT.")
    return post(DEVICE_CODE_URL, {"client_id": cid, "scope": scope})


def poll_access_token(device_code: str, *, cid: str | None = None, post=_post_form) -> dict:
    """Faz um *poll*. Devolve ``status`` ``pending|connected|error`` (+ campos)."""
    cid = (cid if cid is not None else client_id()).strip()
    out = post(
        ACCESS_TOKEN_URL,
        {
            "client_id": cid,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        },
    )
    if out.get("access_token"):
        return {"status": "connected", **out}
    err = out.get("error", "")
    if err in _PENDING_ERRORS:
        res = {"status": "pending", "error": err}
        if "interval" in out:
            res["interval"] = out["interval"]
        return res
    return {"status": "error", "error": err or "unknown"}


def complete_device_login(
    store: ResourceStore,
    *,
    owner: str,
    device_code: str,
    cid: str | None = None,
    post=_post_form,
) -> dict:
    """*Poll* + persiste a ``Credential`` cifrada quando o token chega.

    Devolve ``{"status": "connected", "credential": <id>}`` no sucesso, ou o
    resultado do poll (``pending``/``error``) sem gravar nada.
    """
    out = poll_access_token(device_code, cid=cid, post=post)
    if out["status"] != "connected":
        return out
    cid_cred = cred.save_credential(
        store,
        owner=owner,
        provider="github",
        secret=out["access_token"],
        account=owner,
        scopes=out.get("scope", ""),
    )
    return {"status": "connected", "credential": cid_cred}


# ── PAT fallback ─────────────────────────────────────────────────────────────


def connect_via_pat(store: ResourceStore, *, owner: str, token: str, account: str = "") -> str:
    """Salva um PAT colado como ``Credential`` cifrada. Devolve o id."""
    token = (token or "").strip()
    if not token:
        raise GitHubAuthError("token vazio")
    return cred.save_credential(
        store, owner=owner, provider="github", secret=token, account=account or owner
    )


# ── resolução / git helper escopado ──────────────────────────────────────────


def token_for_owner(store: ResourceStore, owner: str) -> str | None:
    """Token GitHub do dono (descifrado do cofre), ou ``None`` se não conectado."""
    if not owner:
        return None
    return cred.get_secret(cred.credential_id("github", owner))


def git_auth_args(token: str | None) -> list[str]:
    """Args ``-c`` para autenticar uma chamada git **sem persistir** o token.

    Injeta ``Authorization: Basic base64("x-access-token:<token>")`` via
    ``http.extraheader`` — vale por invocação, não vai para ``.git/config``.
    """
    if not token:
        return []
    raw = f"x-access-token:{token}".encode()
    b64 = base64.b64encode(raw).decode("ascii")
    return ["-c", f"http.extraheader=Authorization: Basic {b64}"]
