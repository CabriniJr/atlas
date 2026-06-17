"""Loader de manifestos declarativos (``atlas apply -f``).

Lê arquivos YAML multi-doc no shape ``{kind, name, labels, spec, status}`` e os
aplica via a API HTTP (``PUT /apis/atlas/v1/<kind>/<name>``). É um **cliente** da
API — não conhece domínio nem escreve no store direto (ADR-0015/ADR-0017).
"""

from __future__ import annotations

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
