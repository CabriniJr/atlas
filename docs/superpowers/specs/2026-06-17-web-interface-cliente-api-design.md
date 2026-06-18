---
titulo: Design — Web como interface cliente da API (SPA React + Vercel)
id: SPEC-WEB-INTERFACE
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-17
---

# Design — Web como interface cliente da API

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-17 | Tech Lead | Criação (brainstorming) | PO/PM |

---

> **Sub-projeto 2 de 2.** Sucede o sub-projeto 1 (manifestos de domínio). Cobre,
> numa única spec, três frentes: backend vira **API pura**, novo **SPA** cliente
> em `web/`, e **deploy** (Tailscale + Vercel).

## Objetivo

Tornar explícita a separação **API ↔ interfaces**: o núcleo + a API HTTP são a
fronteira única; Telegram, web e (futuro) Android são **interfaces clientes** sem
lógica de negócio. Concretamente: extrair a UI web (hoje embutida como ~3000
linhas de string em `api.py`) para um **SPA React+Vite+TS** em `web/`, consumindo
a API como backend, deployável estático no Vercel.

## Princípios aplicados
- **Fronteira única (ADR-0015/0017 + novo ADR-0019):** front não tem regra de
  negócio; só chama verbos/endpoints da API.
- **P7 (simplicidade):** SPA client-rendered puro — **sem SSR/Next** (a API é
  separada e VPN-only, SSR seria peso morto).
- **P3 (agnóstico/plugável):** metadata de UI por kind (`_KIND_SCHEMA` + ações)
  passa a ser servida pela API (`/_schema`), fonte única.

## Decisões fechadas (brainstorming)
1. **Conectividade:** API **não pública**; acesso só via rede local/VPN.
2. **HTTPS na VPN:** **Tailscale Serve** expõe a API como
   `https://pi.<tailnet>.ts.net` (resolve mixed-content HTTPS→HTTP).
3. **Stack do front:** **React + Vite + TypeScript**, SPA client-rendered,
   deploy estático no Vercel.
4. **Local do repo:** subpasta **`web/`** no monorepo atual (Vercel Root
   Directory = `web/`).
5. **Escopo da 1ª versão:** **paridade total** com a UI atual.
6. **`GET /`** passa a ser landing mínima; **`GET /_schema`** novo.

---

## Parte A — Backend (neste repositório)

### A1. ADR-0019 — Interfaces são clientes da API
Registra a regra geral: o núcleo não conhece interface; toda interface (CLI,
Telegram, web, Android) consome a API. Consequência: `api.py` não serve UI.

### A2. `api.py` vira API pura
- **Remover** o HTML/CSS/JS inline (`_html_dashboard()` e correlatos, ~3000
  linhas). `GET /` devolve uma **landing mínima**: HTML curto com nome, link para
  o web app e `/health` (ou JSON `{"service":"atlas-api", ...}`). `/health`
  permanece.
- Os endpoints de dados ficam **inalterados** (compatibilidade com os testes
  existentes em `tests/test_api.py`).

### A3. Contrato HTTP congelado
Documento `docs/specs/api-http-contrato.md` listando todos os verbos/endpoints,
formatos de request/response, auth (Bearer) e CORS. Vira o contrato que o SPA e
futuras interfaces consomem.

Endpoints (já existentes, agora documentados como contrato):
| Método | Caminho | Função |
|---|---|---|
| GET | `/health` | healthcheck (sem auth) |
| GET | `/apis/atlas/v1` | kinds + counts |
| GET | `/apis/atlas/v1/<kind>` | lista do kind |
| GET | `/apis/atlas/v1/<kind>/<name>` | um recurso |
| PUT | `/apis/atlas/v1/<kind>/<name>` | apply (upsert) |
| DELETE | `/apis/atlas/v1/<kind>/<name>` | delete |
| POST | `/apis/atlas/v1/_cmd` | roteia comando (paridade Telegram) |
| POST | `/apis/atlas/v1/_run` | executa rotina |
| POST | `/apis/atlas/v1/_insight` | insight IA |
| GET | `/apis/atlas/v1/_status` | visão de status |
| GET | `/apis/atlas/v1/_complete?q=` | autocomplete |
| GET | `/apis/atlas/v1/_schema` | **novo:** schema + ações por kind |

### A4. `GET /_schema` (novo)
Move o `_KIND_SCHEMA` e o mapa de ações por kind (hoje no JS do dashboard) para o
backend, servidos como JSON. Estrutura por kind: lista de campos tipados
(`{key, type: bool|enum|number|text|area, label, hint, options?}`) + lista de
ações (`{id, label, verbo}` traduzíveis para `/_cmd` / `/_run` / `PUT`). O SPA
renderiza forms e botões a partir disso — **zero lógica de negócio no front**.

---

## Parte B — Frontend `web/` (React + Vite + TS, paridade total)

### B1. Estrutura (por responsabilidade, não por camada técnica)
```
web/
  index.html
  package.json  vite.config.ts  tsconfig.json
  vercel.json                      # SPA rewrite p/ index.html
  src/
    main.tsx  App.tsx
    api/        # cliente HTTP tipado + tipos do contrato
    config/     # overlay de conexão (URL da API + token, localStorage)
    explorer/   # árvore de kinds + Docs por label, abas, busca
    resource/   # card (overview) + editor de manifesto + forms/ações por kind
    status/     # página de status (/_status) + graph
    cmd/        # paleta de comandos (/_cmd) + autocomplete (/_complete)
```

### B2. Cliente API (`src/api/`)
- Módulo único com tipos do contrato (`Resource`, `KindSchema`, etc.) e funções
  por endpoint. Lê **base-URL** e **token** de um store (localStorage); injeta
  `Authorization: Bearer` quando há token.
- Tratamento de erro: 401 → abre overlay de conexão; rede/timeout → mensagem
  clara; resposta não-2xx → erro tipado.

### B3. Configuração de conexão (`src/config/`)
Overlay (como o token-overlay atual) pedindo **URL da API** (ex.:
`https://pi.<tailnet>.ts.net`) e **token**, persistidos em localStorage.
Necessário porque o SPA é estático no Vercel e o endpoint é por-usuário (VPN).

### B4. Paridade de features (portar a UI atual)
Explorer (kinds + Docs hierárquico por label, abas, busca), card view, editor de
manifesto (JSON), **forms tipados + ações por kind** (de `/_schema`; Timer
start/stop, Tracker registrar, Routine executar, Goal recalc, Repo insight),
página de status, graph, paleta de comandos e autocomplete.

---

## Parte C — Conectividade & Deploy

### C1. Tailscale Serve (HTTPS na VPN)
A API do Pi é exposta como `https://pi.<tailnet>.ts.net` via `tailscale serve`
(certificado automático). Privado ao tailnet; resolve mixed-content. Documentado
em `docs/specs/deploy-web.md`.

### C2. Vercel (estático)
Build Vite do `web/`; Vercel com Root Directory = `web/`, `vercel.json` com
rewrite SPA (todas as rotas → `index.html`). Sem variável de ambiente de API
(endpoint é runtime, por-usuário). Passos no mesmo doc de deploy.

---

## Faseamento do plano (uma spec, plano faseado)
- **F1 — Backend:** ADR-0019; `api.py` API pura (landing mínima); `GET /_schema`;
  `docs/specs/api-http-contrato.md`. Testes no repo Python.
- **F2 — Scaffold front:** `web/` React+Vite+TS; cliente API tipado; overlay de
  conexão (URL+token). Vitest configurado.
- **F3 — Núcleo:** explorer (kinds+Docs) + CRUD + editor de manifesto.
- **F4 — Paridade rica:** forms/ações por kind (de `/_schema`), status, graph,
  paleta de comandos, autocomplete.
- **F5 — Deploy:** `vercel.json`, `docs/specs/deploy-web.md` (Tailscale+Vercel).

## Tratamento de erro (resumo)
| Caso | Comportamento |
|---|---|
| 401 da API | SPA abre overlay de conexão (token/URL) |
| API inacessível (fora da VPN) | mensagem clara "verifique Tailscale/URL" |
| mixed-content (URL http em página https) | aviso ao configurar; exige `https://` |
| resposta não-2xx | erro tipado exibido na UI |

## Testes
- **Backend (pytest):** `GET /` é landing mínima (não serve o HTML antigo);
  endpoints de dados intactos (suíte atual verde); `GET /_schema` devolve
  schema+ações esperados.
- **Frontend (Vitest + React Testing Library):** cliente API com `fetch`
  mockado (monta requests/headers certos; trata 401); overlay de conexão
  persiste e injeta config; explorer e forms renderizam a partir de `/_schema`
  mockado. (Playwright e2e → backlog, YAGNI agora.)

## Fora de escopo
- Tornar a API pública / autenticação multiusuário / RBAC.
- App Android (futuro; habilitado pela fronteira, não construído aqui).
- Redesign visual (a UI atual "é boa"; portamos, não redesenhamos).
- SSR/Next.

## Definição de pronto (DoD)
- ADR-0019 escrito; `api.py` sem HTML inline, `GET /` landing mínima, suíte
  Python verde; `GET /_schema` testado; contrato documentado.
- `web/` builda (Vite) e roda em dev; cliente API + overlay de conexão + paridade
  total das features; Vitest verde.
- `vercel.json` + `docs/specs/deploy-web.md` (Tailscale Serve + Vercel) escritos.
- CI verde (ruff/pytest no backend; lint/test do front conforme F2).
