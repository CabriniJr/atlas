# Web — F1: Backend API pura + `/_schema` + ADR-0019 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tornar o `api.py` uma **API pura** (sem UI embutida), expor a metadata de UI por kind em `GET /_schema`, e registrar a fronteira interface↔API no ADR-0019 + contrato HTTP.

**Architecture:** A UI sai do backend (string HTML de ~3000 linhas removida; `GET /` vira landing mínima). A metadata por kind (`_KIND_SCHEMA` + ações, hoje no JS) é portada para um módulo Python dedicado (`atlas/api_schema.py`) e servida em `GET /apis/atlas/v1/_schema`, virando fonte única para qualquer interface (web/Android). Endpoints de dados ficam inalterados.

**Tech Stack:** Python 3.12 (stdlib `http.server`, `json`), pytest, ruff. Spec: [docs/superpowers/specs/2026-06-17-web-interface-cliente-api-design.md](../specs/2026-06-17-web-interface-cliente-api-design.md). Esta é a **Fase 1 de 5**; F2–F5 (front React em `web/` + deploy) terão planos próprios.

---

### Task 1: ADR-0019 — Interfaces são clientes da API

**Files:**
- Create: `docs/arquitetura/adr/ADR-0019-interfaces-clientes-da-api.md`
- Modify: `docs/arquitetura/adr/README.md`

- [ ] **Step 1: Escrever o ADR-0019**

Criar `docs/arquitetura/adr/ADR-0019-interfaces-clientes-da-api.md`:

```markdown
---
titulo: ADR-0019 — Interfaces são clientes da API
id: ADR-0019
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-17
substitui: —
substituido-por: —
---

# ADR-0019 — Interfaces são clientes da API

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-17 | Tech Lead | Proposta + aceite | PO/PM |

## Status
`aceito`.

## Contexto
O Atlas tem múltiplas formas de interação (CLI, Telegram, web) e planeja outras
(Android). Até aqui o dashboard web era servido pelo próprio `api.py` como uma
string HTML embutida (~3000 linhas), misturando interface e núcleo. O PO definiu:
"a API é o backend; Telegram, web e Android são interfaces — tudo isso tem que
ser tratado como interface".

## Decisão
1. O **núcleo + a API HTTP** são a fronteira única do sistema. Nenhuma interface
   carrega regra de negócio; toda interface consome a API (verbos/endpoints).
2. O `api.py` **não serve UI**. `GET /` devolve uma landing mínima; a web é um
   cliente externo (SPA em `web/`).
3. Metadata de UI por kind (schema de campos + ações) é **servida pela API**
   (`GET /_schema`), fonte única para qualquer interface.

## Alternativas consideradas
| Alternativa | Por que não |
|---|---|
| Manter UI embutida no `api.py` | mistura interface e núcleo; arquivo gigante; não escala p/ Android |
| Schema por kind duplicado em cada interface | divergência; viola fonte única |

## Consequências
- **Positivas:** fronteira clara; `api.py` enxuto; novas interfaces (Android)
  reusam o mesmo contrato e `/_schema`. Reforça ADR-0015 e ADR-0017.
- **Custos:** a web passa a precisar de deploy próprio (sub-projeto 2, F2–F5).
- **Impacto na constituição:** nenhuma decisão anterior muda; formaliza um
  princípio já implícito.
```

- [ ] **Step 2: Registrar no índice de ADRs**

Em `docs/arquitetura/adr/README.md`, ler o arquivo primeiro para copiar o padrão
exato. Adicionar uma linha na tabela de revisão (versão seguinte à atual) e a
entrada de índice no mesmo formato das demais:
`| [0019](ADR-0019-interfaces-clientes-da-api.md) | Interfaces são clientes da API | aceito | API pura + /_schema (sub-projeto 2) |`

- [ ] **Step 3: Commit**

```bash
git add docs/arquitetura/adr/ADR-0019-interfaces-clientes-da-api.md docs/arquitetura/adr/README.md
git commit -m "docs: ADR-0019 — interfaces são clientes da API"
```

---

### Task 2: Módulo `api_schema.py` (schema + ações por kind)

**Files:**
- Create: `src/atlas/api_schema.py`
- Test: `tests/test_api_schema.py`

- [ ] **Step 1: Escrever o teste**

Criar `tests/test_api_schema.py`:

```python
"""TDD — metadata de UI por kind servida pela API (/_schema)."""

from __future__ import annotations

from atlas.api_schema import schema_payload


def test_payload_tem_kinds_principais():
    p = schema_payload()
    kinds = p["kinds"]
    for k in ("Tracker", "Goal", "Routine", "Timer", "Repo", "Prompt"):
        assert k in kinds


def test_tracker_tem_campos_e_meta():
    tracker = schema_payload()["kinds"]["Tracker"]
    assert tracker["meta"]["icon"]
    campos = {c["k"]: c for c in tracker["spec"]}
    assert campos["unit"]["type"] == "text"
    assert campos["type"]["type"] == "select"
    assert "number" in campos["type"]["opts"]


def test_acoes_por_kind():
    kinds = schema_payload()["kinds"]
    # Timer expõe start/stop; Routine expõe run; Goal expõe check
    assert any(a["id"] == "start" for a in kinds["Timer"]["actions"])
    assert any(a["id"] == "stop" for a in kinds["Timer"]["actions"])
    assert any(a["id"] == "run" for a in kinds["Routine"]["actions"])
    assert any(a["id"] == "check" for a in kinds["Goal"]["actions"])


def test_serializa_para_json():
    import json
    json.dumps(schema_payload())  # não levanta
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_api_schema.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'atlas.api_schema'`

- [ ] **Step 3: Implementar `api_schema.py`**

Criar `src/atlas/api_schema.py` (porte fiel do `_KIND_SCHEMA` do JS de `api.py`,
mais um mapa de ações por kind conforme ADR-0017):

```python
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
            {"k": "type", "type": "select", "label": "Tipo", "opts": ["number", "text", "duration"], "hint": "Tipo do valor"},
            {"k": "active", "type": "bool", "label": "Ativo", "hint": "Desativar para parar de coletar"},
        ],
        "labels": [{"k": "domain", "label": "Domínio", "hint": "fisico · estudo · sono · saude · trabalho"}],
    },
    "Goal": {
        "meta": {"icon": "🎯", "desc": "Meta com progresso calculado"},
        "spec": [
            {"k": "tracker", "type": "text", "label": "Tracker", "hint": "Nome do Tracker a monitorar"},
            {"k": "target", "type": "number", "label": "Meta (target)", "hint": "Valor alvo"},
            {"k": "start", "type": "number", "label": "Valor inicial", "hint": "Baseline para %"},
            {"k": "unit", "type": "text", "label": "Unidade", "hint": "Ex: kg, dias, pontos"},
            {"k": "direction", "type": "select", "label": "Direção", "opts": ["down", "up"], "hint": "down = menor é melhor"},
        ],
        "labels": [{"k": "domain", "label": "Domínio", "hint": "fisico · estudo · sono · saude"}],
    },
    "Alarm": {
        "meta": {"icon": "⏰", "desc": "Lembrete agendado via Telegram"},
        "spec": [
            {"k": "hora", "type": "time", "label": "Horário", "hint": "Quando dispara"},
            {"k": "mensagem", "type": "text", "label": "Mensagem", "hint": "Texto enviado"},
            {"k": "once", "type": "bool", "label": "Uma vez só", "hint": "false = repete diariamente"},
        ],
        "labels": [],
    },
    "Routine": {
        "meta": {"icon": "🧩", "desc": "Rotina agendada ou por trigger"},
        "spec": [
            {"k": "agenda", "type": "cron", "label": "Agenda", "hint": "Preset ou cron"},
            {"k": "modelo", "type": "select", "label": "Modelo IA", "opts": ["none", "claude-haiku-4-5-20251001", "claude-sonnet-4-6"], "hint": "none = sem IA"},
            {"k": "saida", "type": "select", "label": "Saída", "opts": ["telegram", "none"], "hint": "Destino do resultado"},
            {"k": "label", "type": "text", "label": "Label grupo", "hint": "coletar-por-label"},
            {"k": "coletar", "type": "text", "label": "Collect fn", "hint": "default = nome da rotina"},
        ],
        "labels": [{"k": "domain", "label": "Domínio", "hint": "fisico · estudo · sono · saude · trabalho"}],
    },
    "Repo": {
        "meta": {"icon": "📦", "desc": "Repositório git monitorado (repo-sync)"},
        "spec": [{"k": "url", "type": "text", "label": "URL", "hint": "https://github.com/user/repo"}],
        "labels": [],
    },
    "Idea": {
        "meta": {"icon": "💡", "desc": "Ideia capturada para o pool"},
        "spec": [{"k": "body", "type": "area", "label": "Corpo", "hint": "Descrição completa"}],
        "labels": [{"k": "estado", "label": "Estado", "hint": "capturada · ativo · arquivada · descartada"}],
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
            {"k": "model", "type": "select", "label": "Modelo", "opts": ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"], "hint": "Haiku = barato/rápido"},
            {"k": "fonte", "type": "text", "label": "Fonte de {dados}", "hint": "grupo:<g> · kind:<K> · repo:<r> · texto:<t>"},
            {"k": "timeout", "type": "number", "label": "Timeout (s)", "hint": "Máximo de espera"},
        ],
        "labels": [{"k": "grupo", "label": "Grupo", "hint": "Agrupa recursos"}],
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
    "Routine": [
        {"id": "run", "label": "▶ Executar", "verbo": "run", "template": "{name}"},
    ],
    "Goal": [
        {"id": "check", "label": "🎯 Recalcular", "verbo": "cmd", "template": "/goal check {name}"},
    ],
    "Repo": [
        {"id": "insight", "label": "🧠 Insight", "verbo": "insight", "template": "{name}"},
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
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_api_schema.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atlas/api_schema.py tests/test_api_schema.py
git commit -m "feat(api): módulo api_schema com metadata de UI por kind"
```

---

### Task 3: Endpoint `GET /apis/atlas/v1/_schema`

**Files:**
- Modify: `src/atlas/api.py` (dentro de `do_GET`, junto aos outros `_API_PREFIX + "/_..."`)
- Test: `tests/test_api.py`

- [ ] **Step 1: Escrever o teste (usa o harness existente)**

Adicionar a `tests/test_api.py` (o arquivo já tem as fixtures `store`,
`api_server`, `free_tcp_port` e o helper `_get`):

```python
def test_schema_endpoint(api_server):
    status, body = _get(api_server, "/apis/atlas/v1/_schema")
    assert status == 200
    assert "kinds" in body
    assert "Tracker" in body["kinds"]
    assert body["kinds"]["Timer"]["actions"]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_api.py::test_schema_endpoint -v`
Expected: FAIL (404 / `_schema` não roteado)

- [ ] **Step 3: Rotear o endpoint**

Em `src/atlas/api.py`, dentro de `do_GET`, logo após o bloco do `_status`
(`if path == _API_PREFIX + "/_status":`), inserir:

```python
        # /_schema → metadata de UI por kind (forms + ações)
        if path == _API_PREFIX + "/_schema":
            from atlas.api_schema import schema_payload
            self._json(200, schema_payload())
            return
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_api.py::test_schema_endpoint -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atlas/api.py tests/test_api.py
git commit -m "feat(api): expõe GET /_schema (metadata de UI por kind)"
```

---

### Task 4: `api.py` vira API pura (remove o HTML, landing mínima)

**Files:**
- Modify: `src/atlas/api.py` (remover `_html_dashboard()` e ajustar `do_GET` `/`)
- Test: `tests/test_api.py`

- [ ] **Step 1: Escrever o teste do novo `/`**

Adicionar a `tests/test_api.py`:

```python
def test_root_landing_minima(api_server):
    import http.client
    conn = http.client.HTTPConnection("127.0.0.1", api_server)
    conn.request("GET", "/")
    resp = conn.getresponse()
    body = resp.read().decode()
    conn.close()
    assert resp.status == 200
    # landing mínima, não o dashboard antigo
    assert "renderTree" not in body
    assert "_KIND_SCHEMA" not in body
    assert "Atlas API" in body
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_api.py::test_root_landing_minima -v`
Expected: FAIL (o `/` ainda serve o dashboard com `renderTree`)

- [ ] **Step 3: Substituir `_html_dashboard()` pela landing mínima**

Em `src/atlas/api.py`, **apagar toda a função `_html_dashboard()`** (da linha
`def _html_dashboard() -> str:` até o `"""` de fechamento da string gigante /
fim da função) e colocar no lugar:

```python
def _html_landing() -> str:
    """Landing mínima — a UI é um cliente externo (ADR-0019)."""
    return (
        "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='utf-8'>"
        "<title>Atlas API</title></head><body style='font-family:sans-serif;"
        "max-width:42rem;margin:3rem auto;line-height:1.6'>"
        "<h1>Atlas API</h1>"
        "<p>Backend de objetos do Atlas. A interface web é um cliente externo "
        "(ver ADR-0019).</p>"
        "<ul><li><a href='/health'>/health</a></li>"
        "<li><code>/apis/atlas/v1</code> — kinds + counts (requer token)</li>"
        "<li><code>/apis/atlas/v1/_schema</code> — metadata de UI por kind</li>"
        "</ul></body></html>"
    )
```

- [ ] **Step 4: Apontar `do_GET` `/` para a landing**

Em `do_GET`, trocar a chamada que serve `/`:

```python
        if path == "" or path == "/":
            self._html(_html_landing())
            return
```

(antes era `self._html(_html_dashboard())`).

- [ ] **Step 5: Garantir que não sobrou referência**

Run: `grep -n "_html_dashboard" src/atlas/api.py`
Expected: nenhuma linha (a função foi removida e a chamada trocada).

- [ ] **Step 6: Rodar testes do módulo**

Run: `python -m pytest tests/test_api.py -v`
Expected: PASS (incluindo `test_root_landing_minima`; os demais testes de API
seguem verdes pois os endpoints de dados não mudaram)

- [ ] **Step 7: Lint (o arquivo encolheu muito)**

Run: `ruff check src/atlas/api.py && ruff format --check src/atlas/api.py`
Expected: sem erros (corrigir import órfão de `_html_dashboard` se houver)

- [ ] **Step 8: Commit**

```bash
git add src/atlas/api.py tests/test_api.py
git commit -m "refactor(api): remove UI embutida; GET / vira landing mínima (ADR-0019)"
```

---

### Task 5: Contrato HTTP documentado

**Files:**
- Create: `docs/specs/api-http-contrato.md`

- [ ] **Step 1: Escrever o contrato**

Criar `docs/specs/api-http-contrato.md`:

```markdown
---
titulo: Spec — Contrato HTTP da API do Atlas
id: SPEC-API-HTTP
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-17
---

# Spec — Contrato HTTP da API do Atlas

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-17 | Tech Lead | Criação | PO/PM |

> Implementa [ADR-0019](../arquitetura/adr/ADR-0019-interfaces-clientes-da-api.md).
> Este é o contrato que toda interface (web, Android, scripts) consome.

## Base e autenticação
- Prefixo: `/apis/atlas/v1`. Porta default `8080` (`ATLAS_API_PORT`).
- Auth: header `Authorization: Bearer <ATLAS_API_TOKEN>`. Sem token definido, a
  API aceita apenas loopback (127.0.0.1).
- CORS: `Access-Control-Allow-Origin: *`; métodos `GET,POST,PUT,DELETE,OPTIONS`.

## Endpoints
| Método | Caminho | Auth | Descrição |
|---|---|---|---|
| GET | `/health` | não | `{"status":"ok"}` |
| GET | `/` | não | landing mínima (HTML) |
| GET | `/apis/atlas/v1` | sim | `{<kind>: <count>}` |
| GET | `/apis/atlas/v1/<kind>` | sim | lista de recursos do kind |
| GET | `/apis/atlas/v1/<kind>/<name>` | sim | um recurso (ou 404) |
| PUT | `/apis/atlas/v1/<kind>/<name>` | sim | upsert; corpo `{labels, spec}` |
| DELETE | `/apis/atlas/v1/<kind>/<name>` | sim | remove (ou 404) |
| POST | `/apis/atlas/v1/_cmd` | sim | `{text}` → `{output}` (paridade Telegram) |
| POST | `/apis/atlas/v1/_run` | sim | `{routine}` → resultado da execução |
| POST | `/apis/atlas/v1/_insight` | sim | `{scope,name,model}` → insight IA |
| GET | `/apis/atlas/v1/_status` | sim | visão de status do sistema |
| GET | `/apis/atlas/v1/_complete?q=` | sim | sugestões de autocomplete |
| GET | `/apis/atlas/v1/_schema` | sim | metadata de UI por kind (forms + ações) |

## Formato do recurso
```json
{ "apiVersion": "atlas/v1", "kind": "...", "metadata": {"name": "...",
  "labels": {}, "criado_em": "...", "atualizado_em": "..."},
  "spec": {}, "status": {} }
```
`status` é somente-leitura (escrito pelo motor). `PUT` aceita `labels` e `spec`.

## `/_schema`
```json
{ "kinds": { "<Kind>": { "meta": {"icon","desc"},
  "spec": [{"k","type","label","hint","opts?"}],
  "labels": [{"k","label","hint"}],
  "actions": [{"id","label","verbo","template"}] } } }
```
`verbo`: `cmd` (POST `/_cmd`), `run` (POST `/_run`), `insight` (POST `/_insight`).
```

- [ ] **Step 2: Commit**

```bash
git add docs/specs/api-http-contrato.md
git commit -m "docs: contrato HTTP da API (SPEC-API-HTTP)"
```

---

### Task 6: Verificação final da F1

**Files:** —

- [ ] **Step 1: Suíte completa**

Run: `python -m pytest -q`
Expected: PASS (nada legado quebrado; novos testes verdes)

- [ ] **Step 2: Gates de lint da CI**

Run: `ruff check . && ruff format --check .`
Expected: ambos sem erros

- [ ] **Step 3: Smoke manual do `/_schema` e da landing**

```bash
ATLAS_API_PORT=8080 python -c "import threading,atlas.api as a; from atlas.core.store import ResourceStore; a._store=ResourceStore('/tmp/f1.db'); a._TOKEN=''; from http.server import HTTPServer; s=HTTPServer(('127.0.0.1',8087),a._Handler); threading.Thread(target=s.serve_forever,daemon=True).start(); import urllib.request,json; print('schema kinds:', list(json.load(urllib.request.urlopen('http://127.0.0.1:8087/apis/atlas/v1/_schema'))['kinds'])[:5]); print('landing ok:', 'Atlas API' in urllib.request.urlopen('http://127.0.0.1:8087/').read().decode()); s.shutdown()"
rm -f /tmp/f1.db
```
Expected: imprime os primeiros kinds do schema e `landing ok: True`.

---

## Notas de verificação para o curador
- **Fronteira:** `api.py` não contém mais HTML de app (só a landing curta);
  `grep -c "renderTree" src/atlas/api.py` → 0.
- **Fonte única:** o schema vive em `api_schema.py`; o `/_schema` o serve.
- **Compatibilidade:** endpoints de dados inalterados — `tests/test_api.py`
  legado segue verde.
- **Próximas fases:** F2 (scaffold `web/` React+Vite+TS + cliente API + config de
  conexão) terá plano próprio, consumindo este `/_schema` e o contrato.
