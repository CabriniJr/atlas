#!/usr/bin/env python3
"""Migração única: Routine → Job no ResourceStore (ADR-0021).

Uso:
    python scripts/migrate_routine_to_job.py [--db atlas.sqlite]

Operações:
  1. Renomeia todos os resources kind=Routine para kind=Job
  2. Renomeia Doc/kind-routine para Doc/kind-job (referência de UI)
  3. Garante que Repo/nora existe com spec.url correto

Idempotente: pode rodar mais de uma vez com segurança.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path


def run(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    agora = datetime.now().isoformat()

    # 1. Routine → Job
    routines = conn.execute(
        "SELECT name FROM resources WHERE kind = 'Routine'"
    ).fetchall()
    migrated = 0
    for row in routines:
        name = row["name"]
        existing_job = conn.execute(
            "SELECT 1 FROM resources WHERE kind = 'Job' AND name = ?", (name,)
        ).fetchone()
        if existing_job:
            # já existe como Job — apaga o Routine duplicado
            conn.execute(
                "DELETE FROM resources WHERE kind = 'Routine' AND name = ?", (name,)
            )
            print(f"  [skip-dup] Routine/{name} → Job/{name} já existia; Routine removido")
        else:
            conn.execute(
                "UPDATE resources SET kind = 'Job', atualizado_em = ? "
                "WHERE kind = 'Routine' AND name = ?",
                (agora, name),
            )
            print(f"  [migrado ] Routine/{name} → Job/{name}")
        migrated += 1
    print(f"  {migrated} routine(s) migrada(s) para Job")

    # 2. Doc/kind-routine → Doc/kind-job
    old_doc = conn.execute(
        "SELECT spec_json FROM resources WHERE kind = 'Doc' AND name = 'kind-routine'"
    ).fetchone()
    if old_doc:
        spec = json.loads(old_doc["spec_json"] or "{}")
        # atualiza corpo para mencionar Job
        new_body = (
            "Job — job agendado ou por trigger (ex-Routine, ADR-0021)\n\n"
            "spec: description, schedule (cron), model, triggers, active\n"
            "status: last_run, run_count\n"
            "labels: model, active\n\n"
            "Listar: /jobs\n"
            "Detalhe: /job <nome>\n"
            "Executar: /run <nome>\n"
            "Ativar/Desativar: /activate <nome>   /deactivate <nome>\n"
            "Editar agenda: /job <nome> set agenda '0 20 * * *'\n"
            "Inspecionar: /describe Job treino"
        )
        spec["title"] = "Job — referência"
        spec["body"] = new_body
        # verifica se já existe Doc/kind-job
        existing_job_doc = conn.execute(
            "SELECT 1 FROM resources WHERE kind = 'Doc' AND name = 'kind-job'"
        ).fetchone()
        if existing_job_doc:
            conn.execute(
                "DELETE FROM resources WHERE kind = 'Doc' AND name = 'kind-routine'"
            )
            print("  [skip-dup] Doc/kind-routine deletado (Doc/kind-job já existe)")
        else:
            conn.execute(
                "UPDATE resources SET name = 'kind-job', spec_json = ?, "
                "labels_json = ?, atualizado_em = ? "
                "WHERE kind = 'Doc' AND name = 'kind-routine'",
                (json.dumps(spec), json.dumps({"topic": "kindref", "for": "Job"}), agora),
            )
            print("  [migrado ] Doc/kind-routine → Doc/kind-job")
    else:
        print("  [ok      ] Doc/kind-routine não existe (nada a migrar)")

    # 3. Garante Repo/nora com URL correta
    nora = conn.execute(
        "SELECT spec_json FROM resources WHERE kind = 'Repo' AND name = 'nora'"
    ).fetchone()
    if nora is None:
        spec = json.dumps({"url": "https://github.com/sys0xFF/nora"})
        labels = json.dumps({})
        status = json.dumps({})
        conn.execute(
            "INSERT INTO resources (kind, name, api_version, labels_json, spec_json, "
            "status_json, criado_em, atualizado_em) VALUES (?,?,?,?,?,?,?,?)",
            ("Repo", "nora", "atlas/v1", labels, spec, status, agora, agora),
        )
        print("  [criado  ] Repo/nora spec.url=https://github.com/sys0xFF/nora")
    else:
        sp = json.loads(nora["spec_json"] or "{}")
        if not sp.get("url"):
            sp["url"] = "https://github.com/sys0xFF/nora"
            conn.execute(
                "UPDATE resources SET spec_json = ?, atualizado_em = ? "
                "WHERE kind = 'Repo' AND name = 'nora'",
                (json.dumps(sp), agora),
            )
            print("  [atualizado] Repo/nora spec.url adicionado")
        else:
            print(f"  [ok      ] Repo/nora já existe — url: {sp['url']}")

    conn.commit()
    conn.close()
    print("Migração concluída.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default="atlas.sqlite", help="Caminho do banco SQLite")
    args = p.parse_args()
    db = Path(args.db)
    if not db.exists():
        print(f"Banco não encontrado: {db}")
        raise SystemExit(1)
    print(f"Migrando: {db}")
    run(str(db))
