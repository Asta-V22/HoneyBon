import type { SubmissionStatus } from "../lib/api";

const LABELS: Record<SubmissionStatus, string> = {
  queued: "Queued",
  analyzing: "Analyzing",
  reviewed: "Reviewed",
  failed: "Failed",
};

export function StatusChip({ status, detail }: { status: SubmissionStatus; detail?: string }) {
  const tone =
    status === "analyzing"
      ? "border-accent/30 bg-accent-soft text-accent-text"
      : status === "failed"
        ? "border-attention/30 bg-attention-soft text-attention-text"
        : "border-border-strong bg-chip text-text-secondary";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs whitespace-nowrap ${tone}`}
    >
      {status === "analyzing" && <span className="size-1.5 animate-pulse rounded-full bg-accent" aria-hidden />}
      {LABELS[status]}
      {detail && ` · ${detail}`}
    </span>
  );
}

export function Chip({ children, attention = false }: { children: React.ReactNode; attention?: boolean }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs whitespace-nowrap ${
        attention
          ? "border-attention/30 bg-attention-soft text-attention-text"
          : "border-border-strong bg-chip text-text-secondary"
      }`}
    >
      {children}
    </span>
  );
}
