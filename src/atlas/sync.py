"""Sincronização do ResourceStore com dados existentes no boot (E0-04).

Popula o store a partir das tabelas legadas (trackers, alarms) e das rotinas
carregadas de TOML. Idempotente — usa ``apply`` (upsert). Roda uma vez no boot.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.db import Database
from atlas.routines import Rotina

_log = logging.getLogger("atlas.sync")


def sincronizar_store(
    db: Database,
    store: ResourceStore,
    rotinas: list[Rotina],
    agora: datetime | None = None,
) -> None:
    """Popula o store com dados existentes. Idempotente."""
    agora = agora or datetime.now()
    _sync_trackers(db, store, agora)
    _sync_alarms(db, store, agora)
    _sync_routines(rotinas, store, agora)
    _sync_pool(db, store, agora)
    _sync_docs(store, agora)
    kinds = store.kinds()
    _log.info("Store sincronizado: %s", ", ".join(f"{k}={len(store.list(k))}" for k in kinds))


def _sync_trackers(db: Database, store: ResourceStore, agora: datetime) -> None:
    rows = db.connection.execute(
        "SELECT nome, dominio, tipo, unidade, sintaxe, agregacao, ativo, criado_em FROM trackers"
    ).fetchall()
    for r in rows:
        res = Resource(
            kind="Tracker",
            name=r["nome"],
            labels={"domain": r["dominio"] or "geral", "active": str(bool(r["ativo"])).lower()},
            spec={
                "unit": r["unidade"] or "",
                "type": r["tipo"] or "number",
                "syntax": r["sintaxe"] or f"{r['nome']}:",
                "aggregation": r["agregacao"] or "last",
                "active": bool(r["ativo"]),
            },
        )
        store.apply(res, agora)


def _sync_alarms(db: Database, store: ResourceStore, agora: datetime) -> None:
    rows = db.connection.execute(
        "SELECT id, horario, mensagem, recorrencia, proximo_disparo, ativo FROM alarms"
    ).fetchall()
    for r in rows:
        mode = "once" if r["recorrencia"] == "uma_vez" else "daily"
        res = Resource(
            kind="Alarm",
            name=f"alarm-{r['id']}",
            labels={"mode": mode, "active": str(bool(r["ativo"])).lower()},
            spec={"time": r["horario"], "mode": mode, "message": r["mensagem"]},
            status={"active": bool(r["ativo"]), "next_fire": r["proximo_disparo"]},
        )
        store.apply(res, agora)


def _sync_pool(db: Database, store: ResourceStore, agora: datetime) -> None:
    _TIPO_PARA_KIND = {"ideia": "Idea", "tarefa": "Task", "rotina": "RoutineRequest"}
    try:
        rows = db.connection.execute(
            "SELECT id, tipo, titulo, corpo, prioridade, estado, criado_em FROM ideas"
        ).fetchall()
    except Exception:  # noqa: BLE001 — tabela pode não existir ainda
        return
    for r in rows:
        kind = _TIPO_PARA_KIND.get(r["tipo"], r["tipo"].capitalize())
        res = Resource(
            kind=kind,
            name=f"idea-{r['id']}",
            labels={"tipo": r["tipo"], "estado": r["estado"]},
            spec={
                "title": r["titulo"] or "",
                "body": r["corpo"] or "",
                "priority": r["prioridade"] or 100,
            },
            status={"state": r["estado"]},
        )
        store.apply(res, agora)


def _sync_docs(store: ResourceStore, agora: datetime) -> None:
    """Carrega docs Markdown como Kind Doc no store + kind-refs embutidas."""
    docs_root = Path(os.environ.get("ATLAS_DOCS_DIR", "docs"))

    # Mapa: slug → (path_relativo, labels extras)
    _DOCS_MAP = {
        "kinds":          ("arquitetura/kinds.md",        {"topic": "arch"}),
        "arch":           ("arquitetura/visao-geral.md",  {"topic": "arch"}),
        "constituicao":   ("arquitetura/constituicao.md", {"topic": "arch"}),
        "modelo-dados":   ("arquitetura/modelo-de-dados.md", {"topic": "arch"}),
        "seguranca":      ("arquitetura/seguranca.md",    {"topic": "arch"}),
        "ciclo":          ("arquitetura/ciclo-de-vida-rotina.md", {"topic": "arch"}),
        "backlog":        ("roadmap/backlog.md",           {"topic": "roadmap"}),
        "amadurecimento": ("roadmap/amadurecimento.md",   {"topic": "roadmap"}),
        "planejamento":   ("roadmap/planejamento.md",     {"topic": "roadmap"}),
        "spec-trackers":  ("specs/trackers-via-chat.md",  {"topic": "spec"}),
        "spec-alarmes":   ("specs/alarmes.md",            {"topic": "spec"}),
        "spec-pool":      ("specs/pool-de-ideias.md",     {"topic": "spec"}),
        "spec-scheduler": ("specs/scheduler.md",          {"topic": "spec"}),
        "spec-executor":  ("specs/executor-e-notificacao.md", {"topic": "spec"}),
        "spec-interface": ("specs/interface-config-chat.md", {"topic": "spec"}),
        "spec-barreira":  ("specs/barreira-entrada.md",   {"topic": "spec"}),
        "spec-core-api":  ("specs/core-api-objetos.md",   {"topic": "spec"}),
        "spec-meta-loop": ("specs/meta-loop-chat.md",     {"topic": "spec"}),
    }

    for slug, (rel_path, extra_labels) in _DOCS_MAP.items():
        path = docs_root / rel_path
        if not path.exists():
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            continue
        labels = {"format": "markdown", **extra_labels}
        res = Resource(
            kind="Doc",
            name=slug,
            labels=labels,
            spec={"title": slug.replace("-", " ").title(), "body": body,
                  "source": str(rel_path)},
            status={"chars": len(body)},
        )
        store.apply(res, agora)

    # ADRs
    adr_dir = docs_root / "arquitetura" / "adr"
    if adr_dir.exists():
        for adr_file in sorted(adr_dir.iterdir()):
            if adr_file.suffix != ".md" or adr_file.name == "README.md":
                continue
            try:
                body = adr_file.read_text(encoding="utf-8")
            except OSError:
                continue
            slug = adr_file.stem.lower()  # adr-0015-core-api-de-objetos
            res = Resource(
                kind="Doc",
                name=slug,
                labels={"topic": "adr", "format": "markdown"},
                spec={
                    "title": adr_file.stem,
                    "body": body,
                    "source": str(adr_file.relative_to(docs_root)),
                },
                status={"chars": len(body)},
            )
            store.apply(res, agora)

    # Kind-refs embutidas: cada Kind tem um Doc descrevendo seu uso
    _KIND_REFS = {
        "kind-tracker": (
            "Tracker", "Tracker — rastreador de métricas numéricas\n\n"
            "spec: unit, type, syntax, aggregation, active\n"
            "status: last_value, count_today\n"
            "labels: domain, active\n\n"
            "Criar: /track new <nome> [unidade]\n"
            "Registrar: <nome>: <valor>   (ex: peso: 82.3)\n"
            "Listar: /track\n"
            "Detalhe: /track <nome>\n"
            "Remover: /track <nome> rm\n"
            "Filtrar: /list Tracker -l domain=fisico\n"
            "Inspecionar: /describe Tracker peso"
        ),
        "kind-alarm": (
            "Alarm", "Alarm — lembrete temporal (diário ou único)\n\n"
            "spec: time (HH:MM), mode (daily|once), message, active\n"
            "status: active, next_fire, fire_count\n"
            "labels: mode, active\n\n"
            "Criar: /alarm 07:30 <mensagem>   [@once para único]\n"
            "Listar: /alarms\n"
            "Remover: /alarm <id> remove\n"
            "Inspecionar: /describe Alarm alarm-1"
        ),
        "kind-timer": (
            "Timer", "Timer — cronômetro que grava duração em activities\n\n"
            "spec: label\n"
            "status: state (running|done), started_at, finished_at, duration_min\n"
            "labels: state\n\n"
            "Iniciar: /timer start <nome>\n"
            "Parar: /timer finish <nome>   → grava em activities (rotina=timer)\n"
            "Status: /timer status <nome>\n"
            "Listar ativos: /timers\n"
            "Inspecionar: /describe Timer estudo"
        ),
        "kind-goal": (
            "Goal", "Goal — meta mensurável com progresso calculado\n\n"
            "spec: target, unit, tracker, start, direction (up|down)\n"
            "status: current, progress (%), checked_at, done_at\n"
            "labels: state (active|done)\n\n"
            "Criar: /goal set <nome> target=<val> unit=<u> tracker=<t> start=<val> direction=down\n"
            "Listar: /goals\n"
            "Detalhe: /goal status <nome>\n"
            "Calcular: /goal check <nome>   → lê último valor do tracker\n"
            "Concluir: /goal done <nome>\n"
            "Inspecionar: /describe Goal peso"
        ),
        "kind-idea": (
            "Idea", "Idea / Task / RoutineRequest — pool de captura\n\n"
            "spec: title, body, priority\n"
            "status: state (capturada|priorizada|ativada|arquivada|descartada)\n"
            "labels: tipo, estado\n\n"
            "Capturar: /idea <texto>   /task <texto>   /queue <texto>\n"
            "Listar: /pool\n"
            "Detalhe: /pool <id>\n"
            "Priorizar: /pool <id> prio <n>\n"
            "Filtrar: /list Idea -l estado=capturada"
        ),
        "kind-routine": (
            "Routine", "Routine — rotina carregada de routines/<nome>/routine.toml\n\n"
            "spec: description, schedule (cron), model, triggers, active\n"
            "status: last_run, run_count\n"
            "labels: model, active\n\n"
            "Listar: /routines\n"
            "Detalhe: /routine <nome>\n"
            "Executar: /run <nome>\n"
            "Ativar/Desativar: /activate <nome>   /deactivate <nome>\n"
            "Editar agenda: /routine <nome> set agenda '0 20 * * *'\n"
            "Inspecionar: /describe Routine treino"
        ),
        "kind-doc": (
            "Doc", "Doc — documento em plain text/markdown no store\n\n"
            "spec: title, body, source\n"
            "status: chars\n"
            "labels: topic (arch|roadmap|spec|adr|kindref|user), format, for\n\n"
            "Listar docs de arquitetura: /list Doc -l topic=arch\n"
            "Listar ADRs: /list Doc -l topic=adr\n"
            "Ler doc: /describe Doc kinds\n"
            "Criar nota pessoal: /apply Doc minha-nota labels.topic=user spec.body=<texto>\n"
            "Associar a um kind: /apply Doc kind-peso labels.for=Goal labels.topic=kindref"
        ),
    }

    for slug, (kind_for, body) in _KIND_REFS.items():
        res = Resource(
            kind="Doc",
            name=slug,
            labels={"topic": "kindref", "format": "text", "for": kind_for},
            spec={"title": f"{kind_for} — referência", "body": body},
            status={"chars": len(body)},
        )
        store.apply(res, agora)


def _sync_routines(rotinas: list[Rotina], store: ResourceStore, agora: datetime) -> None:
    for rot in rotinas:
        res = Resource(
            kind="Routine",
            name=rot.nome,
            labels={"model": rot.modelo, "active": str(rot.ativa).lower()},
            spec={
                "description": rot.descricao,
                "schedule": rot.agenda or "",
                "model": rot.modelo,
                "triggers": rot.triggers,
                "active": rot.ativa,
            },
        )
        store.apply(res, agora)
