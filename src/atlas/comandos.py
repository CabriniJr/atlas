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
    """Renderiza o ``/ajuda`` (texto puro, agrupado por tema)."""
    return (
        "🧭 Atlas — o que dá pra fazer:\n\n"
        "💡 Pool de ideias\n"
        "  /ideia <texto>    — captura uma ideia\n"
        "  /tarefa <texto>   — captura uma tarefa\n"
        "  /licao <texto>    — captura uma lição de casa\n"
        "  /rotina_nova <txt>— pede uma rotina nova\n"
        "  /ideias           — lista o pool\n"
        "  /ideia <id>       — detalhe; + prio <n> | editar <txt> | feito | arquivar | remover\n\n"
        "📝 Registro\n"
        "  /reg <texto>      — registra uma nota livre\n\n"
        "📊 Sistema\n"
        "  /status           — resumo do dia\n"
        "  /ajuda            — esta mensagem"
    )


def texto_boas_vindas() -> str:
    """Mensagem de /start."""
    return (
        "👋 Bem-vindo ao Atlas — seu motor de rotinas pessoais.\n\n"
        "Capture ideias e tarefas pelo chat e eu guardo tudo. Ex.:\n"
        "  /ideia comprar uma webcam\n"
        "  /tarefa revisar o relatório\n"
        "  /ideias  (pra ver a lista)\n\n"
        "Digite /ajuda para ver todos os comandos."
    )


def para_telegram() -> list[dict[str, str]]:
    """Formato do ``setMyCommands`` (command sem barra + description)."""
    return [{"command": cmd, "description": desc} for cmd, desc in COMANDOS]
