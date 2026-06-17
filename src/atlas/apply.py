"""Loader de manifestos declarativos (``atlas apply -f``).

Lê arquivos YAML multi-doc no shape ``{kind, name, labels, spec, status}`` e os
aplica via a API HTTP (``PUT /apis/atlas/v1/<kind>/<name>``). É um **cliente** da
API — não conhece domínio nem escreve no store direto (ADR-0015/ADR-0017).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

import yaml

# Assinatura do transporte HTTP injetável (testabilidade): recebe método, URL,
# corpo e headers; devolve o corpo da resposta.
Sender = Callable[[str, str, bytes, dict[str, str]], bytes]


class ManifestoInvalido(ValueError):
    """Manifesto malformado ou faltando campos obrigatórios."""


def parse_manifests(text: str) -> list[dict]:
    """Parseia YAML multi-doc em uma lista de manifestos validados.

    Cada documento precisa ser um mapa com ``kind`` e ``name``. Documentos
    vazios (``None``) são ignorados. YAML inválido vira ``ManifestoInvalido``.
    """
    try:
        docs = [d for d in yaml.safe_load_all(text) if d is not None]
    except yaml.YAMLError as exc:
        raise ManifestoInvalido(f"YAML inválido: {exc}") from exc
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
    send: Sender | None = None,
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


_DEFAULT_URL = os.environ.get("ATLAS_API_URL", "http://127.0.0.1:8080")


def send_http(method: str, url: str, body: bytes, headers: dict[str, str]) -> bytes:
    """Realiza a chamada HTTP real. Erros viram mensagens claras (ADR-0006)."""
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise RuntimeError(
                "401 não autorizado — verifique --token / ATLAS_API_TOKEN"
            ) from exc
        raise RuntimeError(f"HTTP {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"falha ao conectar em {url}: {exc.reason}") from exc


def cli_apply(argv: list[str]) -> int:
    """Subcomando ``atlas apply -f <arquivo>``. Retorna o código de saída."""
    p = argparse.ArgumentParser(prog="atlas apply")
    p.add_argument("-f", "--file", required=True, help="manifesto YAML")
    p.add_argument("--api-url", default=_DEFAULT_URL, help="URL base da API")
    p.add_argument(
        "--token",
        default=os.environ.get("ATLAS_API_TOKEN"),
        help="Bearer token (ou ATLAS_API_TOKEN)",
    )
    p.add_argument(
        "--dry-run", action="store_true", help="valida e mostra, sem aplicar"
    )
    args = p.parse_args(argv)

    try:
        with open(args.file, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        print(f"✗ não foi possível ler {args.file}: {exc}", file=sys.stderr)
        return 1

    try:
        manifests = parse_manifests(text)
    except ManifestoInvalido as exc:
        print(f"✗ manifesto inválido: {exc}", file=sys.stderr)
        return 1

    res = apply_manifests(
        manifests, args.api_url, args.token, dry_run=args.dry_run
    )

    prefixo = "[dry-run] " if args.dry_run else ""
    for ref in res.aplicados:
        print(f"{prefixo}✓ {ref}")
    for ref, erro in res.falhas:
        print(f"✗ {ref}: {erro}", file=sys.stderr)

    return 0 if res.ok else 1
