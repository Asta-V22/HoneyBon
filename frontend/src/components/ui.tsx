import type { ButtonHTMLAttributes, ReactNode } from "react";

export function PageHeader({ eyebrow, title, children }: { eyebrow?: string; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <p className="text-[13px] text-text-muted">{eyebrow}</p>}
        <h1 className="mt-0.5 text-[26px] font-semibold tracking-tight">{title}</h1>
      </div>
      {children}
    </div>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-border bg-surface ${className}`}>{children}</div>;
}

export function SectionTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="flex items-baseline gap-2">
      <h2 className="text-sm font-medium text-text-heading">{children}</h2>
      {aside && <span className="text-xs text-text-faint">{aside}</span>}
    </div>
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" };

export function Button({ variant = "secondary", className = "", ...props }: ButtonProps) {
  const styles = {
    primary: "border-transparent bg-accent text-on-accent font-medium hover:opacity-90",
    secondary: "border-border-strong bg-chip text-text hover:bg-selected",
    danger: "border-attention/40 bg-attention-soft text-attention-text hover:opacity-90",
  }[variant];
  return (
    <button
      type="button"
      {...props}
      className={`inline-flex min-h-8 items-center justify-center gap-1.5 rounded-lg border px-3 text-[13px] disabled:cursor-not-allowed disabled:opacity-50 ${styles} ${className}`}
    />
  );
}

export const inputClass =
  "w-full rounded-lg border border-border-strong bg-raised px-3 py-2 text-sm text-text placeholder:text-text-faint focus:border-accent focus:outline-none";

export function Field({ label, hint, children, htmlFor }: { label: string; hint?: string; children: ReactNode; htmlFor: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-[13px] font-medium text-text-secondary">
        {label}
      </label>
      {children}
      {hint && <p className="text-xs text-text-muted">{hint}</p>}
    </div>
  );
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p role="alert" className="text-sm text-attention-text">
      {error instanceof Error ? error.message : String(error)}
    </p>
  );
}
