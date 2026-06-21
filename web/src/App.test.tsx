import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { setConnection } from "./config/connection";

beforeEach(() => localStorage.clear());

function stubRoutes(routes: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      const key = Object.keys(routes).find((k) => url.endsWith(k));
      return Promise.resolve({ ok: true, status: 200, json: async () => routes[key!] } as Response);
    }),
  );
}

describe("App", () => {
  it("sem conexão mostra overlay", () => {
    render(<App />);
    expect(screen.getByRole("dialog", { name: /Conexão com a API/i })).toBeInTheDocument();
  });

  it("conectado: explorer + selecionar recurso mostra o card", async () => {
    setConnection({ apiUrl: "https://api.test", token: "t" });
    stubRoutes({
      "/_schema": { kinds: { Tracker: { meta: { icon: "📊", desc: "" }, spec: [], labels: [], actions: [] } } },
      "/apis/atlas/v1": { Tracker: 1 },
      "/apis/atlas/v1/Tracker/peso": { api_version: "atlas/v1", kind: "Tracker", name: "peso", labels: {}, spec: { unit: "kg" }, status: {} },
      "/apis/atlas/v1/Tracker": [{ api_version: "atlas/v1", kind: "Tracker", name: "peso", labels: {}, spec: { unit: "kg" }, status: {} }],
    });
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Tracker/ }));
    await userEvent.click(await screen.findByText("peso"));
    expect(await screen.findByText(/Tracker\/peso/)).toBeInTheDocument();
  });
});
