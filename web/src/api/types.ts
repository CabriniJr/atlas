// Espelha docs/specs/api-http-contrato.md

export interface Resource {
  apiVersion: string;
  kind: string;
  metadata: {
    name: string;
    labels?: Record<string, string>;
    criado_em?: string;
    atualizado_em?: string;
  };
  spec: Record<string, unknown>;
  status: Record<string, unknown>;
}

export type FieldType = "text" | "area" | "number" | "bool" | "select" | "time" | "cron";

export interface SchemaField {
  k: string;
  type: FieldType;
  label: string;
  hint?: string;
  opts?: string[];
}

export interface KindAction {
  id: string;
  label: string;
  verbo: "cmd" | "run" | "insight";
  template: string;
}

export interface KindSchema {
  meta: { icon: string; desc: string };
  spec: SchemaField[];
  labels: SchemaField[];
  actions: KindAction[];
}

export interface SchemaPayload {
  kinds: Record<string, KindSchema>;
}
