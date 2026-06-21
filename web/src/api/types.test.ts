import { describe, it, expect } from "vitest";
import type { Resource, SchemaPayload } from "./types";

describe("tipos do contrato", () => {
  it("Resource é flat (name/labels no topo)", () => {
    const r: Resource = {
      api_version: "atlas/v1",
      kind: "Tracker",
      name: "peso",
      labels: { grupo: "academia" },
      spec: { unit: "kg" },
      status: {},
    };
    expect(r.name).toBe("peso");
    expect(r.labels.grupo).toBe("academia");
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
