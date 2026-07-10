import type { HTMLAttributes, ReactNode } from "react";
import "./Card.css";

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Deixa o card clicável (hover/active + role/tab). Combine com onClick. */
  clickable?: boolean;
}

/** Contêiner de superfície do design system. */
export function Card({ clickable = false, className, children, ...rest }: CardProps) {
  const cls = ["ui-card", clickable && "ui-card--clickable", className]
    .filter(Boolean)
    .join(" ");
  const a11y = clickable ? { role: "button", tabIndex: 0 } : {};
  return (
    <div className={cls} {...a11y} {...rest}>
      {children}
    </div>
  );
}

export interface CardHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  /** Ícone/emoji à esquerda. */
  icon?: ReactNode;
  /** Slot à direita (ex.: um Badge de status). */
  trailing?: ReactNode;
}

export function CardHeader({ title, subtitle, icon, trailing }: CardHeaderProps) {
  return (
    <div className="ui-card__header">
      {icon != null && <div className="ui-card__icon">{icon}</div>}
      <div className="ui-card__heading">
        <p className="ui-card__title">{title}</p>
        {subtitle != null && <p className="ui-card__subtitle">{subtitle}</p>}
      </div>
      {trailing != null && <div className="ui-card__trailing">{trailing}</div>}
    </div>
  );
}

export function CardBody({ children, className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  const cls = ["ui-card__body", className].filter(Boolean).join(" ");
  return (
    <div className={cls} {...rest}>
      {children}
    </div>
  );
}
