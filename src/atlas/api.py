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

import hmac
import json
import logging
import os
import re
import subprocess
import threading
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from atlas import agente_ollama, credentials, curadoria, github_auth, scoping, sessions, users
from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.traducao.pool import pool_global as _traducao_pool

_log = logging.getLogger("atlas.api")

_API_PREFIX = "/apis/atlas/v1"
_TOKEN = os.environ.get("ATLAS_API_TOKEN", "")
# Dono default p/ admin (token/loopback) e fallback de escopo (Fase 5).
_DEFAULT_OWNER = os.environ.get("ATLAS_DEFAULT_OWNER", "admin")
_SESSION_COOKIE = "atlas_session"


def _set_cookie(token: str) -> str:
    """Cookie de sessão httpOnly (SameSite=Lax). HTTP na Tailnet ⇒ sem Secure."""
    return f"{_SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={sessions._DEFAULT_TTL}"


def _clear_cookie() -> str:
    return f"{_SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"


_PORT = int(os.environ.get("ATLAS_API_PORT", "8080"))
# Raiz do projeto Atlas — usada pelo agente modo=code para cwd + --add-dir
_PROJECT_DIR = str(
    Path(os.environ["ATLAS_PROJECT_DIR"]).resolve()
    if "ATLAS_PROJECT_DIR" in os.environ
    else Path(__file__).parent.parent.parent.resolve()
)

# Store injetado no boot — partilhado com o bot Telegram
_store: ResourceStore | None = None

# Pool de execução de traduções (ADR-0038/0039): teto escalável em runtime + fila
# FIFO — instância compartilhada com rotinas/traduzir_pdf.py (paralelismo de páginas).


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
    ct_map = {
        ".js": "application/javascript",
        ".css": "text/css",
        ".html": "text/html; charset=utf-8",
        ".json": "application/json",
    }
    ct = ct_map.get(ext, "application/octet-stream")
    return target.read_bytes(), ct


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: ANN401
        _log.debug(fmt, *args)

    def _is_admin_token(self) -> bool:
        """Portador do ATLAS_API_TOKEN ou loopback ⇒ admin (retrocompat E0-05)."""
        if not _TOKEN:
            ip = self.client_address[0]
            return ip in ("127.0.0.1", "::1", "::ffff:127.0.0.1")
        return self.headers.get("Authorization", "") == f"Bearer {_TOKEN}"

    def _session_token(self) -> str:
        """Lê o token de sessão do cookie ``atlas_session``."""
        from http.cookies import SimpleCookie

        raw = self.headers.get("Cookie", "")
        if not raw:
            return ""
        try:
            morsel = SimpleCookie(raw).get(_SESSION_COOKIE)
        except Exception:  # noqa: BLE001 — cookie malformado ⇒ sem sessão
            return ""
        return morsel.value if morsel else ""

    def _identity(self) -> tuple[str | None, str | None]:
        """``(user, role)`` do request: admin (token/loopback) ou sessão; senão ``(None, None)``."""
        if self._is_admin_token():
            return (_DEFAULT_OWNER, "admin")
        sess = sessions.resolve_session(self._session_token())
        if sess:
            return (sess["user"], sess["role"])
        return (None, None)

    def _auth(self) -> bool:
        """Autorizado se admin (token/loopback) ou sessão válida."""
        return self._identity()[0] is not None

    def _owner(self) -> str:
        """Dono corrente para escopar recursos (Fase 5); admin/loopback ⇒ default."""
        return self._identity()[0] or _DEFAULT_OWNER

    def _json(self, code: int, body: Any, *, cookies: list[str] | None = None) -> None:
        data = json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        for c in cookies or []:
            self.send_header("Set-Cookie", c)
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

    def _download_traducao(self, label: str, previa: bool = False) -> None:
        """Stream do PDF de ``Traducao/<label>`` — a saída final (status.saida) ou,
        com ``previa=True``, o snapshot renderizado durante a tradução (status.previa)."""
        if _store is None:
            self._json(503, {"error": "store not ready"})
            return
        t = _store.get("Traducao", label) if label else None
        if t is None:
            self._json(404, {"error": f"Traducao/{label} not found"})
            return
        campo = "previa" if previa else "saida"
        saida = (t.status or {}).get(campo)
        if not saida:
            falta = (
                "prévia ainda não gerada" if previa else "tradução ainda não concluída (sem saída)"
            )
            self._json(409, {"error": falta})
            return
        alvo = Path(saida)
        if not alvo.is_file():
            self._json(404, {"error": f"arquivo de saída ausente: {saida}"})
            return
        data = alvo.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="{alvo.name}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _exportar_traducao(self, label: str, fmt: str) -> None:
        """Gera e faz stream do arquivo ``fmt`` (md|epub) da tradução (ADR-0032)."""
        from atlas.traducao.exportar import PandocAusente, exportar

        if _store is None:
            self._json(503, {"error": "store not ready"})
            return
        t = _store.get("Traducao", label) if label else None
        if t is None:
            self._json(404, {"error": f"Traducao/{label} not found"})
            return
        saida = (t.status or {}).get("saida")
        if not saida or not Path(saida).is_file():
            self._json(409, {"error": "tradução ainda não concluída (sem saída)"})
            return
        try:
            caminho = exportar(saida, fmt)
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
            return
        except PandocAusente as exc:
            self._json(503, {"error": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001 — falha de conversão não derruba a API
            self._json(500, {"error": f"falha ao exportar: {exc}"})
            return
        alvo = Path(caminho)
        data = alvo.read_bytes()
        ctype = "application/epub+zip" if fmt == "epub" else "text/markdown; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="{alvo.name}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization,Content-Type")
        self.end_headers()

    def _handle_curadoria(self, path: str, prefix: str) -> None:
        """POST /_agent_run/{id}/discard|approve — curadoria do gate (SPEC-CURADORIA-GATE)."""
        acao = "discard" if path.endswith("/discard") else "approve"
        run_id = path[len(prefix) : -len("/" + acao)]
        owner, role = self._identity()
        res = _curate_run(_store, run_id, owner, role)
        if res is None:
            self._json(404, {"error": f"run '{run_id}' não encontrado"})
            return
        ws = res.spec.get("workspace")
        try:
            if acao == "discard":
                curadoria.discard_workspace(_PROJECT_DIR, ws)
                res.status["review"] = "discarded"
                _store.set_status("AgentRun", run_id, res.status, datetime.now())
                self._json(200, {"id": run_id, "review": "discarded"})
            else:
                branch = f"agent/{run_id}"
                task = (res.spec.get("task") or "").splitlines()[0][:60]
                agente = res.spec.get("agente") or "agente"
                msg = (
                    f"agent({agente}): {task}\n\n"
                    f"Curadoria do run {run_id} (modo code).\n\n"
                    "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
                )
                curadoria.approve_to_branch(_PROJECT_DIR, ws, branch, msg)
                res.status["review"] = "approved"
                res.status["branch"] = branch
                _store.set_status("AgentRun", run_id, res.status, datetime.now())
                self._json(200, {"id": run_id, "review": "approved", "branch": branch})
        except Exception as exc:  # noqa: BLE001
            self._json(500, {"error": f"falha na curadoria ({acao}): {exc}"})

    def _handle_auth_post(self, path: str, body: dict) -> None:
        """Endpoints públicos de login/sessão (ADR-0027 F4)."""
        if path == _API_PREFIX + "/_auth/login":
            out, token = _auth_login(_store, body.get("user", ""), body.get("password", ""))
            cookies = [_set_cookie(token)] if token else None
            self._json(200 if out.get("ok") else 401, out, cookies=cookies)
            return
        # Auto-registro com código compartilhado (SPEC-AUTO-REGISTRO) — público.
        if path == _API_PREFIX + "/_auth/register":
            out, token, status = _auth_register(
                _store, body.get("user", ""), body.get("password", ""), body.get("code", "")
            )
            cookies = [_set_cookie(token)] if token else None
            self._json(status, out, cookies=cookies)
            return
        if path == _API_PREFIX + "/_auth/logout":
            sessions.destroy_session(self._session_token())
            self._json(200, {"ok": True}, cookies=[_clear_cookie()])
            return
        # Provisionamento de usuários — só admin (token/loopback ou sessão admin).
        if path == _API_PREFIX + "/_auth/users":
            if self._identity()[1] != "admin":
                self._json(403, {"error": "admin requerido"})
                return
            name = body.get("user", "").strip()
            if not name:
                self._json(400, {"error": "user obrigatório"})
                return
            u = users.create_user(
                _store,
                name,
                display_name=body.get("display_name", "").strip(),
                role=body.get("role", "member").strip() or "member",
                password=body.get("password") or None,
            )
            self._json(200, {"ok": True, "user": u.name})
            return
        # Login via GitHub (device flow) — reusa a Fase 3, mas cria sessão.
        if path == _API_PREFIX + "/_auth/github/start":
            self._json(200, _github_device_start(body.get("scope", "")))
            return
        if path == _API_PREFIX + "/_auth/github/poll":
            out, token = _github_login_poll(_store, device_code=body.get("device_code", "").strip())
            cookies = [_set_cookie(token)] if token else None
            self._json(200, out, cookies=cookies)
            return
        self._json(404, {"error": "not found"})

    def do_GET(self) -> None:
        path = self.path.split("?")[0].rstrip("/")

        if path == "" or path == "/":
            self._html(_html_dashboard())
            return
        if path == "/health":
            self._json(200, {"status": "ok"})
            return
        # Identidade corrente (público): quem sou eu? (ADR-0027 F4)
        if path == _API_PREFIX + "/_auth/me":
            user, role = self._identity()
            if user is None:
                self._json(200, {"authenticated": False})
            else:
                self._json(200, {"authenticated": True, "user": user, "role": role})
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

        # SSE stream de um run agêntico: GET /_agent_run/{run_id}/stream
        _ar_prefix = _API_PREFIX + "/_agent_run/"
        if path.startswith(_ar_prefix) and path.endswith("/stream"):
            run_id = path[len(_ar_prefix) : -len("/stream")]
            with _runs_lock:
                run = _runs.get(run_id)
            if run is None:
                self._json(404, {"error": f"run '{run_id}' não encontrado"})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            _stream_run_sse(run, self.wfile)
            return

        # GET /_agent_run/{run_id}/diff → diff da curadoria (SPEC-CURADORIA-GATE)
        if path.startswith(_ar_prefix) and path.endswith("/diff"):
            run_id = path[len(_ar_prefix) : -len("/diff")]
            owner, role = self._identity()
            res = _curate_run(_store, run_id, owner, role)
            if res is None:
                self._json(404, {"error": f"run '{run_id}' não encontrado"})
                return
            try:
                diff = curadoria.workspace_diff(_PROJECT_DIR, res.spec.get("workspace"))
            except Exception as exc:  # noqa: BLE001
                self._json(500, {"error": f"falha ao calcular diff: {exc}"})
                return
            self._json(200, {"id": run_id, "diff": diff, "review": res.status.get("review")})
            return

        # GET /_agent_run/{run_id} → estado do run (done, event count)
        if path.startswith(_ar_prefix):
            run_id = path[len(_ar_prefix) :]
            with _runs_lock:
                run = _runs.get(run_id)
            if run is None:
                self._json(404, {"error": f"run '{run_id}' não encontrado"})
                return
            with run["cond"]:
                self._json(
                    200,
                    {
                        "id": run["id"],
                        "agente": run["agente"],
                        "task": run["task"],
                        "done": run["done"],
                        "event_count": len(run["events"]),
                        "started_at": run["started_at"],
                    },
                )
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

        # /_estimar?label=<Traducao> | ?origem=<pdf>&motor=<claude|ollama>
        # Prévia grátis (sem IA, P1) de páginas/blocos/tokens/custo antes de rodar
        # (ADR-0030 §Estimativa; ADR-0005 orçamento reativo).
        # /_download?label=<Traducao> → baixa o PDF traduzido (status.saida)
        if path == _API_PREFIX + "/_download":
            from urllib.parse import parse_qs, urlparse

            q = parse_qs(urlparse(self.path).query)
            label = q.get("label", [""])[0].strip()
            previa = q.get("previa", ["0"])[0] in ("1", "true", "yes")
            self._download_traducao(label, previa=previa)
            return

        # /_exportar?label=<Traducao>&fmt=md|epub → serializa e baixa (ADR-0032)
        if path == _API_PREFIX + "/_exportar":
            from urllib.parse import parse_qs, urlparse

            q = parse_qs(urlparse(self.path).query)
            label = q.get("label", [""])[0].strip()
            fmt = (q.get("fmt", ["md"])[0] or "md").strip().lower()
            self._exportar_traducao(label, fmt)
            return

        if path == _API_PREFIX + "/_estimar":
            from urllib.parse import parse_qs, urlparse

            qs = parse_qs(urlparse(self.path).query)
            label = qs.get("label", [""])[0].strip()
            origem = qs.get("origem", [""])[0].strip()
            motor = qs.get("motor", [""])[0].strip()
            code, payload = _estimar_payload(_store, label, origem, motor)
            self._json(code, payload)
            return

        # GET /_traducao_pool → visibilidade agregada (ADR-0038): quem roda/na fila.
        if path == _API_PREFIX + "/_traducao_pool":
            code, payload = _traducao_pool_estado()
            self._json(code, payload)
            return

        rest = path[len(_API_PREFIX) :].strip("/")
        parts = rest.split("/") if rest else []

        owner, role = self._identity()
        if len(parts) == 1:
            kind = parts[0]
            resources = scoping.visible(_store.list(kind), owner, role)
            self._json(200, [_resource_to_dict(r) for r in resources])
            return

        if len(parts) == 2:
            kind, name = parts
            r = _store.get(kind, name)
            # invisível ⇒ 404 (não revela a existência de recurso alheio)
            if r is None or not scoping.can_see(r, owner, role):
                self._json(404, {"error": f"{kind}/{name} not found"})
                return
            self._json(200, _resource_to_dict(r))
            return

        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = self.path.split("?")[0].rstrip("/")
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""

        # Upload de PDF (corpo binário, não-JSON): salvo aqui antes do parse.
        if path == _API_PREFIX + "/_upload":
            if not self._auth():
                self._json(401, {"error": "unauthorized"})
                return
            from urllib.parse import parse_qs, urlparse

            qs = parse_qs(urlparse(self.path).query)
            self._json(*_salvar_upload(qs.get("name", [""])[0], qs.get("label", [""])[0], raw))
            return

        body = json.loads(raw) if raw else {}

        # Endpoints públicos de login (pré-auth): não se pode estar logado p/ logar.
        if path.startswith(_API_PREFIX + "/_auth/"):
            if _store is None:
                self._json(503, {"error": "store not ready"})
                return
            self._handle_auth_post(path, body)
            return

        if not self._auth():
            self._json(401, {"error": "unauthorized"})
            return
        if _store is None:
            self._json(503, {"error": "store not ready"})
            return

        # Executa uma rotina/Job sob demanda (botão "Executar" no dashboard).
        # Aceita {routine: <nome>} OU {repo: <nome>} (resolve o Job de sync por label).
        if path == _API_PREFIX + "/_run":
            name = body.get("routine", "").strip()
            repo = body.get("repo", "").strip()
            if repo and not name:
                name = _resolve_repo_sync_job(repo) or ""
                if not name:
                    self._json(
                        404,
                        {
                            "ok": False,
                            "error": f"nenhum Job de sync para o repo '{repo}' "
                            "(esperado um Job com spec.coletar=repo-sync e spec.label="
                            f"'{repo}')",
                        },
                    )
                    return
            if not name:
                self._json(400, {"error": "routine ou repo obrigatório"})
                return
            self._json(200, _run_routine(name))
            return

        # Traduz um Traducao/<label> em background (ADR-0030): dispara o collect
        # traduzir-pdf numa thread; o progresso vai para o status (polling da view).
        if path == _API_PREFIX + "/_traduzir":
            label = body.get("label", "").strip()
            if not label:
                self._json(400, {"error": "label obrigatório"})
                return
            self._json(*_iniciar_traducao(label))
            return

        # Renderiza uma PRÉVIA do cache atual durante a tradução (E9): não bloqueia
        # o job em curso; gera .previa.pdf em background e grava status.previa.
        if path == _API_PREFIX + "/_previa":
            label = body.get("label", "").strip()
            if not label:
                self._json(400, {"error": "label obrigatório"})
                return
            self._json(*_iniciar_previa(label))
            return

        # POST /_traducao_pool/escalar {max_concorrente} → muda o teto em runtime
        # (ADR-0038: escalonamento tipo "réplicas"; drena a fila se subiu).
        if path == _API_PREFIX + "/_traducao_pool/escalar":
            self._json(*_traducao_pool_escalar(body))
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

        # Agente modo=code — inicia run agêntico em background, devolve run_id.
        if path == _API_PREFIX + "/_agent_run":
            agente_name = body.get("agente", "").strip()
            mensagem = body.get("mensagem", "").strip()
            if not agente_name or not mensagem:
                self._json(400, {"error": "agente e mensagem obrigatórios"})
                return
            # Teto de concorrência (ADR-0028 §3): protege a Rasp e a assinatura.
            if active_runs_count() >= _RUNS_CONCURRENT_MAX:
                self._json(
                    429,
                    {
                        "error": f"limite de {_RUNS_CONCURRENT_MAX} runs simultâneos atingido",
                        "retry": True,
                    },
                )
                return
            run = _new_run(agente_name, mensagem)
            run["owner"] = self._owner()
            threading.Thread(
                target=_run_agent_bg,
                args=(run, _store),
                daemon=True,
                name=f"agent-run-{run['id']}",
            ).start()
            self._json(202, {"run_id": run["id"], "agente": agente_name})
            return

        # Curadoria do gate (SPEC-CURADORIA-GATE): descartar/aprovar o diff de um run.
        _ar_prefix = _API_PREFIX + "/_agent_run/"
        if path.startswith(_ar_prefix) and path.endswith(("/discard", "/approve")):
            self._handle_curadoria(path, _ar_prefix)
            return

        # GitHub device flow (ADR-0027 F3): conectar a conta do usuário sem callback.
        if path == _API_PREFIX + "/_github/device/start":
            self._json(200, _github_device_start(body.get("scope", "")))
            return
        if path == _API_PREFIX + "/_github/device/poll":
            self._json(
                200,
                _github_device_poll(
                    _store,
                    owner=body.get("owner", "").strip() or self._owner(),
                    device_code=body.get("device_code", "").strip(),
                ),
            )
            return
        # Fallback: colar um PAT quando o OAuth App não está configurado.
        if path == _API_PREFIX + "/_github/pat":
            self._json(
                200,
                _github_pat(
                    _store,
                    owner=body.get("owner", "").strip() or self._owner(),
                    token=body.get("token", "").strip(),
                    account=body.get("account", "").strip(),
                ),
            )
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
        owner, role = self._identity()
        if not scoping.can_write(existing, owner, role):
            self._json(403, {"error": "sem permissão sobre este recurso"})
            return
        labels = {**((existing.labels or {}) if existing else {}), **body.get("labels", {})}
        labels = scoping.stamp_owner(labels, owner, role)  # member não escolhe o dono
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

        # DELETE /_traducao_pool/fila/<label> → cancela da fila (ADR-0038).
        if len(parts) == 3 and parts[0] == "_traducao_pool" and parts[1] == "fila":
            self._json(*_traducao_pool_cancelar_fila(parts[2]))
            return

        if len(parts) != 2:
            self._json(400, {"error": "DELETE requires /apis/atlas/v1/<kind>/<name>"})
            return

        kind, name = parts
        existing = _store.get(kind, name)
        owner, role = self._identity()
        # invisível ⇒ 404; visível mas sem permissão (alheio/system) ⇒ 403
        if existing is None or not scoping.can_see(existing, owner, role):
            self._json(404, {"error": f"{kind}/{name} not found"})
            return
        if not scoping.can_write(existing, owner, role):
            self._json(403, {"error": "sem permissão sobre este recurso"})
            return
        ok = _store.delete(kind, name)
        if ok:
            _limpar_artefatos(existing)  # tradução pronta é efêmera: some com o objeto
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


def _estimar_payload(
    store: ResourceStore | None, label: str, origem: str, motor: str
) -> tuple[int, dict]:
    """Prévia de custo/tamanho de uma tradução (ADR-0030). Grátis: não chama IA (P1).

    Aceita ``label`` de um ``Traducao`` existente (usa spec.origem/motor) OU ``origem``
    (caminho do PDF) + ``motor`` diretos. Devolve ``(código_http, corpo)``.
    """
    from atlas.traducao.estimativa import estimar

    if label:
        if store is None:
            return 503, {"error": "store not ready"}
        t = store.get("Traducao", label)
        if t is None:
            return 404, {"error": f"Traducao/{label} not found"}
        origem = (t.spec.get("origem") or "").strip()
        motor = motor or t.spec.get("motor", "claude")
    if not origem:
        return 400, {"error": "label ou origem obrigatório"}
    if not Path(origem).exists():
        return 400, {"error": f"origem inexistente: {origem!r}"}
    try:
        est = estimar(origem, motor=motor or "claude")
    except Exception as exc:  # noqa: BLE001 — PDF inválido não derruba a API
        return 500, {"error": f"falha ao estimar: {exc}"}
    return 200, est.to_dict()


def _pdf_dir() -> Path:
    """Diretório onde uploads de PDF são gravados (ADR-0030). Configurável por env."""
    d = os.environ.get("ATLAS_PDF_DIR") or str(Path(_PROJECT_DIR) / "data" / "pdfs")
    p = Path(d)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe_pdf_name(name: str) -> str:
    """Basename saneado terminando em .pdf (evita path traversal)."""
    base = os.path.basename((name or "").strip()) or "upload.pdf"
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    return base


def _salvar_upload(name: str, label: str, data: bytes) -> tuple[int, dict]:
    """Grava um PDF enviado em ``data/pdfs/`` (ADR-0030). Devolve ``(código, corpo)``.

    Se ``label`` aponta um ``Traducao`` existente, atualiza ``spec.origem`` para o
    arquivo salvo — o upload já deixa o recurso pronto para estimar/traduzir.
    """
    if not data:
        return 400, {"error": "corpo vazio (envie o PDF como bytes)"}
    if data[:5] != b"%PDF-":
        return 400, {"error": "arquivo não é um PDF (%PDF- ausente)"}
    destino = _pdf_dir() / _safe_pdf_name(name)
    destino.write_bytes(data)
    caminho = str(destino)
    if label and _store is not None and _store.get("Traducao", label) is not None:
        _store.patch("Traducao", label, {"origem": caminho}, datetime.now())
    return 200, {"ok": True, "path": caminho, "name": destino.name}


def _iniciar_traducao(label: str) -> tuple[int, dict]:
    """Dispara a tradução de ``Traducao/<label>`` em background (ADR-0030),
    passando pelo pool de execução (ADR-0038: teto escalável + fila FIFO).

    Se há slot livre, roda agora (thread daemon); acima do teto, enfileira
    (``status.fase = "fila"``) e é despachada automaticamente quando um slot
    libera. Devolve ``(código_http, corpo)``.
    """
    from atlas.rotinas import obter as _obter

    if _store is None:
        return 503, {"error": "store not ready"}
    t = _store.get("Traducao", label)
    if t is None:
        return 404, {"error": f"Traducao/{label} not found"}
    fase_atual = (t.status or {}).get("fase")
    if fase_atual in ("traduzindo", "fila"):
        return 409, {"ok": False, "error": f"Traducao/{label} já está {fase_atual}"}
    origem = (t.spec.get("origem") or "").strip()
    if not origem or not Path(origem).exists():
        return 400, {"error": f"origem inválida: {origem!r}"}
    try:
        _obter("traduzir-pdf")  # valida antes de reservar slot no pool
    except Exception as exc:  # noqa: BLE001
        return 500, {"error": f"collect traduzir-pdf não registrado: {exc}"}

    if _traducao_pool.tentar_iniciar(label):
        _disparar_traducao_thread(label)
        return 200, {"ok": True, "label": label, "fase": "traduzindo"}

    _store.set_status("Traducao", label, {**(t.status or {}), "fase": "fila"}, datetime.now())
    return 200, {"ok": True, "label": label, "fase": "fila"}


def _disparar_traducao_thread(label: str) -> None:
    """Roda o collect ``traduzir-pdf`` de ``label`` numa thread daemon.

    Ao terminar (sucesso, erro ou pausa), libera o slot no pool e despacha o
    próximo da fila, se houver (ADR-0038) — encadeando até a fila esvaziar.
    """
    from atlas.executor import ContextoExecucao
    from atlas.rotinas import obter as _obter
    from atlas.routines import Rotina

    rot = Rotina(nome=label, descricao="", label=label, coletar="traduzir-pdf")

    def _run() -> None:
        try:
            collect = _obter("traduzir-pdf")
            ctx = ContextoExecucao(agora=datetime.now(), rotina=rot, origem="web", store=_store)
            collect(ctx)
        except Exception:  # noqa: BLE001 — status já é marcado como erro pelo collect
            _log.exception("traducao %s falhou", label)
        finally:
            proximo = _traducao_pool.liberar(label)
            if proximo:
                _disparar_traducao_thread(proximo)

    threading.Thread(target=_run, daemon=True, name=f"traduzir-{label}").start()


def _traducao_pool_estado() -> tuple[int, dict]:
    """``GET /_traducao_pool`` (ADR-0038): visibilidade agregada do pool."""
    return 200, _traducao_pool.estado()


def _traducao_pool_escalar(body: dict) -> tuple[int, dict]:
    """``POST /_traducao_pool/escalar`` (ADR-0038): muda o teto em runtime.

    Se o novo teto é maior, despacha imediatamente quem estava na fila.
    """
    try:
        novo_max = int(body.get("max_concorrente"))
    except (TypeError, ValueError):
        return 400, {"error": "max_concorrente deve ser um inteiro"}
    if novo_max < 1:
        return 400, {"error": "max_concorrente deve ser >= 1"}
    despachados = _traducao_pool.escalar(novo_max)
    for label in despachados:
        _disparar_traducao_thread(label)
    return 200, _traducao_pool.estado()


def _traducao_pool_cancelar_fila(label: str) -> tuple[int, dict]:
    """``DELETE /_traducao_pool/fila/<label>`` (ADR-0038): tira da fila antes
    de rodar (sem custo de IA). 404 se o label não está na fila."""
    if not _traducao_pool.cancelar_da_fila(label):
        return 404, {"error": f"{label!r} não está na fila"}
    if _store is not None:
        t = _store.get("Traducao", label)
        if t is not None and (t.status or {}).get("fase") == "fila":
            _store.set_status(
                "Traducao", label, {**(t.status or {}), "fase": "cancelado"}, datetime.now()
            )
    return 200, {"ok": True, "label": label}


def _iniciar_previa(label: str) -> tuple[int, dict]:
    """Renderiza uma prévia (snapshot do cache atual) em background — pode rodar
    concorrente à tradução em curso (E9). Não altera a ``fase`` do job."""
    from atlas.rotinas.traduzir_pdf import render_previa

    if _store is None:
        return 503, {"error": "store not ready"}
    t = _store.get("Traducao", label)
    if t is None:
        return 404, {"error": f"Traducao/{label} not found"}
    if (t.status or {}).get("previa_gerando"):
        return 409, {"ok": False, "error": "prévia já está sendo gerada"}

    def _run() -> None:
        try:
            render_previa(_store, label, datetime.now())
        except Exception:  # noqa: BLE001 — status já registra o erro (ADR-0006)
            _log.exception("prévia %s falhou", label)

    threading.Thread(target=_run, daemon=True, name=f"previa-{label}").start()
    return 200, {"ok": True, "label": label, "previa_gerando": True}


def _limpar_artefatos(res) -> None:
    """Remove arquivos gerados por um recurso ao deletá-lo (tradução é efêmera).

    Para ``Traducao``: apaga o PDF de saída (``status.saida``) e o cache de
    tradução em disco. Best-effort — nunca levanta (ADR-0006). O PDF de origem
    (enviado pelo usuário) é preservado.
    """
    if res is None or getattr(res, "kind", None) != "Traducao":
        return
    from atlas.rotinas.traduzir_pdf import _cache_para

    spec = res.spec or {}
    status = res.status or {}
    origem = (spec.get("origem") or "").strip()
    idioma_destino = spec.get("idioma_destino", "pt-BR")
    candidatos = [status.get("saida")]
    if origem:
        candidatos.append(_cache_para(origem, idioma_destino))
    for caminho in candidatos:
        if not caminho:
            continue
        try:
            p = Path(caminho)
            if p.exists():
                p.unlink()
                _log.info("artefato removido: %s", caminho)
        except OSError as exc:
            _log.warning("falha ao remover artefato %s: %s", caminho, exc)


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


def _resolve_repo_sync_job(repo: str) -> str | None:
    """Acha o Job de sync de um Repo **por label** (P11), não por nome.

    Convenção: o Job de sync tem ``spec.coletar == 'repo-sync'`` e
    ``spec.label == <nome do repo>``. O nome do Job é livre.
    """
    if _store is None or not repo:
        return None
    for j in _store.list("Job"):
        sp = j.spec or {}
        if sp.get("coletar") == "repo-sync" and sp.get("label") == repo:
            return j.name
    return None


def _rotina_from_job(job):  # noqa: ANN001, ANN201
    """Constrói uma ``Rotina`` a partir de um Job do store (criado pela API/IA)."""
    from atlas.routines import Rotina

    sp = job.spec or {}
    return Rotina(
        nome=job.name,
        descricao=sp.get("description", ""),
        agenda=sp.get("schedule"),
        modelo=sp.get("model", "none"),
        saida=sp.get("saida") or sp.get("output"),
        ativa=bool(sp.get("active", True)),
        label=sp.get("label"),
        coletar=sp.get("coletar"),
    )


def _run_routine(name: str) -> dict:
    """Executa o collect de uma rotina/Job sob demanda (sem esperar a agenda).

    Resolve a rotina do disco (``routines/``) **ou**, se não existir lá, de um
    ``Job`` do store (recursos criados pela API/IA também rodam).
    """
    from pathlib import Path

    from atlas.db import Database as _DB
    from atlas.executor import ContextoExecucao
    from atlas.rotinas import obter as _obter
    from atlas.routines import carregar_rotinas

    rdir = os.environ.get("ATLAS_ROUTINES_DIR", "routines")
    carga = carregar_rotinas(Path(rdir))
    rot = next((r for r in carga.rotinas if r.nome == name), None)
    if rot is None and _store is not None:
        # Fallback: Job existente no store (ex.: criado pela IA via API)
        job = _store.get("Job", name)
        if job is not None:
            rot = _rotina_from_job(job)
    if rot is None:
        return {"ok": False, "error": f"rotina/Job '{name}' não encontrada"}

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
    """Gera um insight por IA sobre o sistema ou um repositório (sob demanda).

    Para repo, a análise é feita pelo **Agente configurado** em
    ``Repo.spec.analyze_agente`` (default ``repo-analyzer``) — o Agente dita
    motor/modelo (via LLMProvider, ADR-0022/0026) e a persona/prompt (ADR-0024).
    """
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

        # Despacha ao Agente de análise configurado (ADR-0024).
        agente_name = (rp.spec.get("analyze_agente") or "repo-analyzer").strip()
        agente = _store.get("Agente", agente_name)
        if agente is not None:
            res = _agente_chat(agente_name, ctx_txt, _store)
            if res.get("error"):
                return {"ok": False, "error": res["error"]}
            resposta = res.get("response", "")
            used_model = res.get("modelo", model)
            doc_name = _salvar_insight_doc(scope, name, resposta, used_model)
            return {
                "ok": True,
                "scope": scope,
                "name": name,
                "model": used_model,
                "agente": agente_name,
                "insight": resposta,
                "doc": doc_name,
            }
        # Fallback: Agente ausente → prompt embutido (retrocompat)
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


def _resolve_engine(agente_spec: dict, store: ResourceStore) -> dict:
    """Resolve motor/modelo/endpoint/timeout de um Agente (ADR-0022/0026).

    Ordem: se ``spec.provider`` aponta para um ``LLMProvider`` existente, ele dita
    motor/endpoint/timeout e o modelo padrão; ``spec.modelo`` (se houver) sobrepõe
    o modelo do provider. Sem provider, usa os campos próprios do Agente (fallback
    retrocompatível).
    """
    spec = agente_spec or {}
    prov_name = (spec.get("provider") or "").strip()
    prov_spec: dict = {}
    if prov_name and store is not None:
        prov = store.get("LLMProvider", prov_name)
        if prov is not None:
            prov_spec = prov.spec or {}

    motor = (prov_spec.get("motor") or spec.get("motor") or "claude").strip()
    # modelo: override do Agente > modelo do provider > default por motor
    modelo = (
        (spec.get("modelo") or "").strip()
        or (prov_spec.get("modelo") or "").strip()
        or ("claude-haiku-4-5-20251001" if motor == "claude" else "gemma4")
    )
    endpoint = (
        (prov_spec.get("endpoint") or "").strip()
        or (spec.get("endpoint") or "").strip()
        or os.environ.get("ATLAS_OLLAMA_ENDPOINT", "")
    )
    try:
        timeout = int(spec.get("timeout") or prov_spec.get("timeout") or 60)
    except (TypeError, ValueError):
        timeout = 60
    return {
        "motor": motor,
        "modelo": modelo,
        "endpoint": endpoint,
        "timeout": timeout,
        "provider": prov_name or None,
    }


# ── Login / sessão (ADR-0027 Fase 4) ──────────────────────────────────────────


def _user_role(store: ResourceStore, user: str) -> str:
    r = store.get("User", user)
    return (r.spec.get("role") if r else None) or "member"


def _auth_login(store: ResourceStore, user: str, password: str) -> tuple[dict, str | None]:
    """Login por senha local → cria sessão. Devolve ``(body, token|None)``."""
    user = (user or "").strip().lower()
    if not user or not users.verify_password(user, password):
        return ({"ok": False, "error": "credenciais inválidas"}, None)
    role = _user_role(store, user)
    token = sessions.create_session(user, role=role)
    return ({"ok": True, "user": user, "role": role}, token)


def _auth_register(
    store: ResourceStore, user: str, password: str, code: str
) -> tuple[dict, str | None, int]:
    """Auto-registro com código compartilhado (SPEC-AUTO-REGISTRO).

    Cria sempre um usuário ``member`` e abre sessão. Devolve ``(body, token, status)``.
    Desabilitado se ``ATLAS_SIGNUP_CODE`` não estiver setado.
    """
    expected = os.environ.get("ATLAS_SIGNUP_CODE", "")
    if not expected:
        return ({"ok": False, "error": "auto-registro desabilitado"}, None, 403)
    if not code or not hmac.compare_digest(str(code), expected):
        return ({"ok": False, "error": "código de cadastro inválido"}, None, 403)
    try:
        name = users.normalize_name(user)
    except ValueError:
        return ({"ok": False, "error": "usuário inválido"}, None, 400)
    if not password:
        return ({"ok": False, "error": "senha obrigatória"}, None, 400)
    if store.get("User", name) is not None:
        return ({"ok": False, "error": "usuário já existe"}, None, 409)
    users.create_user(store, name, role="member", password=password)
    token = sessions.create_session(name, role="member")
    return ({"ok": True, "user": name, "role": "member"}, token, 200)


def _github_login_poll(store: ResourceStore, *, device_code: str) -> tuple[dict, str | None]:
    """Login via GitHub: poll → resolve username → cria User/credencial + sessão."""
    if not device_code:
        return ({"status": "error", "error": "device_code obrigatório"}, None)
    out = github_auth.poll_access_token(device_code)
    if out.get("status") != "connected":
        return (out, None)
    token = out["access_token"]
    try:
        login = github_auth.fetch_github_login(token)
    except github_auth.GitHubAuthError as exc:
        return ({"status": "error", "error": str(exc)}, None)
    user = users.normalize_name(login)
    if store.get("User", user) is None:
        users.create_user(store, user, display_name=login)
    # guarda a credencial cifrada (o repo-sync passa a usar a conta do usuário)
    credentials.save_credential(
        store,
        owner=user,
        provider="github",
        secret=token,
        account=login,
        scopes=out.get("scope", ""),
    )
    sess = sessions.create_session(user, role=_user_role(store, user))
    return ({"status": "connected", "user": user}, sess)


# ── GitHub device flow + PAT (ADR-0027 Fase 3) ────────────────────────────────


def _github_device_start(scope: str = "") -> dict:
    """Inicia o device flow do GitHub. Devolve user_code/verification_uri ou {error}."""
    try:
        return github_auth.start_device_flow(scope=scope or github_auth.DEFAULT_SCOPE)
    except github_auth.GitHubAuthError as exc:
        return {"error": str(exc)}


def _github_device_poll(store: ResourceStore, *, owner: str, device_code: str) -> dict:
    """Faz um poll; ao obter o token, cifra e grava a Credential do dono."""
    if not device_code:
        return {"error": "device_code obrigatório"}
    try:
        return github_auth.complete_device_login(
            store, owner=owner or _DEFAULT_OWNER, device_code=device_code
        )
    except github_auth.GitHubAuthError as exc:
        return {"status": "error", "error": str(exc)}


def _github_pat(store: ResourceStore, *, owner: str, token: str, account: str = "") -> dict:
    """Fallback: salva um PAT colado como Credential cifrada do dono."""
    try:
        cid = github_auth.connect_via_pat(
            store, owner=owner or _DEFAULT_OWNER, token=token, account=account
        )
        return {"status": "connected", "credential": cid}
    except github_auth.GitHubAuthError as exc:
        return {"error": str(exc)}


def _agente_chat(agente_name: str, mensagem: str, store: ResourceStore) -> dict:
    """Executa o Kind Agente em modo chat (E7-25, ADR-0024).

    Busca o recurso Agente, constrói o prompt com o template e chama o motor
    resolvido (via LLMProvider ou campos próprios — ADR-0026). Suporta
    nivel_contexto (resumo|completo) para injetar schema e contexto do projeto
    (E7-24 — builder). Devolve {response, motor, modelo, commands?} ou {error}.
    """
    from atlas.ia import InvocarErro, invocar

    if not agente_name or not mensagem:
        return {"error": "agente e mensagem são obrigatórios"}
    agente = store.get("Agente", agente_name)
    if agente is None:
        return {"error": f"Agente '{agente_name}' não encontrado"}

    spec = agente.spec or {}
    eng = _resolve_engine(spec, store)
    motor = eng["motor"]
    modelo = eng["modelo"]
    timeout = eng["timeout"]
    endpoint = eng["endpoint"]
    template = spec.get("prompt") or "{mensagem}"
    nivel = spec.get("nivel_contexto", "none")
    agora_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Injecao de contexto (E7-24)
    ctx_inject = ""
    if nivel in ("resumo", "completo"):
        ctx_inject = _schema_context(store, completo=(nivel == "completo"))

    prompt = (
        template.replace("{mensagem}", mensagem)
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
            campos = "; ".join(f"{f['k']} ({f['type']}): {f.get('hint', '')}" for f in info["spec"])
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


# ── Registro de runs agênticos (in-memory, máx 30) ──────────────────────────
_runs: dict[str, dict] = {}
_runs_lock = threading.Lock()
_RUNS_MAX = 30
# Teto de runs agênticos simultâneos (ADR-0028 §3). Protege CPU/IO + assinatura.
_RUNS_CONCURRENT_MAX = int(os.environ.get("ATLAS_AGENT_MAX_CONCURRENT", "3"))


def _csv_clean(value: str | None) -> str:
    """Normaliza um csv: tira espaços, descarta itens vazios. ``"a, ,b,"`` → ``"a,b"``."""
    if not value:
        return ""
    return ",".join(part.strip() for part in value.split(",") if part.strip())


def build_tool_args(allowed: str | None, denied: str | None) -> list[str]:
    """Monta os flags de allow/deny de tools do `claude` CLI (ADR-0028 §2).

    Função pura: csv vazio → sem flag (comportamento atual preservado).
    """
    args: list[str] = []
    allow = _csv_clean(allowed)
    deny = _csv_clean(denied)
    if allow:
        args += ["--allowedTools", allow]
    if deny:
        args += ["--disallowedTools", deny]
    return args


def resolve_workspace(project_dir: str, sub: str | None) -> str:
    """Resolve o workspace confinado de um run modo `code` (ADR-0028 §1).

    Retorna o caminho absoluto de ``<project_dir>/<sub>``, garantindo que ele fica
    **dentro** de ``project_dir`` (recusa traversal ``..``, caminho absoluto e
    symlink que escapa). Recusa caminho inexistente. ``sub`` vazio = a raiz.
    """
    root = Path(project_dir).resolve()
    if not sub or not sub.strip():
        return str(root)
    sub = sub.strip()
    if Path(sub).is_absolute():
        raise ValueError(f"workspace deve ser relativo, não absoluto: {sub!r}")
    target = (root / sub).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"workspace {sub!r} escapa da raiz do projeto")
    if not target.is_dir():
        raise ValueError(f"workspace {sub!r} não existe sob a raiz do projeto")
    return str(target)


def active_runs_count() -> int:
    """Quantos runs agênticos ainda não terminaram (ADR-0028 §3)."""
    with _runs_lock:
        return sum(1 for r in _runs.values() if not r.get("done"))


def summarize_run(run: dict) -> dict:
    """Resumo persistível de um run agêntico (ADR-0028 §5).

    ``status``: ``done`` (sem erro), ``error`` (algum evento de erro) ou
    ``running`` (ainda não terminou).
    """
    events = run.get("events", [])
    if not run.get("done"):
        status = "running"
    elif any(e.get("type") == "error" for e in events):
        status = "error"
    else:
        status = "done"
    # Pede curadoria só quando o run foi gated e terminou bem (SPEC-CURADORIA-GATE).
    review = "pending" if (run.get("gated") and status == "done") else None
    return {
        "agente": run.get("agente"),
        "task": run.get("task"),
        "owner": run.get("owner"),
        "workspace": run.get("workspace"),
        "status": status,
        "review": review,
        "cost_usd": run.get("cost", 0.0),
        "events": len(events),
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
    }


def _curate_run(
    store: ResourceStore,
    run_id: str,
    owner: str | None,
    role: str | None,
) -> Resource | None:
    """Resolve o ``AgentRun`` para curadoria, respeitando o dono (ADR-0027).

    Retorna ``None`` se não existe **ou** se é de outro dono (caller responde 404 —
    não revela a existência de recurso alheio, como ``scoping.py``).
    """
    res = store.get("AgentRun", run_id)
    if res is None or not scoping.can_see(res, owner, role):
        return None
    return res


def persist_agent_run(store: ResourceStore | None, run: dict) -> None:
    """Persiste o run como Kind ``AgentRun`` (ADR-0028 §5), escopado por dono.

    Uma vez no store, a API genérica (ADR-0027) já serve/escopa o histórico por
    `labels.owner`. Degrade silencioso (ADR-0006): falha ao persistir não derruba
    o run.
    """
    if store is None:
        return
    s = summarize_run(run)
    status = {k: s[k] for k in ("status", "cost_usd", "events", "finished_at")}
    if s["review"] is not None:
        status["review"] = s["review"]
    try:
        store.apply(
            Resource(
                kind="AgentRun",
                name=run["id"],
                labels={"owner": s["owner"] or _DEFAULT_OWNER, "origem": "agent-run"},
                spec={
                    "agente": s["agente"],
                    "task": s["task"],
                    "started_at": s["started_at"],
                    "workspace": s["workspace"],
                },
                status=status,
            ),
            datetime.now(),
        )
    except Exception:  # noqa: BLE001
        _log.exception("falha ao persistir AgentRun %s", run.get("id"))


def _new_run(agente_name: str, mensagem: str) -> dict:
    """Cria entrada de run no registro; descarta os mais velhos acima do limite."""
    run_id = uuid.uuid4().hex[:8]
    run: dict = {
        "id": run_id,
        "agente": agente_name,
        "task": mensagem,
        "events": [],
        "done": False,
        "started_at": datetime.now().isoformat(),
        "cond": threading.Condition(threading.Lock()),
    }
    with _runs_lock:
        if len(_runs) >= _RUNS_MAX:
            oldest = min(_runs.keys(), key=lambda k: _runs[k]["started_at"])
            del _runs[oldest]
        _runs[run_id] = run
    return run


def _emit(run: dict, obj: dict) -> None:
    """Adiciona evento ao run e notifica waiters."""
    with run["cond"]:
        run["events"].append(obj)
        run["cond"].notify_all()


def _finish_run(run: dict) -> None:
    with run["cond"]:
        run["done"] = True
        run["cond"].notify_all()


def _run_agent_bg(run: dict, store: ResourceStore) -> None:
    """Thread de background do modo=code: despacha pro motor resolvido.

    ``motor=claude`` → CLI ``claude -p`` agêntico (ADR-0025/0028). ``motor=ollama``
    → loop de tool-calling nativo (``agente_ollama``, ADR-0042); se o endpoint
    estiver fora do ar, cai pro caminho claude automaticamente (mesmo fallback
    bidirecional do ADR-0040, agora também no modo code).
    """
    agente_name = run["agente"]
    mensagem = run["task"]

    def _done(cost: float = 0.0) -> None:
        """Carimba fim + custo, finaliza o run e persiste (ADR-0028 §5)."""
        run["cost"] = cost
        run["finished_at"] = datetime.now().isoformat()
        _finish_run(run)
        persist_agent_run(store, run)

    agente = store.get("Agente", agente_name) if store else None
    if agente is None:
        _emit(run, {"type": "error", "message": f"Agente '{agente_name}' não encontrado"})
        _done()
        return

    spec = agente.spec or {}
    eng = _resolve_engine(spec, store)
    system_prompt = spec.get("prompt", "")

    # Workspace restrito (ADR-0028 §1): confina cwd/--add-dir ao subdir permitido.
    try:
        cwd = resolve_workspace(_PROJECT_DIR, spec.get("workspace"))
    except ValueError as exc:
        _emit(run, {"type": "error", "message": f"workspace inválido: {exc}"})
        _done()
        return

    # Conhecimento operacional do Atlas: schema de objetos + como usar a API.
    # Garante que o agente CRIE recursos pela API (não editando SQLite/arquivos soltos).
    api_context = _agent_api_context(store)
    full_system = (system_prompt + "\n\n" + api_context) if system_prompt else api_context

    # Gate de curadoria (ADR-0028 §4): default true p/ code. Nada gerado aqui é
    # auto-comitado/ativado — a promoção é a revisão humana do diff (CLAUDE.md §6).
    gate_raw = spec.get("gate", True)
    gated = (
        gate_raw
        if isinstance(gate_raw, bool)
        else str(gate_raw).strip().lower() not in ("false", "0", "no", "")
    )
    amplo = cwd == str(Path(_PROJECT_DIR).resolve())
    run["workspace"] = os.path.relpath(cwd, _PROJECT_DIR)  # relativo p/ a curadoria
    run["gated"] = gated

    endpoint = eng["endpoint"] or os.environ.get("ATLAS_OLLAMA_ENDPOINT", "")
    if eng["motor"] == "ollama" and agente_ollama.ollama_disponivel(endpoint):
        _run_agent_bg_ollama(
            run, store, spec, eng, endpoint, cwd, full_system, mensagem, amplo, gated, _done
        )
        return

    if eng["motor"] == "ollama":
        _emit(
            run, {"type": "warning", "message": f"ollama ({endpoint}) indisponível — usando claude"}
        )
    _run_agent_bg_claude(run, store, spec, eng, cwd, full_system, mensagem, amplo, gated, _done)


def _run_agent_bg_claude(
    run: dict,
    store: ResourceStore,
    spec: dict,
    eng: dict,
    cwd: str,
    full_system: str,
    mensagem: str,
    amplo: bool,
    gated: bool,
    _done,
) -> None:
    """Roda o modo=code via ``claude -p`` agêntico (ADR-0025/0028)."""
    from atlas.ia import _resolver_claude  # noqa: PLC0415

    agente_name = run["agente"]
    # modo code roda sempre via claude CLI → exige um modelo claude (default sonnet).
    modelo = eng["modelo"]
    if not modelo or not modelo.startswith("claude"):
        modelo = "claude-sonnet-4-6"
    timeout = max(int(spec.get("timeout") or 0), eng["timeout"], 300)

    try:
        claude_bin = _resolver_claude()
    except Exception as exc:  # noqa: BLE001
        _emit(run, {"type": "error", "message": f"claude CLI não encontrado: {exc}"})
        _done()
        return

    # O prompt é argumento posicional — deve vir DEPOIS de todos os flags
    # stream-json exige --verbose (retorna eventos em tempo real)
    args = [
        claude_bin,
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--dangerously-skip-permissions",
        "--model",
        modelo,
        "--add-dir",
        cwd,
        "--append-system-prompt",
        full_system,
    ]
    # Allow/deny de tools por Agente (ADR-0028 §2) — vazios = sem restrição.
    args += build_tool_args(spec.get("allowed_tools"), spec.get("denied_tools"))
    args += [mensagem]

    _emit(
        run,
        {
            "type": "init",
            "agente": agente_name,
            "modelo": modelo,
            "cwd": cwd,
            "workspace_amplo": amplo,
            "gated": gated,
        },
    )

    proc = None
    custo = 0.0  # acumula o gasto de IA deste run (evento result)
    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=cwd,
        )

        for raw_line in proc.stdout:  # type: ignore[union-attr]
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                if event.get("type") == "result":
                    custo = (
                        float(event.get("total_cost_usd") or event.get("cost_usd") or 0) or custo
                    )
                _emit(run, event)
            except json.JSONDecodeError:
                _emit(run, {"type": "raw", "text": line})

        proc.wait(timeout=30)
        if proc.returncode != 0:
            _emit(
                run, {"type": "error", "message": f"claude encerrou com código {proc.returncode}"}
            )
        else:
            _emit(run, {"type": "done"})
        _registrar_gasto_agente(store, agente_name, custo, modelo)

    except subprocess.TimeoutExpired:
        _emit(run, {"type": "error", "message": f"timeout após {timeout}s"})
    except FileNotFoundError:
        _emit(run, {"type": "error", "message": "binário 'claude' não encontrado"})
    except Exception as exc:  # noqa: BLE001
        _emit(run, {"type": "error", "message": str(exc)})
    finally:
        if proc is not None:
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass
        _done(custo)


def _run_agent_bg_ollama(
    run: dict,
    store: ResourceStore,
    spec: dict,
    eng: dict,
    endpoint: str,
    cwd: str,
    full_system: str,
    mensagem: str,
    amplo: bool,
    gated: bool,
    _done,
) -> None:
    """Roda o modo=code via loop de tool-calling nativo do Ollama (ADR-0042).

    Grátis (custo 0) e local. Erro de UMA tool vira evento ``warning`` (não
    termina o run — pedido do PO: "erro simples não me trava"); só falha do
    endpoint em si (``OllamaIndisponivel``) termina o run com ``error``.
    """
    agente_name = run["agente"]
    modelo = eng["modelo"] or "llama3.1"
    timeout = max(int(spec.get("timeout") or 0), eng["timeout"], 90)

    _emit(
        run,
        {
            "type": "init",
            "agente": agente_name,
            "modelo": modelo,
            "cwd": cwd,
            "workspace_amplo": amplo,
            "gated": gated,
        },
    )
    try:
        agente_ollama.rodar_loop(
            mensagem,
            system_prompt=full_system,
            cwd=cwd,
            modelo=modelo,
            endpoint=endpoint,
            timeout=timeout,
            allowed_tools=spec.get("allowed_tools"),
            denied_tools=spec.get("denied_tools"),
            on_evento=lambda ev: _emit(run, ev),
        )
        _registrar_gasto_agente(store, agente_name, 0.0, modelo)
    except agente_ollama.OllamaIndisponivel as exc:
        _emit(run, {"type": "error", "message": f"ollama ficou indisponível durante o run: {exc}"})
    except Exception as exc:  # noqa: BLE001 — nunca deixa o loop travar o run (ADR-0006)
        _emit(run, {"type": "error", "message": str(exc)})
    finally:
        _done(0.0)


def _registrar_gasto_agente(
    store: ResourceStore,
    agente_name: str,
    custo: float,
    modelo: str,
) -> None:
    """Acumula gasto de IA no status do Agente (E7-44): runs, custo total, último.

    "Gasto da IA como métrica do agente quando evocado" — fica visível no render do
    Agente e pode virar base de orçamento/meta.
    """
    if store is None or not agente_name:
        return
    try:
        agente = store.get("Agente", agente_name)
        if agente is None:
            return
        st = dict(agente.status or {})
        runs = int(st.get("runs", 0)) + 1
        total = round(float(st.get("custo_total_usd", 0) or 0) + (custo or 0), 6)
        st.update(
            {
                "runs": runs,
                "custo_total_usd": total,
                "ultimo_custo_usd": round(custo or 0, 6),
                "ultimo_modelo": modelo,
                "ultima_execucao": datetime.now().isoformat(timespec="seconds"),
            }
        )
        store.set_status("Agente", agente_name, st, datetime.now())
    except Exception:  # noqa: BLE001 — telemetria não pode derrubar o run
        pass


def _stream_run_sse(run: dict, wfile) -> None:
    """Envia (replay + live) eventos de um run via SSE para o cliente."""
    cond = run["cond"]

    def _sse(obj: dict) -> bool:
        try:
            wfile.write(("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode())
            wfile.flush()
            return True
        except (BrokenPipeError, OSError):
            return False

    sent_idx = 0
    try:
        while True:
            with cond:
                chunk = list(run["events"][sent_idx:])
                is_done = run["done"]

            for ev in chunk:
                if not _sse(ev):
                    return  # cliente desconectou
            sent_idx += len(chunk)

            if is_done:
                break  # run encerrou e todos os eventos foram enviados

            # Aguarda novo evento (timeout p/ evitar deadlock se o cliente sumiu)
            with cond:
                if not run["done"] and len(run["events"]) <= sent_idx:
                    cond.wait(timeout=5)

        # Varredura final (pode haver eventos adicionados entre checks)
        with cond:
            chunk = list(run["events"][sent_idx:])
        for ev in chunk:
            _sse(ev)

    except (BrokenPipeError, OSError):
        pass


def _agent_api_context(store: ResourceStore) -> str:
    """Instruções operacionais p/ o Agente modo=code: modelo de objetos + uso da API.

    Faz o agente criar/editar recursos de domínio **pela API REST** (seguindo o
    schema de cada Kind), em vez de mexer no SQLite ou inventar arquivos.
    """
    from atlas.api_schema import schema_payload  # noqa: PLC0415

    base = f"http://127.0.0.1:{_PORT}/apis/atlas/v1"
    payload = schema_payload()

    linhas: list[str] = [
        "=== Atlas — Modelo de Objetos (API REST estilo Kubernetes) ===",
        "",
        "Você opera o Atlas. Recursos de domínio são objetos {kind, name, spec, labels}.",
        f"A API roda em {base} (loopback, sem token quando local).",
        "",
        "REGRA: para CRIAR/EDITAR/REMOVER um recurso de domínio (Job, Tracker, Goal,",
        "Repo, Agente, Doc, Prompt, etc.), use SEMPRE a API abaixo. NUNCA edite o",
        "SQLite diretamente nem crie arquivos avulsos para representar dados.",
        "",
        "  Criar/atualizar (idempotente):",
        f"    curl -s -X PUT {base}/<Kind>/<name> \\",
        "      -H 'Content-Type: application/json' \\",
        '      -d \'{"spec": {<campos>}, "labels": {<labels>}}\'',
        f"  Listar:    curl -s {base}/<Kind>",
        f"  Detalhe:   curl -s {base}/<Kind>/<name>",
        f"  Remover:   curl -s -X DELETE {base}/<Kind>/<name>",
        f"  Schema:    curl -s {base}/_schema   (forms e campos por Kind)",
        "",
        "Kinds e campos de spec (respeite tipos e opções):",
    ]
    for kind, info in payload["kinds"].items():
        if info["meta"].get("hidden"):
            continue
        campos = []
        for f in info["spec"]:
            t = f.get("type", "text")
            opts = f.get("opts")
            campos.append(f"{f['k']}:{t}" + (f"={'|'.join(opts)}" if opts else ""))
        lbls = ", ".join(f["k"] for f in info.get("labels", []))
        desc = info["meta"].get("desc", "")
        linha = f"- {kind} — {desc}"
        if campos:
            linha += f"\n    spec: {', '.join(campos)}"
        if lbls:
            linha += f"\n    labels: {lbls}"
        linhas.append(linha)

    linhas += [
        "",
        "=== Relações entre recursos (P11 — relacione por LABELS, não por nome) ===",
        "Recursos se relacionam por labels/selectors, nunca por convenção de nome.",
        "NÃO invente nomes mágicos do tipo '<repo>-sync' para criar vínculo; o vínculo",
        "é o label. Relações que já existem:",
        "- Branch/Commit/Diff pertencem a um Repo via labels.repo=<repo>.",
        "- RepoGroup.spec.repos lista nomes de Repo (membros do grupo).",
        "- Agente.spec.provider → nome de um LLMProvider (dita motor/modelo).",
        "- Repo.spec.analyze_agente → nome de um Agente que faz a análise/insight.",
        "- Doc serializado de um repo: labels.repo=<repo>, labels.tipo=serial.",
        "",
        "IMPORTANTE — tornar um Repo sincronizável (criar Repo + seu Job de sync):",
        "  1) Crie o Repo:",
        f'     PUT {base}/Repo/<repo> -d \'{{"spec": {{"url": "https://github.com/u/r"}}}}\'',
        "  2) Crie o Job de sync — o vínculo é spec.label (= nome do Repo), e",
        "     spec.coletar DEVE ser exatamente 'repo-sync'. O NOME do Job é livre",
        "     (convenção sugerida: '<repo>-sync', mas o que liga é o label):",
        f'     PUT {base}/Job/<repo>-sync -d \'{{"spec": {{',
        '       "coletar": "repo-sync", "label": "<repo>", "schedule": "@daily 09:00",',
        '       "model": "none", "active": true, "description": "Sincroniza <repo>"',
        "     }}}}'",
        '  Rodar sob demanda: POST /_run -d \'{"repo": "<repo>"}\' (resolve o Job por label).',
        "",
        "Ao criar um novo TIPO de coisa, crie um novo Kind (não force em Kind existente).",
        "",
        "Padrões do projeto (CLAUDE.md): a doc em docs/ é a fonte de verdade; decisão",
        "de arquitetura vira ADR antes de virar código; TDD ao implementar; commits",
        "Conventional. Ao terminar, confirme objetivamente o que foi criado/alterado.",
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

    server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)

    def _run() -> None:
        _log.info(
            "API HTTP no ar: http://0.0.0.0:%d  (token=%s)",
            port,
            "sim" if _TOKEN else "loopback-only",
        )
        server.serve_forever()

    t = threading.Thread(target=_run, daemon=True, name="atlas-api")
    t.start()
