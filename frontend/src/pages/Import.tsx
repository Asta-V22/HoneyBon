import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { ModelPicker } from "../components/ModelPicker";
import { Button, Card, ErrorText, Field, inputClass, PageHeader, SectionTitle } from "../components/ui";
import { api, PROVIDER_LABELS, type AnalysisMode, type ImportJob, type Me, type ModeEstimate } from "../lib/api";
import { useMe } from "../lib/hooks";

const busy = (job: ImportJob) =>
  job.status === "pending" || job.status === "running" || job.analysis_status === "running";

export function ImportPage() {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const { data: jobs, error } = useQuery({
    queryKey: ["imports"],
    queryFn: api.imports,
    // Follow progress while anything runs.
    refetchInterval: (q) => (q.state.data?.some(busy) ? 2000 : false),
  });
  const latest = jobs?.[0];
  const [repo, setRepo] = useState("");
  useEffect(() => {
    if (latest && !repo) setRepo(`https://github.com/${latest.repository}`);
  }, [latest, repo]);

  const start = useMutation({
    mutationFn: () => api.startImport(repo.trim()),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["imports"] }),
  });
  const running = latest?.status === "pending" || latest?.status === "running";

  return (
    <div className="flex max-w-3xl flex-col gap-8">
      <PageHeader eyebrow="Settings" title="Import from GitHub" />
      <p className="-mt-4 text-sm text-text-secondary">
        Bring in the solutions you wrote before Honeybon, so Insights has your history from day one. Works with any
        public repository in the LeetHub layout: one folder per problem, named like{" "}
        <code className="font-mono text-xs">1036-rotting-oranges</code>. Problem statements in the READMEs are never
        stored.
      </p>

      <Card className="p-4">
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (repo.trim()) start.mutate();
          }}
        >
          <div className="flex-[1_1_320px]">
            <Field label="Public repository" htmlFor="repo">
              <input
                id="repo"
                value={repo}
                onChange={(e) => setRepo(e.target.value)}
                placeholder="https://github.com/you/leetcode"
                className={inputClass}
                maxLength={300}
              />
            </Field>
          </div>
          <Button type="submit" variant="primary" disabled={!repo.trim() || start.isPending || running}>
            {latest ? "Import again" : "Import"}
          </Button>
        </form>
        {latest && (
          <p className="mt-2 text-xs text-text-muted">
            Importing again only adds solutions that are new or changed since last time.
          </p>
        )}
        <ErrorText error={start.error ?? error} />
      </Card>

      {latest && me && <JobView job={latest} me={me} />}
    </div>
  );
}

function Progress({ done, total, label }: { done: number; total: number; label: string }) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex justify-between text-xs text-text-muted">
        <span>{label}</span>
        <span className="font-mono">
          {done} / {total || "…"}
        </span>
      </div>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        className="h-1.5 overflow-hidden rounded-full bg-chip"
      >
        <div className="h-full rounded-full bg-accent transition-[width]" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function JobView({ job, me }: { job: ImportJob; me: Me }) {
  return (
    <section className="flex flex-col gap-4">
      <SectionTitle aside={new Date(job.created_at).toLocaleString()}>{job.repository}</SectionTitle>
      <Card className="flex flex-col gap-3 p-4">
        {job.status === "pending" || job.status === "running" ? (
          <Progress done={job.processed} total={job.total} label="Reading the repository" />
        ) : job.status === "failed" ? (
          <p role="alert" className="text-sm text-attention-text">
            {job.error}
          </p>
        ) : (
          <p className="text-sm text-text-secondary">
            Imported <strong className="text-text">{job.imported}</strong> solution{job.imported === 1 ? "" : "s"}
            {job.duplicates > 0 && `, skipped ${job.duplicates} you already had`}
            {job.unmatched.length > 0 && `, ${job.unmatched.length} folder${job.unmatched.length === 1 ? "" : "s"} to map`}
            .
          </p>
        )}
      </Card>
      {job.unmatched.length > 0 && <Unmatched job={job} />}
      {job.status === "completed" && <Analysis job={job} me={me} />}
    </section>
  );
}

function Unmatched({ job }: { job: ImportJob }) {
  return (
    <div className="flex flex-col gap-2">
      <SectionTitle aside="Not named <id>-<slug>; paste each one's problem link, or skip it">
        Folders to map
      </SectionTitle>
      <Card className="divide-y divide-divider">
        {job.unmatched.map((u) => (
          <UnmatchedRow key={u.folder} job={job} folder={u.folder} files={u.files} />
        ))}
      </Card>
    </div>
  );
}

function UnmatchedRow({ job, folder, files }: { job: ImportJob; folder: string; files: { path: string; language: string }[] }) {
  const qc = useQueryClient();
  const [link, setLink] = useState("");
  const resolve = useMutation({
    mutationFn: (value: string | null) => api.resolveFolder(job.id, folder, value),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["imports"] }),
  });
  const id = `map-${folder}`;
  return (
    <form
      className="flex flex-col gap-2 p-3.5"
      onSubmit={(e) => {
        e.preventDefault();
        if (link.trim()) resolve.mutate(link.trim());
      }}
    >
      <label htmlFor={id} className="text-sm">
        <span className="font-mono text-xs">{folder}/</span>
        <span className="ml-2 text-xs text-text-muted">
          {files.map((f) => f.path.split("/").pop()).join(", ")}
        </span>
      </label>
      <div className="flex flex-wrap gap-2">
        <input
          id={id}
          value={link}
          onChange={(e) => setLink(e.target.value)}
          placeholder="https://leetcode.com/problems/…"
          className={`${inputClass} flex-[1_1_240px] py-1.5`}
        />
        <Button type="submit" disabled={!link.trim() || resolve.isPending}>
          Map
        </Button>
        <Button onClick={() => resolve.mutate(null)} disabled={resolve.isPending}>
          Skip
        </Button>
      </div>
      <ErrorText error={resolve.error} />
    </form>
  );
}

const MODES: { id: AnalysisMode; title: string; body: string }[] = [
  {
    id: "tags_only",
    title: "Quick analysis",
    body: "One short call per solution: the technique you used, the optimal one, and both complexities. Enough for Insights. Any solution can get a full review later.",
  },
  { id: "full", title: "Full reviews", body: "All four tiers for every solution. Much slower and costlier." },
  { id: "none", title: "No analysis", body: "Keep the code only. You can analyse later from here." },
];

function Analysis({ job, me }: { job: ImportJob; me: Me }) {
  const qc = useQueryClient();
  const saved = me.providers.map((p) => p.provider);
  const [mode, setMode] = useState<AnalysisMode>("tags_only");
  const [provider, setProvider] = useState(me.default_provider ?? saved[0] ?? "");
  const [model, setModel] = useState(
    (provider === me.default_provider ? me.default_model : null) ?? me.provider_models[provider]?.[0] ?? "",
  );
  const refresh = (j: ImportJob) => qc.setQueryData<ImportJob[]>(["imports"], (old) => old?.map((o) => (o.id === j.id ? j : o)));
  const start = useMutation({
    mutationFn: () => api.startAnalysis(job.id, { mode, provider: provider || undefined, model: model.trim() || undefined }),
    onSuccess: refresh,
  });
  const cancel = useMutation({ mutationFn: () => api.cancelAnalysis(job.id), onSuccess: refresh });
  const estimate = useQuery({
    queryKey: ["import-estimate", job.id, job.pending, provider, model],
    queryFn: () => api.importEstimate(job.id, provider || undefined, model.trim() || undefined),
    enabled: job.pending > 0 && saved.length > 0 && job.analysis_status !== "running",
  });

  if (job.analysis_status === "running") {
    return (
      <Card className="flex flex-col gap-3 p-4">
        <Progress
          done={job.analysis_done}
          total={job.analysis_total}
          label={`${job.analysis_mode === "full" ? "Reviewing" : "Analysing"} with ${job.analysis_model}`}
        />
        <div className="flex flex-wrap items-center gap-3">
          <p className="flex-1 text-xs text-text-muted">
            Runs in the background; you can leave this page.
            {job.analysis_failed > 0 && ` ${job.analysis_failed} failed so far (retry them from the Library).`}
          </p>
          <Button onClick={() => cancel.mutate()} disabled={cancel.isPending}>
            Stop
          </Button>
        </div>
        <ErrorText error={cancel.error} />
      </Card>
    );
  }

  const finished = job.analysis_mode && job.analysis_mode !== "none" && job.analysis_done > 0;
  return (
    <div className="flex flex-col gap-3">
      {job.analysis_error && (
        <p role="alert" className="text-sm text-attention-text">
          {job.analysis_error}
        </p>
      )}
      {finished && (
        <Card className="flex flex-wrap items-center gap-3 p-4">
          <p className="flex-1 text-sm text-text-secondary">
            {job.analysis_status === "cancelled" ? "Stopped after" : "Analysed"} {job.analysis_done - job.analysis_failed}{" "}
            solution{job.analysis_done - job.analysis_failed === 1 ? "" : "s"}
            {job.analysis_failed > 0 && `; ${job.analysis_failed} failed`}.
          </p>
          <Link
            to="/insights"
            className="inline-flex min-h-8 items-center rounded-lg border border-transparent bg-accent px-3 text-[13px] font-medium text-on-accent no-underline hover:opacity-90"
          >
            Open Insights
          </Link>
        </Card>
      )}
      {job.pending > 0 && (
        <>
          <SectionTitle aside={`${job.pending} solution${job.pending === 1 ? "" : "s"} not analysed yet`}>
            {finished ? "Analyse the rest" : "Analyse the imported solutions"}
          </SectionTitle>
          {saved.length === 0 ? (
            <Card className="p-4 text-sm text-text-muted">
              Add an API key in <Link to="/settings" className="text-accent-text">Settings</Link> first.
            </Card>
          ) : (
            <Card className="flex flex-col gap-4 p-4">
              <fieldset className="flex flex-col gap-2">
                <legend className="sr-only">Analysis</legend>
                {MODES.map((m) => {
                  const est = m.id === "tags_only" ? estimate.data?.tags_only : m.id === "full" ? estimate.data?.full : undefined;
                  return (
                    <label
                      key={m.id}
                      className={`flex cursor-pointer gap-3 rounded-lg border p-3 ${
                        mode === m.id ? "border-accent/60 bg-accent-soft" : "border-border-strong"
                      }`}
                    >
                      <input type="radio" name="mode" checked={mode === m.id} onChange={() => setMode(m.id)} className="mt-1" />
                      <span className="flex flex-col gap-1">
                        <span className="text-sm font-medium">{m.title}</span>
                        <span className="text-xs text-text-muted">{m.body}</span>
                        {est && <EstimateLine est={est} provider={provider} />}
                      </span>
                    </label>
                  );
                })}
              </fieldset>
              {mode !== "none" && (
                <div className="flex flex-wrap items-end gap-3">
                  <div className="w-36">
                    <Field label="Provider" htmlFor="an-provider">
                      <select
                        id="an-provider"
                        value={provider}
                        onChange={(e) => {
                          setProvider(e.target.value);
                          setModel(me.provider_models[e.target.value]?.[0] ?? "");
                        }}
                        className={inputClass}
                      >
                        {saved.map((p) => (
                          <option key={p} value={p}>
                            {PROVIDER_LABELS[p] ?? p}
                          </option>
                        ))}
                      </select>
                    </Field>
                  </div>
                  <div className="flex-[1_1_220px]">
                    <Field label="Model" htmlFor="an-model">
                      <ModelPicker id="an-model" models={me.provider_models[provider] ?? []} value={model} onChange={setModel} />
                    </Field>
                  </div>
                </div>
              )}
              <ErrorText error={estimate.error} />
              <div>
                <Button
                  variant="primary"
                  onClick={() => start.mutate()}
                  disabled={start.isPending || (mode !== "none" && !model.trim())}
                >
                  {mode === "none" ? "Skip analysis" : `Analyse ${job.pending}`}
                </Button>
              </div>
              <ErrorText error={start.error} />
            </Card>
          )}
        </>
      )}
    </div>
  );
}

const compact = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });

function EstimateLine({ est, provider }: { est: ModeEstimate; provider: string }) {
  const tokens = est.input_tokens + est.output_tokens;
  // Groq's free tier allows about 8,000 tokens a minute.
  const minutes = provider === "groq" ? Math.max(1, Math.ceil(tokens / 8000)) : null;
  return (
    <span className="font-mono text-xs text-text-faint">
      ≈ {compact.format(tokens)} tokens
      {est.cost_usd != null ? ` · ≈ $${Number(est.cost_usd).toFixed(2)}` : " · no price on file (free tier)"}
      {minutes != null && ` · ≈ ${minutes < 90 ? `${minutes} min` : `${Math.round(minutes / 60)} h`} on Groq's free tier`}
    </span>
  );
}
