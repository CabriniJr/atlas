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
