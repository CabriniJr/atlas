import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Input, Field } from "./Input";

describe("Input", () => {
  it("marca invalid com classe e aria-invalid", () => {
    render(<Input invalid placeholder="p" />);
    const el = screen.getByPlaceholderText("p");
    expect(el).toHaveClass("ui-input", "ui-input--invalid");
    expect(el).toHaveAttribute("aria-invalid", "true");
  });

  it("sem invalid não põe aria-invalid", () => {
    render(<Input placeholder="p" />);
    expect(screen.getByPlaceholderText("p")).not.toHaveAttribute("aria-invalid");
  });
});

describe("Field", () => {
  it("liga label ao controle e mostra hint", () => {
    render(
      <Field label="Usuário" hint="minúsculas">
        {({ id, describedBy }) => (
          <Input id={id} aria-describedby={describedBy} placeholder="u" />
        )}
      </Field>,
    );
    const input = screen.getByLabelText("Usuário");
    expect(input).toBeInTheDocument();
    expect(screen.getByText("minúsculas")).toBeInTheDocument();
  });

  it("erro tem prioridade sobre hint", () => {
    render(
      <Field label="Senha" hint="dica" error="obrigatória">
        {({ id }) => <Input id={id} type="password" />}
      </Field>,
    );
    expect(screen.getByText("obrigatória")).toBeInTheDocument();
    expect(screen.queryByText("dica")).toBeNull();
  });
});
