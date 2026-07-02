"""Invocador de IA (E1-05 / ADR-0022) — modo análise (2a).

Adapters disponíveis:
  - ``claude`` (default): chama ``claude -p`` via subprocess (ADR-0001).
  - ``ollama``: HTTP POST ao endpoint local (ADR-0022 / E7-26).

Uso interno: ``invocar(prompt, modelo, timeout, motor)`` → str.
``invocar_ollama(prompt, modelo, endpoint, timeout)`` → str (adapter direto).
"""

from __future__ import annotations

import glob
import json
import logging
import os
import shutil
import subprocess
import threading
import urllib.request

_log = logging.getLogger(__name__)

_MODELO_PADRAO = "claude-haiku-4-5-20251001"
_MODELO_OLLAMA_PADRAO = "gemma4"
_TIMEOUT_PADRAO = 60
_OLLAMA_ENDPOINT_PADRAO = "http://192.168.86.38:11434"

# Um servidor Ollama local processa inferência sequencialmente (não é a nuvem
# elástica do Claude) — disparar N chamadas HTTP simultâneas (ex.: paralelismo
# de páginas da tradução, ADR-0039) faz as depois da 1ª ficarem na fila do lado
# do servidor, estourando o timeout client-side e disparando falso-positivo do
# fallback pro claude (ADR-0040). Serializa aqui pra bater com a capacidade real
# do servidor (ADR-0043). Configurável se o servidor suportar mais (env
# OLLAMA_NUM_PARALLEL do lado dele).
_OLLAMA_MAX_CONCURRENT = max(1, int(os.environ.get("ATLAS_OLLAMA_MAX_CONCURRENT", "1")))
_OLLAMA_SEMAFORO = threading.Semaphore(_OLLAMA_MAX_CONCURRENT)


def modelo_padrao(motor: str) -> str:
    """Modelo default de *motor* (``claude`` ou ``ollama``) quando nenhum é pedido."""
    return _MODELO_OLLAMA_PADRAO if motor == "ollama" else _MODELO_PADRAO


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


def invocar_ollama(
    prompt: str,
    modelo: str = _MODELO_OLLAMA_PADRAO,
    endpoint: str = _OLLAMA_ENDPOINT_PADRAO,
    timeout: int = _TIMEOUT_PADRAO,
) -> str:
    """Adapter Ollama (ADR-0022 / E7-26): POST /api/chat → conteúdo da resposta.

    Raises:
        InvocarErro: qualquer falha de rede ou parsing.
    """
    payload = json.dumps(
        {
            "model": modelo,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
    ).encode()
    req = urllib.request.Request(
        endpoint.rstrip("/") + "/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data["message"]["content"].strip()
    except Exception as exc:
        raise InvocarErro(f"ollama: {exc}") from exc


def _chamar_claude(prompt: str, modelo: str | None, timeout: int) -> str:
    """Chama ``claude -p`` via subprocess. ``modelo`` vazio ⇒ default claude."""
    args = [_resolver_claude(), "-p", "--model", modelo or _MODELO_PADRAO]
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


def _chamar_ollama(prompt: str, modelo: str | None, timeout: int) -> str:
    """Chama o endpoint Ollama. ``modelo`` vazio ⇒ default ollama (nunca um nome
    ``claude-*``, que não existe nesse servidor). Serializado por
    ``_OLLAMA_SEMAFORO`` (ADR-0043) — chamadas concorrentes esperam a vez em vez
    de estourar timeout contra um servidor local que processa sequencialmente.
    """
    endpoint = os.environ.get("ATLAS_OLLAMA_ENDPOINT", _OLLAMA_ENDPOINT_PADRAO)
    with _OLLAMA_SEMAFORO:
        return invocar_ollama(
            prompt, modelo=modelo or _MODELO_OLLAMA_PADRAO, endpoint=endpoint, timeout=timeout
        )


def invocar(
    prompt: str,
    modelo: str | None = None,
    timeout: int = _TIMEOUT_PADRAO,
    motor: str = "claude",
) -> str:
    """Envia *prompt* ao motor selecionado e devolve a resposta.

    Args:
        motor: ``"claude"`` (default, via CLI) ou ``"ollama"`` (local).
        modelo: vazio ⇒ default do *motor* pedido (``modelo_padrao``) — nunca
            mistura o default de um motor com o adapter do outro (nem no
            pedido original, nem no fallback).

    Fallback bidirecional (plug-and-play — rede de segurança nos dois sentidos):
        - ``motor="ollama"`` e o endpoint está fora do ar ⇒ tenta ``claude``.
        - ``motor="claude"`` e bate limite/erro (ex.: sessão esgotada) ⇒ tenta
          ``ollama``.
        Se o motor pedido funciona, o fallback nunca é tentado. Se os dois
        falham, propaga o erro do **fallback** (é a última tentativa real).

    Raises:
        InvocarErro: falha do motor pedido e do fallback.
    """
    primario, fallback = (
        (_chamar_ollama, _chamar_claude) if motor == "ollama" else (_chamar_claude, _chamar_ollama)
    )
    try:
        return primario(prompt, modelo, timeout)
    except InvocarErro as exc:
        _log.warning("motor=%s indisponível (%s); caindo para o outro motor", motor, exc)
        return fallback(prompt, None, timeout)
