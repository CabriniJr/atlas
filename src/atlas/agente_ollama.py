"""Agente modo=``code`` via Ollama nativo (ADR-0042).

Segundo consumidor da camada 2b (ADR-0001/0025), ao lado do adapter `claude -p`
existente em ``api._run_agent_bg``. Implementa um loop de tool-calling contra
``POST /api/chat`` do Ollama (formato OpenAI-style ``tools``/``tool_calls``,
suportado por modelos com capability ``tools`` — ex.: llama3.1, qwen3.6).

Mesma superfície de segurança do modo=code via claude: workspace confinado
(``api.resolve_workspace``), allow/deny de tools (``filtrar_ferramentas``,
espelha ``api.build_tool_args``) e o mesmo gate de curadoria por diff — este
módulo só escreve arquivos, não decide o que promover.

Erro de UMA tool nunca derruba o run (pedido do PO: "erro simples não me
trava") — vira evento ``warning`` (visível, não-fatal) e o modelo tenta de
novo. Só falha de rede/endpoint é fatal (propagada; o chamador decide o
fallback para claude, ver ``api._run_agent_bg``).
"""

from __future__ import annotations

import json
import re
import subprocess
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

TURNOS_MAX_PADRAO = 40  # público — api.py usa como default quando spec.max_turnos vazio (ADR-0044)
_TURNOS_MAX = TURNOS_MAX_PADRAO
_TAMANHO_MAX_ARQUIVO = 200_000  # chars — protege contra ler um arquivo gigante
_TAMANHO_MAX_SAIDA_COMANDO = 4_000  # chars de stdout+stderr guardados no evento
_TAMANHO_MAX_BUSCA = 200  # linhas/arquivos por chamada de search_text/find_files
_DIRS_IGNORADOS = {".git", ".venv", "__pycache__", "node_modules", ".ruff_cache", ".pytest_cache"}


class FerramentaErro(RuntimeError):
    """Falha de execução de uma tool — não é fatal para o loop."""


class OllamaIndisponivel(RuntimeError):
    """Falha de rede/endpoint ao chamar o Ollama — fatal, propaga pro chamador."""


# ── Ferramentas nativas (equivalentes ao Read/Write/Edit/Bash do Claude Code) ──


def _resolver_no_workspace(cwd: str, caminho: str) -> Path:
    raiz = Path(cwd).resolve()
    bruto = Path(caminho)
    alvo = bruto.resolve() if bruto.is_absolute() else (raiz / bruto).resolve()
    if alvo != raiz and raiz not in alvo.parents:
        raise FerramentaErro(f"caminho {caminho!r} escapa do workspace")
    return alvo


def ferramenta_read_file(cwd: str, path: str) -> str:
    alvo = _resolver_no_workspace(cwd, path)
    if not alvo.is_file():
        raise FerramentaErro(f"arquivo não encontrado: {path}")
    texto = alvo.read_text(encoding="utf-8", errors="replace")
    if len(texto) > _TAMANHO_MAX_ARQUIVO:
        texto = texto[:_TAMANHO_MAX_ARQUIVO] + "\n… (truncado)"
    return texto


def ferramenta_list_dir(cwd: str, path: str = ".") -> str:
    alvo = _resolver_no_workspace(cwd, path)
    if not alvo.is_dir():
        raise FerramentaErro(f"diretório não encontrado: {path}")
    itens = sorted(p.name + ("/" if p.is_dir() else "") for p in alvo.iterdir())
    return "\n".join(itens) or "(vazio)"


def ferramenta_write_file(cwd: str, path: str, content: str) -> str:
    alvo = _resolver_no_workspace(cwd, path)
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text(content, encoding="utf-8")
    return f"escrito: {path} ({len(content)} chars)"


def ferramenta_edit_file(cwd: str, path: str, old_string: str, new_string: str) -> str:
    alvo = _resolver_no_workspace(cwd, path)
    if not alvo.is_file():
        raise FerramentaErro(f"arquivo não encontrado: {path}")
    texto = alvo.read_text(encoding="utf-8")
    n = texto.count(old_string)
    if n == 0:
        raise FerramentaErro(f"old_string não encontrado em {path}")
    if n > 1:
        raise FerramentaErro(f"old_string aparece {n}× em {path} — precisa ser único")
    alvo.write_text(texto.replace(old_string, new_string, 1), encoding="utf-8")
    return f"editado: {path}"


def ferramenta_run_command(cwd: str, command: str, timeout: int = 60) -> str:
    try:
        proc = subprocess.run(
            command, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        raise FerramentaErro(f"timeout após {timeout}s: {command}") from exc
    saida = (proc.stdout or "") + (proc.stderr or "")
    return f"(exit {proc.returncode})\n{saida[-_TAMANHO_MAX_SAIDA_COMANDO:]}"


def _arquivos_do_workspace(raiz: Path, base: Path):
    for p in raiz.rglob("*"):
        if not p.is_file():
            continue
        if any(parte in _DIRS_IGNORADOS for parte in p.relative_to(base).parts):
            continue
        yield p


def ferramenta_search_text(cwd: str, pattern: str, path: str = ".") -> str:
    """Busca por padrão (regex) linha a linha nos arquivos do workspace —
    equivalente ao Grep do Claude Code (pendência do ADR-0042)."""
    raiz = _resolver_no_workspace(cwd, path)
    if not raiz.is_dir():
        raise FerramentaErro(f"diretório não encontrado: {path}")
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        raise FerramentaErro(f"pattern regex inválido: {exc}") from exc
    base = Path(cwd).resolve()
    achados: list[str] = []
    for arq in _arquivos_do_workspace(raiz, base):
        try:
            texto = arq.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = arq.relative_to(base)
        for i, linha in enumerate(texto.splitlines(), start=1):
            if regex.search(linha):
                achados.append(f"{rel}:{i}: {linha.strip()[:200]}")
                if len(achados) >= _TAMANHO_MAX_BUSCA:
                    achados.append("… (truncado)")
                    return "\n".join(achados)
    return "\n".join(achados) or "(nenhum resultado)"


def ferramenta_find_files(cwd: str, pattern: str, path: str = ".") -> str:
    """Busca arquivos por padrão de nome (glob) — equivalente ao Glob do
    Claude Code (pendência do ADR-0042)."""
    raiz = _resolver_no_workspace(cwd, path)
    if not raiz.is_dir():
        raise FerramentaErro(f"diretório não encontrado: {path}")
    base = Path(cwd).resolve()
    achados = sorted(
        str(p.relative_to(base))
        for p in raiz.rglob(pattern)
        if not any(parte in _DIRS_IGNORADOS for parte in p.relative_to(base).parts)
    )
    if len(achados) > _TAMANHO_MAX_BUSCA:
        achados = [*achados[:_TAMANHO_MAX_BUSCA], "… (truncado)"]
    return "\n".join(achados) or "(nenhum resultado)"


_FERRAMENTAS: dict[str, Callable[..., str]] = {
    "read_file": ferramenta_read_file,
    "list_dir": ferramenta_list_dir,
    "write_file": ferramenta_write_file,
    "edit_file": ferramenta_edit_file,
    "run_command": ferramenta_run_command,
    "search_text": ferramenta_search_text,
    "find_files": ferramenta_find_files,
}

_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Lê o conteúdo de um arquivo do workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Caminho relativo ao workspace"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "Lista arquivos e subdiretórios de um caminho do workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Caminho relativo (default: raiz)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_text",
            "description": (
                "Busca um padrão (regex) linha a linha nos arquivos do workspace "
                "(equivalente ao Grep) — use ANTES de ler arquivo por arquivo às cegas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex a buscar"},
                    "path": {"type": "string", "description": "Subpasta (default: raiz)"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_files",
            "description": (
                "Busca arquivos por padrão de nome/glob (ex.: '*.py', '**/*.js') no "
                "workspace — equivalente ao Glob."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Padrão glob (ex.: '**/*.py')"},
                    "path": {"type": "string", "description": "Subpasta (default: raiz)"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Cria ou sobrescreve um arquivo do workspace com o conteúdo dado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Substitui uma ocorrência ÚNICA de old_string por new_string num "
                "arquivo existente do workspace."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "Executa um comando de shell no workspace (testes, git, lint, etc.) "
                "e devolve stdout+stderr."
            ),
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
]


def filtrar_ferramentas(allowed: str | None, denied: str | None) -> list[dict]:
    """Aplica allow/deny CSV (ADR-0028 §2) sobre o catálogo nativo de tools."""
    allow = {t.strip() for t in (allowed or "").split(",") if t.strip()}
    deny = {t.strip() for t in (denied or "").split(",") if t.strip()}
    schemas = _TOOL_SCHEMAS
    if allow:
        schemas = [s for s in schemas if s["function"]["name"] in allow]
    if deny:
        schemas = [s for s in schemas if s["function"]["name"] not in deny]
    return schemas


def executar_tool_call(cwd: str, chamada: dict) -> str:
    """Executa uma tool call e devolve o texto do resultado.

    Raises:
        FerramentaErro: falha da tool (arquivo ausente, comando com erro
            capturável, etc.) — o chamador do loop trata como não-fatal.
    """
    nome = chamada["function"]["name"]
    args = _args_da_chamada(chamada)
    fn = _FERRAMENTAS.get(nome)
    if fn is None:
        raise FerramentaErro(f"tool desconhecida: {nome}")
    try:
        return fn(cwd, **args)
    except FerramentaErro:
        raise
    except TypeError as exc:
        raise FerramentaErro(f"argumentos inválidos para {nome}: {exc}") from exc


def _args_da_chamada(chamada: dict) -> dict:
    raw = chamada.get("function", {}).get("arguments", {})
    if isinstance(raw, str):
        try:
            return json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError as exc:
            raise FerramentaErro(f"argumentos não são JSON válido: {exc}") from exc
    return dict(raw or {})


def chamar_ollama_chat(
    endpoint: str, modelo: str, messages: list[dict], tools: list[dict], timeout: int
) -> dict:
    """POST /api/chat com tools (function-calling nativo do Ollama). Devolve o
    JSON decodificado (``{"message": {...}}``).

    Raises:
        OllamaIndisponivel: qualquer falha de rede/HTTP/parsing.
    """
    payload = json.dumps(
        {"model": modelo, "messages": messages, "tools": tools, "stream": False}
    ).encode()
    req = urllib.request.Request(
        endpoint.rstrip("/") + "/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        raise OllamaIndisponivel(f"ollama: {exc}") from exc


_INSTRUCOES_BASE = """\
Você é um agente de desenvolvimento com acesso a um workspace de arquivos via tools.

Regras obrigatórias de uso das tools:
- Prefira search_text (grep por regex) e find_files (glob por nome) a navegar
  list_dir pasta por pasta às cegas — são mais rápidas pra achar onde algo
  está definido antes de ler o arquivo inteiro.
- NUNCA edite ou escreva um arquivo sem antes ler o conteúdo atual com read_file
  (ou confirmar com list_dir que ele não existe, se for criar um novo).
- Em edit_file, old_string deve ser copiado EXATAMENTE do conteúdo real do
  arquivo (lido via read_file) — nunca invente ou adivinhe o texto original.
- Caminhos são sempre relativos à raiz do workspace (ex.: "calc.py",
  "src/modulo.py") — nunca use caminhos absolutos como "/home/..." ou "/etc/...".
- Faça uma tool call de cada vez e espere o resultado antes de decidir o próximo
  passo — não assuma o resultado de uma tool que ainda não rodou.
- Se uma tool falhar, leia a mensagem de erro e corrija a abordagem (ex.:
  caminho errado, old_string desatualizado) — não desista nem peça ao usuário
  para colar o conteúdo do arquivo; use read_file de novo.
- Quando terminar a tarefa, responda com um resumo curto em texto (sem tool
  call) do que foi feito.
"""


def ollama_disponivel(endpoint: str, timeout: float = 4.0) -> bool:
    """Probe rápido de saúde do endpoint (``GET /api/tags``) — decide se o run
    modo=code roda no Ollama ou cai pro fallback claude (ADR-0042/ADR-0040),
    antes de comprometer um run inteiro a um endpoint fora do ar."""
    if not endpoint:
        return False
    try:
        with urllib.request.urlopen(endpoint.rstrip("/") + "/api/tags", timeout=timeout):
            return True
    except Exception:
        return False


def rodar_loop(
    mensagem: str,
    *,
    system_prompt: str,
    cwd: str,
    modelo: str,
    endpoint: str,
    timeout: int = 90,
    allowed_tools: str | None = None,
    denied_tools: str | None = None,
    max_turnos: int = _TURNOS_MAX,
    chamar_fn: Callable[..., dict] = chamar_ollama_chat,
    on_evento: Callable[[dict], None] | None = None,
) -> None:
    """Loop de tool-calling nativo do Ollama (ADR-0042).

    Emite eventos no MESMO formato do modo=code via claude (ADR-0025) — o
    dashboard existente (``dashboard/kinds/agente.js``) já sabe renderizar
    ``assistant`` (texto + ``tool_use``) e ``done`` sem mudança nenhuma.
    ``warning`` é uma extensão pequena (erro de tool, não-fatal — não termina
    o run, ao contrário de ``error``).

    Só propaga (``OllamaIndisponivel``) quando o endpoint está de fato fora do
    ar — falha de UMA tool vira ``warning`` e o loop continua (pedido do PO:
    erro simples não trava o run).
    """

    def emitir(ev: dict) -> None:
        if on_evento is not None:
            on_evento(ev)

    tools = filtrar_ferramentas(allowed_tools, denied_tools)
    system_completo = f"{_INSTRUCOES_BASE}\n{system_prompt}" if system_prompt else _INSTRUCOES_BASE
    messages: list[dict] = [
        {"role": "system", "content": system_completo},
        {"role": "user", "content": mensagem},
    ]

    for _ in range(max_turnos):
        resp = chamar_fn(endpoint, modelo, messages, tools, timeout)
        msg = resp.get("message") or {}
        texto = (msg.get("content") or "").strip()
        chamadas = msg.get("tool_calls") or []

        blocos = []
        if texto:
            blocos.append({"type": "text", "text": texto})
        for c in chamadas:
            blocos.append(
                {
                    "type": "tool_use",
                    "name": c.get("function", {}).get("name", "?"),
                    "input": _args_da_chamada(c),
                }
            )
        if blocos:
            emitir({"type": "assistant", "message": {"content": blocos}})

        if not chamadas:
            emitir({"type": "done"})
            return

        messages.append({"role": "assistant", "content": texto, "tool_calls": chamadas})
        for c in chamadas:
            nome = c.get("function", {}).get("name", "?")
            try:
                resultado = executar_tool_call(cwd, c)
            except FerramentaErro as exc:
                resultado = f"ERRO: {exc}"
                emitir({"type": "warning", "message": f"{nome}: {exc}"})
            messages.append({"role": "tool", "content": resultado})

    emitir({"type": "warning", "message": f"limite de {max_turnos} turnos atingido, encerrando"})
    emitir({"type": "done"})
