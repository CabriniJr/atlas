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
