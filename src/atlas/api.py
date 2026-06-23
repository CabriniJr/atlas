"""API HTTP do Atlas (E0-02 / ADR-0015).

Expõe o ResourceStore como REST API estilo Kubernetes:

  GET    /apis/atlas/v1/                   → lista kinds + counts
  GET    /apis/atlas/v1/<kind>             → lista recursos do kind
  GET    /apis/atlas/v1/<kind>/<name>      → detalhe de um recurso
  PUT    /apis/atlas/v1/<kind>/<name>      → apply (upsert)
  DELETE /apis/atlas/v1/<kind>/<name>      → delete
  GET    /health                           → {"status": "ok"}
  GET    /                                 → dashboard HTML (E0-06 lite)

Auth (E0-05): Bearer token via ATLAS_API_TOKEN env. Se não definido a API
aceita só conexões de loopback (127.0.0.1 / ::1).

Roda em thread daemon paralela ao bot Telegram.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore

_log = logging.getLogger("atlas.api")

_API_PREFIX = "/apis/atlas/v1"
_TOKEN = os.environ.get("ATLAS_API_TOKEN", "")
_PORT = int(os.environ.get("ATLAS_API_PORT", "8080"))

# Store injetado no boot — partilhado com o bot Telegram
_store: ResourceStore | None = None


_DASHBOARD_DIR = Path(__file__).parent / "dashboard"


def _html_dashboard() -> str:
    return (_DASHBOARD_DIR / "index.html").read_text(encoding="utf-8")


def _dashboard_static(path: str) -> tuple[bytes, str] | None:
    """Serve static files under /dashboard/. Returns (data, content_type) or None."""
    rel = path.removeprefix("/dashboard/").lstrip("/")
    target = _DASHBOARD_DIR / rel
    try:
        target = target.resolve()
        # Safety: must stay inside _DASHBOARD_DIR
        target.relative_to(_DASHBOARD_DIR.resolve())
    except (ValueError, OSError):
        return None
    if not target.is_file():
        return None
    ext = target.suffix.lower()
    ct_map = {".js": "application/javascript", ".css": "text/css",
              ".html": "text/html; charset=utf-8", ".json": "application/json"}
    ct = ct_map.get(ext, "application/octet-stream")
    return target.read_bytes(), ct




class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: ANN401
        _log.debug(fmt, *args)

    def _auth(self) -> bool:
        if not _TOKEN:
            ip = self.client_address[0]
            return ip in ("127.0.0.1", "::1", "::ffff:127.0.0.1")
        auth = self.headers.get("Authorization", "")
        return auth == f"Bearer {_TOKEN}"

    def _json(self, code: int, body: Any) -> None:
        data = json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _html(self, body: str) -> None:
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        # Sem cache: garante que o dashboard sempre carregue a versão atual
        # (evita celular/navegador servir HTML antigo após um rebuild).
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization,Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path.split("?")[0].rstrip("/")

        if path == "" or path == "/":
            self._html(_html_dashboard())
            return
        if path == "/health":
            self._json(200, {"status": "ok"})
            return
        if path.startswith("/dashboard/"):
            result = _dashboard_static(path)
            if result is None:
                self._json(404, {"error": "not found"})
                return
            data, ct = result
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if not self._auth():
            self._json(401, {"error": "unauthorized"})
            return
        if _store is None:
            self._json(503, {"error": "store not ready"})
            return

        if path == _API_PREFIX:
            counts = {k: len(_store.list(k)) for k in _store.kinds()}
            self._json(200, counts)
            return

        # /_complete?q=<text> → sugestões de autocomplete
        if path == _API_PREFIX + "/_complete":
            from urllib.parse import parse_qs, urlparse

            q = parse_qs(urlparse(self.path).query).get("q", [""])[0]
            self._json(200, _autocomplete(q, _store))
            return

        # /_status → visão abstraída (o que está rodando)
        if path == _API_PREFIX + "/_status":
            self._json(200, _status_payload())
            return

        # /_schema → metadata de UI por kind (forms + ações)
        if path == _API_PREFIX + "/_schema":
            from atlas.api_schema import schema_payload

            self._json(200, schema_payload())
            return

        rest = path[len(_API_PREFIX) :].strip("/")
        parts = rest.split("/") if rest else []

        if len(parts) == 1:
            kind = parts[0]
            resources = _store.list(kind)
            self._json(200, [_resource_to_dict(r) for r in resources])
            return

        if len(parts) == 2:
            kind, name = parts
            r = _store.get(kind, name)
            if r is None:
                self._json(404, {"error": f"{kind}/{name} not found"})
                return
            self._json(200, _resource_to_dict(r))
            return

        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not self._auth():
            self._json(401, {"error": "unauthorized"})
            return
        if _store is None:
            self._json(503, {"error": "store not ready"})
            return

        path = self.path.split("?")[0].rstrip("/")
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        # Executa uma rotina sob demanda (botão "Executar" no dashboard).
        if path == _API_PREFIX + "/_run":
            name = body.get("routine", "").strip()
            if not name:
                self._json(400, {"error": "routine required"})
                return
            self._json(200, _run_routine(name))
            return

        # Insight por IA (sob demanda) — sistema ou repositório.
        if path == _API_PREFIX + "/_insight":
            self._json(
                200,
                _ai_insight(
                    body.get("scope", "system"),
                    body.get("name", ""),
                    body.get("model", "claude-haiku-4-5-20251001"),
                ),
            )
            return

        # Chat interativo do Kind Agente (E7-25, ADR-0024).
        if path == _API_PREFIX + "/_chat":
            self._json(200, _agente_chat(body.get("agente", ""), body.get("mensagem", ""), _store))
            return

        if path != _API_PREFIX + "/_cmd":
            self._json(404, {"error": "not found"})
            return

        text = body.get("text", "").strip()
        if not text:
            self._json(400, {"error": "text required"})
            return

        output = _cmd_router(text, _store)
        self._json(200, {"output": output})

    def do_PUT(self) -> None:
        if not self._auth():
            self._json(401, {"error": "unauthorized"})
            return
        if _store is None:
            self._json(503, {"error": "store not ready"})
            return

        path = self.path.split("?")[0].rstrip("/")
        rest = path[len(_API_PREFIX) :].strip("/")
        parts = rest.split("/") if rest else []
        if len(parts) != 2:
            self._json(400, {"error": "PUT requires /apis/atlas/v1/<kind>/<name>"})
            return

        kind, name = parts
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        existing = _store.get(kind, name)
        labels = {**((existing.labels or {}) if existing else {}), **body.get("labels", {})}
        spec = {**((existing.spec or {}) if existing else {}), **body.get("spec", {})}
        status = {**((existing.status or {}) if existing else {}), **body.get("status", {})}

        res = Resource(kind=kind, name=name, labels=labels, spec=spec, status=status)
        _store.apply(res, datetime.now())
        self._json(200, _resource_to_dict(_store.get(kind, name)))

    def do_DELETE(self) -> None:
        if not self._auth():
            self._json(401, {"error": "unauthorized"})
            return
        if _store is None:
            self._json(503, {"error": "store not ready"})
            return

        path = self.path.split("?")[0].rstrip("/")
        rest = path[len(_API_PREFIX) :].strip("/")
        parts = rest.split("/") if rest else []
        if len(parts) != 2:
            self._json(400, {"error": "DELETE requires /apis/atlas/v1/<kind>/<name>"})
            return

        kind, name = parts
        ok = _store.delete(kind, name)
        if ok:
            self._json(200, {"deleted": f"{kind}/{name}"})
        else:
            self._json(404, {"error": f"{kind}/{name} not found"})


_CMD_VERBS = [
    "/list",
    "/get",
    "/describe",
    "/apply",
    "/delete",
    "/resources",
    "/docs",
    "/snip",
    "/help",
    "/uso",
    "/ls",
    "/r",
    "/cat",
    "/d",
    "/a",
    "/rm",
]
_VERBS_KIND = {
    "/list",
    "/get",
    "/describe",
    "/apply",
    "/delete",
    "/ls",
    "/r",
    "/cat",
    "/d",
    "/a",
    "/rm",
}
_VERBS_NAME = {"/get", "/describe", "/delete", "/r", "/cat", "/d", "/rm"}


def _cmd_router(text: str, store: ResourceStore) -> str:
    """Roteia um comando do dashboard pelo handler completo (paridade com Telegram).

    Inclui a micro-sintaxe de tracker (``peso: 82.3``), ``/reg``, ``/goal`` etc.,
    permitindo registrar valores de forma visual pelo web.
    """
    from atlas.db import Database as _DB
    from atlas.handler import responder

    agora = datetime.now()
    _db_path = os.environ.get("ATLAS_DB_PATH", "atlas.sqlite")
    try:
        _db = _DB(_db_path)
    except Exception as exc:  # noqa: BLE001
        return f"⚠️ erro ao abrir o banco: {exc}"

    # /uso tem renderização própria (histórico de execuções).
    try:
        from atlas.uso import responder_uso

        uso = responder_uso(text, _db, agora)
        if uso is not None:
            return uso
    except Exception:  # noqa: BLE001
        pass

    return responder(text, _db, agora, store=store)


def _autocomplete(q: str, store: ResourceStore) -> list[str]:
    parts = q.split()
    verb = parts[0] if parts else ""
    kind = parts[1] if len(parts) > 1 else ""
    name_frag = parts[2] if len(parts) > 2 else ""

    # completando verbo
    if not verb or (len(parts) == 1 and not q.endswith(" ")):
        frag = verb.lower()
        return [v for v in _CMD_VERBS if v.startswith(frag or "/")]

    # completando kind
    if verb in _VERBS_KIND and (len(parts) == 1 or (len(parts) == 2 and not q.endswith(" "))):
        frag = kind.lower()
        kinds = store.kinds()
        matches = [k for k in kinds if k.lower().startswith(frag)]
        return [f"{verb} {k}" for k in matches]

    # completando name
    if (
        verb in _VERBS_NAME
        and kind
        and (len(parts) == 2 or (len(parts) == 3 and not q.endswith(" ")))
    ):
        frag = name_frag.lower()
        try:
            resources = store.list(kind)
        except Exception:  # noqa: BLE001
            return []
        matches = [r.name for r in resources if r.name.lower().startswith(frag)]
        return [f"{verb} {kind} {n}" for n in matches]

    return []


def _resource_to_dict(r: Resource) -> dict:
    return {
        "api_version": r.api_version,
        "kind": r.kind,
        "name": r.name,
        "labels": r.labels,
        "spec": r.spec,
        "status": r.status,
        "criado_em": r.criado_em,
        "atualizado_em": r.atualizado_em,
    }


def _status_payload() -> dict:
    """Visão abstraída do sistema: o que está ativo, rodando e a atividade recente."""
    from atlas.db import Database as _DB
    from atlas.scheduler import _ler_ultimo, proxima_execucao

    agora = datetime.now()
    out: dict = {
        "now": agora.isoformat(),
        "kinds": {},
        "total": 0,
        "routines": [],
        "running": [],
        "alarms": [],
        "repos": [],
        "recent_runs": [],
    }
    if _store is None:
        return out

    out["kinds"] = {k: len(_store.list(k)) for k in _store.kinds()}
    out["total"] = sum(out["kinds"].values())

    db = None
    try:
        db = _DB(os.environ.get("ATLAS_DB_PATH", "atlas.sqlite"))
    except Exception:  # noqa: BLE001
        db = None

    for r in _store.list("Job"):
        agenda = r.spec.get("schedule") or ""
        ativa = bool(r.spec.get("active"))
        ultimo = None
        nxt = None
        if db is not None:
            try:
                ultimo = _ler_ultimo(db, r.name)
            except Exception:  # noqa: BLE001
                ultimo = None
        if agenda and ativa:
            try:
                nxt = proxima_execucao(agenda, ultimo, agora)
            except Exception:  # noqa: BLE001
                nxt = None
        coletar = r.spec.get("coletar", "") or ""
        grupo = r.spec.get("label", "") or ""
        out["routines"].append(
            {
                "name": r.name,
                "active": ativa,
                "schedule": agenda,
                "model": r.spec.get("model", "none"),
                "description": r.spec.get("description", ""),
                "last_run": ultimo.isoformat() if ultimo else None,
                "next_run": nxt.isoformat() if nxt else None,
                "coletar": coletar,
                "grupo": grupo,
                # check-in visual: a rotina coleta valores de tracker de um grupo
                "checkin": bool(grupo) and coletar in ("coletar-por-label",),
            }
        )

    for t in _store.list("Timer"):
        if (t.status or {}).get("state") == "running":
            out["running"].append(
                {
                    "name": t.name,
                    "since": t.status.get("started_at", ""),
                    "domain": (t.labels or {}).get("domain", ""),
                }
            )

    for a in _store.list("Alarm"):
        if a.spec.get("active", True):
            out["alarms"].append(
                {
                    "name": a.name,
                    "hora": a.spec.get("hora", ""),
                    "mensagem": a.spec.get("mensagem", "") or a.spec.get("message", ""),
                    "once": bool(a.spec.get("once", False)),
                }
            )

    for rp in _store.list("Repo"):
        st = rp.status or {}
        out["repos"].append(
            {
                "name": rp.name,
                "url": rp.spec.get("url", ""),
                "last_commit": st.get("last_commit"),
                "last_commit_msg": st.get("last_commit_msg"),
                "last_author": st.get("last_author"),
                "last_summary": st.get("last_summary"),
                "last_sync": st.get("last_sync"),
                "last_check": st.get("last_check"),
                "files_changed": st.get("files_changed"),
                "insertions": st.get("insertions"),
                "deletions": st.get("deletions"),
            }
        )

    if db is not None:
        try:
            rows = db.connection.execute(
                "SELECT rotina,status,camada,iniciado_em,terminado_em "
                "FROM runs ORDER BY id DESC LIMIT 15"
            ).fetchall()
            out["recent_runs"] = [
                {
                    "rotina": row[0],
                    "status": row[1],
                    "camada": row[2],
                    "iniciado_em": row[3],
                    "terminado_em": row[4],
                }
                for row in rows
            ]
        except Exception:  # noqa: BLE001
            pass

    return out


def _run_routine(name: str) -> dict:
    """Executa o collect de uma rotina sob demanda (sem esperar a agenda)."""
    from pathlib import Path

    from atlas.db import Database as _DB
    from atlas.executor import ContextoExecucao
    from atlas.rotinas import obter as _obter
    from atlas.routines import carregar_rotinas

    rdir = os.environ.get("ATLAS_ROUTINES_DIR", "routines")
    carga = carregar_rotinas(Path(rdir))
    rot = next((r for r in carga.rotinas if r.nome == name), None)
    if rot is None:
        return {"ok": False, "error": f"rotina '{name}' não encontrada"}

    db = None
    try:
        db = _DB(os.environ.get("ATLAS_DB_PATH", "atlas.sqlite"))
    except Exception:  # noqa: BLE001
        db = None

    agora = datetime.now()
    ctx = ContextoExecucao(agora=agora, rotina=rot, origem="manual", db=db, store=_store)
    try:
        collect = _obter(rot.coletar or rot.nome)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"collect '{rot.coletar or rot.nome}' não registrado: {exc}"}

    ok = True
    saida = ""
    try:
        result = collect(ctx)
        saida = (result.data or {}).get("_saida", "") if result else ""
    except Exception as exc:  # noqa: BLE001
        ok = False
        saida = f"erro: {exc}"

    if db is not None:
        try:
            ts = datetime.now().isoformat()
            db.connection.execute(
                "INSERT INTO runs (rotina, iniciado_em, terminado_em, status, camada) "
                "VALUES (?,?,?,?,?)",
                (name, agora.isoformat(), ts, "ok" if ok else "erro", "manual"),
            )
            db.connection.commit()
        except Exception:  # noqa: BLE001
            pass

    return {"ok": ok, "routine": name, "model": rot.modelo, "output": saida or "(sem saída)"}


def _ai_insight(scope: str, name: str = "", model: str = "claude-haiku-4-5-20251001") -> dict:
    """Gera um insight por IA sobre o sistema ou um repositório (sob demanda)."""
    from atlas.ia import InvocarErro, invocar

    if _store is None:
        return {"ok": False, "error": "store indisponível"}

    if scope == "repo" and name:
        rp = _store.get("Repo", name)
        if rp is None:
            return {"ok": False, "error": f"Repo/{name} não existe"}
        st = rp.status or {}
        ctx_txt = (
            f"Repositório: {name}\nURL: {rp.spec.get('url', '')}\n"
            f"Último commit: {st.get('last_commit')} — {st.get('last_commit_msg', '')}\n"
            f"Autor: {st.get('last_author', '')}\n"
            f"Data: {st.get('last_commit_date', '')}\n"
            f"Stats: {st.get('files_changed')} arquivos, "
            f"+{st.get('insertions')}/-{st.get('deletions')}\n"
        )
        diffs = _store.list("Diff", labels={"repo": name})
        if diffs:
            d = sorted(diffs, key=lambda x: (x.status or {}).get("synced_at", ""))[-1]
            ctx_txt += f"Arquivos: {', '.join(d.spec.get('files_list', [])[:15])}\n"
            ctx_txt += f"\nDiff (parcial):\n{d.spec.get('diff_raw', '')[:3500]}\n"
        prompt = (
            "Você é um revisor técnico. Analise a última atualização deste repositório com "
            "os metadados fornecidos (NÃO peça acesso ao repo; trabalhe com o que há). "
            "Responda em PT-BR, máximo 180 palavras, com bullets em duas seções:\n"
            "## O que mudou\n## Sugestões (o que eu poderia propor)\n\n" + ctx_txt
        )
    else:
        s = _status_payload()
        ativas = [r["name"] for r in s["routines"] if r["active"]]
        repos = [(r["name"], r.get("last_summary")) for r in s["repos"]]
        runs = [(r["rotina"], r["status"]) for r in s["recent_runs"][:8]]
        prompt = (
            "Você é o copiloto do Atlas (motor de rotinas pessoais). Com base no estado abaixo, "
            "dê um insight curto e útil em PT-BR: o que está saudável, o que precisa de atenção e "
            "1-2 sugestões práticas. Máximo 150 palavras, use bullet points.\n\n"
            f"Total de recursos: {s['total']} {s['kinds']}\n"
            f"Rotinas ativas: {ativas}\n"
            f"Repositórios: {repos}\n"
            f"Em execução agora: {s['running']}\n"
            f"Execuções recentes: {runs}\n"
        )

    try:
        resposta = invocar(prompt, modelo=model, timeout=90)
    except InvocarErro as exc:
        return {"ok": False, "error": str(exc)}

    doc_name = _salvar_insight_doc(scope, name, resposta, model)
    return {
        "ok": True,
        "scope": scope,
        "name": name,
        "model": model,
        "insight": resposta,
        "doc": doc_name,
    }


def _agente_chat(agente_name: str, mensagem: str, store: ResourceStore) -> dict:
    """Executa o Kind Agente em modo chat (E7-25, ADR-0024).

    Busca o recurso Agente, constrói o prompt com o template e chama o motor
    selecionado. Suporta nivel_contexto (resumo|completo) para injetar schema
    e contexto do projeto (E7-24 — builder). Devolve {response, motor, modelo,
    commands?} ou {error}.
    """
    from atlas.ia import InvocarErro, invocar

    if not agente_name or not mensagem:
        return {"error": "agente e mensagem são obrigatórios"}
    agente = store.get("Agente", agente_name)
    if agente is None:
        return {"error": f"Agente '{agente_name}' não encontrado"}

    spec = agente.spec or {}
    motor = spec.get("motor", "claude")
    modelo = spec.get("modelo") or (
        "claude-haiku-4-5-20251001" if motor == "claude" else "gemma4"
    )
    timeout = int(spec.get("timeout") or 60)
    endpoint = spec.get("endpoint") or os.environ.get("ATLAS_OLLAMA_ENDPOINT", "")
    template = spec.get("prompt") or "{mensagem}"
    nivel = spec.get("nivel_contexto", "none")
    agora_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Injecao de contexto (E7-24)
    ctx_inject = ""
    if nivel in ("resumo", "completo"):
        ctx_inject = _schema_context(store, completo=(nivel == "completo"))

    prompt = (
        template
        .replace("{mensagem}", mensagem)
        .replace("{agora}", agora_str)
        .replace("{schema}", ctx_inject)
    )
    # Se o template não usou {schema}, pré-pende o contexto
    if ctx_inject and "{schema}" not in template:
        prompt = ctx_inject + "\n\n" + prompt

    invoke_kwargs: dict = {"modelo": modelo, "timeout": timeout, "motor": motor}
    if motor == "ollama" and endpoint:
        import atlas.ia as _ia_mod
        try:
            resposta = _ia_mod.invocar_ollama(prompt, modelo, endpoint, timeout)
        except InvocarErro as e:
            return {"error": str(e), "motor": motor, "modelo": modelo}
    else:
        try:
            resposta = invocar(prompt, **invoke_kwargs)
        except InvocarErro as e:
            return {"error": str(e), "motor": motor, "modelo": modelo}

    # Extrai comandos /apply da resposta para o front destacar (E7-24)
    import re
    commands = re.findall(r"(?m)^/?apply\s+\S[^\n]*", resposta)
    result: dict = {"response": resposta, "motor": motor, "modelo": modelo}
    if commands:
        result["commands"] = [c if c.startswith("/") else "/" + c for c in commands]
    return result


def _schema_context(store: ResourceStore, *, completo: bool = False) -> str:
    """Gera contexto textual do schema do Atlas para injeção no prompt (E7-24)."""
    from atlas.api_schema import schema_payload

    payload = schema_payload()
    recursos_ativos = store.kinds()
    linhas = [
        "=== Atlas — Schema de Recursos ===",
        f"Kinds disponíveis: {', '.join(recursos_ativos)}",
        "",
    ]
    for kind, info in payload["kinds"].items():
        if info["meta"].get("hidden"):
            continue
        if completo:
            campos = "; ".join(
                f"{f['k']} ({f['type']}): {f.get('hint','')}"
                for f in info["spec"]
            )
        else:
            campos = ", ".join(f["k"] for f in info["spec"])
        linhas.append(f"- {kind}: [{campos}]")
    linhas += [
        "",
        "Para criar/editar recursos use: /apply Kind nome spec.campo=valor",
        "Para listar: /list Kind",
        "Para detalhe: /describe Kind nome",
    ]
    return "\n".join(linhas)


def _salvar_insight_doc(scope: str, name: str, texto: str, model: str) -> str | None:
    """Salva o insight como Doc. Para repo, fica na 'pasta' do repo (labels.repo)."""
    if _store is None:
        return None
    agora = datetime.now()
    ts = agora.strftime("%Y%m%d-%H%M%S")
    if scope == "repo" and name:
        doc_name = f"insight-{name}-{ts}"
        labels = {"topic": "repo", "repo": name, "tipo": "insight"}
        titulo = f"{name} · insight ({agora.strftime('%d/%m %H:%M')})"
    else:
        doc_name = f"insight-sistema-{ts}"
        labels = {"topic": "insight", "tipo": "sistema"}
        titulo = f"sistema · insight ({agora.strftime('%d/%m %H:%M')})"
    body = "\n".join(
        [
            f"# {titulo}",
            "",
            f"_via {model} · {agora.isoformat(timespec='seconds')}_",
            "",
            texto or "",
        ]
    )
    try:
        _store.apply(
            Resource(
                kind="Doc",
                name=doc_name,
                labels=labels,
                spec={"title": titulo, "body": body},
                status={"gerado_em": agora.isoformat()},
            ),
            agora,
        )
        return doc_name
    except Exception:  # noqa: BLE001
        return None


def iniciar(store: ResourceStore, port: int = _PORT) -> None:
    """Inicia o servidor HTTP em thread daemon. Chamado pelo app no boot."""
    global _store
    _store = store

    server = HTTPServer(("0.0.0.0", port), _Handler)

    def _run() -> None:
        _log.info(
            "API HTTP no ar: http://0.0.0.0:%d  (token=%s)",
            port,
            "sim" if _TOKEN else "loopback-only",
        )
        server.serve_forever()

    t = threading.Thread(target=_run, daemon=True, name="atlas-api")
    t.start()
