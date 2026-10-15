import { techniqueLabel, type Insights } from "../../lib/api";
import type { Selection } from "../../lib/insightViews";
import { Card } from "../ui";

/**
 * Rows: the technique the problem needed. Columns: the one you used. The diagonal is a match.
 * Shade = the cell's share of its row, so a rarely needed technique still reads clearly.
 */
export function Heatmap({ data, selection, onSelect }: { data: Insights; selection: Selection; onSelect: (s: Selection) => void }) {
  const cells = new Map(data.cells.map((c) => [`${c.needed}|${c.used}`, c]));
  const rowTotals = new Map<string, number>();
  for (const c of data.cells) rowTotals.set(c.needed, (rowTotals.get(c.needed) ?? 0) + c.count);
  const isSelected = (n: string, u: string) =>
    typeof selection === "object" && selection.kind === "cell" && selection.needed === n && selection.used === u;

  return (
    <Card className="flex flex-col gap-3 p-3">
      <div className="overflow-x-auto">
        <table className="border-separate border-spacing-0.5 text-xs">
          <caption className="sr-only">
            Rows are the technique each problem needed, columns the technique you used; cells count problems.
          </caption>
          <thead>
            <tr>
              <th scope="col" className="p-1.5 text-left align-bottom text-[11px] font-normal text-text-faint">
                needed ↓ · used →
              </th>
              {data.used.map((u) => (
                <th key={u} scope="col" title={techniqueLabel(u)} className="w-16 p-1 align-bottom text-[11px] leading-tight font-normal break-words text-text-muted">
                  {techniqueLabel(u)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.needed.map((n) => (
              <tr key={n}>
                <th scope="row" className="p-1.5 pr-3 text-left font-normal whitespace-nowrap text-text-secondary">
                  {techniqueLabel(n)}
                </th>
                {data.used.map((u) => {
                  const c = cells.get(`${n}|${u}`);
                  const match = n === u;
                  if (!c) {
                    return <td key={u} className={`h-10 w-16 rounded-md bg-raised ${match ? "outline-1 -outline-offset-1 outline-dashed outline-border-strong" : ""}`} />;
                  }
                  const share = c.count / (rowTotals.get(n) || 1);
                  const pct = Math.round(share * 100);
                  const tip = `${techniqueLabel(n)} needed, ${techniqueLabel(u)} used: ${c.count} problem${c.count === 1 ? "" : "s"} (${pct}% of ${techniqueLabel(n)})${
                    c.worse ? `, ${c.worse} with worse complexity` : ""
                  }${match ? " · match" : ""}`;
                  return (
                    <td key={u} className="p-0">
                      <button
                        type="button"
                        title={tip}
                        aria-label={tip}
                        aria-pressed={isSelected(n, u)}
                        onClick={() => onSelect({ kind: "cell", needed: n, used: u })}
                        className={`relative flex h-10 w-16 flex-col items-center justify-center rounded-md font-mono leading-none text-text ${
                          isSelected(n, u) ? "outline-2 outline-offset-1 outline-text" : match ? "outline-1 -outline-offset-1 outline-accent" : ""
                        } ${!match && c.worse ? "ring-1 ring-attention ring-inset" : ""}`}
                        style={{ backgroundColor: `color-mix(in srgb, var(--accent) ${Math.round((0.1 + 0.6 * share) * 100)}%, transparent)` }}
                      >
                        <span className="text-[13px]">{c.count}</span>
                        <span className="text-[10px] text-text opacity-75">{pct}%</span>
                        {!match && c.worse > 0 && (
                          <span className="absolute top-0.5 right-1 text-[10px] text-attention-text" aria-hidden>
                            !
                          </span>
                        )}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">
        <span>Darker = a bigger share of that row</span>
        <span>Outlined diagonal = you used the needed technique</span>
        <span>
          <span className="text-attention-text">!</span> orange outline = a worse time or space complexity
        </span>
      </p>
    </Card>
  );
}
