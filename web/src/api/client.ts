import { getConnection } from "../config/connection";
import type { Resource, SchemaPayload } from "./types";

const PREFIX = "/apis/atlas/v1";

export class ApiError extends Error {
  status: number;
  unauthorized: boolean;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.unauthorized = status === 401;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { apiUrl, token } = getConnection();
  if (!apiUrl) throw new ApiError("conexão não configurada", 0);

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  let resp: Response;
  try {
    resp = await fetch(apiUrl + path, { ...init, headers });
  } catch (e) {
    throw new ApiError(`falha de rede ao chamar ${apiUrl}${path}: ${String(e)}`, 0);
  }
  if (!resp.ok) {
    let detail = "";
    try {
      detail = JSON.stringify(await resp.json());
    } catch {
      /* corpo não-JSON */
    }
    throw new ApiError(`HTTP ${resp.status} em ${path} ${detail}`, resp.status);
  }
  return (await resp.json()) as T;
}

export function listKinds(): Promise<Record<string, number>> {
  return request(PREFIX);
}

export function listKind(kind: string): Promise<Resource[]> {
  return request(`${PREFIX}/${kind}`);
}

export function getResource(kind: string, name: string): Promise<Resource> {
  return request(`${PREFIX}/${kind}/${name}`);
}

export function putResource(
  kind: string,
  name: string,
  body: { labels?: Record<string, string>; spec?: Record<string, unknown> },
): Promise<Resource> {
  return request(`${PREFIX}/${kind}/${name}`, { method: "PUT", body: JSON.stringify(body) });
}

export function deleteResource(kind: string, name: string): Promise<{ deleted: string }> {
  return request(`${PREFIX}/${kind}/${name}`, { method: "DELETE" });
}

export function runCmd(text: string): Promise<{ output: string }> {
  return request(`${PREFIX}/_cmd`, { method: "POST", body: JSON.stringify({ text }) });
}

export function runRoutine(routine: string): Promise<unknown> {
  return request(`${PREFIX}/_run`, { method: "POST", body: JSON.stringify({ routine }) });
}

export function fetchStatus(): Promise<unknown> {
  return request(`${PREFIX}/_status`);
}

export function fetchSchema(): Promise<SchemaPayload> {
  return request(`${PREFIX}/_schema`);
}
