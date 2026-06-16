"""Command registry — single source of truth (E5-01).

One list feeds the dynamic ``/help`` AND the Telegram command menu
(``setMyCommands``). Add a command = add an entry here. Terms are kept in
English/technical to match the engine's vocabulary.
"""

from __future__ import annotations

# (command_without_slash, short description). Order = display order.
COMANDOS: list[tuple[str, str]] = [
    ("start", "Welcome & quick start"),
    ("idea", "Capture an idea"),
    ("task", "Capture a task / homework"),
    ("queue", "Queue a new routine request (autogen candidate)"),
    ("note", "Log a free-form note"),
    ("pool", "List / inspect / manage the idea pool"),
    ("routines", "List loaded routines"),
    ("run", "Run a routine now"),
    ("activate", "Activate a routine"),
    ("deactivate", "Deactivate a routine"),
    ("status", "Daily summary"),
    ("debug", "Diagnostics & system info (try /debug help)"),
    ("help", "Show available commands"),
]


def texto_ajuda() -> str:
    """Render ``/help`` (plain text, grouped by area)."""
    return (
        "🧭 Atlas — command reference\n\n"
        "💡 Capture\n"
        "  /idea <text>      capture an idea\n"
        "  /task <text>      capture a task / homework\n"
        "  /queue <text>     queue a new routine request (autogen candidate)\n"
        "  /note <text>      log a free-form note\n\n"
        "🗂 Pool\n"
        "  /pool             list open items (by priority)\n"
        "  /pool <state>     filter (capturada|priorizada|gerada|ativada)\n"
        "  /pool <id>        item detail\n"
        "  /pool <id> prio <n> | edit <text> | done | archive | drop\n\n"
        "🧩 Routines\n"
        "  /routines         list loaded routines\n"
        "  /routine <name>   routine detail\n"
        "  /run <name>       run a routine now\n"
        "  /activate <name> | /deactivate <name>\n\n"
        "📊 System\n"
        "  /status           daily summary\n"
        "  /debug            diagnostics (see /debug help)\n"
        "  /help             this message"
    )


def texto_boas_vindas() -> str:
    """``/start`` message."""
    return (
        "👋 Welcome to Atlas — your personal routine engine.\n\n"
        "Capture things straight from chat and I'll store them:\n"
        "  /idea buy a webcam\n"
        "  /task review the report\n"
        "  /pool   → see your list\n\n"
        "Type /help for the full command list, or /debug for system info."
    )


def para_telegram() -> list[dict[str, str]]:
    """``setMyCommands`` format (command without slash + description)."""
    return [{"command": cmd, "description": desc} for cmd, desc in COMANDOS]
