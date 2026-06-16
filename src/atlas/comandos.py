"""Registro único dos comandos do bot (fonte de verdade — E5-01).

Uma só lista alimenta o ``/ajuda`` dinâmico **e** o menu do Telegram
(``setMyCommands``). Adicionar um comando = adicionar uma entrada aqui.
"""

from __future__ import annotations

# (comando_sem_barra, descrição curta). A ordem é a ordem exibida.
COMANDOS: list[tuple[str, str]] = [
    ("status", "Resumo do dia"),
    ("ideia", "Captura uma ideia · /ideia <id> p/ ver e gerenciar"),
    ("ideias", "Lista o pool de ideias"),
    ("tarefa", "Captura uma tarefa"),
    ("licao", "Captura uma lição de casa"),
    ("rotina_nova", "Registra pedido de rotina nova"),
    ("reg", "Registra uma nota livre"),
    ("ajuda", "Mostra os comandos disponíveis"),
]


def texto_ajuda() -> str:
    """Renderiza o ``/ajuda`` a partir do registro."""
    linhas = [f"• /{cmd} — {desc}" for cmd, desc in COMANDOS]
    return "🧭 *Atlas* — comandos:\n" + "\n".join(linhas)


def para_telegram() -> list[dict[str, str]]:
    """Formato do ``setMyCommands`` (command sem barra + description)."""
    return [{"command": cmd, "description": desc} for cmd, desc in COMANDOS]
