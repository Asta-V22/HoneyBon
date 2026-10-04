import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";

import { CodeView, DiffView } from "../components/Code";
import { DiscussionPanel } from "../components/DiscussionPanel";
import { ModelPicker } from "../components/ModelPicker";
import { Prose } from "../components/Prose";
import { Chip, StatusChip } from "../components/StatusChip";
import { Button, Card, ErrorText, inputClass } from "../components/ui";
import { api, PROVIDER_LABELS, techniqueLabel, type Complexity, type ReviewJson, type Submission } from "../lib/api";
import { useMe } from "../lib/hooks";

function useLiveSubmission(id: string) {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["submission", id], queryFn: () => api.submission(id) });
  const running = query.data?.status === "queued" || query.data?.status === "analyzing";

  useEffect(() => {
    if (!running) return;
    const source = new EventSource(`/api/submissions/${id}/events`);
    const refresh = () => qc.invalidateQueries({ queryKey: ["submission", id] });
    source.addEventListener("ready", refresh);
    source.onmessage = (e) => {
      refresh();
      const type = JSON.parse(e.data).type;
      if (type === "done" || type === "failed") {
        source.close();
        qc.invalidateQueries({ queryKey: ["submissions"] });
      }
    };
    return () => source.close();
  }, [id, running, qc]);

  return query;
}

const REVEAL_KEY = "hb:revealed";

function useRevealed(id: string): [boolean, () => void] {
  const [revealed, setRevealed] = useState(() => {
    try {
      return (JSON.parse(localStorage.getItem(REVEAL_KEY) ?? "[]") as string[]).includes(id);
    } catch {
      return false;
    }
  });
  const reveal = () => {
    setRevealed(true);
    try {
      const ids = JSON.parse(localStorage.getItem(REVEAL_KEY) ?? "[]") as string[];
      localStorage.setItem(REVEAL_KEY, JSON.stringify([...ids.slice(-500), id]));
    } catch {
      /* storage unavailable: reveal for this visit only */
    }
  };
  return [revealed, reveal];
}

export function ReviewPage() {
  const { submissionId = "" } = useParams();
  const { data: sub, error, isLoading } = useLiveSubmission(submissionId);
  const [revealed, reveal] = useRevealed(submissionId);
  const { data: me } = useMe();
  const [discussOpen, setDiscussOpen] = useState(false);
  const [quote, setQuote] = useState("");
  const [focusKey, setFocusKey] = useState(0);
  const bodyRef = useRef<HTMLDivElement>(null);
  const selection = useSelectionIn(bodyRef);

  const askAbout = (text: string) => {
    setQuote(text);
    setDiscussOpen(true);
    setFocusKey((k) => k + 1);
    window.getSelection()?.removeAllRanges();
  };

  if (isLoading) return <p className="text-text-muted">Loading…</p>;
  if (error || !sub) return <ErrorText error={error ?? "Not found"} />;

  const review = sub.review;
  const json = review?.review_json ?? null;
  const running = sub.status === "queued" || sub.status === "analyzing";
  const problem = sub.problem;

  const content = (
    <div className="flex min-w-0 flex-col gap-6">
      <header className="flex flex-col gap-3">
        <Link to="/library" className="text-[13px] text-text-muted no-underline hover:text-text">
          ← Library
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-[26px] font-semibold tracking-tight">{problem.title ?? problem.slug}</h1>
          <StatusChip status={sub.status} detail={running ? progressDetail(json) : undefined} />
          <Button
            className="ml-auto"
            aria-pressed={discussOpen}
            onClick={() => {
              setDiscussOpen((o) => !o);
              setFocusKey((k) => k + 1);
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z" />
            </svg>
            {discussOpen ? "Close discussion" : "Discuss"}
          </Button>
        </div>
        <p className="text-[13px] text-text-muted">
          {[problem.difficulty, sub.language, platformLabel(problem.platform)].filter(Boolean).join(" · ")}
          {problem.url && (
            <>
              {" · "}
              <a href={problem.url} target="_blank" rel="noreferrer noopener" className="text-accent-text">
                Open problem
              </a>
            </>
          )}
        </p>
      </header>

      {sub.status === "failed" && review?.error && <FailedBanner sub={sub} />}
      {json && <VerdictCard verdict={json.verdict} />}

      <div ref={bodyRef} className={`grid gap-6 ${discussOpen ? "" : "lg:grid-cols-2"}`}>
        <section aria-labelledby="your-code" className="flex min-w-0 flex-col gap-3">
          <h2 id="your-code" className="text-sm font-medium text-text-heading">
            Your code
          </h2>
          <Card className="overflow-hidden">
            <CodeView code={sub.code} language={sub.language} label="Your submitted code" />
          </Card>
        </section>

        <div className="flex min-w-0 flex-col gap-6">
          {json?.tier1 ? (
            <Tier n={1} title="Your code, improved">
              <Prose className="text-text-secondary">{json.tier1.summary}</Prose>
              <Card className="overflow-hidden">
                <DiffView
                  original={sub.code}
                  modified={json.tier1.code}
                  language={sub.language}
                  label="Diff of your code against the improved version"
                />
              </Card>
              {json.tier1.line_comments.length > 0 && (
                <ul className="flex flex-col gap-1.5 text-[13px]">
                  {json.tier1.line_comments.map((c) => (
                    <li key={`${c.line}-${c.comment}`} className="flex gap-3">
                      <span className="w-10 shrink-0 font-mono text-xs leading-5 text-text-faint">L{c.line}</span>
                      <span className="text-text-secondary">{c.comment}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Tier>
          ) : running ? (
            <Pending>Reading your code…</Pending>
          ) : null}

          {json && (json.tier4 ? (
            revealed ? (
              <LaterTiers json={json} language={sub.language} />
            ) : (
              <Card className="flex flex-col items-start gap-3 p-5">
                <p className="text-sm text-text-secondary">
                  {json.verdict.is_optimal
                    ? "Your solution is already optimal. The contest-style take is ready."
                    : "Tiers 2–4 show a better approach, the optimal one, and a contest-style take."}{" "}
                  Try improving it yourself first.
                </p>
                <Button variant="primary" onClick={reveal}>
                  Reveal tiers {json.verdict.is_optimal ? "4" : "2–4"}
                </Button>
              </Card>
            )
          ) : running ? (
            <Pending>Writing tiers 2–4…</Pending>
          ) : null)}
        </div>
      </div>

      {review && <ReviewFooter sub={sub} />}
    </div>
  );

  return (
    <>
      {discussOpen && me ? (
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_400px]">
          {content}
          <DiscussionPanel
            sub={sub}
            me={me}
            quote={quote}
            onQuoteChange={setQuote}
            onClose={() => setDiscussOpen(false)}
            focusKey={focusKey}
          />
        </div>
      ) : (
        content
      )}
      {selection && (
        <button
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => askAbout(selection.text)}
          style={{ top: selection.top, left: selection.left }}
          className="fixed z-40 rounded-lg border border-border-strong bg-raised px-2.5 py-1 text-xs text-text shadow-lg hover:bg-selected"
        >
          Ask about selection
        </button>
      )}
    </>
  );
}

/** Tracks a non-empty text selection inside `ref`, positioned for a floating button. */
function useSelectionIn(ref: React.RefObject<HTMLElement | null>) {
  const [selection, setSelection] = useState<{ text: string; top: number; left: number } | null>(null);
  useEffect(() => {
    const update = () => {
      const s = window.getSelection();
      const text = s?.toString().trim() ?? "";
      if (!s || !text || s.rangeCount === 0 || !ref.current?.contains(s.anchorNode)) {
        setSelection(null);
        return;
      }
      const rect = s.getRangeAt(0).getBoundingClientRect();
      setSelection({
        text: text.slice(0, 8000),
        top: Math.min(rect.bottom + 6, window.innerHeight - 40),
        left: Math.max(8, Math.min(rect.left, window.innerWidth - 170)),
      });
    };
    const clearIfEmpty = () => {
      if (!window.getSelection()?.toString().trim()) setSelection(null);
    };
    const hide = () => setSelection(null);
    document.addEventListener("mouseup", update);
    document.addEventListener("keyup", update);
    document.addEventListener("selectionchange", clearIfEmpty);
    window.addEventListener("scroll", hide, true);
    return () => {
      document.removeEventListener("mouseup", update);
      document.removeEventListener("keyup", update);
      document.removeEventListener("selectionchange", clearIfEmpty);
      window.removeEventListener("scroll", hide, true);
    };
  }, [ref]);
  return selection;
}

function progressDetail(json: ReviewJson | null): string {
  if (!json) return "verdict";
  return json.tier4 ? "finishing" : "tiers 2–4";
}

function platformLabel(p: string) {
  return { leetcode: "LeetCode", codeforces: "Codeforces", other: "Other" }[p] ?? p;
}

function Pending({ children }: { children: ReactNode }) {
  return (
    <Card className="flex items-center gap-3 p-5 text-sm text-text-muted">
      <span className="size-2 animate-pulse rounded-full bg-accent" aria-hidden />
      {children}
    </Card>
  );
}

function Tier({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <section aria-label={`Tier ${n}: ${title}`} className="flex flex-col gap-3">
      <h2 className="flex items-baseline gap-2 text-sm font-medium text-text-heading">
        <span className="font-mono text-xs text-text-faint">{n}</span>
        {title}
      </h2>
      {children}
    </section>
  );
}

function ComplexityLine({ time, space }: { time: Complexity; space: Complexity }) {
  return (
    <p className="font-mono text-xs text-text-muted">
      time {time.display} · space {space.display}
    </p>
  );
}

function VerdictCard({ verdict }: { verdict: ReviewJson["verdict"] }) {
  const matched = verdict.optimal_techniques.includes(verdict.used_technique);
  const worse = !verdict.is_optimal;
  const worseTime = verdict.time.normalized !== verdict.optimal_time.normalized;
  const optimalSpace = verdict.optimal_space;
  const worseSpace = optimalSpace != null && verdict.space.normalized !== optimalSpace.normalized;
  return (
    <Card className="flex flex-col gap-4 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="mr-1 text-sm font-medium text-text-heading">Verdict</h2>
        <Chip attention={!verdict.correct}>{verdict.correct ? "Correct" : "Incorrect"}</Chip>
        <Chip attention={worse}>
          {matched
            ? `${techniqueLabel(verdict.used_technique)} · match`
            : `${techniqueLabel(verdict.used_technique)} → ${verdict.optimal_techniques.map(techniqueLabel).join(" / ")}`}
        </Chip>
        <Chip attention={worseTime}>
          time {verdict.time.display}
          {worseTime && ` → ${verdict.optimal_time.display}`}
        </Chip>
        <Chip attention={worseSpace}>
          space {verdict.space.display}
          {worseSpace && ` → ${optimalSpace.display}`}
        </Chip>
      </div>
      <Prose className="text-[14.5px]">{verdict.summary}</Prose>
      <div className="grid gap-4 sm:grid-cols-2">
        <List title="Bugs" items={verdict.bugs} />
        <List title="Missed edge cases" items={verdict.missed_edge_cases} />
      </div>
      {verdict.failing_inputs.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="text-xs font-medium text-text-muted">Inputs that would fail</h3>
          <ul className="flex flex-col gap-2">
            {verdict.failing_inputs.map((f) => (
              <li key={f.input} className="rounded-lg border border-border bg-raised px-3 py-2 text-[13px]">
                <code className="font-mono text-text">{f.input}</code>
                <span className="text-text-muted">
                  {" "}
                  — {f.outcome.replace("_", " ")}: {f.reason}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <ComplexityLine time={verdict.time} space={verdict.space} />
    </Card>
  );
}

function List({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="flex flex-col gap-1.5">
      <h3 className="text-xs font-medium text-text-muted">{title}</h3>
      {items.length === 0 ? (
        <p className="text-[13px] text-text-faint">None found</p>
      ) : (
        <ul className="flex list-disc flex-col gap-1 pl-4 text-[13px] text-text-secondary">
          {items.map((i) => (
            <li key={i}>
              <Prose>{i}</Prose>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function LaterTiers({ json, language }: { json: ReviewJson; language: string }) {
  return (
    <>
      {json.verdict.is_optimal && (
        <p className="text-sm text-text-secondary">Your solution is already optimal, so this skips to tier 4.</p>
      )}
      {json.tier2 && (
        <Tier n={2} title="Slightly better">
          <Prose>{json.tier2.approach}</Prose>
          <Prose className="text-text-secondary">{`**What changes.** ${json.tier2.what_changes}`}</Prose>
          <Prose className="text-text-secondary">{`**Why it's faster.** ${json.tier2.why_faster}`}</Prose>
          <Card className="overflow-hidden">
            <CodeView code={json.tier2.code} language={language} label="Tier 2 code" />
          </Card>
          <ComplexityLine time={json.tier2.time} space={json.tier2.space} />
        </Tier>
      )}
      {json.tier3 && (
        <Tier n={3} title="Optimal">
          <Prose>{json.tier3.insight}</Prose>
          <Card className="overflow-hidden">
            <CodeView code={json.tier3.code} language={language} label="Optimal code" />
          </Card>
          <ComplexityLine time={json.tier3.time} space={json.tier3.space} />
        </Tier>
      )}
      {json.tier4 && (
        <Tier n={4} title="CP master">
          <Prose>{json.tier4.notes}</Prose>
          <Card className="overflow-hidden">
            <CodeView code={json.tier4.code} language={language} label="Contest-style code" />
          </Card>
          {json.tier4.interview_caveat && (
            <p className="rounded-lg border border-attention/30 bg-attention-soft px-3 py-2 text-[13px] text-attention-text">
              In an interview: {json.tier4.interview_caveat}
            </p>
          )}
        </Tier>
      )}
      {json.pattern && (
        <section aria-label="Pattern and follow-up" className="flex flex-col gap-2">
          <h2 className="text-sm font-medium text-text-heading">Pattern · {json.pattern.name}</h2>
          <ul className="flex flex-wrap gap-2">
            {json.pattern.related_problems.map((p) => (
              <li key={p.title}>
                {p.platform === "leetcode" && p.slug ? (
                  <a
                    href={`https://leetcode.com/problems/${p.slug}/`}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="inline-flex rounded-full border border-border-strong bg-chip px-2.5 py-0.5 text-xs text-accent-text no-underline"
                  >
                    {p.title}
                  </a>
                ) : (
                  <Chip>{p.title}</Chip>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

function useReReview(sub: Submission) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { provider?: string; model?: string }) => api.requestReview(sub.id, body),
    onSuccess: (data) => {
      qc.setQueryData(["submission", sub.id], data);
      qc.invalidateQueries({ queryKey: ["submissions"] });
    },
  });
}

function FailedBanner({ sub }: { sub: Submission }) {
  const retry = useReReview(sub);
  return (
    <Card className="flex flex-wrap items-center gap-3 border-attention/40 p-4">
      <p className="min-w-0 flex-1 text-sm text-attention-text">{sub.review?.error}</p>
      <Button
        onClick={() => retry.mutate({ provider: sub.review?.provider, model: sub.review?.model })}
        disabled={retry.isPending}
      >
        Retry
      </Button>
      <ErrorText error={retry.error} />
    </Card>
  );
}

function ReviewFooter({ sub }: { sub: Submission }) {
  const review = sub.review!;
  const { data: me } = useMe();
  const reReview = useReReview(sub);
  const [provider, setProvider] = useState(review.provider);
  const [model, setModel] = useState(review.model);
  const running = sub.status === "queued" || sub.status === "analyzing";

  const stats = [
    review.served_model ?? review.model,
    review.input_tokens != null && `${review.input_tokens.toLocaleString()} in / ${review.output_tokens?.toLocaleString()} out`,
    review.latency_ms != null && `${(review.latency_ms / 1000).toFixed(1)} s`,
    review.cost_usd != null && `$${Number(review.cost_usd).toFixed(4)}`,
    review.repair_attempted && "repaired once",
  ].filter(Boolean);

  return (
    <footer className="flex flex-wrap items-end justify-between gap-4 border-t border-border pt-4">
      <p className="font-mono text-xs text-text-faint">{stats.join(" · ")}</p>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          reReview.mutate({ provider, model: model.trim() || undefined });
        }}
      >
        <label className="sr-only" htmlFor="rr-provider">
          Provider
        </label>
        <select
          id="rr-provider"
          value={provider}
          onChange={(e) => {
            setProvider(e.target.value);
            setModel(me?.provider_models[e.target.value]?.[0] ?? "");
          }}
          className={`${inputClass} w-auto py-1.5 text-xs`}
        >
          {(me?.providers ?? []).map((p) => (
            <option key={p.provider} value={p.provider}>
              {PROVIDER_LABELS[p.provider] ?? p.provider}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor="rr-model">
          Model
        </label>
        <ModelPicker
          id="rr-model"
          models={me?.provider_models[provider] ?? []}
          value={model}
          onChange={setModel}
          compact
        />
        <Button type="submit" disabled={running || reReview.isPending || !model.trim()}>
          Re-review
        </Button>
        <ErrorText error={reReview.error} />
      </form>
    </footer>
  );
}
