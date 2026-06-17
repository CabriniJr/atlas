# Manifestos de domínio + loader `apply -f` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar objetos de domínio declarativos (academia, saúde, produtividade) reusando kinds existentes, mais um loader `atlas apply -f` que aplica manifestos YAML via a API HTTP.

**Architecture:** Manifestos YAML multi-doc no shape flat `{kind, name, labels, spec, status}` (o mesmo do editor da web). O loader é um **cliente HTTP** da API: parseia o YAML e faz `PUT /apis/atlas/v1/<kind>/<name>` por objeto — zero lógica de negócio, honra a fronteira interface↔núcleo (ADR-0015/0017). Rotinas de check-in são pastas `routines/check-<grupo>/routine.toml` com `coletar="coletar-por-label"`, lidas pelo scheduler.

**Tech Stack:** Python 3.12 (stdlib `argparse`, `json`, `urllib.request`), PyYAML (primeira dependência), pytest, ruff. Spec de origem: [docs/superpowers/specs/2026-06-17-manifestos-dominio-design.md](../specs/2026-06-17-manifestos-dominio-design.md).

---

### Task 1: Adicionar dependência PyYAML

**Files:**
- Modify: `pyproject.toml:6`
- Test: `tests/test_apply.py` (criado aqui; expandido nas tasks seguintes)

- [ ] **Step 1: Escrever teste de fumaça que importa yaml**

Criar `tests/test_apply.py`:

```python
"""TDD — loader de manifestos (atlas apply -f)."""

from __future__ import annotations


def test_pyyaml_disponivel():
    import yaml  # noqa: F401

    assert hasattr(yaml, "safe_load_all")
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `python -m pytest tests/test_apply.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'yaml'`

- [ ] **Step 3: Declarar a dependência**

Em `pyproject.toml`, trocar a linha 6:

```toml
dependencies = ["pyyaml>=6"]
```

- [ ] **Step 4: Instalar e rodar o teste**

Run: `pip install -e . && python -m pytest tests/test_apply.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/test_apply.py
git commit -m "build: adiciona PyYAML (primeira dependência) para manifestos"
```

---

### Task 2: `parse_manifests` — parse + validação

**Files:**
- Create: `src/atlas/apply.py`
- Test: `tests/test_apply.py`

- [ ] **Step 1: Escrever os testes de parse e validação**

Adicionar a `tests/test_apply.py`:

```python
import pytest

from atlas.apply import ManifestoInvalido, parse_manifests

_YAML_OK = """
kind: Tracker
name: peso
labels:
  grupo: academia
spec:
  unit: kg
  type: number
---
kind: Goal
name: peso-alvo
labels:
  grupo: academia
spec:
  target: 78
  unit: kg
"""


def test_parse_multidoc_retorna_lista():
    docs = parse_manifests(_YAML_OK)
    assert [d["kind"] for d in docs] == ["Tracker", "Goal"]
    assert docs[0]["name"] == "peso"
    assert docs[0]["labels"]["grupo"] == "academia"


def test_parse_ignora_documento_vazio():
    docs = parse_manifests("---\n\n---\nkind: Tracker\nname: peso\n")
    assert len(docs) == 1


def test_parse_erro_sem_kind():
    with pytest.raises(ManifestoInvalido, match="kind"):
        parse_manifests("name: peso\nspec: {}\n")


def test_parse_erro_sem_name():
    with pytest.raises(ManifestoInvalido, match="name"):
        parse_manifests("kind: Tracker\nspec: {}\n")


def test_parse_erro_documento_nao_mapa():
    with pytest.raises(ManifestoInvalido, match="mapa"):
        parse_manifests("- isto\n- e uma lista\n")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_apply.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'atlas.apply'`

- [ ] **Step 3: Implementar `parse_manifests`**

Criar `src/atlas/apply.py`:

```python
"""Loader de manifestos declarativos (``atlas apply -f``).

Lê arquivos YAML multi-doc no shape ``{kind, name, labels, spec, status}`` e os
aplica via a API HTTP (``PUT /apis/atlas/v1/<kind>/<name>``). É um **cliente** da
API — não conhece domínio nem escreve no store direto (ADR-0015/ADR-0017).
"""

from __future__ import annotations

import yaml


class ManifestoInvalido(ValueError):
    """Manifesto malformado ou faltando campos obrigatórios."""


def parse_manifests(text: str) -> list[dict]:
    """Parseia YAML multi-doc em uma lista de manifestos validados.

    Cada documento precisa ser um mapa com ``kind`` e ``name``. Documentos
    vazios (``None``) são ignorados.
    """
    docs = [d for d in yaml.safe_load_all(text) if d is not None]
    for i, d in enumerate(docs):
        if not isinstance(d, dict):
            raise ManifestoInvalido(f"documento {i}: não é um mapa")
        if not d.get("kind"):
            raise ManifestoInvalido(f"documento {i}: falta 'kind'")
        if not d.get("name"):
            raise ManifestoInvalido(
                f"documento {i} ({d['kind']}): falta 'name'"
            )
    return docs
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_apply.py -v`
Expected: PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add src/atlas/apply.py tests/test_apply.py
git commit -m "feat(apply): parse e validação de manifestos YAML multi-doc"
```

---

### Task 3: `build_request` — montagem do PUT (pura)

**Files:**
- Modify: `src/atlas/apply.py`
- Test: `tests/test_apply.py`

- [ ] **Step 1: Escrever os testes**

Adicionar a `tests/test_apply.py`:

```python
import json as _json

from atlas.apply import build_request


def test_build_request_monta_put():
    m = {"kind": "Tracker", "name": "peso", "labels": {"grupo": "academia"}, "spec": {"unit": "kg"}}
    method, url, body, headers = build_request("http://127.0.0.1:8080", m, token="t0k")
    assert method == "PUT"
    assert url == "http://127.0.0.1:8080/apis/atlas/v1/Tracker/peso"
    assert _json.loads(body) == {"labels": {"grupo": "academia"}, "spec": {"unit": "kg"}}
    assert headers["Authorization"] == "Bearer t0k"
    assert headers["Content-Type"] == "application/json"


def test_build_request_sem_token_nao_inclui_auth():
    m = {"kind": "Goal", "name": "peso-alvo"}
    _, url, body, headers = build_request("http://127.0.0.1:8080/", m, token=None)
    assert url == "http://127.0.0.1:8080/apis/atlas/v1/Goal/peso-alvo"
    assert "Authorization" not in headers
    assert _json.loads(body) == {"labels": {}, "spec": {}}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_apply.py -v`
Expected: FAIL com `ImportError: cannot import name 'build_request'`

- [ ] **Step 3: Implementar `build_request`**

Adicionar a `src/atlas/apply.py` (após os imports, acrescentar `import json`):

```python
import json

_API_PREFIX = "/apis/atlas/v1"


def build_request(
    api_url: str, manifest: dict, token: str | None = None
) -> tuple[str, str, bytes, dict[str, str]]:
    """Monta a chamada ``PUT`` para um manifesto. Função pura (sem rede)."""
    kind = manifest["kind"]
    name = manifest["name"]
    url = f"{api_url.rstrip('/')}{_API_PREFIX}/{kind}/{name}"
    body = json.dumps(
        {"labels": manifest.get("labels", {}), "spec": manifest.get("spec", {})}
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return ("PUT", url, body, headers)
```

> Nota: `status` é deliberadamente omitido do corpo — só o motor escreve status
> (ADR-0015).

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_apply.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atlas/apply.py tests/test_apply.py
git commit -m "feat(apply): montagem pura do PUT por manifesto"
```

---

### Task 4: `apply_manifests` — laço resiliente + `--dry-run`

**Files:**
- Modify: `src/atlas/apply.py`
- Test: `tests/test_apply.py`

- [ ] **Step 1: Escrever os testes (sender injetado)**

Adicionar a `tests/test_apply.py`:

```python
from atlas.apply import apply_manifests

_MANIFESTS = [
    {"kind": "Tracker", "name": "peso", "labels": {"grupo": "academia"}, "spec": {"unit": "kg"}},
    {"kind": "Goal", "name": "peso-alvo", "labels": {"grupo": "academia"}, "spec": {}},
]


def test_apply_chama_sender_por_objeto():
    chamadas = []

    def fake_send(method, url, body, headers):
        chamadas.append((method, url))

    res = apply_manifests(_MANIFESTS, "http://api", token="t", send=fake_send)
    assert res.ok is True
    assert res.aplicados == ["Tracker/peso", "Goal/peso-alvo"]
    assert chamadas == [
        ("PUT", "http://api/apis/atlas/v1/Tracker/peso"),
        ("PUT", "http://api/apis/atlas/v1/Goal/peso-alvo"),
    ]


def test_apply_dry_run_nao_chama_sender():
    def boom(*a, **k):
        raise AssertionError("não deveria chamar HTTP em dry-run")

    res = apply_manifests(_MANIFESTS, "http://api", token=None, dry_run=True, send=boom)
    assert res.ok is True
    assert res.aplicados == ["Tracker/peso", "Goal/peso-alvo"]


def test_apply_falha_parcial_continua_e_marca_nao_ok():
    def flaky_send(method, url, body, headers):
        if "Goal" in url:
            raise RuntimeError("HTTP 500")

    res = apply_manifests(_MANIFESTS, "http://api", token=None, send=flaky_send)
    assert res.ok is False
    assert res.aplicados == ["Tracker/peso"]
    assert res.falhas == [("Goal/peso-alvo", "HTTP 500")]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_apply.py -v`
Expected: FAIL com `ImportError: cannot import name 'apply_manifests'`

- [ ] **Step 3: Implementar `apply_manifests` + `ResultadoApply`**

Adicionar a `src/atlas/apply.py` (acrescentar `from dataclasses import dataclass, field` aos imports):

```python
from dataclasses import dataclass, field


@dataclass
class ResultadoApply:
    """Resumo de uma aplicação de manifestos (ADR-0006: resiliente)."""

    aplicados: list[str] = field(default_factory=list)
    falhas: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.falhas


def apply_manifests(
    manifests: list[dict],
    api_url: str,
    token: str | None = None,
    *,
    dry_run: bool = False,
    send=None,
) -> ResultadoApply:
    """Aplica cada manifesto via ``send(method, url, body, headers)``.

    Falha num objeto é registrada e **não** interrompe os demais. Em
    ``dry_run`` nenhuma chamada é feita.
    """
    if send is None:
        send = send_http
    res = ResultadoApply()
    for m in manifests:
        ref = f"{m['kind']}/{m['name']}"
        method, url, body, headers = build_request(api_url, m, token)
        if dry_run:
            res.aplicados.append(ref)
            continue
        try:
            send(method, url, body, headers)
            res.aplicados.append(ref)
        except Exception as exc:  # noqa: BLE001 — resiliência por objeto
            res.falhas.append((ref, str(exc)))
    return res
```

> `send_http` é definido na Task 5; em testes o `send` é injetado, então a
> ausência ainda não quebra (só seria chamada com `send=None` real).

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_apply.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/atlas/apply.py tests/test_apply.py
git commit -m "feat(apply): laço resiliente de aplicação com dry-run"
```

---

### Task 5: `send_http` + CLI `atlas apply -f`

**Files:**
- Modify: `src/atlas/apply.py`
- Modify: `src/atlas/__main__.py`
- Test: `tests/test_apply.py`

- [ ] **Step 1: Escrever os testes da CLI (dry-run lê arquivo, sem HTTP)**

Adicionar a `tests/test_apply.py`:

```python
from atlas.apply import cli_apply


def test_cli_apply_dry_run_le_arquivo(tmp_path, capsys):
    arq = tmp_path / "m.yaml"
    arq.write_text(
        "kind: Tracker\nname: peso\nlabels:\n  grupo: academia\nspec:\n  unit: kg\n"
    )
    rc = cli_apply(["-f", str(arq), "--api-url", "http://api", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Tracker/peso" in out


def test_cli_apply_arquivo_inexistente_retorna_erro(tmp_path):
    rc = cli_apply(["-f", str(tmp_path / "nao-existe.yaml"), "--dry-run"])
    assert rc != 0
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_apply.py -v`
Expected: FAIL com `ImportError: cannot import name 'cli_apply'`

- [ ] **Step 3: Implementar `send_http` e `cli_apply`**

Primeiro, **normalizar o bloco de imports** no topo de `src/atlas/apply.py` para o
estado final canônico (evita erro de ordenação `I001` do ruff). O topo do arquivo
deve ficar exatamente assim:

```python
"""Loader de manifestos declarativos (``atlas apply -f``).

Lê arquivos YAML multi-doc no shape ``{kind, name, labels, spec, status}`` e os
aplica via a API HTTP (``PUT /apis/atlas/v1/<kind>/<name>``). É um **cliente** da
API — não conhece domínio nem escreve no store direto (ADR-0015/ADR-0017).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field

import yaml
```

Em seguida, adicionar as funções abaixo a `src/atlas/apply.py`:

```python
_DEFAULT_URL = os.environ.get("ATLAS_API_URL", "http://127.0.0.1:8080")


def send_http(method: str, url: str, body: bytes, headers: dict[str, str]) -> bytes:
    """Realiza a chamada HTTP real. Erros viram mensagens claras (ADR-0006)."""
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise RuntimeError(
                "401 não autorizado — verifique --token / ATLAS_API_TOKEN"
            ) from exc
        raise RuntimeError(f"HTTP {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"falha ao conectar em {url}: {exc.reason}") from exc


def cli_apply(argv: list[str]) -> int:
    """Subcomando ``atlas apply -f <arquivo>``. Retorna o código de saída."""
    p = argparse.ArgumentParser(prog="atlas apply")
    p.add_argument("-f", "--file", required=True, help="manifesto YAML")
    p.add_argument("--api-url", default=_DEFAULT_URL, help="URL base da API")
    p.add_argument(
        "--token",
        default=os.environ.get("ATLAS_API_TOKEN"),
        help="Bearer token (ou ATLAS_API_TOKEN)",
    )
    p.add_argument(
        "--dry-run", action="store_true", help="valida e mostra, sem aplicar"
    )
    args = p.parse_args(argv)

    try:
        with open(args.file, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        print(f"✗ não foi possível ler {args.file}: {exc}", file=sys.stderr)
        return 1

    try:
        manifests = parse_manifests(text)
    except ManifestoInvalido as exc:
        print(f"✗ manifesto inválido: {exc}", file=sys.stderr)
        return 1

    res = apply_manifests(
        manifests, args.api_url, args.token, dry_run=args.dry_run
    )

    prefixo = "[dry-run] " if args.dry_run else ""
    for ref in res.aplicados:
        print(f"{prefixo}✓ {ref}")
    for ref, erro in res.falhas:
        print(f"✗ {ref}: {erro}", file=sys.stderr)

    return 0 if res.ok else 1
```

- [ ] **Step 4: Ligar o subcomando no `__main__`**

Substituir todo o conteúdo de `src/atlas/__main__.py` por:

```python
"""Ponto de entrada: ``python -m atlas`` inicia o bot.

Subcomando ``apply`` aplica manifestos via API (``python -m atlas apply -f …``).
"""

from __future__ import annotations

import sys

from atlas.app import run


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "apply":
        from atlas.apply import cli_apply

        return cli_apply(argv[1:])
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Rodar e ver passar**

Run: `python -m pytest tests/test_apply.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/atlas/apply.py src/atlas/__main__.py tests/test_apply.py
git commit -m "feat(apply): send_http e CLI 'atlas apply -f' com dry-run"
```

---

### Task 6: Manifestos YAML dos três grupos

**Files:**
- Create: `manifests/academia.yaml`
- Create: `manifests/saude.yaml`
- Create: `manifests/produtividade.yaml`
- Test: `tests/test_manifests.py`

- [ ] **Step 1: Escrever o teste de conteúdo dos manifestos**

Criar `tests/test_manifests.py`:

```python
"""TDD — valida o conteúdo dos manifestos seed por grupo."""

from __future__ import annotations

from pathlib import Path

import yaml

_MANIFESTS = Path(__file__).resolve().parent.parent / "manifests"


def _carregar(grupo: str) -> dict[str, dict]:
    docs = yaml.safe_load_all((_MANIFESTS / f"{grupo}.yaml").read_text("utf-8"))
    return {d["name"]: d for d in docs if d}


def test_academia():
    objs = _carregar("academia")
    assert set(objs) == {"peso", "treino", "peso-alvo"}
    assert all(o["labels"]["grupo"] == "academia" for o in objs.values())
    peso = objs["peso"]
    assert peso["kind"] == "Tracker"
    assert peso["spec"] == {
        "unit": "kg", "type": "number", "syntax": "peso:", "aggregation": "last"
    }
    assert objs["treino"]["spec"]["type"] == "text"
    assert objs["peso-alvo"]["kind"] == "Goal"
    assert objs["peso-alvo"]["spec"]["unit"] == "kg"


def test_saude():
    objs = _carregar("saude")
    assert set(objs) == {"agua", "sono"}
    assert all(o["labels"]["grupo"] == "saude" for o in objs.values())
    assert objs["agua"]["spec"] == {
        "unit": "copos", "type": "count", "syntax": "agua:", "aggregation": "sum"
    }
    assert objs["sono"]["spec"]["aggregation"] == "mean"


def test_produtividade():
    objs = _carregar("produtividade")
    assert set(objs) == {"estudo", "foco"}
    assert all(o["labels"]["grupo"] == "produtividade" for o in objs.values())
    assert objs["estudo"]["spec"] == {
        "unit": "h", "type": "duration", "syntax": "estudo:", "aggregation": "sum"
    }
    assert objs["foco"]["kind"] == "Timer"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_manifests.py -v`
Expected: FAIL com `FileNotFoundError` (manifests/academia.yaml)

- [ ] **Step 3: Criar `manifests/academia.yaml`**

```yaml
# Grupo academia — peso, entry de treino e meta de peso.
# Aplicar com: python -m atlas apply -f manifests/academia.yaml
kind: Tracker
name: peso
labels:
  grupo: academia
spec:
  unit: kg
  type: number
  syntax: "peso:"
  aggregation: last
---
kind: Tracker
name: treino
labels:
  grupo: academia
spec:
  type: text
  syntax: "treino:"
---
kind: Goal
name: peso-alvo
labels:
  grupo: academia
spec:
  target: 78
  unit: kg
```

- [ ] **Step 4: Criar `manifests/saude.yaml`**

```yaml
# Grupo saude — hidratação e sono.
# Aplicar com: python -m atlas apply -f manifests/saude.yaml
kind: Tracker
name: agua
labels:
  grupo: saude
spec:
  unit: copos
  type: count
  syntax: "agua:"
  aggregation: sum
---
kind: Tracker
name: sono
labels:
  grupo: saude
spec:
  unit: h
  type: duration
  syntax: "sono:"
  aggregation: mean
```

- [ ] **Step 5: Criar `manifests/produtividade.yaml`**

```yaml
# Grupo produtividade — tempo de estudo e timer de foco.
# Tasks: crie com /task e rotule labels.grupo=produtividade.
# Aplicar com: python -m atlas apply -f manifests/produtividade.yaml
kind: Tracker
name: estudo
labels:
  grupo: produtividade
spec:
  unit: h
  type: duration
  syntax: "estudo:"
  aggregation: sum
---
kind: Timer
name: foco
labels:
  grupo: produtividade
spec: {}
```

- [ ] **Step 6: Rodar e ver passar**

Run: `python -m pytest tests/test_manifests.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add manifests/ tests/test_manifests.py
git commit -m "feat(manifests): objetos seed de academia, saude e produtividade"
```

---

### Task 7: Rotinas de check-in por grupo

**Files:**
- Create: `routines/check-academia/routine.toml`
- Create: `routines/check-saude/routine.toml`
- Create: `routines/check-produtividade/routine.toml`
- Test: `tests/test_rotinas_checkin.py`

- [ ] **Step 1: Escrever o teste de carga das rotinas**

Criar `tests/test_rotinas_checkin.py`:

```python
"""TDD — rotinas de check-in por grupo carregam e nascem inativas."""

from __future__ import annotations

from pathlib import Path

from atlas.routines import carregar_rotinas

_ROUTINES = Path(__file__).resolve().parent.parent / "routines"


def test_rotinas_checkin_carregam_inativas():
    res = carregar_rotinas(_ROUTINES)
    por_nome = {r.nome: r for r in res.rotinas}
    for grupo in ("academia", "saude", "produtividade"):
        r = por_nome[f"check-{grupo}"]
        assert r.coletar == "coletar-por-label"
        assert r.label == grupo
        assert r.ativa is False
        assert r.modelo == "none"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_rotinas_checkin.py -v`
Expected: FAIL com `KeyError: 'check-academia'`

- [ ] **Step 3: Criar `routines/check-academia/routine.toml`**

```toml
nome      = "check-academia"
descricao = "Check-in diário do grupo academia (peso, treino, metas)."
label     = "academia"
coletar   = "coletar-por-label"
agenda    = "0 20 * * *"
modelo    = "none"
saida     = "telegram"
ativa     = false
```

- [ ] **Step 4: Criar `routines/check-saude/routine.toml`**

```toml
nome      = "check-saude"
descricao = "Check-in diário do grupo saude (água, sono)."
label     = "saude"
coletar   = "coletar-por-label"
agenda    = "0 21 * * *"
modelo    = "none"
saida     = "telegram"
ativa     = false
```

- [ ] **Step 5: Criar `routines/check-produtividade/routine.toml`**

```toml
nome      = "check-produtividade"
descricao = "Check-in diário do grupo produtividade (estudo, foco)."
label     = "produtividade"
coletar   = "coletar-por-label"
agenda    = "0 22 * * *"
modelo    = "none"
saida     = "telegram"
ativa     = false
```

- [ ] **Step 6: Rodar e ver passar**

Run: `python -m pytest tests/test_rotinas_checkin.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add routines/check-academia routines/check-saude routines/check-produtividade tests/test_rotinas_checkin.py
git commit -m "feat(routines): check-in diário por grupo (inativo por padrão)"
```

---

### Task 8: ADR-0018 + docs do loader + nota em kinds.md

**Files:**
- Create: `docs/arquitetura/adr/ADR-0018-manifestos-e-apply-f.md`
- Create: `docs/specs/manifestos.md`
- Modify: `docs/arquitetura/kinds.md`
- Modify: `docs/arquitetura/adr/README.md`

- [ ] **Step 1: Escrever ADR-0018**

Criar `docs/arquitetura/adr/ADR-0018-manifestos-e-apply-f.md`:

```markdown
---
titulo: ADR-0018 — Manifestos declarativos e `apply -f` (interface como cliente da API)
id: ADR-0018
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-17
substitui: —
substituido-por: —
---

# ADR-0018 — Manifestos declarativos e `apply -f`

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-17 | Tech Lead | Proposta + aceite | PO/PM |

## Status
`aceito`.

## Contexto
Objetos de domínio (Tracker, Goal, Timer agrupados por `labels.grupo`) precisavam
ser criados repetidamente para tornar a plataforma usável. Criar um a um por
comando é frágil e não versionável. O PO definiu também que **toda interface é
cliente da API** (Telegram, web, futuro Android) — o núcleo não conhece interface.

## Decisão
1. Manifestos declarativos em **YAML multi-doc**, shape flat
   `{kind, name, labels, spec, status}` (o mesmo do editor de manifesto da web).
2. Um loader `atlas apply -f <arquivo>` que **atua como cliente HTTP da API**:
   parseia o YAML e faz `PUT /apis/atlas/v1/<kind>/<name>` por objeto. **Não**
   escreve no store direto — preserva a fronteira interface↔núcleo (ADR-0015/0017).
3. Adoção da **primeira dependência** do projeto, **PyYAML**, restrita ao parse de
   manifestos. Justificada por legibilidade e paridade com o padrão K8s; HTTP/JSON
   seguem em stdlib.

## Alternativas consideradas
| Alternativa | Por que não |
|---|---|
| Loader escreve no store direto | fura a fronteira interface↔núcleo |
| Manifesto JSON (zero dep) | menos legível à mão; PO preferiu YAML |
| Manifesto TOML (zero dep) | formato diverge do editor web (shape K8s) |
| Sem loader (só `/apply` manual) | não versionável; frágil |

## Consequências
- **Positivas:** objetos versionados no repo (P4); reaplicação idempotente; o
  mesmo manifesto serve qualquer ambiente; reforça "interfaces são clientes da API".
- **Custos:** primeira dependência a manter (PyYAML); o loader exige a API no ar
  e token para aplicar.
- **Impacto na constituição:** nenhuma decisão anterior muda; reforça P2/P3/P4.

## Pendências
- ADR amplo "todas as interfaces são clientes da API" (web/Android) — sub-projeto 2.
```

- [ ] **Step 2: Escrever a spec do loader**

Criar `docs/specs/manifestos.md`:

```markdown
---
titulo: Spec — Manifestos declarativos e loader `apply -f`
id: SPEC-MANIFESTOS
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-17
---

# Spec — Manifestos declarativos e loader `apply -f`

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-17 | Tech Lead | Criação | PO/PM |

> Implementa [ADR-0018](../arquitetura/adr/ADR-0018-manifestos-e-apply-f.md).

## Formato
YAML multi-doc; um Resource por documento (`---`), shape flat:
```yaml
kind: Tracker        # obrigatório
name: peso           # obrigatório (slug kebab-case)
labels:              # opcional — use grupo=<g> para agrupar
  grupo: academia
spec:                # campos do kind (ver kinds.md)
  unit: kg
```
`status` é ignorado pelo loader (só o motor escreve status).

## Uso
```
python -m atlas apply -f manifests/academia.yaml \
  [--api-url http://127.0.0.1:8080] [--token T] [--dry-run]
```
- `--api-url`: default `ATLAS_API_URL` ou `http://127.0.0.1:8080`.
- `--token`: default `ATLAS_API_TOKEN`.
- `--dry-run`: valida e lista o que faria, sem chamar a API.
- Idempotente (upsert via `PUT`). Falha num objeto não interrompe os demais;
  o processo sai com código ≠0 se algum falhou.

## Manifestos seed
`manifests/{academia,saude,produtividade}.yaml` — Trackers/Goal/Timer agrupados
por `labels.grupo`. As rotinas `routines/check-<grupo>/` (coletar-por-label) fazem
o check-in diário; nascem `ativa=false` (ligue com `/ativar check-<grupo>`).
```

- [ ] **Step 3: Adicionar nota em `kinds.md`**

Em `docs/arquitetura/kinds.md`, logo após a linha `o store é genérico e não conhece domínios.` (fim da seção "Kinds atuais no store"), inserir:

```markdown

## Manifestos declarativos

Objetos podem ser definidos em arquivos YAML e aplicados em lote com
`python -m atlas apply -f <arquivo>` — ver [spec de manifestos](../specs/manifestos.md)
e [ADR-0018](adr/ADR-0018-manifestos-e-apply-f.md). Os grupos seed vivem em
`manifests/` e são agrupados por `labels.grupo`.
```

Atualizar também o cabeçalho de `kinds.md`: `versao: 1.2` e acrescentar linha ao
histórico de revisão:

```markdown
| 1.2    | 2026-06-17 | Tech Lead | Manifestos declarativos (`apply -f`) e grupos seed | PO/PM |
```

- [ ] **Step 4: Registrar o ADR no índice**

Em `docs/arquitetura/adr/README.md`, adicionar uma entrada para ADR-0018 seguindo
o padrão das linhas existentes (link + uma frase: "Manifestos declarativos e
`apply -f`; interface como cliente da API").

- [ ] **Step 5: Commit**

```bash
git add docs/arquitetura/adr/ADR-0018-manifestos-e-apply-f.md docs/specs/manifestos.md docs/arquitetura/kinds.md docs/arquitetura/adr/README.md
git commit -m "docs: ADR-0018, spec de manifestos e nota em kinds.md"
```

---

### Task 9: Verificação final (suíte + lint)

**Files:** —

- [ ] **Step 1: Rodar a suíte completa**

Run: `python -m pytest -q`
Expected: PASS (incluindo os testes novos; nada legado quebrado)

- [ ] **Step 2: Lint**

Run: `ruff check src/atlas/apply.py src/atlas/__main__.py tests/test_apply.py tests/test_manifests.py tests/test_rotinas_checkin.py`
Expected: sem erros

- [ ] **Step 3: Smoke manual do dry-run (opcional, sem API no ar)**

Run: `python -m atlas apply -f manifests/saude.yaml --dry-run`
Expected: imprime `[dry-run] ✓ Tracker/agua` e `[dry-run] ✓ Tracker/sono`, exit 0

---

## Notas de verificação para o curador
- **Fronteira respeitada:** o loader só fala HTTP (`urllib`); não importa
  `core.store`. Confirme que `apply.py` não tem `import` de store/handler.
- **Status nunca enviado:** `build_request` só serializa `labels`/`spec`.
- **Rotinas inativas:** as três `routine.toml` têm `ativa = false` (P9).
- **Nada legado tocado:** só arquivos novos + `pyproject.toml` (dep) +
  `__main__.py` (subcomando preservando `run()`).
