"""Invocador de IA (E1-05) — modo análise (2a).

Chama ``claude -p`` via subprocess. O binário ``claude`` é o cliente CLI da
Anthropic; deve estar autenticado no ambiente (login via browser ou
ANTHROPIC_API_KEY). No Pi (arm64) verificar que ``claude`` está na PATH.

Uso interno: ``invocar(prompt, modelo, timeout)`` → str com a resposta.
"""

from __future__ import annotations

import subprocess

_MODELO_PADRAO = "claude-haiku-4-5-20251001"
_TIMEOUT_PADRAO = 60


class InvocarErro(RuntimeError):
    """Falha ao invocar o cliente de IA."""


def invocar(
    prompt: str,
    modelo: str = _MODELO_PADRAO,
    timeout: int = _TIMEOUT_PADRAO,
) -> str:
    """Envia *prompt* para o modelo via ``claude -p`` e devolve a resposta.

    Raises:
        InvocarErro: se o processo retornar código != 0 ou se ocorrer timeout.
    """
    args = ["claude", "-p", "--model", modelo]
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
