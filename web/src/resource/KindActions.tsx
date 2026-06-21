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
