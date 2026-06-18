import { describe, it, expect, beforeEach } from "vitest";
import { getConnection, setConnection, isConfigured, clearConnection } from "./connection";

beforeEach(() => localStorage.clear());

describe("connection store", () => {
  it("vazio por padrão", () => {
    expect(getConnection()).toEqual({ apiUrl: "", token: "" });
    expect(isConfigured()).toBe(false);
  });

  it("persiste e lê apiUrl + token", () => {
    setConnection({ apiUrl: "https://pi.tailnet.ts.net", token: "t0k" });
    expect(getConnection()).toEqual({ apiUrl: "https://pi.tailnet.ts.net", token: "t0k" });
    expect(isConfigured()).toBe(true);
  });

  it("normaliza barra final da apiUrl", () => {
    setConnection({ apiUrl: "https://pi.ts.net/", token: "" });
    expect(getConnection().apiUrl).toBe("https://pi.ts.net");
  });

  it("isConfigured exige apiUrl (token opcional)", () => {
    setConnection({ apiUrl: "https://pi.ts.net", token: "" });
    expect(isConfigured()).toBe(true);
  });

  it("clear remove tudo", () => {
    setConnection({ apiUrl: "https://x", token: "y" });
    clearConnection();
    expect(isConfigured()).toBe(false);
  });
});
