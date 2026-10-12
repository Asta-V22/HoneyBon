import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import { InsightCardView } from "../components/InsightCard";
import { SubmissionRow } from "../components/SubmissionRow";
import { Button, Card, ErrorText, PageHeader, SectionTitle } from "../components/ui";
import { api } from "../lib/api";
import { useListNavigation } from "../lib/hooks";

const dayKey = (d: Date) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
const timeFormat = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
const headingFormat = new Intl.DateTimeFormat(undefined, { weekday: "long", day: "numeric", month: "long" });
const dayLetter = new Intl.DateTimeFormat(undefined, { weekday: "narrow" });

export function TodayPage() {
  const { data, error } = useQuery({
    queryKey: ["submissions", "recent"],
    // Imports are past work, not today's practice.
    queryFn: () => api.submissions({ limit: 200, exclude_source: "import" }),
  });
  const { data: insights } = useQuery({ queryKey: ["insights", "today"], queryFn: () => api.insights({}) });
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

      {insights?.card && <InsightCardView card={insights.card} compact />}

      <div className="flex flex-wrap items-start gap-6">
      <section className="flex min-w-0 flex-[2_1_520px] flex-col gap-3">
        <SectionTitle aside={`${today.length} submission${today.length === 1 ? "" : "s"}`}>Today's activity</SectionTitle>
        <ErrorText error={error} />
        {today.length === 0 ? (
          <Card className="p-6 text-sm text-text-muted">
            Nothing yet today. <Link to="/paste" className="text-accent-text">Paste a solution</Link> to get a review
            {insights && insights.problems === 0 && (
              <>
                , or{" "}
                <Link to="/import" className="text-accent-text">
                  import your past solutions from GitHub
                </Link>
              </>
            )}
            .
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
      <ReviewQueue />
      </div>
    </div>
  );
}

const queuedFormat = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" });

/** Submissions captured in Capture mode, waiting for you to send them for review. */
function ReviewQueue() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { data } = useQuery({
    queryKey: ["submissions", "queue"],
    queryFn: () => api.submissions({ in_queue: true, limit: 50 }),
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ["submissions"] });
  const analyze = useMutation({
    mutationFn: (id: string) => api.requestReview(id, {}),
    onSuccess: (sub) => {
      refresh();
      navigate(`/review/${sub.id}`);
    },
  });
  const analyzeAll = useMutation({ mutationFn: api.analyzeAll, onSuccess: refresh });
  const items = data?.items ?? [];

  return (
    <section aria-labelledby="queue-h" className="flex min-w-0 flex-[1_1_300px] flex-col gap-3">
      <div className="flex items-center gap-2">
        <h2 id="queue-h" className="text-sm font-medium text-text-heading">
          Review queue
        </h2>
        <span className="text-xs text-text-faint">{data?.total ?? 0}</span>
        {items.length > 0 && (
          <Button
            variant="primary"
            className="ml-auto"
            onClick={() => analyzeAll.mutate()}
            disabled={analyzeAll.isPending}
          >
            Analyze all
          </Button>
        )}
      </div>
      {items.length === 0 ? (
        <Card className="p-4 text-sm text-text-muted">
          Empty. In Capture mode, accepted LeetCode submissions wait here until you analyze them.
        </Card>
      ) : (
        <Card className="overflow-hidden">
          {items.map((item) => (
            <div key={item.id} className="flex items-center gap-3 border-b border-divider px-3.5 py-3 last:border-b-0">
              <Link to={`/review/${item.id}`} className="min-w-0 flex-1 text-text no-underline">
                <div className="truncate font-medium">{item.problem.title ?? item.problem.slug}</div>
                <div className="text-[12.5px] text-text-muted">
                  {[item.problem.difficulty, `captured ${queuedFormat.format(new Date(item.created_at))}`]
                    .filter(Boolean)
                    .join(" · ")}
                </div>
              </Link>
              <Button onClick={() => analyze.mutate(item.id)} disabled={analyze.isPending}>
                Analyze
              </Button>
            </div>
          ))}
        </Card>
      )}
      {analyzeAll.data && analyzeAll.data.remaining > 0 && (
        <p className="text-xs text-text-muted">
          Started {analyzeAll.data.queued}; {analyzeAll.data.remaining} more left. Run Analyze all again for the rest.
        </p>
      )}
      <ErrorText error={analyze.error ?? analyzeAll.error} />
    </section>
  );
}
