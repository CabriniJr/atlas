import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Button } from "./Button";

describe("Button", () => {
  it("aplica variante e tamanho como classes", () => {
    render(<Button variant="primary" size="lg">Salvar</Button>);
    const b = screen.getByRole("button", { name: "Salvar" });
    expect(b).toHaveClass("ui-btn", "ui-btn--primary", "ui-btn--lg");
  });

  it("default é secondary/md e type=button", () => {
    render(<Button>Ok</Button>);
    const b = screen.getByRole("button", { name: "Ok" });
    expect(b).toHaveClass("ui-btn--secondary", "ui-btn--md");
    expect(b).toHaveAttribute("type", "button");
  });

  it("dispara onClick", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Vai</Button>);
    await userEvent.click(screen.getByRole("button", { name: "Vai" }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("não dispara quando disabled", async () => {
    const onClick = vi.fn();
    render(<Button disabled onClick={onClick}>Não</Button>);
    await userEvent.click(screen.getByRole("button", { name: "Não" }));
    expect(onClick).not.toHaveBeenCalled();
  });
});
