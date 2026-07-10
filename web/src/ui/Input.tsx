import { forwardRef, useId } from "react";
import type { InputHTMLAttributes, ReactNode } from "react";
import "./Input.css";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
}

/** Campo de entrada do design system. */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { invalid = false, className, ...rest },
  ref,
) {
  const cls = ["ui-input", invalid && "ui-input--invalid", className]
    .filter(Boolean)
    .join(" ");
  return <input ref={ref} className={cls} aria-invalid={invalid || undefined} {...rest} />;
});

export interface FieldProps {
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  /** id do controle; se ausente, um é gerado e ligado ao label. */
  htmlFor?: string;
  children: (ids: { id: string; describedBy?: string }) => ReactNode;
}

/** Rótulo + controle + hint/erro. `children` recebe os ids p/ acessibilidade. */
export function Field({ label, hint, error, htmlFor, children }: FieldProps) {
  const auto = useId();
  const id = htmlFor ?? auto;
  const msgId = error || hint ? `${id}-msg` : undefined;
  return (
    <div className="ui-field">
      <label className="ui-field__label" htmlFor={id}>
        {label}
      </label>
      {children({ id, describedBy: msgId })}
      {error != null ? (
        <span className="ui-field__error" id={msgId}>
          {error}
        </span>
      ) : hint != null ? (
        <span className="ui-field__hint" id={msgId}>
          {hint}
        </span>
      ) : null}
    </div>
  );
}
