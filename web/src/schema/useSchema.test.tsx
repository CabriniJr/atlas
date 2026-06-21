import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useSchema } from "./useSchema";
import { setConnection } from "../config/connection";

beforeEach(() => {
  localStorage.clear();
  setConnection({ apiUrl: "https://api.test", token: "t" });
});

function mockFetch(body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => body } as Response),
  );
}

describe("useSchema", () => {
  it("carrega kinds do /_schema", async () => {
    mockFetch({ kinds: { Tracker: { meta: { icon: "📊", desc: "" }, spec: [], labels: [], actions: [] } } });
    const { result } = renderHook(() => useSchema());
    await waitFor(() => expect(result.current.schema).not.toBeNull());
    expect(result.current.schema!.kinds.Tracker.meta.icon).toBe("📊");
  });
});
