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
