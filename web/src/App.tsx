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
