import { useState } from "react";

import type { InsightItem } from "../../lib/api";
import { monthlyProgress, type ProgressPoint, type Selection } from "../../lib/insightViews";
import { Card } from "../ui";
import { OUTCOME_FILL, OUTCOME_STROKE } from "./Legend";

const W = 880;
const H = 220;
const PAD = { top: 16, right: 24, bottom: 30, left: 40 };
const pct = (v: number) => `${Math.round(v * 100)}%`;

/** Share of problems solved with the optimal technique (and with a worse complexity), per month. */
export function ProgressChart({
  items,
  selection,
  onSelect,
}: {
  items: InsightItem[];
  selection: Selection;
  onSelect: (s: Selection) => void;
}) {
  const { baseline, months } = monthlyProgress(items);
  const points = [...(baseline ? [baseline] : []), ...months];
  const [hover, setHover] = useState<ProgressPoint | null>(null);

  if (points.length < 2) {
    return (
      <Card className="flex flex-col gap-2 p-5 text-sm text-text-muted">
        <p>Progress needs problems from at least two different months.</p>
        <p>
          {baseline
            ? `Your ${baseline.total} imported problems are the starting point (you used the optimal technique in ${pct(baseline.matchRate)}). `
            : ""}
          Problems you solve from now on, captured by the extension or pasted, add a point for each month.
        </p>
      </Card>
    );
  }

  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const step = plotW / (points.length - 1);
  const x = (i: number) => PAD.left + i * step;
  const y = (v: number) => PAD.top + (1 - v) * plotH;
  const line = (key: "matchRate" | "worseRate", from: number) =>
    points
      .slice(from)
      .map((p, i) => `${i ? "L" : "M"}${x(i + from)},${y(p[key])}`)
      .join(" ");
  // The baseline isn't a month: it's drawn apart, joined to the first month by a dotted segment.
  const first = baseline ? 1 : 0;
  const isSelected = (p: ProgressPoint) => typeof selection === "object" && selection.kind === "month" && selection.key === p.key;
  const shown = hover ?? points[points.length - 1];

  return (
    <Card className="flex flex-col gap-3 p-4">
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted" aria-label="Legend">
        <li className="flex items-center gap-1.5">
          <span className={`h-0.5 w-4 rounded ${OUTCOME_FILL.match}`} aria-hidden />
          Used the optimal technique
        </li>
        <li className="flex items-center gap-1.5">
          <span className={`h-0.5 w-4 rounded ${OUTCOME_FILL.worse}`} aria-hidden />
          Another technique, worse complexity
        </li>
      </ul>
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} width={W} className="mx-auto block h-auto max-w-full min-w-[480px]" role="img" aria-label="Monthly share of problems solved with the optimal technique" onMouseLeave={() => setHover(null)}>
          {[0, 0.5, 1].map((v) => (
            <g key={v}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y(v)} y2={y(v)} stroke="var(--divider)" />
              <text x={PAD.left - 8} y={y(v)} dy="0.35em" textAnchor="end" className="fill-text-faint text-[11px]">
                {pct(v)}
              </text>
            </g>
          ))}
          {baseline && <line x1={x(0) + step / 2} x2={x(0) + step / 2} y1={PAD.top} y2={H - PAD.bottom} stroke="var(--border-strong)" strokeDasharray="3 4" />}
          {(["matchRate", "worseRate"] as const).map((key) => {
            const color = key === "matchRate" ? OUTCOME_STROKE.match : OUTCOME_STROKE.worse;
            return (
              <g key={key} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                {baseline && <path d={line(key, 0).split(" ").slice(0, 2).join(" ")} strokeDasharray="2 5" />}
                <path d={line(key, first)} />
              </g>
            );
          })}
          {points.map((p, i) => (
            <g key={p.key}>
              {hover === p && <line x1={x(i)} x2={x(i)} y1={PAD.top} y2={H - PAD.bottom} stroke="var(--border-strong)" />}
              {(["matchRate", "worseRate"] as const).map((key) => (
                <circle
                  key={key}
                  cx={x(i)}
                  cy={y(p[key])}
                  r={isSelected(p) || hover === p ? 5 : 4}
                  fill={key === "matchRate" ? OUTCOME_STROKE.match : OUTCOME_STROKE.worse}
                  stroke="var(--surface)"
                  strokeWidth={2}
                />
              ))}
              <text x={x(i)} y={H - 10} textAnchor="middle" className={`text-[11px] ${isSelected(p) ? "fill-text" : "fill-text-muted"}`}>
                {p.key === "baseline" ? "Before" : p.label}
              </text>
              {/* Hit target: the whole column, wider than the marks. */}
              <rect
                x={x(i) - step / 2}
                y={0}
                width={step}
                height={H}
                fill="transparent"
                className="cursor-pointer"
                onMouseEnter={() => setHover(p)}
                onClick={() => onSelect({ kind: "month", key: p.key })}
              >
                <title>{describe(p)}</title>
              </rect>
            </g>
          ))}
        </svg>
      </div>
      <p className="min-h-5 text-xs text-text-muted" aria-live="polite">
        {describe(shown)} · click a month to list its problems
      </p>
      <table className="sr-only">
        <caption>Monthly progress</caption>
        <thead>
          <tr>
            <th>Period</th>
            <th>Problems</th>
            <th>Used the optimal technique</th>
            <th>Worse complexity</th>
          </tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={p.key}>
              <td>{p.label}</td>
              <td>{p.total}</td>
              <td>{pct(p.matchRate)}</td>
              <td>{pct(p.worseRate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function describe(p: ProgressPoint) {
  return `${p.label}: ${p.total} problem${p.total === 1 ? "" : "s"}, optimal technique in ${pct(p.matchRate)}, worse complexity in ${pct(p.worseRate)}`;
}
