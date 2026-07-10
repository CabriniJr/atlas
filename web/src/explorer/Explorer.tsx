import { useEffect, useState } from "react";
import { listKinds, listKind } from "../api/client";
import type { Resource } from "../api/types";
import { Badge } from "../ui";
import "./Explorer.css";

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
    <nav className="explorer">
      {erro && <p className="explorer__erro">{erro}</p>}
      {Object.entries(counts).map(([kind, n]) => (
        <div key={kind}>
          <button className="explorer__kind" onClick={() => toggle(kind)}>
            <span className="explorer__caret">{aberto === kind ? "▾" : "▸"}</span>
            <span className="explorer__kind-name">{kind}</span>
            <Badge variant="neutral">{n}</Badge>
          </button>
          {aberto === kind &&
            (recursos[kind] ?? []).map((r) => (
              <button
                key={r.name}
                className="explorer__res"
                onClick={() => onSelect(kind, r.name)}
              >
                {r.name}
              </button>
            ))}
        </div>
      ))}
    </nav>
  );
}
