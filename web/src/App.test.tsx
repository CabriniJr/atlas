import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "./App";
import { setConnection } from "./config/connection";

beforeEach(() => localStorage.clear());

describe("App", () => {
  it("mostra overlay quando não configurado", () => {
    render(<App />);
    expect(screen.getByRole("dialog", { name: /Conexão com a API/i })).toBeInTheDocument();
  });

  it("quando configurado, busca e lista kinds", async () => {
    setConnection({ apiUrl: "https://api.test", token: "t" });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ Tracker: 3, Goal: 1 }),
      } as Response),
    );
    render(<App />);
    expect(await screen.findByText(/Tracker/)).toBeInTheDocument();
    expect(await screen.findByText(/3/)).toBeInTheDocument();
  });
});
