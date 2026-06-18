"""Aliases e expansão de comandos curtos (UX / autocomplete layer).

Expande atalhos antes do roteamento normal, sem alterar nenhum módulo
de comando existente. Também faz fuzzy-match de Kind names.

Aliases de verbo:
  r, read, get   → /get
  ls, l          → /list
  cat, d         → /describe
  a              → /apply
  rm, del        → /delete
  new            → /apply (atalho de criação)

Aliases de Kind (case-insensitive, plural, abreviação):
  tracker, trackers, track, t  → Tracker
  alarm, alarms, al            → Alarm
  timer, timers                → Timer
  goal, goals, g               → Goal
  idea, ideas                  → Idea
  task, tasks                  → Task
  routine, routines, rot       → Routine
  doc, docs                    → Doc
  rr, routinerequest           → RoutineRequest

Snips (/snip <Kind>): templates prontos para copiar e colar.
"""

from __future__ import annotations

_VERB_ALIASES: dict[str, str] = {
    # get
    "/r": "/get",
    "/read": "/get",
    # list
    "/ls": "/list",
    "/l": "/list",
    # describe
    "/cat": "/describe",
    "/d": "/describe",
    # apply
    "/a": "/apply",
    # delete
    "/rm": "/delete",
    "/del": "/delete",
}

_KIND_ALIASES: dict[str, str] = {
    "tracker": "Tracker",
    "trackers": "Tracker",
    "track": "Tracker",
    "t": "Tracker",
    "alarm": "Alarm",
    "alarms": "Alarm",
    "al": "Alarm",
    "timer": "Timer",
    "timers": "Timer",
    "goal": "Goal",
    "goals": "Goal",
    "g": "Goal",
    "idea": "Idea",
    "ideas": "Idea",
    "task": "Task",
    "tasks": "Task",
    "routine": "Routine",
    "routines": "Routine",
    "rot": "Routine",
    "doc": "Doc",
    "docs": "Doc",
    "rr": "RoutineRequest",
    "routinerequest": "RoutineRequest",
    "checkin": "CheckIn",
    "repo": "Repo",
    "repos": "Repo",
    "diff": "Diff",
    "diffs": "Diff",
    "prompt": "Prompt",
    "prompts": "Prompt",
    "ia": "Prompt",
}

_SNIPS: dict[str, str] = {
    "Tracker": (
        "📋 Snip — Kind Tracker\n\n"
        "Criar:\n"
        "  /track new <nome> [unidade]\n"
        "  /apply Tracker <nome> spec.unit=kg spec.type=number\n\n"
        "Registrar valor:\n"
        "  <nome>: <valor>     (ex: peso: 82.3)\n\n"
        "Inspecionar:\n"
        "  /describe Tracker <nome>\n"
        "  /list Tracker -l domain=fisico\n\n"
        "Remover:\n"
        "  /track <nome> rm"
    ),
    "Alarm": (
        "📋 Snip — Kind Alarm\n\n"
        "Criar diário:\n"
        "  /alarm 07:30 acordar!\n\n"
        "Criar único:\n"
        "  /alarm 23:00 dormir @once\n\n"
        "Inspecionar:\n"
        "  /alarms\n"
        "  /describe Alarm alarm-1\n\n"
        "Remover:\n"
        "  /alarm <id> remove"
    ),
    "Timer": (
        "📋 Snip — Kind Timer\n\n"
        "Iniciar:\n"
        "  /timer start estudo\n\n"
        "Parar (grava duração em activities):\n"
        "  /timer finish estudo\n\n"
        "Status:\n"
        "  /timer status estudo\n"
        "  /timers\n\n"
        "Inspecionar:\n"
        "  /describe Timer estudo"
    ),
    "Goal": (
        "📋 Snip — Kind Goal\n\n"
        "Criar:\n"
        "  /goal set <nome> target=80 unit=kg tracker=peso start=90 direction=down\n\n"
        "Calcular progresso:\n"
        "  /goal check <nome>\n\n"
        "Detalhe:\n"
        "  /goal status <nome>\n"
        "  /goals\n\n"
        "Concluir:\n"
        "  /goal done <nome>\n\n"
        "Inspecionar:\n"
        "  /describe Goal <nome>"
    ),
    "Idea": (
        "📋 Snip — Kind Idea / Task / RoutineRequest\n\n"
        "Capturar:\n"
        "  /idea <texto>           → Kind Idea\n"
        "  /task <texto>           → Kind Task\n"
        "  /queue <texto>          → Kind RoutineRequest\n\n"
        "Listar:\n"
        "  /pool\n"
        "  /list Idea -l estado=capturada\n\n"
        "Ações:\n"
        "  /pool <id> prio <n>     → priorizar\n"
        "  /pool <id> done         → ativar\n"
        "  /pool <id> archive      → arquivar"
    ),
    "Routine": (
        "📋 Snip — Kind Routine\n\n"
        "Listar:\n"
        "  /routines\n\n"
        "Detalhe:\n"
        "  /routine <nome>\n\n"
        "Executar agora:\n"
        "  /run <nome>\n\n"
        "Testar collect (harness, sem IA):\n"
        "  /run <nome> --test\n\n"
        "Ativar / desativar:\n"
        "  /activate <nome>\n"
        "  /deactivate <nome>\n\n"
        "Editar agenda:\n"
        "  /routine <nome> set agenda 0 20 * * *"
    ),
    "Repo": (
        "📋 Snip — Kind Repo\n\n"
        "Criar (obrigatório antes de ativar repo-sync):\n"
        "  /apply Repo <nome> spec.url=https://github.com/user/repo\n"
        "  /apply Repo nora spec.url=https://github.com/sys0xFF/nora\n\n"
        "Routine TOML para monitorar:\n"
        '  nome     = "<nome>-sync"\n'
        '  label    = "<nome>"          # = nome do Repo Resource\n'
        '  coletar  = "repo-sync"\n'
        '  agenda   = "0 9 * * *"\n'
        '  modelo   = "none"\n'
        '  saida    = "telegram"\n'
        "  ativa    = false\n\n"
        "Inspecionar:\n"
        "  /list Repo\n"
        "  /describe Repo nora\n\n"
        "Ver histórico de diffs:\n"
        "  /list Diff -l repo=nora\n"
        "  /describe Diff nora-abc1234"
    ),
    "Prompt": (
        "📋 Snip — Kind Prompt (chamada de IA plugável)\n\n"
        "Qualquer rotina chama IA apontando para um Prompt — sem código.\n\n"
        "Criar:\n"
        '  /apply Prompt resumo-ia spec.template="Resuma em PT-BR: {dados}" \\\n'
        "      spec.model=claude-haiku-4-5-20251001 spec.fonte=grupo:saude\n\n"
        "Placeholders no template:\n"
        "  {dados}  → contexto montado pela spec.fonte\n"
        "  {agora}  → data/hora atual\n\n"
        "Fontes de {dados} (spec.fonte):\n"
        "  grupo:<g>   recursos com labels.grupo=<g>\n"
        "  kind:<K>    todos os recursos de um Kind\n"
        "  repo:<r>    diff mais recente do repositório <r>\n"
        "  texto:<t>   texto fixo\n\n"
        "Routine que usa o Prompt:\n"
        '  nome="resumo-ia"  label="resumo-ia"  coletar="prompt"\n'
        '  agenda="@daily 21:00"  modelo="none"  saida="telegram"\n\n"'
        "Inspecionar:\n"
        "  /describe Prompt resumo-ia    (status.last_output guarda a última resposta)"
    ),
    "Diff": (
        "📋 Snip — Kind Diff\n\n"
        "Criado automaticamente pelo collect repo-sync.\n"
        "Não criar manualmente.\n\n"
        "Listar diffs de um repo:\n"
        "  /list Diff -l repo=nora\n"
        "  /list Diff -l repo=alpha\n\n"
        "Ver detalhe de um diff:\n"
        "  /describe Diff nora-abc1234\n\n"
        "Campos disponíveis (spec):\n"
        "  commit     → SHA abreviado do commit\n"
        "  diff_raw   → patch completo (truncado em 8 KB)\n"
        "  explicacao → análise do Haiku em PT-BR\n\n"
        "Campos de status:\n"
        "  synced_at  → ISO timestamp do sync"
    ),
    "Doc": (
        "📋 Snip — Kind Doc\n\n"
        "Índice:\n"
        "  /docs\n\n"
        "Ler doc:\n"
        "  /docs <slug>            ex: /docs backlog\n"
        "  /docs kind Tracker\n"
        "  /docs adr 15\n"
        "  /docs spec trackers\n\n"
        "Filtrar:\n"
        "  /list Doc -l topic=arch\n"
        "  /list Doc -l topic=kindref\n\n"
        "Criar nota pessoal:\n"
        "  /apply Doc minha-nota labels.topic=user spec.body=texto\n\n"
        "Inspecionar:\n"
        "  /describe Doc backlog"
    ),
}


def expandir(texto: str) -> str:
    """Expande aliases de verbo e normaliza Kind antes do roteamento.

    Exemplos:
      '/r Tracker peso'   → '/get Tracker peso'
      '/ls tracker'       → '/list Tracker'
      '/cat t peso'       → '/describe Tracker peso'
      '/d goal minha'     → '/describe Goal minha'
    """
    if not texto.startswith("/"):
        return texto
    partes = texto.split()
    if not partes:
        return texto

    # Expande verbo
    verbo = partes[0].lower()
    if verbo in _VERB_ALIASES:
        partes[0] = _VERB_ALIASES[verbo]

    # Normaliza Kind (posição 1 nos verbos kubectl)
    if len(partes) >= 2 and partes[0] in ("/get", "/list", "/describe", "/apply", "/delete"):
        kind_key = partes[1].lower()
        if kind_key in _KIND_ALIASES:
            partes[1] = _KIND_ALIASES[kind_key]

    return " ".join(partes)


def responder_snip(texto: str) -> str | None:
    """Responde /snip <Kind> com template copy-paste. Retorna None se não for /snip."""
    partes = texto.strip().split()
    if not partes or partes[0] != "/snip":
        return None
    if len(partes) == 1:
        kinds = ", ".join(sorted(_SNIPS))
        return f"📋 /snip <Kind>\nKinds disponíveis: {kinds}"
    kind_key = partes[1].lower()
    kind = _KIND_ALIASES.get(kind_key, partes[1])
    snip = _SNIPS.get(kind)
    if snip is None:
        return f"❓ sem snip para '{partes[1]}'. Disponíveis: {', '.join(sorted(_SNIPS))}"
    return snip


def sugerir_kind(fragmento: str, store_kinds: list[str]) -> list[str]:
    """Retorna kinds que casam com o fragmento (prefixo, case-insensitive)."""
    frag = fragmento.lower()
    return [k for k in store_kinds if k.lower().startswith(frag)]
