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
