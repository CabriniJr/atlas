import { useState } from "react";
import { getConnection, setConnection } from "./connection";
import { Button, Card, CardBody, CardHeader, Field, Input } from "../ui";
import "./ConnectionOverlay.css";

export function ConnectionOverlay({ onSaved }: { onSaved: () => void }) {
  const current = getConnection();
  const [apiUrl, setApiUrl] = useState(current.apiUrl);
  const [token, setToken] = useState(current.token);
  const [erro, setErro] = useState("");

  function conectar() {
    const url = apiUrl.trim();
    const ehLocal = /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?/.test(url);
    const ehHttps = /^https:\/\//.test(url);
    if (!ehHttps && !ehLocal) {
      setErro("Use https:// (http só é permitido em localhost/127.0.0.1).");
      return;
    }
    setConnection({ apiUrl: url, token });
    onSaved();
  }

  return (
    <div role="dialog" aria-label="Conexão com a API" className="conn-overlay">
      <Card className="conn-box">
        <CardHeader title="Conectar ao Atlas" subtitle="URL da API + token de acesso" icon="🔌" />
        <CardBody>
          <div className="conn-form">
            <Field label="URL da API">
              {({ id }) => (
                <Input
                  id={id}
                  value={apiUrl}
                  onChange={(e) => setApiUrl(e.target.value)}
                  placeholder="https://pi.<tailnet>.ts.net"
                />
              )}
            </Field>
            <Field label="Token" error={erro || undefined}>
              {({ id, describedBy }) => (
                <Input
                  id={id}
                  type="password"
                  value={token}
                  invalid={!!erro}
                  aria-describedby={describedBy}
                  onChange={(e) => setToken(e.target.value)}
                />
              )}
            </Field>
            <Button variant="primary" onClick={conectar}>
              Conectar
            </Button>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
