"""Loader de manifestos declarativos (``atlas apply -f``).

Lê arquivos YAML multi-doc no shape ``{kind, name, labels, spec, status}`` e os
aplica via a API HTTP (``PUT /apis/atlas/v1/<kind>/<name>``). É um **cliente** da
API — não conhece domínio nem escreve no store direto (ADR-0015/ADR-0017).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import yaml


class ManifestoInvalido(ValueError):
    """Manifesto malformado ou faltando campos obrigatórios."""


def parse_manifests(text: str) -> list[dict]:
    """Parseia YAML multi-doc em uma lista de manifestos validados.

    Cada documento precisa ser um mapa com ``kind`` e ``name``. Documentos
    vazios (``None``) são ignorados.
    """
    docs = [d for d in yaml.safe_load_all(text) if d is not None]
    for i, d in enumerate(docs):
        if not isinstance(d, dict):
            raise ManifestoInvalido(f"documento {i}: não é um mapa")
        if not d.get("kind"):
            raise ManifestoInvalido(f"documento {i}: falta 'kind'")
        if not d.get("name"):
            raise ManifestoInvalido(
                f"documento {i} ({d['kind']}): falta 'name'"
            )
    return docs


_API_PREFIX = "/apis/atlas/v1"


def build_request(
    api_url: str, manifest: dict, token: str | None = None
) -> tuple[str, str, bytes, dict[str, str]]:
    """Monta a chamada ``PUT`` para um manifesto. Função pura (sem rede)."""
    kind = manifest["kind"]
    name = manifest["name"]
    url = f"{api_url.rstrip('/')}{_API_PREFIX}/{kind}/{name}"
    body = json.dumps(
        {"labels": manifest.get("labels", {}), "spec": manifest.get("spec", {})}
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return ("PUT", url, body, headers)


@dataclass
class ResultadoApply:
    """Resumo de uma aplicação de manifestos (ADR-0006: resiliente)."""

    aplicados: list[str] = field(default_factory=list)
    falhas: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.falhas


def apply_manifests(
    manifests: list[dict],
    api_url: str,
    token: str | None = None,
    *,
    dry_run: bool = False,
    send=None,
) -> ResultadoApply:
    """Aplica cada manifesto via ``send(method, url, body, headers)``.

    Falha num objeto é registrada e **não** interrompe os demais. Em
    ``dry_run`` nenhuma chamada é feita.
    """
    if send is None:
        send = send_http
    res = ResultadoApply()
    for m in manifests:
        ref = f"{m['kind']}/{m['name']}"
        method, url, body, headers = build_request(api_url, m, token)
        if dry_run:
            res.aplicados.append(ref)
            continue
        try:
            send(method, url, body, headers)
            res.aplicados.append(ref)
        except Exception as exc:  # noqa: BLE001 — resiliência por objeto
            res.falhas.append((ref, str(exc)))
    return res
