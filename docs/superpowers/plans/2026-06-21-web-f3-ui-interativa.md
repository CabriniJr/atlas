# Web — F3: UI interativa (explorer + CRUD + forms por /_schema + ações + paleta) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar o app shell (F2) na aplicação web da ADR-19: explorer de kinds/recursos, visualização, criar/editar via forms tipados derivados de `/_schema`, deletar, ações por kind e paleta de comandos — uma GUI que abstrai a API.

**Architecture:** SPA React+TS consumindo a API. A metadata de UI vem de `/_schema` (forms e ações são renderizados a partir dela — zero regra de negócio no front, ADR-0017/0019). Componentes focados: hook de schema, explorer (sidebar), card (view), form tipado (create/edit), ações por kind, paleta de comandos, e o App que faz o layout.

**Tech Stack:** React 19 + Vite + TS, Vitest + Testing Library. Cliente/തtypes já existem (F2). Node user-local (`export PATH="$HOME/.local/node/bin:$PATH"`). Trabalhar de `/home/guaxinim/atlas/web`, branch `feat/web-interface-cliente-api`.

> **Correção de base (Task 1):** a API serializa recursos **flat** (`{api_version,
> kind, name, labels, spec, status}`), não no shape K8s aninhado. O tipo `Resource`
> e o contrato precisam ser corrigidos antes de construir a UI.

---

### Task 1: Corrigir o tipo `Resource` (flat) + contrato + teste

**Files:**
- Modify: `web/src/api/types.ts`
- Modify: `web/src/api/types.test.ts`
- Modify: `docs/specs/api-http-contrato.md` (seção "Formato do recurso")

- [ ] **Step 1: Ajustar o teste de tipos para o shape flat**

Em `web/src/api/types.test.ts`, substituir o teste do Resource por:
```ts
  it("Resource é flat (name/labels no topo)", () => {
    const r: Resource = {
      api_version: "atlas/v1",
      kind: "Tracker",
      name: "peso",
      labels: { grupo: "academia" },
      spec: { unit: "kg" },
      status: {},
    };
    expect(r.name).toBe("peso");
    expect(r.labels.grupo).toBe("academia");
  });
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /home/guaxinim/atlas/web && npx vitest run src/api/types.test.ts`
Expected: FAIL de tipo/compilação (Resource ainda tem `metadata`)

- [ ] **Step 3: Corrigir o tipo `Resource`**

Em `web/src/api/types.ts`, substituir a interface `Resource` por:
```ts
export interface Resource {
  api_version: string;
  kind: string;
  name: string;
  labels: Record<string, string>;
  spec: Record<string, unknown>;
  status: Record<string, unknown>;
  criado_em?: string;
  atualizado_em?: string;
}
```
(As demais interfaces — `SchemaField`, `KindAction`, `KindSchema`, `SchemaPayload` — ficam iguais.)

- [ ] **Step 4: Rodar e ver passar**

Run: `cd /home/guaxinim/atlas/web && npx vitest run src/api/types.test.ts && npm run typecheck`
Expected: PASS e typecheck limpo.

- [ ] **Step 5: Corrigir o contrato (doc-as-contract)**

Em `docs/specs/api-http-contrato.md`, na seção "Formato do recurso", substituir o bloco JSON nested pelo shape real:
```json
{ "api_version": "atlas/v1", "kind": "...", "name": "...",
  "labels": {}, "spec": {}, "status": {},
  "criado_em": "...", "atualizado_em": "..." }
```
E ajustar a frase para: "`status` é somente-leitura (escrito pelo motor). `PUT`
aceita `labels` e `spec`. A serialização HTTP é **flat** (não usa `metadata`)."

- [ ] **Step 6: Commit**

```bash
cd /home/guaxinim/atlas
git add web/src/api/types.ts web/src/api/types.test.ts docs/specs/api-http-contrato.md
git commit -m "fix(web): Resource é flat (alinha tipo e contrato à serialização real da API)"
```

---

### Task 2: Hook de schema (`useSchema`)

**Files:**
- Create: `web/src/schema/useSchema.ts`
- Create: `web/src/schema/useSchema.test.tsx`

- [ ] **Step 1: Escrever o teste**

Criar `web/src/schema/useSchema.test.tsx`:
```tsx
import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useSchema } from "./useSchema";
import { setConnection } from "../config/connection";

beforeEach(() => {
  localStorage.clear();
  setConnection({ apiUrl: "https://api.test", token: "t" });
});

function mockFetch(body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => body } as Response),
  );
}

describe("useSchema", () => {
  it("carrega kinds do /_schema", async () => {
    mockFetch({ kinds: { Tracker: { meta: { icon: "📊", desc: "" }, spec: [], labels: [], actions: [] } } });
    const { result } = renderHook(() => useSchema());
    await waitFor(() => expect(result.current.schema).not.toBeNull());
    expect(result.current.schema!.kinds.Tracker.meta.icon).toBe("📊");
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /home/guaxinim/atlas/web && npx vitest run src/schema/useSchema.test.tsx`
Expected: FAIL (módulo não existe)

- [ ] **Step 3: Implementar**

Criar `web/src/schema/useSchema.ts`:
```ts
import { useEffect, useState } from "react";
import { fetchSchema } from "../api/client";
import type { SchemaPayload } from "../api/types";

export function useSchema() {
  const [schema, setSchema] = useState<SchemaPayload | null>(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    let vivo = true;
    fetchSchema()
      .then((s) => vivo && setSchema(s))
      .catch((e: unknown) => vivo && setErro(e instanceof Error ? e.message : String(e)));
    return () => {
      vivo = false;
    };
  }, []);

  return { schema, erro };
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd /home/guaxinim/atlas/web && npx vitest run src/schema/useSchema.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /home/guaxinim/atlas
git add web/src/schema
git commit -m "feat(web): hook useSchema (carrega /_schema)"
```

---

### Task 3: Explorer (sidebar de kinds + recursos)

**Files:**
- Create: `web/src/explorer/Explorer.tsx`
- Create: `web/src/explorer/Explorer.test.tsx`

- [ ] **Step 1: Escrever o teste**

Criar `web/src/explorer/Explorer.test.tsx`:
```tsx
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Explorer } from "./Explorer";
import { setConnection } from "../config/connection";

beforeEach(() => {
  localStorage.clear();
  setConnection({ apiUrl: "https://api.test", token: "t" });
});

function stubFetch(routes: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      const key = Object.keys(routes).find((k) => url.endsWith(k));
      return Promise.resolve({ ok: true, status: 200, json: async () => routes[key!] } as Response);
    }),
  );
}

describe("Explorer", () => {
  it("lista kinds com contagem e expande recursos ao clicar", async () => {
    stubFetch({
      "/apis/atlas/v1": { Tracker: 2 },
      "/apis/atlas/v1/Tracker": [
        { api_version: "atlas/v1", kind: "Tracker", name: "peso", labels: {}, spec: {}, status: {} },
        { api_version: "atlas/v1", kind: "Tracker", name: "agua", labels: {}, spec: {}, status: {} },
      ],
    });
    render(<Explorer onSelect={vi.fn()} />);
    expect(await screen.findByText(/Tracker/)).toBeInTheDocument();
    await userEvent.click(screen.getByText(/Tracker/));
    expect(await screen.findByText("peso")).toBeInTheDocument();
    expect(screen.getByText("agua")).toBeInTheDocument();
  });

  it("clicar num recurso chama onSelect(kind,name)", async () => {
    stubFetch({
      "/apis/atlas/v1": { Tracker: 1 },
      "/apis/atlas/v1/Tracker": [
        { api_version: "atlas/v1", kind: "Tracker", name: "peso", labels: {}, spec: {}, status: {} },
      ],
    });
    const onSelect = vi.fn();
    render(<Explorer onSelect={onSelect} />);
    await userEvent.click(await screen.findByText(/Tracker/));
    await userEvent.click(await screen.findByText("peso"));
    expect(onSelect).toHaveBeenCalledWith("Tracker", "peso");
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /home/guaxinim/atlas/web && npx vitest run src/explorer/Explorer.test.tsx`
Expected: FAIL (componente não existe)

- [ ] **Step 3: Implementar**

Criar `web/src/explorer/Explorer.tsx`:
```tsx
import { useEffect, useState } from "react";
import { listKinds, listKind } from "../api/client";
import type { Resource } from "../api/types";

export function Explorer({ onSelect }: { onSelect: (kind: string, name: string) => void }) {
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [aberto, setAberto] = useState<string | null>(null);
  const [recursos, setRecursos] = useState<Record<string, Resource[]>>({});
  const [erro, setErro] = useState("");

  useEffect(() => {
    listKinds()
      .then(setCounts)
      .catch((e: unknown) => setErro(e instanceof Error ? e.message : String(e)));
  }, []);

  async function toggle(kind: string) {
    if (aberto === kind) {
      setAberto(null);
      return;
    }
    setAberto(kind);
    if (!recursos[kind]) {
      try {
        const rs = await listKind(kind);
        setRecursos((prev) => ({ ...prev, [kind]: rs }));
      } catch (e: unknown) {
        setErro(e instanceof Error ? e.message : String(e));
      }
    }
  }

  return (
    <nav style={{ width: 260, borderRight: "1px solid #ddd", overflowY: "auto", padding: 8 }}>
      {erro && <p style={{ color: "crimson" }}>{erro}</p>}
      {Object.entries(counts).map(([kind, n]) => (
        <div key={kind}>
          <button
            onClick={() => toggle(kind)}
            style={{ display: "block", width: "100%", textAlign: "left", padding: "6px 4px", border: "none", background: "none", cursor: "pointer", fontWeight: 600 }}
          >
            {aberto === kind ? "▾" : "▸"} {kind} <span style={{ color: "#888" }}>({n})</span>
          </button>
          {aberto === kind &&
            (recursos[kind] ?? []).map((r) => (
              <button
                key={r.name}
                onClick={() => onSelect(kind, r.name)}
                style={{ display: "block", width: "100%", textAlign: "left", padding: "4px 4px 4px 22px", border: "none", background: "none", cursor: "pointer" }}
              >
                {r.name}
              </button>
            ))}
        </div>
      ))}
    </nav>
  );
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd /home/guaxinim/atlas/web && npx vitest run src/explorer/Explorer.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /home/guaxinim/atlas
git add web/src/explorer
git commit -m "feat(web): explorer (kinds + recursos) na sidebar"
```

---

### Task 4: Card de recurso (view)

**Files:**
- Create: `web/src/resource/ResourceCard.tsx`
- Create: `web/src/resource/ResourceCard.test.tsx`

- [ ] **Step 1: Escrever o teste**

Criar `web/src/resource/ResourceCard.test.tsx`:
```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ResourceCard } from "./ResourceCard";
import type { Resource } from "../api/types";

const r: Resource = {
  api_version: "atlas/v1",
  kind: "Tracker",
  name: "peso",
  labels: { grupo: "academia" },
  spec: { unit: "kg", type: "number" },
  status: { last_value: "82" },
};

describe("ResourceCard", () => {
  it("mostra kind/name, labels, spec e status", () => {
    render(<ResourceCard res={r} />);
    expect(screen.getByText(/Tracker\/peso/)).toBeInTheDocument();
    expect(screen.getByText(/grupo/)).toBeInTheDocument();
    expect(screen.getByText(/academia/)).toBeInTheDocument();
    expect(screen.getByText(/unit/)).toBeInTheDocument();
    expect(screen.getByText(/last_value/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /home/guaxinim/atlas/web && npx vitest run src/resource/ResourceCard.test.tsx`
Expected: FAIL (componente não existe)

- [ ] **Step 3: Implementar**

Criar `web/src/resource/ResourceCard.tsx`:
```tsx
import type { Resource } from "../api/types";

function KV({ titulo, obj }: { titulo: string; obj: Record<string, unknown> }) {
  const entries = Object.entries(obj);
  if (entries.length === 0) return null;
  return (
    <div style={{ marginTop: 12 }}>
      <h4 style={{ margin: "0 0 4px", color: "#555" }}>{titulo}</h4>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <tbody>
          {entries.map(([k, v]) => (
            <tr key={k}>
              <td style={{ padding: "2px 8px 2px 0", color: "#888", verticalAlign: "top" }}>{k}</td>
              <td style={{ padding: 2, fontFamily: "monospace" }}>{JSON.stringify(v)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ResourceCard({ res }: { res: Resource }) {
  return (
    <section>
      <h2 style={{ margin: 0 }}>
        {res.kind}/{res.name}
      </h2>
      <KV titulo="labels" obj={res.labels} />
      <KV titulo="spec" obj={res.spec} />
      <KV titulo="status" obj={res.status} />
    </section>
  );
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd /home/guaxinim/atlas/web && npx vitest run src/resource/ResourceCard.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /home/guaxinim/atlas
git add web/src/resource/ResourceCard.tsx web/src/resource/ResourceCard.test.tsx
git commit -m "feat(web): card de visualização do recurso"
```

---

### Task 5: Form tipado (create/edit a partir do schema)

**Files:**
- Create: `web/src/resource/ResourceForm.tsx`
- Create: `web/src/resource/ResourceForm.test.tsx`

- [ ] **Step 1: Escrever o teste**

Criar `web/src/resource/ResourceForm.test.tsx`:
```tsx
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ResourceForm } from "./ResourceForm";
import { setConnection } from "../config/connection";
import type { KindSchema } from "../api/types";

beforeEach(() => {
  localStorage.clear();
  setConnection({ apiUrl: "https://api.test", token: "t" });
});

const schema: KindSchema = {
  meta: { icon: "📊", desc: "" },
  spec: [
    { k: "unit", type: "text", label: "Unidade" },
    { k: "type", type: "select", label: "Tipo", opts: ["number", "text"] },
    { k: "active", type: "bool", label: "Ativo" },
  ],
  labels: [{ k: "grupo", type: "text", label: "Grupo" }],
  actions: [],
};

describe("ResourceForm", () => {
  it("cria recurso: monta PUT com name, labels e spec", async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({}) } as Response);
    vi.stubGlobal("fetch", f);
    const onSaved = vi.fn();
    render(<ResourceForm kind="Tracker" schema={schema} onSaved={onSaved} />);

    await userEvent.type(screen.getByLabelText(/Nome/i), "peso");
    await userEvent.type(screen.getByLabelText(/Unidade/i), "kg");
    await userEvent.selectOptions(screen.getByLabelText(/Tipo/i), "number");
    await userEvent.click(screen.getByLabelText(/Ativo/i));
    await userEvent.type(screen.getByLabelText(/Grupo/i), "academia");
    await userEvent.click(screen.getByRole("button", { name: /salvar/i }));

    const [url, init] = f.mock.calls[0];
    expect(url).toBe("https://api.test/apis/atlas/v1/Tracker/peso");
    expect(init.method).toBe("PUT");
    const body = JSON.parse(init.body as string);
    expect(body.spec).toEqual({ unit: "kg", type: "number", active: true });
    expect(body.labels).toEqual({ grupo: "academia" });
    expect(onSaved).toHaveBeenCalled();
  });

  it("edição: name vem travado e spec/labels pré-preenchidos", async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({}) } as Response);
    vi.stubGlobal("fetch", f);
    render(
      <ResourceForm
        kind="Tracker"
        schema={schema}
        existing={{ api_version: "atlas/v1", kind: "Tracker", name: "peso", labels: { grupo: "academia" }, spec: { unit: "kg" }, status: {} }}
        onSaved={vi.fn()}
      />,
    );
    const nome = screen.getByLabelText(/Nome/i) as HTMLInputElement;
    expect(nome.value).toBe("peso");
    expect(nome).toBeDisabled();
    expect((screen.getByLabelText(/Unidade/i) as HTMLInputElement).value).toBe("kg");
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /home/guaxinim/atlas/web && npx vitest run src/resource/ResourceForm.test.tsx`
Expected: FAIL (componente não existe)

- [ ] **Step 3: Implementar**

Criar `web/src/resource/ResourceForm.tsx`:
```tsx
import { useState } from "react";
import { putResource } from "../api/client";
import type { KindSchema, Resource, SchemaField } from "../api/types";

type Vals = Record<string, string | boolean>;

function initVals(fields: SchemaField[], src: Record<string, unknown>): Vals {
  const v: Vals = {};
  for (const f of fields) {
    const cur = src[f.k];
    if (f.type === "bool") v[f.k] = cur === true;
    else v[f.k] = cur === undefined || cur === null ? "" : String(cur);
  }
  return v;
}

function coerce(fields: SchemaField[], vals: Vals): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    const v = vals[f.k];
    if (f.type === "bool") out[f.k] = v === true;
    else if (v === "") continue;
    else if (f.type === "number") out[f.k] = Number(v);
    else out[f.k] = v;
  }
  return out;
}

function Field({ f, val, set }: { f: SchemaField; val: string | boolean; set: (v: string | boolean) => void }) {
  if (f.type === "bool") {
    return (
      <label style={row}>
        {f.label}
        <input type="checkbox" checked={val === true} onChange={(e) => set(e.target.checked)} />
      </label>
    );
  }
  if (f.type === "select") {
    return (
      <label style={row}>
        {f.label}
        <select value={String(val)} onChange={(e) => set(e.target.value)}>
          <option value="">—</option>
          {(f.opts ?? []).map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      </label>
    );
  }
  const inputType = f.type === "number" ? "number" : f.type === "time" ? "time" : "text";
  if (f.type === "area") {
    return (
      <label style={row}>
        {f.label}
        <textarea value={String(val)} onChange={(e) => set(e.target.value)} rows={4} />
      </label>
    );
  }
  return (
    <label style={row}>
      {f.label}
      <input type={inputType} value={String(val)} onChange={(e) => set(e.target.value)} />
    </label>
  );
}

export function ResourceForm({
  kind,
  schema,
  existing,
  onSaved,
}: {
  kind: string;
  schema: KindSchema;
  existing?: Resource;
  onSaved: (kind: string, name: string) => void;
}) {
  const [name, setName] = useState(existing?.name ?? "");
  const [spec, setSpec] = useState<Vals>(initVals(schema.spec, existing?.spec ?? {}));
  const [labels, setLabels] = useState<Vals>(initVals(schema.labels, existing?.labels ?? {}));
  const [erro, setErro] = useState("");
  const editando = Boolean(existing);

  async function salvar() {
    if (!name.trim()) {
      setErro("Nome é obrigatório.");
      return;
    }
    try {
      await putResource(kind, name.trim(), {
        labels: coerce(schema.labels, labels) as Record<string, string>,
        spec: coerce(schema.spec, spec),
      });
      onSaved(kind, name.trim());
    } catch (e: unknown) {
      setErro(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <section style={{ maxWidth: 480 }}>
      <h2>
        {editando ? "Editar" : "Novo"} {kind}
      </h2>
      <label style={row}>
        Nome
        <input value={name} disabled={editando} onChange={(e) => setName(e.target.value)} />
      </label>
      <h4 style={{ color: "#555" }}>spec</h4>
      {schema.spec.map((f) => (
        <Field key={f.k} f={f} val={spec[f.k]} set={(v) => setSpec((p) => ({ ...p, [f.k]: v }))} />
      ))}
      {schema.labels.length > 0 && <h4 style={{ color: "#555" }}>labels</h4>}
      {schema.labels.map((f) => (
        <Field key={f.k} f={f} val={labels[f.k]} set={(v) => setLabels((p) => ({ ...p, [f.k]: v }))} />
      ))}
      {erro && <p style={{ color: "crimson" }}>{erro}</p>}
      <button onClick={salvar}>Salvar</button>
    </section>
  );
}

const row: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 4,
  marginBottom: 10,
};
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd /home/guaxinim/atlas/web && npx vitest run src/resource/ResourceForm.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /home/guaxinim/atlas
git add web/src/resource/ResourceForm.tsx web/src/resource/ResourceForm.test.tsx
git commit -m "feat(web): form tipado de criar/editar (derivado do /_schema)"
```

---

### Task 6: Ações por kind + paleta de comandos

**Files:**
- Create: `web/src/resource/KindActions.tsx`
- Create: `web/src/resource/KindActions.test.tsx`
- Create: `web/src/cmd/CommandPalette.tsx`
- Create: `web/src/cmd/CommandPalette.test.tsx`

- [ ] **Step 1: Escrever os testes**

Criar `web/src/resource/KindActions.test.tsx`:
```tsx
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { KindActions } from "./KindActions";
import { setConnection } from "../config/connection";
import type { Resource } from "../api/types";

beforeEach(() => {
  localStorage.clear();
  setConnection({ apiUrl: "https://api.test", token: "t" });
});

const res: Resource = { api_version: "atlas/v1", kind: "Timer", name: "foco", labels: {}, spec: {}, status: {} };

describe("KindActions", () => {
  it("ação verbo=cmd faz POST /_cmd com template preenchido", async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ output: "ok" }) } as Response);
    vi.stubGlobal("fetch", f);
    render(
      <KindActions
        res={res}
        actions={[{ id: "start", label: "▶ Iniciar", verbo: "cmd", template: "/timer start {name}" }]}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /Iniciar/ }));
    const [url, init] = f.mock.calls[0];
    expect(url).toBe("https://api.test/apis/atlas/v1/_cmd");
    expect(JSON.parse(init.body as string)).toEqual({ text: "/timer start foco" });
    expect(await screen.findByText(/ok/)).toBeInTheDocument();
  });

  it("ação verbo=run faz POST /_run", async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ok: true }) } as Response);
    vi.stubGlobal("fetch", f);
    render(
      <KindActions
        res={{ ...res, kind: "Routine", name: "treino" }}
        actions={[{ id: "run", label: "▶ Executar", verbo: "run", template: "{name}" }]}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /Executar/ }));
    expect(f.mock.calls[0][0]).toBe("https://api.test/apis/atlas/v1/_run");
    expect(JSON.parse(f.mock.calls[0][1].body as string)).toEqual({ routine: "treino" });
  });
});
```

Criar `web/src/cmd/CommandPalette.test.tsx`:
```tsx
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CommandPalette } from "./CommandPalette";
import { setConnection } from "../config/connection";

beforeEach(() => {
  localStorage.clear();
  setConnection({ apiUrl: "https://api.test", token: "t" });
});

describe("CommandPalette", () => {
  it("envia /_cmd e mostra a saída", async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ output: "pong" }) } as Response);
    vi.stubGlobal("fetch", f);
    render(<CommandPalette />);
    await userEvent.type(screen.getByPlaceholderText(/comando/i), "/help");
    await userEvent.click(screen.getByRole("button", { name: /enviar/i }));
    expect(JSON.parse(f.mock.calls[0][1].body as string)).toEqual({ text: "/help" });
    expect(await screen.findByText(/pong/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /home/guaxinim/atlas/web && npx vitest run src/resource/KindActions.test.tsx src/cmd/CommandPalette.test.tsx`
Expected: FAIL (componentes não existem)

- [ ] **Step 3: Implementar `KindActions`**

Criar `web/src/resource/KindActions.tsx`:
```tsx
import { useState } from "react";
import { runCmd, runRoutine } from "../api/client";
import type { KindAction, Resource } from "../api/types";

function preencher(template: string, res: Resource): string {
  return template.replace(/\{name\}/g, res.name).replace(/\{syntax\}/g, String(res.spec.syntax ?? ""));
}

export function KindActions({ res, actions }: { res: Resource; actions: KindAction[] }) {
  const [saida, setSaida] = useState("");
  const [erro, setErro] = useState("");

  async function exec(a: KindAction) {
    setErro("");
    setSaida("");
    try {
      if (a.verbo === "run") {
        await runRoutine(res.name);
        setSaida(`executado: ${res.name}`);
      } else {
        const r = await runCmd(preencher(a.template, res));
        setSaida(r.output);
      }
    } catch (e: unknown) {
      setErro(e instanceof Error ? e.message : String(e));
    }
  }

  if (actions.length === 0) return null;
  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {actions.map((a) => (
          <button key={a.id} onClick={() => exec(a)}>
            {a.label}
          </button>
        ))}
      </div>
      {saida && <pre style={{ whiteSpace: "pre-wrap", background: "#f5f5f5", padding: 8 }}>{saida}</pre>}
      {erro && <p style={{ color: "crimson" }}>{erro}</p>}
    </div>
  );
}
```

- [ ] **Step 4: Implementar `CommandPalette`**

Criar `web/src/cmd/CommandPalette.tsx`:
```tsx
import { useState } from "react";
import { runCmd } from "../api/client";

export function CommandPalette() {
  const [texto, setTexto] = useState("");
  const [saida, setSaida] = useState("");
  const [erro, setErro] = useState("");

  async function enviar() {
    if (!texto.trim()) return;
    setErro("");
    try {
      const r = await runCmd(texto.trim());
      setSaida(r.output);
    } catch (e: unknown) {
      setErro(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div style={{ borderTop: "1px solid #ddd", padding: 8 }}>
      <div style={{ display: "flex", gap: 8 }}>
        <input
          style={{ flex: 1 }}
          placeholder="comando (ex.: /list Tracker)"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && enviar()}
        />
        <button onClick={enviar}>Enviar</button>
      </div>
      {saida && <pre style={{ whiteSpace: "pre-wrap", background: "#f5f5f5", padding: 8 }}>{saida}</pre>}
      {erro && <p style={{ color: "crimson" }}>{erro}</p>}
    </div>
  );
}
```

- [ ] **Step 5: Rodar e ver passar**

Run: `cd /home/guaxinim/atlas/web && npx vitest run src/resource/KindActions.test.tsx src/cmd/CommandPalette.test.tsx`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd /home/guaxinim/atlas
git add web/src/resource/KindActions.tsx web/src/resource/KindActions.test.tsx web/src/cmd
git commit -m "feat(web): ações por kind e paleta de comandos"
```

---

### Task 7: App layout (junta tudo) + delete + novo

**Files:**
- Modify: `web/src/App.tsx`
- Modify: `web/src/App.test.tsx`

- [ ] **Step 1: Reescrever o teste do App**

Substituir `web/src/App.test.tsx` por:
```tsx
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { setConnection } from "./config/connection";

beforeEach(() => localStorage.clear());

function stubRoutes(routes: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      const key = Object.keys(routes).find((k) => url.endsWith(k));
      return Promise.resolve({ ok: true, status: 200, json: async () => routes[key!] } as Response);
    }),
  );
}

describe("App", () => {
  it("sem conexão mostra overlay", () => {
    render(<App />);
    expect(screen.getByRole("dialog", { name: /Conexão com a API/i })).toBeInTheDocument();
  });

  it("conectado: explorer + selecionar recurso mostra o card", async () => {
    setConnection({ apiUrl: "https://api.test", token: "t" });
    stubRoutes({
      "/_schema": { kinds: { Tracker: { meta: { icon: "📊", desc: "" }, spec: [], labels: [], actions: [] } } },
      "/apis/atlas/v1": { Tracker: 1 },
      "/apis/atlas/v1/Tracker/peso": { api_version: "atlas/v1", kind: "Tracker", name: "peso", labels: {}, spec: { unit: "kg" }, status: {} },
      "/apis/atlas/v1/Tracker": [{ api_version: "atlas/v1", kind: "Tracker", name: "peso", labels: {}, spec: { unit: "kg" }, status: {} }],
    });
    render(<App />);
    await userEvent.click(await screen.findByText(/Tracker/));
    await userEvent.click(await screen.findByText("peso"));
    expect(await screen.findByText(/Tracker\/peso/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /home/guaxinim/atlas/web && npx vitest run src/App.test.tsx`
Expected: FAIL (App ainda é o shell da F2)

- [ ] **Step 3: Implementar o App**

Substituir `web/src/App.tsx` por:
```tsx
import { useState } from "react";
import { isConfigured } from "./config/connection";
import { ConnectionOverlay } from "./config/ConnectionOverlay";
import { useSchema } from "./schema/useSchema";
import { Explorer } from "./explorer/Explorer";
import { ResourceCard } from "./resource/ResourceCard";
import { ResourceForm } from "./resource/ResourceForm";
import { KindActions } from "./resource/KindActions";
import { CommandPalette } from "./cmd/CommandPalette";
import { getResource, deleteResource } from "./api/client";
import type { Resource } from "./api/types";

type View = { mode: "vazio" } | { mode: "card"; res: Resource } | { mode: "novo"; kind: string };

export default function App() {
  const [configured, setConfigured] = useState(isConfigured());
  const [view, setView] = useState<View>({ mode: "vazio" });
  const [chave, setChave] = useState(0); // força recarregar o explorer
  const { schema, erro: erroSchema } = useSchema();

  if (!configured) {
    return <ConnectionOverlay onSaved={() => setConfigured(true)} />;
  }

  async function abrir(kind: string, name: string) {
    const res = await getResource(kind, name);
    setView({ mode: "card", res });
  }

  async function remover(res: Resource) {
    if (!confirm(`Apagar ${res.kind}/${res.name}?`)) return;
    await deleteResource(res.kind, res.name);
    setView({ mode: "vazio" });
    setChave((k) => k + 1);
  }

  const kinds = schema ? Object.keys(schema.kinds) : [];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", fontFamily: "sans-serif" }}>
      <header style={{ padding: "8px 12px", borderBottom: "1px solid #ddd", display: "flex", gap: 12, alignItems: "center" }}>
        <strong>Atlas</strong>
        <select value="" onChange={(e) => e.target.value && setView({ mode: "novo", kind: e.target.value })}>
          <option value="">+ Novo…</option>
          {kinds.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        {erroSchema && <span style={{ color: "crimson" }}>{erroSchema}</span>}
      </header>
      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
        <Explorer key={chave} onSelect={abrir} />
        <main style={{ flex: 1, overflowY: "auto", padding: 16 }}>
          {view.mode === "vazio" && <p style={{ color: "#888" }}>Selecione um recurso ou crie um novo.</p>}
          {view.mode === "card" && schema && (
            <>
              <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
                <button onClick={() => setView({ mode: "card", res: view.res })}>↻</button>
                <button onClick={() => remover(view.res)} style={{ color: "crimson" }}>
                  Apagar
                </button>
              </div>
              <ResourceCard res={view.res} />
              {schema.kinds[view.res.kind] && (
                <KindActions res={view.res} actions={schema.kinds[view.res.kind].actions} />
              )}
              {schema.kinds[view.res.kind] && (
                <details style={{ marginTop: 16 }}>
                  <summary>Editar</summary>
                  <ResourceForm
                    kind={view.res.kind}
                    schema={schema.kinds[view.res.kind]}
                    existing={view.res}
                    onSaved={(k, n) => {
                      setChave((c) => c + 1);
                      void abrir(k, n);
                    }}
                  />
                </details>
              )}
            </>
          )}
          {view.mode === "novo" && schema && schema.kinds[view.kind] && (
            <ResourceForm
              kind={view.kind}
              schema={schema.kinds[view.kind]}
              onSaved={(k, n) => {
                setChave((c) => c + 1);
                void abrir(k, n);
              }}
            />
          )}
        </main>
      </div>
      <CommandPalette />
    </div>
  );
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd /home/guaxinim/atlas/web && npx vitest run src/App.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /home/guaxinim/atlas
git add web/src/App.tsx web/src/App.test.tsx
git commit -m "feat(web): layout do app (explorer + card + form + ações + paleta + delete)"
```

---

### Task 8: Verificação final da F3

**Files:** —

- [ ] **Step 1: Suíte + typecheck + build do front**

Run: `cd /home/guaxinim/atlas/web && npm test && npm run typecheck && npm run build`
Expected: todos os testes passam; typecheck limpo; build gera `dist/`.

- [ ] **Step 2: Backend intacto (a F3 só tocou doc + web)**

Run: `cd /home/guaxinim/atlas && python -m pytest -q && ruff check . && ruff format --check .`
Expected: suíte Python verde; lint OK.

- [ ] **Step 3: Smoke manual contra a API real (opcional)**

```bash
# API já rodando em :8080. Dev server do front:
export PATH="$HOME/.local/node/bin:$PATH"
cd /home/guaxinim/atlas/web && npm run dev
# No navegador (dev server): conectar com http://127.0.0.1:8080 + token do .env;
# abrir um kind, ver recursos, abrir o card, criar/editar, rodar uma ação, usar a paleta.
```
Expected: explorer lista os kinds reais; card mostra spec/status; criar/editar persiste; paleta retorna saída.

---

## Notas de verificação para o curador
- **Fronteira:** todos os componentes só chamam funções do cliente (endpoints do
  contrato). Forms/ações vêm de `/_schema` — sem regra de negócio embutida.
- **Tipo flat:** `Resource` agora bate com a serialização real da API; contrato
  corrigido.
- **node_modules fora do git.**
- **Backend não tocado** (exceto a doc de contrato).
- **Backlog (fora desta fase):** página de status (`/_status`), graph, autocomplete
  na paleta (`/_complete`), e o achado da ativação-precisa-restart no scheduler.
