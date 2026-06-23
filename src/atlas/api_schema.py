"""Metadata de UI por kind, servida pela API (``GET /_schema``).

Fonte única para qualquer interface (web/Android) renderizar forms tipados e
ações por kind. Sem lógica de negócio — só descreve campos e quais verbos as
ações chamam (ADR-0017/ADR-0019).
"""

from __future__ import annotations

from typing import Any

# Campos de spec/labels por kind. ``type``: text | area | number | bool |
# select | time | cron. ``opts`` só em ``select``.
_KIND_SCHEMA: dict[str, dict[str, Any]] = {
    "Tracker": {
        "meta": {"icon": "📊", "desc": "Coleta valores via micro-sintaxe no chat"},
        "spec": [
            {"k": "unit", "type": "text", "label": "Unidade", "hint": "Ex: kg, min, ml, km"},
            {"k": "syntax", "type": "text", "label": "Sintaxe", "hint": 'Ex: "peso:"'},
            {
                "k": "type",
                "type": "select",
                "label": "Tipo",
                "opts": ["number", "text", "duration"],
                "hint": "Tipo do valor",
            },
            {
                "k": "active",
                "type": "bool",
                "label": "Ativo",
                "hint": "Desativar para parar de coletar",
            },
        ],
        "labels": [
            {"k": "domain", "label": "Domínio", "hint": "fisico · estudo · sono · saude · trabalho"}
        ],
    },
    "Goal": {
        "meta": {"icon": "🎯", "desc": "Meta com progresso calculado"},
        "spec": [
            {
                "k": "tracker",
                "type": "text",
                "label": "Tracker",
                "hint": "Nome do Tracker a monitorar",
            },
            {"k": "target", "type": "number", "label": "Meta (target)", "hint": "Valor alvo"},
            {"k": "start", "type": "number", "label": "Valor inicial", "hint": "Baseline para %"},
            {"k": "unit", "type": "text", "label": "Unidade", "hint": "Ex: kg, dias, pontos"},
            {
                "k": "direction",
                "type": "select",
                "label": "Direção",
                "opts": ["down", "up"],
                "hint": "down = menor é melhor",
            },
        ],
        "labels": [{"k": "domain", "label": "Domínio", "hint": "fisico · estudo · sono · saude"}],
    },
    "Alarm": {
        "meta": {"icon": "⏰", "desc": "Lembrete agendado via Telegram"},
        "spec": [
            {"k": "hora", "type": "time", "label": "Horário", "hint": "Quando dispara"},
            {"k": "mensagem", "type": "text", "label": "Mensagem", "hint": "Texto enviado"},
            {
                "k": "once",
                "type": "bool",
                "label": "Uma vez só",
                "hint": "false = repete diariamente",
            },
        ],
        "labels": [],
    },
    "Job": {
        "meta": {"icon": "🧩", "desc": "Job agendado ou por trigger (ex-Routine, ADR-0021)"},
        "spec": [
            {"k": "agenda", "type": "cron", "label": "Agenda", "hint": "Preset ou cron"},
            {
                "k": "modelo",
                "type": "select",
                "label": "Modelo IA",
                "opts": ["none", "claude-haiku-4-5-20251001", "claude-sonnet-4-6"],
                "hint": "none = sem IA",
            },
            {
                "k": "saida",
                "type": "select",
                "label": "Saída",
                "opts": ["telegram", "none"],
                "hint": "Destino do resultado",
            },
            {"k": "label", "type": "text", "label": "Label grupo", "hint": "coletar-por-label"},
            {
                "k": "coletar",
                "type": "text",
                "label": "Collect fn",
                "hint": "default = nome do job",
            },
        ],
        "labels": [
            {"k": "domain", "label": "Domínio", "hint": "fisico · estudo · sono · saude · trabalho"}
        ],
    },
    "Routine": {
        "meta": {
            "icon": "🧩",
            "desc": "⚠️ Depreciado — use Job (ADR-0021)",
            "hidden": True,
        },
        "spec": [],
        "labels": [],
    },
    "RepoGroup": {
        "meta": {"icon": "🗂", "desc": "Multirepo: agrupa uma série de Repos num dashboard"},
        "spec": [
            {
                "k": "repos",
                "type": "text",
                "label": "Repos",
                "hint": "Nomes de Repo separados por vírgula (ex.: nora, atlas)",
            },
            {
                "k": "description",
                "type": "area",
                "label": "Descrição",
                "hint": "Para que serve este grupo",
            },
        ],
        "labels": [{"k": "dominio", "label": "Domínio", "hint": "trabalho · pessoal · estudo"}],
    },
    "Repo": {
        "meta": {"icon": "📦", "desc": "Repositório git monitorado (repo-sync, multi-branch)"},
        "spec": [
            {"k": "url", "type": "text", "label": "URL", "hint": "https://github.com/user/repo"},
            {
                "k": "default_branch",
                "type": "text",
                "label": "Branch default",
                "hint": "Vazio = detecta do remoto (origin/HEAD)",
            },
            {
                "k": "branches_exclude",
                "type": "text",
                "label": "Excluir branches",
                "hint": "Globs por vírgula, ex.: dependabot/*, tmp/*",
            },
            {
                "k": "serialize",
                "type": "select",
                "label": "Serializar arquivos",
                "opts": ["off", "docs", "docs+code"],
                "hint": "Extrai texto dos arquivos alterados → Doc",
            },
            {
                "k": "serialize_globs",
                "type": "text",
                "label": "Serializar (globs extra)",
                "hint": "Além do preset, ex.: *.cfg",
            },
            {
                "k": "analyze_branches",
                "type": "text",
                "label": "Analisar (IA) branches",
                "hint": "default · all · allowlist por vírgula",
            },
            {
                "k": "analyze_skip_merges",
                "type": "bool",
                "label": "Pular merges na análise",
                "hint": "Não analisa commits de merge",
            },
            {
                "k": "analyze_min_lines",
                "type": "number",
                "label": "Mín. linhas p/ analisar",
                "hint": "Ignora diffs menores",
            },
            {
                "k": "analyze_max_per_run",
                "type": "number",
                "label": "Máx. análises por run",
                "hint": "Disjuntor de orçamento de IA",
            },
            {
                "k": "stale_days",
                "type": "number",
                "label": "Dias p/ branch stale",
                "hint": "Sem atividade além disso = stale",
            },
        ],
        "labels": [],
    },
    "Branch": {
        "meta": {"icon": "🌿", "desc": "Branch remota (oculto; aninhado no Repo)", "hidden": True},
        "spec": [{"k": "branch", "type": "text", "label": "Branch", "hint": "Nome da branch"}],
        "labels": [{"k": "repo", "label": "Repo", "hint": "Label do Repo"}],
    },
    "Commit": {
        "meta": {"icon": "🔘", "desc": "Commit leve (oculto; nó do git-graph)", "hidden": True},
        "spec": [
            {"k": "subject", "type": "text", "label": "Assunto", "hint": "Mensagem"},
            {"k": "author", "type": "text", "label": "Autor", "hint": "Autor"},
        ],
        "labels": [{"k": "repo", "label": "Repo", "hint": "Label do Repo"}],
    },
    "Diff": {
        "meta": {
            "icon": "📝",
            "desc": "Diff pesado por commit (oculto; sob demanda)",
            "hidden": True,
        },
        "spec": [
            {"k": "subject", "type": "text", "label": "Assunto", "hint": "Mensagem do commit"},
            {"k": "explicacao", "type": "area", "label": "Análise (IA)", "hint": "Explicação"},
        ],
        "labels": [{"k": "repo", "label": "Repo", "hint": "Label do Repo"}],
    },
    "Idea": {
        "meta": {"icon": "💡", "desc": "Ideia capturada para o pool"},
        "spec": [{"k": "body", "type": "area", "label": "Corpo", "hint": "Descrição completa"}],
        "labels": [
            {"k": "estado", "label": "Estado", "hint": "capturada · ativo · arquivada · descartada"}
        ],
    },
    "Task": {
        "meta": {"icon": "✅", "desc": "Tarefa do pool"},
        "spec": [
            {"k": "body", "type": "area", "label": "Corpo", "hint": "Descrição da tarefa"},
            {"k": "done", "type": "bool", "label": "Feita", "hint": "Marcar como concluída"},
        ],
        "labels": [],
    },
    "Doc": {
        "meta": {"icon": "📚", "desc": "Documento markdown no store"},
        "spec": [
            {"k": "title", "type": "text", "label": "Título", "hint": "Título na listagem"},
            {"k": "body", "type": "area", "label": "Corpo (markdown)", "hint": "Conteúdo markdown"},
            {"k": "source", "type": "text", "label": "Fonte (URL)", "hint": "Opcional"},
        ],
        "labels": [{"k": "topic", "label": "Tópico", "hint": "arch · kindref · user · spec · adr"}],
    },
    "RoutineRequest": {
        "meta": {"icon": "📬", "desc": "Solicitação de nova rotina"},
        "spec": [{"k": "body", "type": "area", "label": "Descrição", "hint": "O que a rotina faz"}],
        "labels": [],
    },
    "Timer": {
        "meta": {"icon": "⏱", "desc": "Cronômetro — iniciado/parado via /timer"},
        "spec": [],
        "labels": [{"k": "domain", "label": "Domínio", "hint": "trabalho · estudo · treino"}],
    },
    "Prompt": {
        "meta": {"icon": "🧠", "desc": "Chamada de IA plugável (coletar=prompt)"},
        "spec": [
            {"k": "template", "type": "area", "label": "Template", "hint": "Use {dados} e {agora}"},
            {
                "k": "model",
                "type": "select",
                "label": "Modelo",
                "opts": ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"],
                "hint": "Haiku = barato/rápido",
            },
            {
                "k": "fonte",
                "type": "text",
                "label": "Fonte de {dados}",
                "hint": "grupo:<g> · kind:<K> · repo:<r> · texto:<t>",
            },
            {"k": "timeout", "type": "number", "label": "Timeout (s)", "hint": "Máximo de espera"},
        ],
        "labels": [{"k": "grupo", "label": "Grupo", "hint": "Agrupa recursos"}],
    },
    "Agente": {
        "meta": {
            "icon": "🤖",
            "desc": "Analisador configurável: motor + contexto + prompt (ADR-0024)",
        },
        "spec": [
            {
                "k": "modo",
                "type": "select",
                "label": "Modo",
                "opts": ["chat", "code"],
                "hint": "chat = resposta simples; code = Claude Code agêntico (edita arquivos)",
            },
            {
                "k": "motor",
                "type": "select",
                "label": "Motor",
                "opts": ["claude", "ollama"],
                "hint": "Provider de IA",
            },
            {
                "k": "modelo",
                "type": "text",
                "label": "Modelo",
                "hint": "claude-haiku-4-5-20251001 / claude-sonnet-4-6 / gemma4",
            },
            {
                "k": "nivel_contexto",
                "type": "select",
                "label": "Nível de contexto",
                "opts": ["none", "resumo", "completo"],
                "hint": "Quanto contexto do projeto entra no prompt (só modo=chat)",
            },
            {
                "k": "prompt",
                "type": "area",
                "label": "Prompt / template",
                "hint": "Use {mensagem} e {agora} no modo chat; instrução de sistema no modo code",
            },
            {
                "k": "endpoint",
                "type": "text",
                "label": "Endpoint Ollama",
                "hint": "Ex: http://192.168.86.22:11434 (só para motor=ollama)",
            },
            {"k": "timeout", "type": "number", "label": "Timeout (s)", "hint": "Default: 60 (chat) / 300 (code)"},
        ],
        "labels": [{"k": "dominio", "label": "Domínio", "hint": "repo · estudo · geral · dev"}],
    },
}

# Ações de domínio por kind (ADR-0017). ``verbo`` indica para qual endpoint a
# interface traduz a ação: cmd (POST /_cmd), run (POST /_run).
_ACTIONS: dict[str, list[dict[str, str]]] = {
    "Timer": [
        {"id": "start", "label": "▶ Iniciar", "verbo": "cmd", "template": "/timer start {name}"},
        {"id": "stop", "label": "⏹ Parar", "verbo": "cmd", "template": "/timer finish {name}"},
    ],
    "Tracker": [
        {"id": "register", "label": "📝 Registrar", "verbo": "cmd", "template": "{syntax} {valor}"},
    ],
    "Job": [
        {"id": "run", "label": "▶ Executar", "verbo": "run", "template": "{name}"},
    ],
    "Routine": [
        {"id": "run", "label": "▶ Executar", "verbo": "run", "template": "{name}"},
    ],
    "Goal": [
        {"id": "check", "label": "🎯 Recalcular", "verbo": "cmd", "template": "/goal check {name}"},
    ],
    "Repo": [
        {"id": "insight", "label": "🧠 Insight", "verbo": "insight", "template": "{name}"},
        {
            "id": "backfill",
            "label": "⏬ Backfill",
            "verbo": "cmd",
            "template": "/repo backfill {name}",
        },
    ],
    "Agente": [
        {"id": "chat", "label": "💬 Chat", "verbo": "chat", "template": "{name}"},
    ],
}


def schema_payload() -> dict[str, Any]:
    """Monta o payload de ``GET /_schema``: schema + ações por kind."""
    kinds: dict[str, Any] = {}
    for kind, base in _KIND_SCHEMA.items():
        kinds[kind] = {
            "meta": base["meta"],
            "spec": base["spec"],
            "labels": base["labels"],
            "actions": _ACTIONS.get(kind, []),
        }
    return {"kinds": kinds}
