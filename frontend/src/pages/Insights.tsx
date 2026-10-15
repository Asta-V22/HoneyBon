import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { InsightCardView } from "../components/InsightCard";
import { FlowChart } from "../components/insights/FlowChart";
import { Heatmap } from "../components/insights/Heatmap";
import { ProgressChart } from "../components/insights/ProgressChart";
import { TechniqueBars } from "../components/insights/TechniqueBars";
import { useInsightsView, VIEWS, ViewSwitcher } from "../components/insights/ViewSwitcher";
import { Chip } from "../components/StatusChip";
import { Card, ErrorText, inputClass, PageHeader, SectionTitle } from "../components/ui";
import { api, techniqueLabel, type InsightItem, type Insights } from "../lib/api";
import { filterItems, monthLabel, OTHER, OUTCOME_LABELS, type Selection } from "../lib/insightViews";

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
          <Visual data={data} selection={selection} onSelect={setSelection} />
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

function Visual({ data, selection, onSelect }: { data: Insights; selection: Selection; onSelect: (s: Selection) => void }) {
  const [view, setView] = useInsightsView();
  const props = { items: data.items, selection, onSelect };
  return (
    <section className="flex flex-col gap-3" aria-labelledby="visual-h">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="visual-h" className="text-sm font-medium text-text-heading">
          {VIEWS.find((v) => v.id === view)!.hint}
        </h2>
        <ViewSwitcher
          view={view}
          onChange={(v) => {
            setView(v);
            onSelect("worse"); // a selection from another view would be hard to place
          }}
        />
      </div>
      {view === "bars" && <TechniqueBars {...props} />}
      {view === "flow" && <FlowChart {...props} />}
      {view === "heatmap" && <Heatmap data={data} selection={selection} onSelect={onSelect} />}
      {view === "progress" && <ProgressChart {...props} />}
    </section>
  );
}

function selectionTitle(s: Selection): string {
  if (s === "worse") return "Another technique, worse complexity";
  if (s === "low") return "Low confidence: the AI disagrees with LeetCode's tags";
  if (s.kind === "cell") return `${techniqueLabel(s.needed)} needed · ${techniqueLabel(s.used)} used`;
  if (s.kind === "bar") return `${techniqueLabel(s.needed)} needed · ${OUTCOME_LABELS[s.outcome].toLowerCase()}`;
  if (s.kind === "flow") {
    const [n, u] = s.label.split("|").slice(0, 2).map((id) => (id === OTHER ? "Other" : techniqueLabel(id)));
    return `${n} needed · ${u} used · ${OUTCOME_LABELS[s.outcome].toLowerCase()}`;
  }
  return s.key === "baseline" ? "Imported before Honeybon" : `Solved in ${monthLabel(s.key)}`;
}

function ProblemList({ items, selection }: { items: InsightItem[]; selection: Selection }) {
  const title = selectionTitle(selection);
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
