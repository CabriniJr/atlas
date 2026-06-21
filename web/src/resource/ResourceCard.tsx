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
