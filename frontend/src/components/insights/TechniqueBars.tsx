import { techniqueLabel, type InsightItem } from "../../lib/api";
import { OUTCOME_LABELS, techniqueBars, type Outcome, type Selection } from "../../lib/insightViews";
import { Card } from "../ui";
import { Legend, OUTCOME_FILL } from "./Legend";

const OUTCOMES: Outcome[] = ["match", "same", "worse"];

/** One 100% bar per needed technique, the most avoided at the top. */
export function TechniqueBars({
  items,
  selection,
  onSelect,
}: {
  items: InsightItem[];
  selection: Selection;
  onSelect: (s: Selection) => void;
}) {
  const bars = techniqueBars(items);
  const isSelected = (needed: string, outcome: Outcome) =>
    typeof selection === "object" && selection.kind === "bar" && selection.needed === needed && selection.outcome === outcome;

  return (
    <Card className="flex flex-col gap-4 p-4">
      <Legend />
      <ul className="flex flex-col gap-3.5">
        {bars.map((bar) => (
          <li key={bar.needed} className="grid gap-x-4 gap-y-1.5 sm:grid-cols-[minmax(150px,220px)_1fr] sm:items-center">
            <div className="flex min-w-0 flex-col">
              <span className="truncate text-sm text-text">{techniqueLabel(bar.needed)}</span>
              <span className="text-xs text-text-muted">
                used in {bar.match} of {bar.total}
                {bar.usualInstead && bar.match < bar.total && <> · usually {techniqueLabel(bar.usualInstead)} instead</>}
              </span>
            </div>
            <div className="flex h-5 gap-0.5" role="group" aria-label={`${techniqueLabel(bar.needed)}: ${bar.total} problems`}>
              {OUTCOMES.filter((o) => bar[o] > 0).map((o) => {
                const tip = `${techniqueLabel(bar.needed)} needed · ${OUTCOME_LABELS[o].toLowerCase()}: ${bar[o]} of ${bar.total}`;
                return (
                  <button
                    key={o}
                    type="button"
                    title={tip}
                    aria-label={tip}
                    aria-pressed={isSelected(bar.needed, o)}
                    onClick={() => onSelect({ kind: "bar", needed: bar.needed, outcome: o })}
                    style={{ flexGrow: bar[o], flexBasis: 0 }}
                    className={`min-w-1.5 rounded-[4px] ${OUTCOME_FILL[o]} hover:opacity-85 ${
                      isSelected(bar.needed, o) ? "outline-2 outline-offset-2 outline-text" : ""
                    }`}
                  />
                );
              })}
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
