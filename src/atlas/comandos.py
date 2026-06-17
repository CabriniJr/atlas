"""Command registry — single source of truth (E5-01).

One list feeds the dynamic ``/help`` AND the Telegram command menu
(``setMyCommands``). Add a command = add an entry here. Terms are kept in
English/technical to match the engine's vocabulary.
"""

from __future__ import annotations

# (command_without_slash, short description). Order = display order.
COMANDOS: list[tuple[str, str]] = [
    ("start", "Welcome & quick start"),
    # --- kubectl-like verbs (E0-03) --
    ("resources", "List all kinds in the store"),
    ("list", "List objects of a kind: /list <Kind>"),
    ("get", "Get an object: /get <Kind> <name>"),
    ("describe", "Full detail: /describe <Kind> <name>"),
    ("apply", "Create/update: /apply <Kind> <name> [k=v …]"),
    ("delete", "Delete: /delete <Kind> <name>"),
    # --- capture --
    ("idea", "Capture an idea"),
    ("task", "Capture a task / homework"),
    ("queue", "Queue a new routine request (autogen candidate)"),
    ("reg", "Log a free-form note: /reg <text> or /reg #<domain> <text>"),
    ("note", "Log a note (legacy alias for /reg)"),
    ("pool", "List / inspect / manage the idea pool"),
    ("track", "Trackers: list / new / detail (e.g. 'weight: 82.3')"),
    ("routines", "List loaded routines"),
    ("run", "Run a routine now"),
    ("activate", "Activate a routine"),
    ("deactivate", "Deactivate a routine"),
    ("alarm", "Set a reminder (/alarm HH:MM <msg>)"),
    ("alarms", "List active alarms"),
    ("status", "Daily summary"),
    ("debug", "Diagnostics & system info (try /debug help)"),
    ("help", "Show available commands"),
]


def texto_ajuda() -> str:
    """Render ``/help`` (plain text, grouped by area)."""
    return (
        "🧭 Atlas — command reference\n\n"
        "🔷 API de objetos (kubectl-like)\n"
        "  /resources                         list all kinds in store\n"
        "  /list <Kind>                       list all objects of a kind\n"
        "  /get <Kind> <name>                 get a specific object\n"
        "  /describe <Kind> <name>            full detail (spec + status)\n"
        "  /apply <Kind> <name> [k=v …]       create or update (upsert)\n"
        "  /delete <Kind> <name>              remove an object\n\n"
        "💡 Capture\n"
        "  /idea <text>      capture an idea  → Kind: Idea\n"
        "  /task <text>      capture a task   → Kind: Task\n"
        "  /queue <text>     queue a routine  → Kind: Routine\n"
        "  /reg <text>       log a free note (use /reg #<domain> <text> for domain)\n"
        "  /note <text>      legacy alias for /reg\n\n"
        "🗂 Pool\n"
        "  /pool             list open items (by priority)\n"
        "  /pool <state>     filter (capturada|priorizada|gerada|ativada)\n"
        "  /pool <id>        item detail\n"
        "  /pool <id> prio <n> | edit <text> | done | archive | drop\n\n"
        "📈 Trackers\n"
        "  /track            list trackers\n"
        "  /track new <name> [unit]   create (then log with '<name>: <value>')\n"
        "  /track <name>     history; /track <name> rm to remove\n\n"
        "🧩 Routines\n"
        "  /routines         list loaded routines\n"
        "  /routine <name>   routine detail\n"
        "  /run <name>       run a routine now\n"
        "  /activate <name> | /deactivate <name>\n\n"
        "⏰ Alarms\n"
        "  /alarm HH:MM <msg>   set a reminder (add @once for one-shot)\n"
        "  /alarms              list active alarms\n"
        "  /alarm <id> remove   remove an alarm\n\n"
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
