"""Persistência genérica de objetos — ``ResourceStore`` (ADR-0015).

Uma única tabela ``resources`` guarda qualquer kind; os verbos (get/list/apply/
patch/delete) são uniformes. Domínio mora no JSON (coerente com ADR-0002 / P3).
Resiliente (ADR-0006): um objeto corrompido não derruba o ``list`` dos demais.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from typing import Any

from atlas.core.resource import Resource

_log = logging.getLogger("atlas.core")

SCHEMA = """
CREATE TABLE IF NOT EXISTS resources (
    kind          TEXT NOT NULL,
    name          TEXT NOT NULL,
    api_version   TEXT NOT NULL DEFAULT 'atlas/v1',
    labels_json   TEXT,
    spec_json     TEXT,
    status_json   TEXT,
    criado_em     TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    PRIMARY KEY (kind, name)
);
"""


class ResourceJaExiste(Exception):
    """Tentativa de ``create`` de um ``(kind, name)`` que já existe."""


class ResourceNaoEncontrado(Exception):
    """``patch``/``set_status`` em um objeto que não existe."""


class ResourceStore:
    """Store de objetos sobre SQLite. Cria o schema ao abrir (aditivo)."""

    def __init__(self, path: str = ":memory:") -> None:
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)
        self.connection.commit()

    # --- escrita -----------------------------------------------------------

    def create(self, res: Resource, agora: datetime) -> Resource:
        if self.get(res.kind, res.name) is not None:
            raise ResourceJaExiste(f"{res.kind}/{res.name} já existe")
        carimbo = agora.isoformat()
        res.criado_em = carimbo
        res.atualizado_em = carimbo
        self._inserir(res)
        return res

    def apply(self, res: Resource, agora: datetime) -> Resource:
        """Upsert: cria, ou atualiza spec/labels/status preservando ``criado_em``."""
        existente = self.get(res.kind, res.name)
        carimbo = agora.isoformat()
        if existente is None:
            res.criado_em = carimbo
            res.atualizado_em = carimbo
            self._inserir(res)
            return res
        res.criado_em = existente.criado_em
        res.atualizado_em = carimbo
        self._atualizar(res)
        return res

    def patch(self, kind: str, name: str, spec_patch: dict[str, Any], agora: datetime) -> Resource:
        """Merge raso em ``spec``. Erro se o objeto não existe."""
        res = self._exigir(kind, name)
        res.spec.update(spec_patch)
        res.atualizado_em = agora.isoformat()
        self._atualizar(res)
        return res

    def set_status(self, kind: str, name: str, status: dict[str, Any], agora: datetime) -> Resource:
        """Escreve o ``status`` (só o motor deveria chamar). Erro se não existe."""
        res = self._exigir(kind, name)
        res.status = status
        res.atualizado_em = agora.isoformat()
        self._atualizar(res)
        return res

    def delete(self, kind: str, name: str) -> bool:
        cur = self.connection.execute(
            "DELETE FROM resources WHERE kind = ? AND name = ?", (kind, name)
        )
        self.connection.commit()
        return cur.rowcount > 0

    # --- leitura -----------------------------------------------------------

    def get(self, kind: str, name: str) -> Resource | None:
        row = self.connection.execute(
            "SELECT * FROM resources WHERE kind = ? AND name = ?", (kind, name)
        ).fetchone()
        return self._row_to_resource(row) if row is not None else None

    def list(
        self,
        kind: str,
        selector: dict[str, str] | None = None,
        labels: dict[str, str] | None = None,
    ) -> list[Resource]:
        """Lista um kind, opcionalmente filtrando por labels (match exato AND).

        ``labels`` é o nome K8s-idiomático; ``selector`` é um alias legado.
        """
        selector = selector or labels
        rows = self.connection.execute(
            "SELECT * FROM resources WHERE kind = ? ORDER BY name", (kind,)
        ).fetchall()
        out: list[Resource] = []
        for row in rows:
            res = self._row_to_resource_safe(row)
            if res is None:
                continue  # corrompido: pula, não derruba o list (ADR-0006)
            if selector and not self._casa(res, selector):
                continue
            out.append(res)
        return out

    def kinds(self) -> list[str]:
        rows = self.connection.execute(
            "SELECT DISTINCT kind FROM resources ORDER BY kind"
        ).fetchall()
        return [r["kind"] for r in rows]

    # --- internos ----------------------------------------------------------

    def _exigir(self, kind: str, name: str) -> Resource:
        res = self.get(kind, name)
        if res is None:
            raise ResourceNaoEncontrado(f"{kind}/{name} não existe")
        return res

    def _inserir(self, res: Resource) -> None:
        self.connection.execute(
            "INSERT INTO resources (kind, name, api_version, labels_json, spec_json,"
            " status_json, criado_em, atualizado_em) VALUES (?,?,?,?,?,?,?,?)",
            self._campos(res),
        )
        self.connection.commit()

    def _atualizar(self, res: Resource) -> None:
        self.connection.execute(
            "UPDATE resources SET api_version=?, labels_json=?, spec_json=?,"
            " status_json=?, atualizado_em=? WHERE kind=? AND name=?",
            (
                res.api_version,
                json.dumps(res.labels),
                json.dumps(res.spec),
                json.dumps(res.status),
                res.atualizado_em,
                res.kind,
                res.name,
            ),
        )
        self.connection.commit()

    @staticmethod
    def _campos(res: Resource) -> tuple:
        return (
            res.kind,
            res.name,
            res.api_version,
            json.dumps(res.labels),
            json.dumps(res.spec),
            json.dumps(res.status),
            res.criado_em,
            res.atualizado_em,
        )

    @staticmethod
    def _casa(res: Resource, selector: dict[str, str]) -> bool:
        return all(res.labels.get(k) == v for k, v in selector.items())

    @staticmethod
    def _row_to_resource(row: sqlite3.Row) -> Resource:
        return Resource(
            kind=row["kind"],
            name=row["name"],
            api_version=row["api_version"],
            labels=json.loads(row["labels_json"] or "{}"),
            spec=json.loads(row["spec_json"] or "{}"),
            status=json.loads(row["status_json"] or "{}"),
            criado_em=row["criado_em"],
            atualizado_em=row["atualizado_em"],
        )

    @classmethod
    def _row_to_resource_safe(cls, row: sqlite3.Row) -> Resource | None:
        try:
            return cls._row_to_resource(row)
        except (ValueError, TypeError):
            _log.warning("Resource corrompido ignorado: %s/%s", row["kind"], row["name"])
            return None
