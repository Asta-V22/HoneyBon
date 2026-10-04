import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { SubmissionRow } from "../components/SubmissionRow";
import { Card, ErrorText, PageHeader, SectionTitle } from "../components/ui";
import { api } from "../lib/api";
import { useListNavigation } from "../lib/hooks";

const dayKey = (d: Date) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
const timeFormat = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
const headingFormat = new Intl.DateTimeFormat(undefined, { weekday: "long", day: "numeric", month: "long" });
const dayLetter = new Intl.DateTimeFormat(undefined, { weekday: "narrow" });

export function TodayPage() {
  const { data, error } = useQuery({
    queryKey: ["submissions", "recent"],
    queryFn: () => api.submissions({ limit: 200 }),
  });
  const now = new Date();
  const items = data?.items ?? [];
  const today = items.filter((i) => dayKey(new Date(i.created_at)) === dayKey(now));
  const active = useListNavigation(today.map((i) => `/review/${i.id}`));

  // Momentum: the last seven days, oldest first. A missed day is just an empty dot.
  const activeDays = new Set(items.map((i) => dayKey(new Date(i.created_at))));
  const week = Array.from({ length: 7 }, (_, k) => {
    const d = new Date(now);
    d.setDate(now.getDate() - (6 - k));
    return { d, on: activeDays.has(dayKey(d)) };
  });
  const count = week.filter((w) => w.on).length;

  return (
    <div className="flex flex-col gap-7">
      <PageHeader eyebrow={headingFormat.format(now)} title="Today">
        <div className="flex items-center gap-3.5">
          <span className="text-xs text-text-muted">
            {count} of the last 7 days
          </span>
          <ol className="flex gap-1.5" aria-label="Last seven days">
            {week.map(({ d, on }) => (
              <li key={d.toISOString()} className="flex w-[18px] flex-col items-center gap-1.5">
                <span
                  aria-label={`${d.toDateString()}: ${on ? "practised" : "no submissions"}`}
                  className={`size-2 rounded-full ${on ? "bg-accent" : "border border-border-strong"}`}
                />
                <span className="text-[11px] text-text-faint" aria-hidden>
                  {dayLetter.format(d)}
                </span>
              </li>
            ))}
          </ol>
        </div>
      </PageHeader>

      <section className="flex flex-col gap-3">
        <SectionTitle aside={`${today.length} submission${today.length === 1 ? "" : "s"}`}>Today's activity</SectionTitle>
        <ErrorText error={error} />
        {today.length === 0 ? (
          <Card className="p-6 text-sm text-text-muted">
            Nothing yet today. <Link to="/paste" className="text-accent-text">Paste a solution</Link> to get a review.
          </Card>
        ) : (
          <Card className="overflow-hidden">
            {today.map((item, i) => (
              <SubmissionRow
                key={item.id}
                item={item}
                active={i === active}
                time={timeFormat.format(new Date(item.created_at))}
              />
            ))}
          </Card>
        )}
      </section>
    </div>
  );
}
