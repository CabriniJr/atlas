import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ResourceCard } from "./ResourceCard";
import type { Resource } from "../api/types";

const r: Resource = {
  api_version: "atlas/v1",
  kind: "Tracker",
  name: "peso",
  labels: { grupo: "academia" },
  spec: { unit: "kg", type: "number" },
  status: { last_value: "82" },
};

describe("ResourceCard", () => {
  it("mostra kind/name, labels, spec e status", () => {
    render(<ResourceCard res={r} />);
    expect(screen.getByText(/Tracker\/peso/)).toBeInTheDocument();
    expect(screen.getByText(/grupo/)).toBeInTheDocument();
    expect(screen.getByText(/academia/)).toBeInTheDocument();
    expect(screen.getByText(/unit/)).toBeInTheDocument();
    expect(screen.getByText(/last_value/)).toBeInTheDocument();
  });
});
