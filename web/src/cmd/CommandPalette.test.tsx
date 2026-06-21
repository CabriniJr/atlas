import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CommandPalette } from "./CommandPalette";
import { setConnection } from "../config/connection";

beforeEach(() => {
  localStorage.clear();
  setConnection({ apiUrl: "https://api.test", token: "t" });
});

describe("CommandPalette", () => {
  it("envia /_cmd e mostra a saída", async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ output: "pong" }) } as Response);
    vi.stubGlobal("fetch", f);
    render(<CommandPalette />);
    await userEvent.type(screen.getByPlaceholderText(/comando/i), "/help");
    await userEvent.click(screen.getByRole("button", { name: /enviar/i }));
    expect(JSON.parse(f.mock.calls[0][1].body as string)).toEqual({ text: "/help" });
    expect(await screen.findByText(/pong/)).toBeInTheDocument();
  });
});
