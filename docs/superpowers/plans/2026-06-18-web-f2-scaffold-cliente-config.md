# Web — F2: Scaffold `web/` + cliente API tipado + config de conexão — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Montar o SPA React+Vite+TS em `web/` com cliente HTTP tipado da API e overlay de conexão (URL+token), tudo testado com Vitest.

**Architecture:** SPA client-rendered (sem SSR). `web/` é um projeto Node isolado dentro do monorepo (Vercel Root Directory = `web/`). O cliente API lê URL+token de um store em localStorage e fala com a API documentada no contrato; o overlay de conexão captura/persiste esses valores. Sem lógica de negócio no front — só chama os endpoints (ADR-0019).

**Tech Stack:** Node 24 / npm 11 (instalado em `~/.local/node`, no PATH), React 19, Vite, TypeScript (strict), Vitest + Testing Library + jsdom. Contrato: [docs/specs/api-http-contrato.md](../../specs/api-http-contrato.md). `/_schema` já existe (F1). Fase **2 de 5**.

> **Pré-requisito de ambiente:** `node`/`npm` precisam estar no PATH. Já instalados
> user-local com symlinks em `~/.local/bin` (no PATH). Se algum passo não achar
> `node`, rode antes: `export PATH="$HOME/.local/node/bin:$PATH"`.

---

### Task 1: Scaffold do projeto Vite (React+TS)

**Files:**
- Create: `web/` (via template oficial) — `package.json`, `vite.config.ts`, `tsconfig*.json`, `index.html`, `src/main.tsx`, `src/App.tsx`, etc.
- Create: `web/.gitignore`

- [ ] **Step 1: Gerar o scaffold oficial**

Run:
```bash
cd /home/guaxinim/atlas
npm create vite@latest web -- --template react-ts
cd web && npm install
```
Expected: cria `web/` com a estrutura React+TS e instala dependências (`node_modules`).

- [ ] **Step 2: Garantir `.gitignore` do front**

Confirmar/criar `web/.gitignore` contendo ao menos:
```
node_modules
dist
*.local
.vercel
```

- [ ] **Step 3: Verificar build e typecheck**

Run:
```bash
cd /home/guaxinim/atlas/web && npm run build
```
Expected: build Vite conclui sem erros (gera `dist/`).

- [ ] **Step 4: Commit**

```bash
cd /home/guaxinim/atlas
git add web/ -- ':!web/node_modules'
git commit -m "feat(web): scaffold React+Vite+TS em web/"
```

---

### Task 2: Vitest + Testing Library configurados

**Files:**
- Modify: `web/package.json` (scripts + devDeps)
- Create: `web/vitest.config.ts`
- Create: `web/src/test/setup.ts`
- Create: `web/src/test/smoke.test.ts`

- [ ] **Step 1: Instalar deps de teste**

Run:
```bash
cd /home/guaxinim/atlas/web
npm install -D vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event
```

- [ ] **Step 2: Config do Vitest**

Criar `web/vitest.config.ts`:
```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
```

Criar `web/src/test/setup.ts`:
```ts
import "@testing-library/jest-dom";
```

- [ ] **Step 3: Scripts de teste no package.json**

Em `web/package.json`, no bloco `"scripts"`, garantir:
```json
"test": "vitest run",
"test:watch": "vitest",
"typecheck": "tsc --noEmit"
```

- [ ] **Step 4: Teste de fumaça**

Criar `web/src/test/smoke.test.ts`:
```ts
import { describe, it, expect } from "vitest";

describe("toolchain", () => {
  it("roda vitest", () => {
    expect(1 + 1).toBe(2);
  });
});
```

- [ ] **Step 5: Rodar**

Run: `cd /home/guaxinim/atlas/web && npm test`
Expected: 1 teste passa.

- [ ] **Step 6: Commit**

```bash
cd /home/guaxinim/atlas
git add web/ -- ':!web/node_modules'
git commit -m "test(web): configura Vitest + Testing Library"
```

---

### Task 3: Store de conexão (URL + token em localStorage)

**Files:**
- Create: `web/src/config/connection.ts`
- Create: `web/src/config/connection.test.ts`

- [ ] **Step 1: Escrever os testes**

Criar `web/src/config/connection.test.ts`:
```ts
import { describe, it, expect, beforeEach } from "vitest";
import { getConnection, setConnection, isConfigured, clearConnection } from "./connection";

beforeEach(() => localStorage.clear());

describe("connection store", () => {
  it("vazio por padrão", () => {
    expect(getConnection()).toEqual({ apiUrl: "", token: "" });
    expect(isConfigured()).toBe(false);
  });

  it("persiste e lê apiUrl + token", () => {
    setConnection({ apiUrl: "https://pi.tailnet.ts.net", token: "t0k" });
    expect(getConnection()).toEqual({ apiUrl: "https://pi.tailnet.ts.net", token: "t0k" });
    expect(isConfigured()).toBe(true);
  });

  it("normaliza barra final da apiUrl", () => {
    setConnection({ apiUrl: "https://pi.ts.net/", token: "" });
    expect(getConnection().apiUrl).toBe("https://pi.ts.net");
  });

  it("isConfigured exige apiUrl (token opcional)", () => {
    setConnection({ apiUrl: "https://pi.ts.net", token: "" });
    expect(isConfigured()).toBe(true);
  });

  it("clear remove tudo", () => {
    setConnection({ apiUrl: "https://x", token: "y" });
    clearConnection();
    expect(isConfigured()).toBe(false);
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /home/guaxinim/atlas/web && npx vitest run src/config/connection.test.ts`
Expected: FAIL (módulo não existe)

- [ ] **Step 3: Implementar**

Criar `web/src/config/connection.ts`:
```ts
export interface Connection {
  apiUrl: string;
  token: string;
}

const KEY = "atlas_connection";

export function getConnection(): Connection {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { apiUrl: "", token: "" };
    const c = JSON.parse(raw) as Partial<Connection>;
    return { apiUrl: c.apiUrl ?? "", token: c.token ?? "" };
  } catch {
    return { apiUrl: "", token: "" };
  }
}

export function setConnection(c: Connection): void {
  const apiUrl = c.apiUrl.trim().replace(/\/+$/, "");
  localStorage.setItem(KEY, JSON.stringify({ apiUrl, token: c.token.trim() }));
}

export function isConfigured(): boolean {
  return getConnection().apiUrl.length > 0;
}

export function clearConnection(): void {
  localStorage.removeItem(KEY);
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd /home/guaxinim/atlas/web && npx vitest run src/config/connection.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /home/guaxinim/atlas
git add web/src/config
git commit -m "feat(web): store de conexão (URL+token em localStorage)"
```

---

### Task 4: Tipos do contrato

**Files:**
- Create: `web/src/api/types.ts`
- Create: `web/src/api/types.test.ts`

- [ ] **Step 1: Escrever o teste (compila + shape)**

Criar `web/src/api/types.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import type { Resource, SchemaPayload } from "./types";

describe("tipos do contrato", () => {
  it("Resource aceita o shape K8s", () => {
    const r: Resource = {
      apiVersion: "atlas/v1",
      kind: "Tracker",
      metadata: { name: "peso", labels: { grupo: "academia" } },
      spec: { unit: "kg" },
      status: {},
    };
    expect(r.metadata.name).toBe("peso");
  });

  it("SchemaPayload mapeia kinds", () => {
    const s: SchemaPayload = {
      kinds: {
        Timer: { meta: { icon: "⏱", desc: "" }, spec: [], labels: [], actions: [{ id: "start", label: "▶", verbo: "cmd", template: "/timer start {name}" }] },
      },
    };
    expect(s.kinds.Timer.actions[0].id).toBe("start");
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /home/guaxinim/atlas/web && npx vitest run src/api/types.test.ts`
Expected: FAIL (módulo não existe)

- [ ] **Step 3: Implementar os tipos (do contrato + /_schema)**

Criar `web/src/api/types.ts`:
```ts
// Espelha docs/specs/api-http-contrato.md

export interface Resource {
  apiVersion: string;
  kind: string;
  metadata: {
    name: string;
    labels?: Record<string, string>;
    criado_em?: string;
    atualizado_em?: string;
  };
  spec: Record<string, unknown>;
  status: Record<string, unknown>;
}

export type FieldType = "text" | "area" | "number" | "bool" | "select" | "time" | "cron";

export interface SchemaField {
  k: string;
  type: FieldType;
  label: string;
  hint?: string;
  opts?: string[];
}

export interface KindAction {
  id: string;
  label: string;
  verbo: "cmd" | "run" | "insight";
  template: string;
}

export interface KindSchema {
  meta: { icon: string; desc: string };
  spec: SchemaField[];
  labels: SchemaField[];
  actions: KindAction[];
}

export interface SchemaPayload {
  kinds: Record<string, KindSchema>;
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd /home/guaxinim/atlas/web && npx vitest run src/api/types.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /home/guaxinim/atlas
git add web/src/api/types.ts web/src/api/types.test.ts
git commit -m "feat(web): tipos TypeScript do contrato da API"
```

---

### Task 5: Cliente HTTP tipado

**Files:**
- Create: `web/src/api/client.ts`
- Create: `web/src/api/client.test.ts`

- [ ] **Step 1: Escrever os testes (fetch mockado)**

Criar `web/src/api/client.test.ts`:
```ts
import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { setConnection } from "../config/connection";
import { ApiError, listKinds, getResource, putResource, fetchSchema } from "./client";

beforeEach(() => {
  localStorage.clear();
  setConnection({ apiUrl: "https://api.test", token: "t0k" });
});
afterEach(() => vi.restoreAllMocks());

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response);
}

describe("api client", () => {
  it("listKinds chama a URL certa com Bearer", async () => {
    const f = mockFetch(200, { Tracker: 2 });
    vi.stubGlobal("fetch", f);
    const out = await listKinds();
    expect(out).toEqual({ Tracker: 2 });
    const [url, init] = f.mock.calls[0];
    expect(url).toBe("https://api.test/apis/atlas/v1");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer t0k");
  });

  it("getResource monta kind/name", async () => {
    const f = mockFetch(200, { kind: "Tracker", metadata: { name: "peso" }, spec: {}, status: {} });
    vi.stubGlobal("fetch", f);
    await getResource("Tracker", "peso");
    expect(f.mock.calls[0][0]).toBe("https://api.test/apis/atlas/v1/Tracker/peso");
  });

  it("putResource envia labels+spec via PUT", async () => {
    const f = mockFetch(200, {});
    vi.stubGlobal("fetch", f);
    await putResource("Tracker", "peso", { labels: { grupo: "academia" }, spec: { unit: "kg" } });
    const [url, init] = f.mock.calls[0];
    expect(url).toBe("https://api.test/apis/atlas/v1/Tracker/peso");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({ labels: { grupo: "academia" }, spec: { unit: "kg" } });
  });

  it("401 lança ApiError com flag unauthorized", async () => {
    vi.stubGlobal("fetch", mockFetch(401, { error: "unauthorized" }));
    await expect(listKinds()).rejects.toMatchObject({ status: 401, unauthorized: true });
    await expect(listKinds()).rejects.toBeInstanceOf(ApiError);
  });

  it("fetchSchema retorna kinds", async () => {
    vi.stubGlobal("fetch", mockFetch(200, { kinds: { Timer: { meta: {}, spec: [], labels: [], actions: [] } } }));
    const s = await fetchSchema();
    expect(s.kinds.Timer).toBeTruthy();
  });

  it("sem apiUrl configurada lança ApiError", async () => {
    localStorage.clear();
    await expect(listKinds()).rejects.toBeInstanceOf(ApiError);
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /home/guaxinim/atlas/web && npx vitest run src/api/client.test.ts`
Expected: FAIL (módulo não existe)

- [ ] **Step 3: Implementar o cliente**

Criar `web/src/api/client.ts`:
```ts
import { getConnection } from "../config/connection";
import type { Resource, SchemaPayload } from "./types";

const PREFIX = "/apis/atlas/v1";

export class ApiError extends Error {
  status: number;
  unauthorized: boolean;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.unauthorized = status === 401;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { apiUrl, token } = getConnection();
  if (!apiUrl) throw new ApiError("conexão não configurada", 0);

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  let resp: Response;
  try {
    resp = await fetch(apiUrl + path, { ...init, headers });
  } catch (e) {
    throw new ApiError(`falha de rede ao chamar ${apiUrl}${path}: ${String(e)}`, 0);
  }
  if (!resp.ok) {
    let detail = "";
    try {
      detail = JSON.stringify(await resp.json());
    } catch {
      /* corpo não-JSON */
    }
    throw new ApiError(`HTTP ${resp.status} em ${path} ${detail}`, resp.status);
  }
  return (await resp.json()) as T;
}

export function listKinds(): Promise<Record<string, number>> {
  return request(PREFIX);
}

export function listKind(kind: string): Promise<Resource[]> {
  return request(`${PREFIX}/${kind}`);
}

export function getResource(kind: string, name: string): Promise<Resource> {
  return request(`${PREFIX}/${kind}/${name}`);
}

export function putResource(
  kind: string,
  name: string,
  body: { labels?: Record<string, string>; spec?: Record<string, unknown> },
): Promise<Resource> {
  return request(`${PREFIX}/${kind}/${name}`, { method: "PUT", body: JSON.stringify(body) });
}

export function deleteResource(kind: string, name: string): Promise<{ deleted: string }> {
  return request(`${PREFIX}/${kind}/${name}`, { method: "DELETE" });
}

export function runCmd(text: string): Promise<{ output: string }> {
  return request(`${PREFIX}/_cmd`, { method: "POST", body: JSON.stringify({ text }) });
}

export function runRoutine(routine: string): Promise<unknown> {
  return request(`${PREFIX}/_run`, { method: "POST", body: JSON.stringify({ routine }) });
}

export function fetchStatus(): Promise<unknown> {
  return request(`${PREFIX}/_status`);
}

export function fetchSchema(): Promise<SchemaPayload> {
  return request(`${PREFIX}/_schema`);
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd /home/guaxinim/atlas/web && npx vitest run src/api/client.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /home/guaxinim/atlas
git add web/src/api/client.ts web/src/api/client.test.ts
git commit -m "feat(web): cliente HTTP tipado da API (Bearer, ApiError, 401)"
```

---

### Task 6: Overlay de conexão (React)

**Files:**
- Create: `web/src/config/ConnectionOverlay.tsx`
- Create: `web/src/config/ConnectionOverlay.test.tsx`

- [ ] **Step 1: Escrever o teste (RTL)**

Criar `web/src/config/ConnectionOverlay.test.tsx`:
```tsx
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConnectionOverlay } from "./ConnectionOverlay";
import { getConnection } from "./connection";

beforeEach(() => localStorage.clear());

describe("ConnectionOverlay", () => {
  it("salva URL+token e chama onSaved", async () => {
    const onSaved = vi.fn();
    render(<ConnectionOverlay onSaved={onSaved} />);
    await userEvent.type(screen.getByLabelText(/URL da API/i), "https://pi.ts.net");
    await userEvent.type(screen.getByLabelText(/Token/i), "t0k");
    await userEvent.click(screen.getByRole("button", { name: /conectar/i }));
    expect(getConnection()).toEqual({ apiUrl: "https://pi.ts.net", token: "t0k" });
    expect(onSaved).toHaveBeenCalled();
  });

  it("exige https:// na URL", async () => {
    render(<ConnectionOverlay onSaved={vi.fn()} />);
    await userEvent.type(screen.getByLabelText(/URL da API/i), "http://inseguro");
    await userEvent.click(screen.getByRole("button", { name: /conectar/i }));
    expect(screen.getByText(/https/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /home/guaxinim/atlas/web && npx vitest run src/config/ConnectionOverlay.test.tsx`
Expected: FAIL (componente não existe)

- [ ] **Step 3: Implementar o componente**

Criar `web/src/config/ConnectionOverlay.tsx`:
```tsx
import { useState } from "react";
import { getConnection, setConnection } from "./connection";

export function ConnectionOverlay({ onSaved }: { onSaved: () => void }) {
  const current = getConnection();
  const [apiUrl, setApiUrl] = useState(current.apiUrl);
  const [token, setToken] = useState(current.token);
  const [erro, setErro] = useState("");

  function conectar() {
    const url = apiUrl.trim();
    if (!/^https:\/\//.test(url)) {
      setErro("A URL deve começar com https:// (mixed-content bloqueia http).");
      return;
    }
    setConnection({ apiUrl: url, token });
    onSaved();
  }

  return (
    <div role="dialog" aria-label="Conexão com a API" style={overlay}>
      <div style={box}>
        <h2>Conectar ao Atlas</h2>
        <label>
          URL da API
          <input
            value={apiUrl}
            onChange={(e) => setApiUrl(e.target.value)}
            placeholder="https://pi.<tailnet>.ts.net"
          />
        </label>
        <label>
          Token
          <input type="password" value={token} onChange={(e) => setToken(e.target.value)} />
        </label>
        {erro && <p style={{ color: "crimson" }}>{erro}</p>}
        <button onClick={conectar}>Conectar</button>
      </div>
    </div>
  );
}

const overlay: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,.6)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};
const box: React.CSSProperties = {
  background: "#fff",
  padding: "2rem",
  borderRadius: 8,
  display: "flex",
  flexDirection: "column",
  gap: ".75rem",
  minWidth: 320,
};
```

> Nota: `<label>` envolvendo o `<input>` faz o `getByLabelText` do teste casar.

- [ ] **Step 4: Rodar e ver passar**

Run: `cd /home/guaxinim/atlas/web && npx vitest run src/config/ConnectionOverlay.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /home/guaxinim/atlas
git add web/src/config/ConnectionOverlay.tsx web/src/config/ConnectionOverlay.test.tsx
git commit -m "feat(web): overlay de conexão (URL+token, exige https)"
```

---

### Task 7: App shell (conecta e mostra kinds)

**Files:**
- Modify: `web/src/App.tsx`
- Create: `web/src/App.test.tsx`
- Modify: `web/src/main.tsx` (garantir que renderiza `<App/>`)

- [ ] **Step 1: Escrever o teste (RTL, client mockado)**

Criar `web/src/App.test.tsx`:
```tsx
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "./App";
import { setConnection } from "./config/connection";

beforeEach(() => localStorage.clear());

describe("App", () => {
  it("mostra overlay quando não configurado", () => {
    render(<App />);
    expect(screen.getByRole("dialog", { name: /Conexão com a API/i })).toBeInTheDocument();
  });

  it("quando configurado, busca e lista kinds", async () => {
    setConnection({ apiUrl: "https://api.test", token: "t" });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ Tracker: 3, Goal: 1 }),
      } as Response),
    );
    render(<App />);
    expect(await screen.findByText(/Tracker/)).toBeInTheDocument();
    expect(await screen.findByText(/3/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /home/guaxinim/atlas/web && npx vitest run src/App.test.tsx`
Expected: FAIL (App ainda é o template do Vite)

- [ ] **Step 3: Implementar o App shell**

Substituir `web/src/App.tsx` por:
```tsx
import { useEffect, useState } from "react";
import { isConfigured } from "./config/connection";
import { ConnectionOverlay } from "./config/ConnectionOverlay";
import { listKinds, ApiError } from "./api/client";

export default function App() {
  const [configured, setConfigured] = useState(isConfigured());
  const [kinds, setKinds] = useState<Record<string, number> | null>(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    if (!configured) return;
    listKinds()
      .then(setKinds)
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.unauthorized) {
          setConfigured(false);
        } else {
          setErro(e instanceof Error ? e.message : String(e));
        }
      });
  }, [configured]);

  if (!configured) {
    return <ConnectionOverlay onSaved={() => setConfigured(true)} />;
  }

  return (
    <main style={{ fontFamily: "sans-serif", maxWidth: "42rem", margin: "2rem auto" }}>
      <h1>Atlas</h1>
      {erro && <p style={{ color: "crimson" }}>{erro}</p>}
      {!kinds && !erro && <p>carregando…</p>}
      {kinds && (
        <ul>
          {Object.entries(kinds).map(([k, n]) => (
            <li key={k}>
              {k}: {n}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
```

- [ ] **Step 4: Garantir o main.tsx**

Confirmar que `web/src/main.tsx` importa e renderiza `App` (o template já faz).
Se houver `import "./index.css"` e estilos do template que atrapalhem, podem
ficar — não é escopo desta fase.

- [ ] **Step 5: Rodar testes e build**

Run:
```bash
cd /home/guaxinim/atlas/web && npm test && npm run build && npm run typecheck
```
Expected: todos os testes passam; build e typecheck sem erros.

- [ ] **Step 6: Commit**

```bash
cd /home/guaxinim/atlas
git add web/src/App.tsx web/src/App.test.tsx web/src/main.tsx
git commit -m "feat(web): app shell — conecta e lista kinds da API"
```

---

### Task 8: CI do front (lint/test/build) + vercel.json

**Files:**
- Create: `web/vercel.json`
- Modify: `.github/workflows/ci.yml` (novo job `web`)

- [ ] **Step 1: `vercel.json` (SPA rewrite)**

Criar `web/vercel.json`:
```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
}
```

- [ ] **Step 2: Ler o CI atual**

Run: `sed -n '40,75p' .github/workflows/ci.yml`
Expected: ver o job Python (lint ruff + pytest) para espelhar o estilo.

- [ ] **Step 3: Adicionar job `web` ao CI**

Em `.github/workflows/ci.yml`, adicionar um job (espelhando indentação do arquivo):
```yaml
  web:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "24"
      - run: npm ci
      - run: npm run typecheck
      - run: npm test
      - run: npm run build
```

> `npm ci` exige `package-lock.json` versionado (gerado no Task 1 pelo
> `npm install`). Confirmar que `web/package-lock.json` está commitado.

- [ ] **Step 4: Validar localmente os mesmos passos**

Run:
```bash
cd /home/guaxinim/atlas/web && npm ci && npm run typecheck && npm test && npm run build
```
Expected: tudo verde (mesma sequência da CI).

- [ ] **Step 5: Commit**

```bash
cd /home/guaxinim/atlas
git add web/vercel.json .github/workflows/ci.yml web/package-lock.json
git commit -m "ci(web): job de typecheck/test/build + vercel.json (SPA rewrite)"
```

---

### Task 9: Verificação final da F2

**Files:** —

- [ ] **Step 1: Front verde**

Run: `cd /home/guaxinim/atlas/web && npm run typecheck && npm test && npm run build`
Expected: typecheck limpo, todos os testes passam, build gera `dist/`.

- [ ] **Step 2: Backend intacto**

Run: `cd /home/guaxinim/atlas && python -m pytest -q && ruff check . && ruff format --check .`
Expected: suíte Python verde; gates de lint OK (a F2 não toca Python).

- [ ] **Step 3: Smoke manual (dev server contra a API local)**

```bash
# Terminal A: API local sem token (loopback)
cd /home/guaxinim/atlas && ATLAS_API_PORT=8080 python -m atlas &
# Terminal B: dev server do front
cd /home/guaxinim/atlas/web && npm run dev
# No navegador: abrir o dev server, configurar URL http://127.0.0.1:8080 (em dev,
# mesma origem-insegura é permitida em localhost) e token vazio; ver os kinds.
```
Expected: o overlay aceita a conexão e a tela lista os kinds. (Opcional — o gating
real é typecheck+test+build.)

---

## Notas de verificação para o curador
- **Fronteira:** o front só chama endpoints do contrato; nenhuma regra de negócio.
- **`node_modules` fora do git:** confirmar `web/.gitignore` e que `git status` não
  lista `node_modules`.
- **`package-lock.json` versionado:** necessário para `npm ci` na CI.
- **Sem Python tocado:** a F2 é isolada em `web/` (+ um job no CI).
- **Próxima fase:** F3 (explorer + CRUD + editor de manifesto) consumindo este
  cliente e o `/_schema`.
