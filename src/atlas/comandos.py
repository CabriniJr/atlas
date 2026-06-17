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
    ("list", "List objects: /list <Kind> [-l key=val]"),
    ("get", "Get an object: /get <Kind> <name>"),
    ("describe", "Full detail: /describe <Kind> <name>"),
    ("apply", "Create/update: /apply <Kind> <name> [labels.k=v spec.k=v]"),
    ("delete", "Delete: /delete <Kind> <name>"),
    # --- capture --
    ("idea", "Capture an idea → Kind Idea"),
    ("task", "Capture a task → Kind Task"),
    ("queue", "Queue a routine request → Kind RoutineRequest"),
    ("reg", "Log a free note: /reg [#domain] <text>"),
    ("note", "Alias for /reg"),
    ("pool", "Manage idea pool: /pool [<id> prio|edit|done|archive|drop]"),
    # --- trackers ---
    ("track", "Trackers: list / new / detail / rm"),
    # --- goals ---
    ("goal", "Goals: /goal set|status|check|done <name>"),
    ("goals", "List all goals"),
    # --- timers ---
    ("timer", "Stopwatch: /timer start|finish|status <name>"),
    ("timers", "List running timers"),
    # --- alarms ---
    ("alarm", "Set reminder: /alarm HH:MM <msg> [@once]"),
    ("alarms", "List active alarms"),
    # --- routines ---
    ("routines", "List loaded routines"),
    ("routine", "Routine detail / set field: /routine <name> [set agenda <cron>]"),
    ("run", "Run a routine now: /run <name>"),
    ("activate", "Activate a routine"),
    ("deactivate", "Deactivate a routine"),
    # --- docs ---
    ("docs", "Browse project docs: /docs [kinds|backlog|arch|adr <n>|spec <name>]"),
    ("snip", "Copy-paste template: /snip <Kind>  (Tracker|Goal|Timer|Alarm|Idea|Routine|Doc)"),
    # --- system ---
    ("status", "Daily summary"),
    ("debug", "Diagnostics: /debug [status|runs|routines|db|env]"),
    ("help", "Show this help"),
]


def texto_ajuda() -> str:
    """Render ``/help`` — referência completa com exemplos."""
    return (
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧭  Atlas — referência de comandos\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        "🔷  API de objetos (kubectl-like)\n"
        "  /resources                         lista todos os kinds no store\n"
        "  /list <Kind>                        lista todos os objetos de um kind\n"
        "  /list Tracker -l domain=fisico      filtra por label (AND)\n"
        "  /get <Kind> <name>                  busca um objeto específico\n"
        "  /describe <Kind> <name>             detalhe completo (spec + status)\n"
        "  /apply <Kind> <name> [k=v …]        cria ou atualiza (upsert)\n"
        "  /apply Tracker peso labels.routine=treino\n"
        "  /delete <Kind> <name>               remove um objeto\n\n"

        "💡  Captura rápida\n"
        "  /idea implementar dashboard          → Kind Idea, pool\n"
        "  /task revisar relatório              → Kind Task, pool\n"
        "  /queue nova rotina de meditação      → Kind RoutineRequest, pool\n"
        "  /reg lembrei de algo importante      → nota livre (domínio: geral)\n"
        "  /note texto                          → alias para /reg\n"
        "  /reg #fisico treino pesado hoje      → nota com domínio explícito\n"
        "  /reg #estudo capítulo 3 python       → domínios: fisico·estudo·sono·saude·trabalho\n\n"

        "🗂  Pool de ideias\n"
        "  /pool                                lista itens abertos (por prioridade)\n"
        "  /pool capturada                      filtra por estado\n"
        "  /pool 3                              detalhe do item #3\n"
        "  /pool 3 prio 1                       eleva prioridade\n"
        "  /pool 3 edit novo texto              edita corpo\n"
        "  /pool 3 done                         marca como ativado\n"
        "  /pool 3 archive | drop               arquiva ou descarta\n\n"

        "📈  Trackers  (registro por micro-sintaxe)\n"
        "  /track                               lista trackers ativos + último valor\n"
        "  /track new peso kg                   cria tracker 'peso' em kg\n"
        "  /track peso                          histórico + stats\n"
        "  /track peso rm                       desativa\n"
        "  peso: 82.3                           registra direto no chat\n\n"

        "🎯  Metas\n"
        "  /goal set peso target=80 unit=kg tracker=peso start=90 direction=down\n"
        "  /goals                               lista todas as metas\n"
        "  /goal status peso                    progresso detalhado\n"
        "  /goal check peso                     recalcula do último tracker\n"
        "  /goal done peso                      marca como atingida\n\n"

        "⏱  Timers (cronômetro → registra em activities)\n"
        "  /timer start estudo                  inicia → Kind Timer\n"
        "  /timer finish estudo                 para e grava duração\n"
        "  /timer status estudo                 tempo decorrido\n"
        "  /timers                              lista timers ativos\n\n"

        "⏰  Alarmes\n"
        "  /alarm 07:30 bom dia!                lembrete diário\n"
        "  /alarm 23:00 dormir @once            uma vez só\n"
        "  /alarms                              lista alarmes ativos\n"
        "  /alarm 2 remove                      remove alarme #2\n\n"

        "🧩  Rotinas\n"
        "  /routines                            lista todas as rotinas\n"
        "  /routine treino                      detalhe + estado\n"
        "  /routine checkin set agenda 0 9 * * *   muda horário\n"
        "  /run resumo-diario                   executa agora\n"
        "  /activate checkin                    ativa check-in diário\n"
        "  /deactivate treino                   desativa\n\n"

        "⌨️  Atalhos (aliases de verbo + Kind)\n"
        "  /r  → /get     /ls → /list    /cat → /describe    /a → /apply    /rm → /delete\n"
        "  Kind: t=Tracker  g=Goal  al=Alarm  rot=Routine  doc=Doc  rr=RoutineRequest\n"
        "  ex: /ls t        → /list Tracker\n"
        "      /cat g meta  → /describe Goal meta\n"
        "      /r t peso    → /get Tracker peso\n\n"
        "  /snip <Kind>   template copy-paste pronto para criar/usar o Kind\n"
        "  /snip Tracker  /snip Goal  /snip Timer  /snip Alarm  /snip Doc\n\n"
        "📚  Documentação inline\n"
        "  /docs                                índice de tópicos\n"
        "  /docs kinds                          catálogo de kinds + spec padrão\n"
        "  /docs backlog                        backlog priorizado\n"
        "  /docs arch                           visão geral da arquitetura\n"
        "  /docs adr 15                         ADR-0015 (core API de objetos)\n"
        "  /docs spec trackers                  spec técnica de trackers\n\n"

        "📊  Sistema\n"
        "  /status                              resumo de hoje\n"
        "  /debug                               diagnóstico (db, runs, env)\n"
        "  /debug runs 10                       últimas 10 execuções\n"
        "  /help                                esta mensagem\n\n"

        "Kinds ativos: Idea · Task · RoutineRequest · Tracker · Alarm ·\n"
        "              Timer · Goal · Routine · CheckIn\n"
        "Docs: /docs kinds  |  Arquitetura: /docs arch"
    )


def texto_boas_vindas() -> str:
    """``/start`` — apresentação rica do Atlas."""
    return (
        "👋  Bem-vindo ao Atlas!\n\n"
        "Sou seu motor pessoal de rotinas — tudo que você registra aqui\n"
        "vira um objeto que pode ser inspecionado, filtrado e automatizado.\n\n"
        "━━  Comece por aqui  ━━\n\n"
        "Capture ideias e tarefas:\n"
        "  /idea implementar dashboard web\n"
        "  /task revisar o relatório até sexta\n"
        "  /pool → veja sua lista priorizada\n\n"
        "Rastreie métricas:\n"
        "  /track new peso kg\n"
        "  peso: 82.3          ← registra direto no chat\n"
        "  /track peso         ← histórico + stats\n\n"
        "Defina metas:\n"
        "  /goal set peso target=80 unit=kg tracker=peso start=90 direction=down\n"
        "  /goal check peso    ← calcula progresso\n\n"
        "Cronometre atividades:\n"
        "  /timer start estudo\n"
        "  /timer finish estudo → grava duração automaticamente\n\n"
        "Configure alertas:\n"
        "  /alarm 07:30 acordar!\n"
        "  /alarm 22:00 dormir @once\n\n"
        "Inspecione qualquer objeto:\n"
        "  /resources          ← todos os kinds no store\n"
        "  /list Tracker -l domain=fisico\n"
        "  /describe Goal peso\n\n"
        "Leia a documentação direto aqui:\n"
        "  /docs               ← índice\n"
        "  /docs backlog       ← o que está sendo construído\n"
        "  /docs kinds         ← todos os tipos de objeto\n\n"
        "  /help para a referência completa de comandos."
    )


def para_telegram() -> list[dict[str, str]]:
    """``setMyCommands`` format (command without slash + description)."""
    return [{"command": cmd, "description": desc} for cmd, desc in COMANDOS]
