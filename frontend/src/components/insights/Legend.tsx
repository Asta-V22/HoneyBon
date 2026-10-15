import { OUTCOME_LABELS, type Outcome } from "../../lib/insightViews";

/** Fills for HTML marks and SVG marks; the colours come from the theme tokens in index.css. */
export const OUTCOME_FILL: Record<Outcome, string> = {
  match: "bg-accent",
  same: "bg-neutral-mark",
  worse: "bg-attention",
};

export const OUTCOME_STROKE: Record<Outcome, string> = {
  match: "var(--accent)",
  same: "var(--neutral-mark)",
  worse: "var(--attention)",
};

/** The three outcomes every view colours by. */
export function Legend() {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted" aria-label="Legend">
      {(Object.keys(OUTCOME_FILL) as Outcome[]).map((o) => (
        <li key={o} className="flex items-center gap-1.5">
          <span className={`size-2.5 rounded-[3px] ${OUTCOME_FILL[o]}`} aria-hidden />
          {OUTCOME_LABELS[o]}
        </li>
      ))}
    </ul>
  );
}
