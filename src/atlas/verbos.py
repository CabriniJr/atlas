"""Verbos kubectl-like para o chat do Telegram (E0-03 / ADR-0015).

Comandos uniformes que operam sobre qualquer kind no ResourceStore:
  /list <Kind>                    — lista todos os objetos do kind
  /get <Kind> <name>              — busca um objeto específico
  /describe <Kind> <name>        — detalhe completo (spec + status)
  /apply <Kind> <name> [k=v …]   — upsert com campos opcionais
  /delete <Kind> <name>          — remove o objeto

Retorna str com a resposta, ou None se o texto não é um verbo kubectl.
"""

from __future__ import annotations

import json
from datetime import datetime

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore

_VERBOS = {"/list", "/get", "/describe", "/apply", "/delete", "/resources"}


def responder_verbos(texto: str, store: ResourceStore, agora: datetime) -> str | None:
    """Roteia verbos kubectl. Devolve None se o texto não é um verbo."""
    partes = texto.strip().split()
    if not partes or partes[0] not in _VERBOS:
        return None

    cmd = partes[0]

    if cmd == "/list":
        return _cmd_list(partes, store)
    if cmd == "/get":
        return _cmd_get(partes, store)
    if cmd == "/describe":
        return _cmd_describe(partes, store)
    if cmd == "/apply":
        return _cmd_apply(partes, store, agora)
    if cmd == "/delete":
        return _cmd_delete(partes, store)
    if cmd == "/resources":
        return _cmd_resources(store)
    return None


# --- /list <Kind> [-l key=val,key=val] ---------------------------------------


def _cmd_list(partes: list[str], store: ResourceStore) -> str:
    if len(partes) < 2:
        return "Usage: /list <Kind> [-l key=val,…]   e.g. /list Tracker -l domain=fisico"
    kind = partes[1]
    selector = _parse_label_selector(partes[2:])
    recursos = store.list(kind, labels=selector if selector else None)
    if not recursos:
        filtro = f" (selector: {selector})" if selector else ""
        return f"No {kind} objects found{filtro}."
    linhas = [f"  {r.name}" + (f"  [{_status_resumo(r)}]" if r.status else "") for r in recursos]
    return f"{kind} ({len(recursos)})\n" + "\n".join(linhas)


def _status_resumo(r: Resource) -> str:
    return "  ".join(f"{k}={v}" for k, v in list(r.status.items())[:2])


# --- /get <Kind> <name> -------------------------------------------------------


def _cmd_get(partes: list[str], store: ResourceStore) -> str:
    if len(partes) < 3:
        return "Usage: /get <Kind> <name>   e.g. /get Idea ui-web"
    kind, name = partes[1], partes[2]
    r = store.get(kind, name)
    if r is None:
        return f"Not found: {kind}/{name}"
    linhas = [
        f"{r.api_version}/{r.kind}  {r.name}",
        f"created: {r.criado_em}  updated: {r.atualizado_em}",
    ]
    if r.labels:
        linhas.append("labels: " + "  ".join(f"{k}={v}" for k, v in r.labels.items()))
    if r.spec:
        linhas.append("spec:   " + json.dumps(r.spec, ensure_ascii=False))
    if r.status:
        linhas.append("status: " + json.dumps(r.status, ensure_ascii=False))
    return "\n".join(linhas)


# --- /describe <Kind> <name> --------------------------------------------------


def _cmd_describe(partes: list[str], store: ResourceStore) -> str:
    if len(partes) < 3:
        return "Usage: /describe <Kind> <name>   e.g. /describe Tracker weight"
    kind, name = partes[1], partes[2]
    r = store.get(kind, name)
    if r is None:
        return f"Not found: {kind}/{name}"
    secoes = [
        f"Name:       {r.name}",
        f"Kind:       {r.kind}",
        f"API:        {r.api_version}",
        f"Created:    {r.criado_em}",
        f"Updated:    {r.atualizado_em}",
    ]
    if r.labels:
        secoes.append("Labels:")
        secoes.extend(f"  {k}: {v}" for k, v in r.labels.items())
    secoes.append("Spec:")
    if r.spec:
        secoes.extend(f"  {k}: {v}" for k, v in r.spec.items())
    else:
        secoes.append("  (empty)")
    secoes.append("Status:")
    if r.status:
        secoes.extend(f"  {k}: {v}" for k, v in r.status.items())
    else:
        secoes.append("  (empty)")
    return "\n".join(secoes)


# --- /apply <Kind> <name> [k=v …] --------------------------------------------


def _cmd_apply(partes: list[str], store: ResourceStore, agora: datetime) -> str:
    if len(partes) < 3:
        return (
            "Usage: /apply <Kind> <name> [spec.key=val …] [labels.key=val …]\n"
            "e.g. /apply Tracker peso labels.routine=treino"
        )
    kind, name = partes[1], partes[2]
    kv = _parse_kv(partes[3:])

    # Separa labels.* de spec.*
    labels: dict[str, str] = {}
    spec: dict[str, str] = {}
    for k, v in kv.items():
        if k.startswith("labels."):
            labels[k[len("labels."):]] = v
        elif k.startswith("spec."):
            spec[k[len("spec."):]] = v
        else:
            spec[k] = v

    # Merge com existente (preserva campos não mencionados)
    existente = store.get(kind, name)
    if existente is not None:
        merged_labels = {**existente.labels, **labels}
        merged_spec = {**existente.spec, **spec}
        r = Resource(kind=kind, name=name, labels=merged_labels, spec=merged_spec,
                     status=existente.status)
    else:
        r = Resource(kind=kind, name=name, labels=labels, spec=spec)
    store.apply(r, agora)
    return f"✅ {kind}/{name} applied"


# --- /delete <Kind> <name> ---------------------------------------------------


def _cmd_delete(partes: list[str], store: ResourceStore) -> str:
    if len(partes) < 3:
        return "Usage: /delete <Kind> <name>   e.g. /delete Idea obsoleta"
    kind, name = partes[1], partes[2]
    removido = store.delete(kind, name)
    if removido:
        return f"🗑 {kind}/{name} deleted"
    return f"Not found: {kind}/{name}"


# --- /resources — lista todos os kinds presentes no store --------------------


def _cmd_resources(store: ResourceStore) -> str:
    kinds = store.kinds()
    if not kinds:
        return "No resources in store. Create one with /apply <Kind> <name> [key=value …]"
    linhas = []
    for kind in kinds:
        n = len(store.list(kind))
        linhas.append(f"  {kind:<20} {n} object(s)   → /list {kind}")
    header = f"Resources ({len(kinds)} kind(s)):"
    footer = (
        "\nVerbs: /list <Kind>  /get <Kind> <name>  /describe <Kind> <name>"
        "\n       /apply <Kind> <name> [k=v …]  /delete <Kind> <name>"
    )
    return header + "\n" + "\n".join(linhas) + footer


# --- helpers -----------------------------------------------------------------


def _parse_label_selector(partes: list[str]) -> dict[str, str]:
    """Parseia '-l key=val,key=val' ou '-l key=val -l key2=val2'."""
    selector: dict[str, str] = {}
    i = 0
    while i < len(partes):
        tok = partes[i]
        if tok == "-l" and i + 1 < len(partes):
            i += 1
            for par in partes[i].split(","):
                par = par.strip()
                if "=" in par:
                    k, _, v = par.partition("=")
                    selector[k.strip()] = v.strip()
        elif tok.startswith("-l") and len(tok) > 2:
            for par in tok[2:].split(","):
                if "=" in par:
                    k, _, v = par.partition("=")
                    selector[k.strip()] = v.strip()
        i += 1
    return selector


def _parse_kv(tokens: list[str]) -> dict:
    """Parseia tokens 'chave=valor'. Tokens sem '=' são concatenados ao último."""
    spec: dict[str, str] = {}
    chave_atual: str | None = None
    valor_partes: list[str] = []

    def _flush() -> None:
        if chave_atual is not None:
            spec[chave_atual] = " ".join(valor_partes)

    for tok in tokens:
        if "=" in tok:
            _flush()
            k, _, v = tok.partition("=")
            chave_atual = k
            valor_partes = [v] if v else []
        else:
            valor_partes.append(tok)

    _flush()
    return spec
