import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { KindActions } from "./KindActions";
import { setConnection } from "../config/connection";
import type { Resource } from "../api/types";

beforeEach(() => {
  localStorage.clear();
  setConnection({ apiUrl: "https://api.test", token: "t" });
});

const res: Resource = { api_version: "atlas/v1", kind: "Timer", name: "foco", labels: {}, spec: {}, status: {} };

describe("KindActions", () => {
  it("ação verbo=cmd faz POST /_cmd com template preenchido", async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ output: "ok" }) } as Response);
    vi.stubGlobal("fetch", f);
    render(
      <KindActions
        res={res}
        actions={[{ id: "start", label: "▶ Iniciar", verbo: "cmd", template: "/timer start {name}" }]}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /Iniciar/ }));
    const [url, init] = f.mock.calls[0];
    expect(url).toBe("https://api.test/apis/atlas/v1/_cmd");
    expect(JSON.parse(init.body as string)).toEqual({ text: "/timer start foco" });
    expect(await screen.findByText(/ok/)).toBeInTheDocument();
  });

  it("ação verbo=run faz POST /_run", async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ok: true }) } as Response);
    vi.stubGlobal("fetch", f);
    render(
      <KindActions
        res={{ ...res, kind: "Routine", name: "treino" }}
        actions={[{ id: "run", label: "▶ Executar", verbo: "run", template: "{name}" }]}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /Executar/ }));
    expect(f.mock.calls[0][0]).toBe("https://api.test/apis/atlas/v1/_run");
    expect(JSON.parse(f.mock.calls[0][1].body as string)).toEqual({ routine: "treino" });
  });
});
