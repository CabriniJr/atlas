"""Invocador de IA (E1-05) — modo análise (2a).

Chama ``claude -p`` via subprocess. O binário ``claude`` é o cliente CLI da
Anthropic; deve estar autenticado no ambiente (login via browser ou
ANTHROPIC_API_KEY). No Pi (arm64) verificar que ``claude`` está na PATH.

Uso interno: ``invocar(prompt, modelo, timeout)`` → str com a resposta.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess

_MODELO_PADRAO = "claude-haiku-4-5-20251001"
_TIMEOUT_PADRAO = 60

_claude_bin: str | None = None


class InvocarErro(RuntimeError):
    """Falha ao invocar o cliente de IA."""


def _resolver_claude() -> str:
    """Localiza o binário ``claude`` (cacheado). Ordem:

    1. ``ATLAS_CLAUDE_BIN`` (override explícito)
    2. ``claude`` na PATH
    3. binário embutido da extensão Claude Code do VS Code (versão mais recente)
    4. fallback ``"claude"`` (deixa o subprocess falhar com mensagem clara)
    """
    global _claude_bin
    if _claude_bin is not None:
        return _claude_bin

    env = os.environ.get("ATLAS_CLAUDE_BIN")
    if env and os.path.exists(env):
        _claude_bin = env
        return _claude_bin

    found = shutil.which("claude")
    if found:
        _claude_bin = found
        return _claude_bin

    padroes = [
        "~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude",
        "~/.vscode-server/extensions/anthropic.claude-code-*/resources/native-binary/claude",
        "~/.cursor/extensions/anthropic.claude-code-*/resources/native-binary/claude",
    ]
    candidatos: list[str] = []
    for p in padroes:
        candidatos.extend(glob.glob(os.path.expanduser(p)))
    if candidatos:
        _claude_bin = max(candidatos, key=os.path.getmtime)  # extensão mais recente
        return _claude_bin

    _claude_bin = "claude"
    return _claude_bin


def invocar(
    prompt: str,
    modelo: str = _MODELO_PADRAO,
    timeout: int = _TIMEOUT_PADRAO,
) -> str:
    """Envia *prompt* para o modelo via ``claude -p`` e devolve a resposta.

    Raises:
        InvocarErro: se o processo retornar código != 0 ou se ocorrer timeout.
    """
    args = [_resolver_claude(), "-p", "--model", modelo]
    try:
        proc = subprocess.run(
            args,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise InvocarErro(f"timeout após {timeout}s invocando IA") from exc
    except FileNotFoundError as exc:
        raise InvocarErro("binário 'claude' não encontrado — verifique a PATH") from exc

    if proc.returncode != 0:
        detalhe = (proc.stderr or proc.stdout or "erro desconhecido").strip()
        raise InvocarErro(detalhe)

    return proc.stdout.strip()
