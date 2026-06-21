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
