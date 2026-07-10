import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Card, CardHeader, CardBody } from "./Card";
import { Badge } from "./Badge";

describe("Card", () => {
  it("renderiza header (title/subtitle/trailing) e body", () => {
    render(
      <Card>
        <CardHeader title="Trackers" subtitle="3 ativos" trailing={<Badge>on</Badge>} />
        <CardBody>conteúdo</CardBody>
      </Card>,
    );
    expect(screen.getByText("Trackers")).toBeInTheDocument();
    expect(screen.getByText("3 ativos")).toBeInTheDocument();
    expect(screen.getByText("on")).toBeInTheDocument();
    expect(screen.getByText("conteúdo")).toBeInTheDocument();
  });

  it("clickable vira role=button e dispara onClick", async () => {
    const onClick = vi.fn();
    render(
      <Card clickable onClick={onClick}>
        <CardBody>x</CardBody>
      </Card>,
    );
    await userEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("não é botão quando não-clickable", () => {
    render(
      <Card>
        <CardBody>x</CardBody>
      </Card>,
    );
    expect(screen.queryByRole("button")).toBeNull();
  });
});
