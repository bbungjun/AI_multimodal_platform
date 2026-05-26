import type { ButtonHTMLAttributes, ReactNode } from "react";

type Tone = "default" | "info" | "success" | "warning" | "danger" | "muted";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
  children: ReactNode;
};

export function Button({
  children,
  className = "",
  variant = "secondary",
  ...props
}: ButtonProps) {
  return (
    <button className={`button button--${variant} ${className}`.trim()} {...props}>
      {children}
    </button>
  );
}

export function Panel({
  children,
  className = "",
  title,
  eyebrow,
}: {
  children: ReactNode;
  className?: string;
  title?: string;
  eyebrow?: string;
}) {
  return (
    <section className={`panel ${className}`.trim()}>
      {(title || eyebrow) && (
        <header className="panel__header">
          {eyebrow && <div className="section-label">{eyebrow}</div>}
          {title && <h2>{title}</h2>}
        </header>
      )}
      <div className="panel__body">{children}</div>
    </section>
  );
}

export function Badge({
  children,
  tone = "default",
}: {
  children: ReactNode;
  tone?: Tone;
}) {
  return <span className={`badge badge--${tone}`}>{children}</span>;
}

export function StatusDot({ tone = "default" }: { tone?: Tone | "pending" }) {
  return <span className={`status-dot status-dot--${tone}`} />;
}

export function RoutePlaceholder({
  children,
  title,
  eyebrow,
}: {
  children: ReactNode;
  title: string;
  eyebrow: string;
}) {
  return (
    <div className="route-placeholder">
      <div className="route-placeholder__copy">
        <div className="section-label">{eyebrow}</div>
        <h2>{title}</h2>
        <p>{children}</p>
      </div>
    </div>
  );
}
