import { describe, it, expect } from "vitest";
import type { Resource, SchemaPayload } from "./types";

describe("tipos do contrato", () => {
  it("Resource aceita o shape K8s", () => {
    const r: Resource = {
      apiVersion: "atlas/v1",
      kind: "Tracker",
      metadata: { name: "peso", labels: { grupo: "academia" } },
      spec: { unit: "kg" },
      status: {},
    };
    expect(r.metadata.name).toBe("peso");
  });

  it("SchemaPayload mapeia kinds", () => {
    const s: SchemaPayload = {
      kinds: {
        Timer: { meta: { icon: "⏱", desc: "" }, spec: [], labels: [], actions: [{ id: "start", label: "▶", verbo: "cmd", template: "/timer start {name}" }] },
      },
    };
    expect(s.kinds.Timer.actions[0].id).toBe("start");
  });
});
