import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Badge } from "./Badge";

describe("Badge", () => {
  it("aplica variante", () => {
    render(<Badge variant="success">ativo</Badge>);
    expect(screen.getByText("ativo")).toHaveClass("ui-badge", "ui-badge--success");
  });

  it("default é neutral", () => {
    render(<Badge>x</Badge>);
    expect(screen.getByText("x")).toHaveClass("ui-badge--neutral");
  });

  it("mostra o dot quando dot=true", () => {
    const { container } = render(<Badge dot variant="warning">pendente</Badge>);
    expect(container.querySelector(".ui-badge__dot")).not.toBeNull();
  });

  it("sem dot por padrão", () => {
    const { container } = render(<Badge>sem</Badge>);
    expect(container.querySelector(".ui-badge__dot")).toBeNull();
  });
});
