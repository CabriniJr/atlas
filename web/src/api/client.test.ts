import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { setConnection } from "../config/connection";
import { ApiError, listKinds, getResource, putResource, fetchSchema } from "./client";

beforeEach(() => {
  localStorage.clear();
  setConnection({ apiUrl: "https://api.test", token: "t0k" });
});
afterEach(() => vi.restoreAllMocks());

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response);
}

describe("api client", () => {
  it("listKinds chama a URL certa com Bearer", async () => {
    const f = mockFetch(200, { Tracker: 2 });
    vi.stubGlobal("fetch", f);
    const out = await listKinds();
    expect(out).toEqual({ Tracker: 2 });
    const [url, init] = f.mock.calls[0];
    expect(url).toBe("https://api.test/apis/atlas/v1");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer t0k");
  });

  it("getResource monta kind/name", async () => {
    const f = mockFetch(200, { kind: "Tracker", metadata: { name: "peso" }, spec: {}, status: {} });
    vi.stubGlobal("fetch", f);
    await getResource("Tracker", "peso");
    expect(f.mock.calls[0][0]).toBe("https://api.test/apis/atlas/v1/Tracker/peso");
  });

  it("putResource envia labels+spec via PUT", async () => {
    const f = mockFetch(200, {});
    vi.stubGlobal("fetch", f);
    await putResource("Tracker", "peso", { labels: { grupo: "academia" }, spec: { unit: "kg" } });
    const [url, init] = f.mock.calls[0];
    expect(url).toBe("https://api.test/apis/atlas/v1/Tracker/peso");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({ labels: { grupo: "academia" }, spec: { unit: "kg" } });
  });

  it("401 lança ApiError com flag unauthorized", async () => {
    vi.stubGlobal("fetch", mockFetch(401, { error: "unauthorized" }));
    await expect(listKinds()).rejects.toMatchObject({ status: 401, unauthorized: true });
    await expect(listKinds()).rejects.toBeInstanceOf(ApiError);
  });

  it("fetchSchema retorna kinds", async () => {
    vi.stubGlobal("fetch", mockFetch(200, { kinds: { Timer: { meta: {}, spec: [], labels: [], actions: [] } } }));
    const s = await fetchSchema();
    expect(s.kinds.Timer).toBeTruthy();
  });

  it("sem apiUrl configurada lança ApiError", async () => {
    localStorage.clear();
    await expect(listKinds()).rejects.toBeInstanceOf(ApiError);
  });
});
