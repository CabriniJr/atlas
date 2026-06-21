import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Explorer } from "./Explorer";
import { setConnection } from "../config/connection";

beforeEach(() => {
  localStorage.clear();
  setConnection({ apiUrl: "https://api.test", token: "t" });
});

function stubFetch(routes: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      const key = Object.keys(routes).find((k) => url.endsWith(k));
      return Promise.resolve({ ok: true, status: 200, json: async () => routes[key!] } as Response);
    }),
  );
}

describe("Explorer", () => {
  it("lista kinds com contagem e expande recursos ao clicar", async () => {
    stubFetch({
      "/apis/atlas/v1": { Tracker: 2 },
      "/apis/atlas/v1/Tracker": [
        { api_version: "atlas/v1", kind: "Tracker", name: "peso", labels: {}, spec: {}, status: {} },
        { api_version: "atlas/v1", kind: "Tracker", name: "agua", labels: {}, spec: {}, status: {} },
      ],
    });
    render(<Explorer onSelect={vi.fn()} />);
    expect(await screen.findByText(/Tracker/)).toBeInTheDocument();
    await userEvent.click(screen.getByText(/Tracker/));
    expect(await screen.findByText("peso")).toBeInTheDocument();
    expect(screen.getByText("agua")).toBeInTheDocument();
  });

  it("clicar num recurso chama onSelect(kind,name)", async () => {
    stubFetch({
      "/apis/atlas/v1": { Tracker: 1 },
      "/apis/atlas/v1/Tracker": [
        { api_version: "atlas/v1", kind: "Tracker", name: "peso", labels: {}, spec: {}, status: {} },
      ],
    });
    const onSelect = vi.fn();
    render(<Explorer onSelect={onSelect} />);
    await userEvent.click(await screen.findByText(/Tracker/));
    await userEvent.click(await screen.findByText("peso"));
    expect(onSelect).toHaveBeenCalledWith("Tracker", "peso");
  });
});
