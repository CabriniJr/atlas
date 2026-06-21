import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ResourceForm } from "./ResourceForm";
import { setConnection } from "../config/connection";
import type { KindSchema } from "../api/types";

beforeEach(() => {
  localStorage.clear();
  setConnection({ apiUrl: "https://api.test", token: "t" });
});

const schema: KindSchema = {
  meta: { icon: "📊", desc: "" },
  spec: [
    { k: "unit", type: "text", label: "Unidade" },
    { k: "type", type: "select", label: "Tipo", opts: ["number", "text"] },
    { k: "active", type: "bool", label: "Ativo" },
  ],
  labels: [{ k: "grupo", type: "text", label: "Grupo" }],
  actions: [],
};

describe("ResourceForm", () => {
  it("cria recurso: monta PUT com name, labels e spec", async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({}) } as Response);
    vi.stubGlobal("fetch", f);
    const onSaved = vi.fn();
    render(<ResourceForm kind="Tracker" schema={schema} onSaved={onSaved} />);

    await userEvent.type(screen.getByLabelText(/Nome/i), "peso");
    await userEvent.type(screen.getByLabelText(/Unidade/i), "kg");
    await userEvent.selectOptions(screen.getByLabelText(/Tipo/i), "number");
    await userEvent.click(screen.getByLabelText(/Ativo/i));
    await userEvent.type(screen.getByLabelText(/Grupo/i), "academia");
    await userEvent.click(screen.getByRole("button", { name: /salvar/i }));

    const [url, init] = f.mock.calls[0];
    expect(url).toBe("https://api.test/apis/atlas/v1/Tracker/peso");
    expect(init.method).toBe("PUT");
    const body = JSON.parse(init.body as string);
    expect(body.spec).toEqual({ unit: "kg", type: "number", active: true });
    expect(body.labels).toEqual({ grupo: "academia" });
    expect(onSaved).toHaveBeenCalled();
  });

  it("edição: name vem travado e spec/labels pré-preenchidos", async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({}) } as Response);
    vi.stubGlobal("fetch", f);
    render(
      <ResourceForm
        kind="Tracker"
        schema={schema}
        existing={{ api_version: "atlas/v1", kind: "Tracker", name: "peso", labels: { grupo: "academia" }, spec: { unit: "kg" }, status: {} }}
        onSaved={vi.fn()}
      />,
    );
    const nome = screen.getByLabelText(/Nome/i) as HTMLInputElement;
    expect(nome.value).toBe("peso");
    expect(nome).toBeDisabled();
    expect((screen.getByLabelText(/Unidade/i) as HTMLInputElement).value).toBe("kg");
  });
});
