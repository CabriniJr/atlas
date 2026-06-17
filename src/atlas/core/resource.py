"""O objeto uniforme do Atlas: ``Resource`` (ADR-0015).

A forma espelha o Kubernetes: ``apiVersion``, ``kind``, ``metadata`` (name,
labels, timestamps), ``spec`` (intenção do usuário) e ``status`` (preenchido pelo
motor). O store não conhece domínio — só objetos (P3, agnóstico).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

API_VERSION = "atlas/v1"


@dataclass
class Resource:
    """Um objeto do Atlas. Identidade = ``(kind, name)``."""

    kind: str
    name: str
    api_version: str = API_VERSION
    labels: dict[str, str] = field(default_factory=dict)
    spec: dict[str, Any] = field(default_factory=dict)
    status: dict[str, Any] = field(default_factory=dict)
    criado_em: str | None = None
    atualizado_em: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serializa na forma K8s (apiVersion/kind/metadata/spec/status)."""
        return {
            "apiVersion": self.api_version,
            "kind": self.kind,
            "metadata": {
                "name": self.name,
                "labels": self.labels,
                "criado_em": self.criado_em,
                "atualizado_em": self.atualizado_em,
            },
            "spec": self.spec,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Resource:
        """Reconstrói a partir da forma K8s. Tolera campos ausentes."""
        meta = d.get("metadata") or {}
        return cls(
            kind=d["kind"],
            name=meta["name"],
            api_version=d.get("apiVersion", API_VERSION),
            labels=meta.get("labels") or {},
            spec=d.get("spec") or {},
            status=d.get("status") or {},
            criado_em=meta.get("criado_em"),
            atualizado_em=meta.get("atualizado_em"),
        )
