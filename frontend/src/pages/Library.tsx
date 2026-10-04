import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useDeferredValue, useState } from "react";

import { SubmissionRow } from "../components/SubmissionRow";
import { Card, ErrorText, inputClass, PageHeader } from "../components/ui";
import { api, techniqueLabel, TECHNIQUES } from "../lib/api";
import { useListNavigation } from "../lib/hooks";

const dateFormat = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" });

export function LibraryPage() {
  const [q, setQ] = useState("");
  const [technique, setTechnique] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [platform, setPlatform] = useState("");
  const [suboptimal, setSuboptimal] = useState(false);
  const search = useDeferredValue(q);

  const params = { q: search, technique, difficulty, platform, suboptimal, limit: 100 };
  const { data, error, isLoading } = useQuery({
    queryKey: ["submissions", params],
    queryFn: () => api.submissions(params),
    placeholderData: keepPreviousData,
  });
  const items = data?.items ?? [];
  const active = useListNavigation(items.map((i) => `/review/${i.id}`));

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Library" eyebrow={data ? `${data.total} submissions` : undefined} />
      <div className="flex flex-wrap gap-2">
        <label className="sr-only" htmlFor="lib-search">
          Search problems
        </label>
        <input
          id="lib-search"
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search problems"
          className={`${inputClass} flex-[1_1_220px]`}
        />
        <Select label="Technique" value={technique} onChange={setTechnique}>
          {TECHNIQUES.map((t) => (
            <option key={t} value={t}>
              {techniqueLabel(t)}
            </option>
          ))}
        </Select>
        <Select label="Difficulty" value={difficulty} onChange={setDifficulty}>
          <option value="Easy">Easy</option>
          <option value="Medium">Medium</option>
          <option value="Hard">Hard</option>
        </Select>
        <Select label="Platform" value={platform} onChange={setPlatform}>
          <option value="leetcode">LeetCode</option>
          <option value="codeforces">Codeforces</option>
          <option value="other">Other</option>
        </Select>
        <label className="flex min-h-9 items-center gap-2 rounded-lg border border-border-strong bg-raised px-3 text-sm text-text-secondary">
          <input type="checkbox" checked={suboptimal} onChange={(e) => setSuboptimal(e.target.checked)} />
          Solved suboptimally
        </label>
      </div>

      <ErrorText error={error} />
      {isLoading ? (
        <p className="text-text-muted">Loading…</p>
      ) : items.length === 0 ? (
        <Card className="p-6 text-sm text-text-muted">No submissions match.</Card>
      ) : (
        <Card className="overflow-hidden">
          {items.map((item, i) => (
            <SubmissionRow
              key={item.id}
              item={item}
              active={i === active}
              time={dateFormat.format(new Date(item.created_at))}
            />
          ))}
        </Card>
      )}
      {items.length > 0 && <p className="text-xs text-text-faint">j / k to move · Enter to open</p>}
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  children: React.ReactNode;
}) {
  return (
    <>
      <label className="sr-only" htmlFor={`lib-${label}`}>
        {label}
      </label>
      <select
        id={`lib-${label}`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`${inputClass} w-auto`}
      >
        <option value="">All {label.toLowerCase()}</option>
        {children}
      </select>
    </>
  );
}
