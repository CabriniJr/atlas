import type { HTMLAttributes } from "react";
import "./Badge.css";

export type BadgeVariant =
  | "neutral"
  | "accent"
  | "success"
  | "warning"
  | "danger"
  | "info";

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  /** Mostra o pontinho de status na cor corrente. */
  dot?: boolean;
}

/** Etiqueta de status/rótulo do design system. */
export function Badge({
  variant = "neutral",
  dot = false,
  className,
  children,
  ...rest
}: BadgeProps) {
  const cls = ["ui-badge", `ui-badge--${variant}`, className].filter(Boolean).join(" ");
  return (
    <span className={cls} {...rest}>
      {dot && <span className="ui-badge__dot" aria-hidden="true" />}
      {children}
    </span>
  );
}
