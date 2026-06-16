"""Camada de dados do Atlas (ADR-0002 — modelo de dados SQLite).

O domínio específico vive em ``activities.dados_json`` — domínio nunca vira
coluna, para manter o motor agnóstico (P3).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

# Colunas que guardam JSON: dict/list são serializados na escrita e
# desserializados na leitura.
_JSON_COLUMNS = {"dados_json", "valor"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    id         INTEGER PRIMARY KEY,
    ts         TEXT    NOT NULL,
    dominio    TEXT    NOT NULL,
    rotina     TEXT    NOT NULL,
    texto_cru  TEXT,
    dados_json TEXT
);

CREATE TABLE IF NOT EXISTS goals (
    id        INTEGER PRIMARY KEY,
    titulo    TEXT    NOT NULL,
    categoria TEXT,
    horizonte TEXT,
    alvo      REAL,
    unidade   TEXT,
    progresso REAL    NOT NULL DEFAULT 0,
    prazo     TEXT,
    status    TEXT    NOT NULL DEFAULT 'ativa'
);

CREATE TABLE IF NOT EXISTS goal_links (
    id           INTEGER PRIMARY KEY,
    activity_id  INTEGER NOT NULL REFERENCES activities(id),
    goal_id      INTEGER NOT NULL REFERENCES goals(id),
    contribuicao REAL    NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS books (
    id             INTEGER PRIMARY KEY,
    titulo         TEXT    NOT NULL,
    pagina_atual   INTEGER NOT NULL DEFAULT 0,
    total_paginas  INTEGER,
    percentual     REAL    NOT NULL DEFAULT 0,
    ultimo_visto_ts TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY,
    rotina       TEXT    NOT NULL,
    iniciado_em  TEXT    NOT NULL,
    terminado_em TEXT,
    status       TEXT    NOT NULL,
    camada       TEXT    NOT NULL,
    gate_passou  INTEGER,
    tokens_in    INTEGER,
    tokens_out   INTEGER,
    custo_usd    REAL,
    ref_saida    TEXT
);

CREATE TABLE IF NOT EXISTS routine_state (
    rotina        TEXT NOT NULL,
    chave         TEXT NOT NULL,
    valor         TEXT,
    atualizado_em TEXT NOT NULL,
    PRIMARY KEY (rotina, chave)
);

-- Pool de ideias/desenvolvimento (ADR-0014). Captura de ideias/tarefas/lições.
CREATE TABLE IF NOT EXISTS ideas (
    id            INTEGER PRIMARY KEY,
    tipo          TEXT    NOT NULL DEFAULT 'ideia',
    titulo        TEXT    NOT NULL,
    corpo         TEXT,
    prioridade    INTEGER NOT NULL DEFAULT 100,
    estado        TEXT    NOT NULL DEFAULT 'capturada',
    rotina_alvo   TEXT,
    erro          TEXT,
    criado_em     TEXT    NOT NULL,
    atualizado_em TEXT    NOT NULL
);
"""


class Database:
    """Acesso ao SQLite do Atlas. Cria o schema ao abrir."""

    def __init__(self, path: str = ":memory:") -> None:
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self) -> None:
        # Idempotente (migração mínima): todas as tabelas usam
        # ``CREATE TABLE IF NOT EXISTS``, então rodar o schema num banco já
        # existente apenas cria o que falta (ex.: a tabela ``ideas``) sem
        # tocar nos dados. Ver ADR-0014 / modelo-de-dados (migração de schema).
        self.connection.executescript(SCHEMA)
        self.connection.commit()

    def insert(self, table: str, **fields: Any) -> int:
        """Insere uma linha e devolve o id gerado. Serializa colunas JSON."""
        cols = list(fields)
        values = [self._encode(c, fields[c]) for c in cols]
        placeholders = ", ".join("?" for _ in cols)
        sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
        cur = self.connection.execute(sql, values)
        self.connection.commit()
        return int(cur.lastrowid)

    def get(self, table: str, row_id: int) -> dict[str, Any] | None:
        """Busca uma linha por id. Desserializa colunas JSON."""
        row = self.connection.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
        return self._row_to_dict(row) if row is not None else None

    @staticmethod
    def _encode(column: str, value: Any) -> Any:
        if column in _JSON_COLUMNS and value is not None and not isinstance(value, str):
            return json.dumps(value)
        return value

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        out = dict(row)
        for col in _JSON_COLUMNS:
            if out.get(col) is not None and isinstance(out[col], str):
                out[col] = json.loads(out[col])
        return out
