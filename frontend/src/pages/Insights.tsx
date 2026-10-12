import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { InsightCardView } from "../components/InsightCard";
import { Chip } from "../components/StatusChip";
import { Card, ErrorText, inputClass, PageHeader, SectionTitle } from "../components/ui";
import { api, techniqueLabel, type InsightItem, type Insights } from "../lib/api";

type Selection = { needed: string; used: string } | "worse" | "low";

export function InsightsPage() {
  const [range, setRange] = useState("all");
  const [difficulty, setDifficulty] = useState("");
  const [platform, setPlatform] = useState("");
  const params = { range, difficulty, platform };
  const { data, error, isLoading } = useQuery({
    queryKey: ["insights", params],
    queryFn: () => api.insights(params),
    placeholderData: keepPreviousData,
  });
  const [selection, setSelection] = useState<Selection>("worse");

  return (
    <div className="flex flex-col gap-7">
      <PageHeader title="Insights" eyebrow={data ? `${data.problems} problems analysed` : undefined}>
        <Link to="/import" className="text-[13px] text-accent-text">
          Import from GitHub
        </Link>
      </PageHeader>

      <div className="flex flex-wrap gap-2" role="group" aria-label="Filters">
        <Select label="Time range" value={range} onChange={setRange} all="All time" allValue="all">
          <option value="1y">Last year</option>
          <option value="90d">Last 90 days</option>
          <option value="30d">Last 30 days</option>
        </Select>
        <Select label="Difficulty" value={difficulty} onChange={setDifficulty} all="All difficulties">
          <option value="Easy">Easy</option>
          <option value="Medium">Medium</option>
          <option value="Hard">Hard</option>
        </Select>
        <Select label="Platform" value={platform} onChange={setPlatform} all="All platforms">
          <option value="leetcode">LeetCode</option>
          <option value="codeforces">Codeforces</option>
          <option value="other">Other</option>
        </Select>
      </div>

      <ErrorText error={error} />
      {isLoading ? (
        <p className="text-text-muted">Loading…</p>
      ) : !data || data.problems === 0 ? (
        <Card className="flex flex-col gap-2 p-6 text-sm text-text-muted">
          <p>Nothing analysed yet{range !== "all" || difficulty || platform ? " for these filters" : ""}.</p>
          <p>
            <Link to="/import" className="text-accent-text">
              Import your past solutions from GitHub
            </Link>{" "}
            to fill this page in one go, or <Link to="/paste" className="text-accent-text">paste a solution</Link>.
          </p>
        </Card>
      ) : (
        <>
          {data.card ? (
            <InsightCardView card={data.card} />
          ) : (
            <Card className="p-4 text-sm text-text-muted">
              No pattern yet: the insight card waits until one rests on at least {data.min_problems} problems.
            </Card>
          )}
          <Stats data={data} onSelect={setSelection} />
          <Matrix data={data} selection={selection} onSelect={setSelection} />
          <ProblemList items={filterItems(data.items, selection)} selection={selection} />
        </>
      )}
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  all,
  allValue = "",
  children,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  all: string;
  allValue?: string;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col">
      <span className="sr-only">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} className={`${inputClass} w-auto py-1.5`}>
        <option value={allValue}>{all}</option>
        {children}
      </select>
    </label>
  );
}

const pct = (n: number, d: number) => (d ? `${Math.round((n / d) * 100)}%` : "—");

function Stats({ data, onSelect }: { data: Insights; onSelect: (s: Selection) => void }) {
  const tiles = [
    { label: "Matched the optimal technique", value: pct(data.matched, data.problems), note: `${data.matched} of ${data.problems}` },
    { label: "Another technique, same complexity", value: String(data.style_mismatches), note: "a style choice" },
    {
      label: "Another technique, worse complexity",
      value: String(data.worse_mismatches),
      note: "the real weaknesses",
      attention: data.worse_mismatches > 0,
      select: "worse" as const,
    },
    {
      label: "AI disagrees with LeetCode's tags",
      value: pct(data.disagreements, data.checked),
      note: `${data.disagreements} of ${data.checked} checked · low confidence`,
      select: "low" as const,
    },
  ];
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-3">
      {tiles.map((t) => {
        const body = (
          <>
            <span className="text-xs text-text-muted">{t.label}</span>
            <span className={`text-2xl font-semibold tracking-tight ${t.attention ? "text-attention-text" : "text-text"}`}>
              {t.value}
            </span>
            <span className="text-xs text-text-faint">{t.note}</span>
          </>
        );
        return t.select ? (
          <button
            key={t.label}
            type="button"
            onClick={() => onSelect(t.select)}
            className="flex flex-col gap-1 rounded-xl border border-border bg-surface p-4 text-left hover:bg-raised"
          >
            {body}
          </button>
        ) : (
          <div key={t.label} className="flex flex-col gap-1 rounded-xl border border-border bg-surface p-4">
            {body}
          </div>
        );
      })}
    </div>
  );
}

/** Rows: the technique the problem needed. Columns: the one you used. The diagonal is a match. */
function Matrix({ data, selection, onSelect }: { data: Insights; selection: Selection; onSelect: (s: Selection) => void }) {
  const cells = new Map(data.cells.map((c) => [`${c.needed}|${c.used}`, c]));
  const max = Math.max(1, ...data.cells.map((c) => c.count));
  const isSelected = (n: string, u: string) => typeof selection === "object" && selection.needed === n && selection.used === u;

  return (
    <section className="flex flex-col gap-3" aria-labelledby="matrix-h">
      <SectionTitle aside="Click a cell to list its problems">
        <span id="matrix-h">Approach-avoidance matrix</span>
      </SectionTitle>
      <Card className="overflow-x-auto p-3">
        <table className="border-separate border-spacing-0.5 text-xs">
          <caption className="sr-only">
            Rows are the technique each problem needed, columns the technique you used; cells count problems.
          </caption>
          <thead>
            <tr>
              <th scope="col" className="p-1.5 text-left align-bottom font-normal text-text-faint">
                needed ↓ · used →
              </th>
              {data.used.map((u) => (
                <th key={u} scope="col" className="h-28 w-10 p-1 align-bottom font-normal text-text-muted">
                  <span className="inline-block origin-bottom-left translate-x-3 -rotate-45 whitespace-nowrap">
                    {techniqueLabel(u)}
                  </span>
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
                  if (!c) return <td key={u} className="size-10 rounded-md bg-raised" />;
                  const match = n === u;
                  // One-hue sequential scale for the count; orange marks worse complexity.
                  const strength = 0.12 + 0.6 * (c.count / max);
                  const tip = `${techniqueLabel(n)} needed, ${techniqueLabel(u)} used: ${c.count} problem${c.count === 1 ? "" : "s"}${
                    c.worse ? `, ${c.worse} with worse complexity` : ""
                  }${match ? " (match)" : ""}`;
                  return (
                    <td key={u} className="p-0">
                      <button
                        type="button"
                        title={tip}
                        aria-label={tip}
                        aria-pressed={isSelected(n, u)}
                        onClick={() => onSelect({ needed: n, used: u })}
                        className={`relative flex size-10 items-center justify-center rounded-md font-mono text-text ${
                          isSelected(n, u) ? "outline-2 outline-offset-1 outline-accent" : ""
                        } ${!match && c.worse ? "ring-1 ring-attention ring-inset" : ""}`}
                        style={{ backgroundColor: `color-mix(in srgb, var(--accent) ${Math.round(strength * 100)}%, transparent)` }}
                      >
                        {c.count}
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
      </Card>
      <p className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">
        <span>Darker = more problems</span>
        <span>Diagonal = you used the optimal technique</span>
        <span>
          <span className="text-attention-text">!</span> orange outline = a worse time or space complexity
        </span>
      </p>
    </section>
  );
}

function filterItems(items: InsightItem[], s: Selection): InsightItem[] {
  if (s === "worse") return items.filter((i) => !i.match && i.worse);
  if (s === "low") return items.filter((i) => i.low_confidence);
  return items.filter((i) => i.needed === s.needed && i.used === s.used);
}

function ProblemList({ items, selection }: { items: InsightItem[]; selection: Selection }) {
  const title =
    selection === "worse"
      ? "Another technique, worse complexity"
      : selection === "low"
        ? "Low confidence: the AI disagrees with LeetCode's tags"
        : `${techniqueLabel(selection.needed)} needed · ${techniqueLabel(selection.used)} used`;
  return (
    <section className="flex flex-col gap-3">
      <SectionTitle aside={`${items.length} problem${items.length === 1 ? "" : "s"}`}>{title}</SectionTitle>
      {items.length === 0 ? (
        <Card className="p-4 text-sm text-text-muted">None.</Card>
      ) : (
        <Card className="overflow-hidden">
          {items.map((i) => (
            <Link
              key={i.submission_id}
              to={`/review/${i.submission_id}`}
              className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-divider px-4 py-3 text-text no-underline last:border-b-0 hover:bg-raised"
            >
              <span className="min-w-0 flex-[1_1_200px] truncate font-medium">{i.title}</span>
              {i.difficulty && <span className="text-xs text-text-muted">{i.difficulty}</span>}
              {i.match ? (
                <Chip>{techniqueLabel(i.used)} · match</Chip>
              ) : (
                <Chip attention={i.worse}>
                  {techniqueLabel(i.used)} → {i.optimal.map(techniqueLabel).join(" / ")}
                </Chip>
              )}
              {i.low_confidence && <Chip>low confidence</Chip>}
            </Link>
          ))}
        </Card>
      )}
    </section>
  );
}
