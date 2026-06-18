import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConnectionOverlay } from "./ConnectionOverlay";
import { getConnection } from "./connection";

beforeEach(() => localStorage.clear());

describe("ConnectionOverlay", () => {
  it("salva URL+token e chama onSaved", async () => {
    const onSaved = vi.fn();
    render(<ConnectionOverlay onSaved={onSaved} />);
    await userEvent.type(screen.getByLabelText(/URL da API/i), "https://pi.ts.net");
    await userEvent.type(screen.getByLabelText(/Token/i), "t0k");
    await userEvent.click(screen.getByRole("button", { name: /conectar/i }));
    expect(getConnection()).toEqual({ apiUrl: "https://pi.ts.net", token: "t0k" });
    expect(onSaved).toHaveBeenCalled();
  });

  it("exige https:// na URL", async () => {
    render(<ConnectionOverlay onSaved={vi.fn()} />);
    await userEvent.type(screen.getByLabelText(/URL da API/i), "http://inseguro");
    await userEvent.click(screen.getByRole("button", { name: /conectar/i }));
    expect(screen.getByText(/https/i)).toBeInTheDocument();
  });
});
