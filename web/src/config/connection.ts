export interface Connection {
  apiUrl: string;
  token: string;
}

const KEY = "atlas_connection";

export function getConnection(): Connection {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { apiUrl: "", token: "" };
    const c = JSON.parse(raw) as Partial<Connection>;
    return { apiUrl: c.apiUrl ?? "", token: c.token ?? "" };
  } catch {
    return { apiUrl: "", token: "" };
  }
}

export function setConnection(c: Connection): void {
  const apiUrl = c.apiUrl.trim().replace(/\/+$/, "");
  localStorage.setItem(KEY, JSON.stringify({ apiUrl, token: c.token.trim() }));
}

export function isConfigured(): boolean {
  return getConnection().apiUrl.length > 0;
}

export function clearConnection(): void {
  localStorage.removeItem(KEY);
}
