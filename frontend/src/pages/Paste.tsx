import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Button, Card, ErrorText, Field, inputClass, PageHeader } from "../components/ui";
import { api } from "../lib/api";
import { useMe } from "../lib/hooks";

const LANGUAGES = ["cpp", "python", "java", "javascript", "typescript", "go", "rust", "csharp", "kotlin", "c"];

function platformFromLink(link: string): string {
  if (/leetcode\.(com|cn)\/problems\//i.test(link)) return "leetcode";
  if (/codeforces\.com\//i.test(link)) return "codeforces";
  return link.trim() ? "other" : "";
}

export function PastePage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: me } = useMe();
  const [code, setCode] = useState("");
  const [link, setLink] = useState("");
  const [statement, setStatement] = useState("");
  const [useStatement, setUseStatement] = useState(false);
  const [platform, setPlatform] = useState("");
  const [language, setLanguage] = useState("");
  const [title, setTitle] = useState("");

  const detected = platformFromLink(link);
  const submit = useMutation({
    mutationFn: () =>
      api.paste({
        code,
        link: useStatement ? undefined : link.trim() || undefined,
        statement: useStatement ? statement : undefined,
        platform: platform || (useStatement ? undefined : detected) || undefined,
        language: language || undefined,
        title: title.trim() || undefined,
      }),
    onSuccess: (sub) => {
      qc.setQueryData(["submission", sub.id], sub);
      qc.invalidateQueries({ queryKey: ["submissions"] });
      navigate(`/review/${sub.id}`);
    },
  });

  const noKey = me && me.providers.length === 0;
  const ready = code.trim() && (useStatement ? statement.trim() : link.trim());

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Paste code" eyebrow="Review a solution from Codeforces or anywhere else" />
      {noKey && (
        <Card className="border-attention/40 p-4 text-sm text-attention-text">
          Add an API key in <Link to="/settings" className="text-accent-text">Settings</Link> before your first review.
        </Card>
      )}
      <form
        className="flex flex-col gap-5"
        onSubmit={(e) => {
          e.preventDefault();
          if (ready) submit.mutate();
        }}
      >
        <Field label="Code" htmlFor="code">
          <textarea
            id="code"
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
            spellCheck={false}
            rows={16}
            className={`${inputClass} font-mono text-[13px] leading-relaxed`}
            placeholder="Paste your accepted solution"
          />
        </Field>

        <div className="flex flex-col gap-3">
          <div role="group" aria-label="Problem source" className="flex gap-0.5 self-start rounded-lg border border-border-strong bg-raised p-[3px]">
            {[
              { id: false, label: "Problem link" },
              { id: true, label: "Problem statement" },
            ].map((o) => (
              <button
                key={o.label}
                type="button"
                aria-pressed={useStatement === o.id}
                onClick={() => setUseStatement(o.id)}
                className={`min-h-[30px] rounded-md px-3 text-xs ${useStatement === o.id ? "bg-selected text-text" : "text-text-muted"}`}
              >
                {o.label}
              </button>
            ))}
          </div>
          {useStatement ? (
            <Field label="Problem statement" htmlFor="statement">
              <textarea
                id="statement"
                value={statement}
                onChange={(e) => setStatement(e.target.value)}
                rows={6}
                className={inputClass}
              />
            </Field>
          ) : (
            <Field label="Problem link" htmlFor="link" hint="LeetCode and Codeforces links are recognized.">
              <input
                id="link"
                type="url"
                value={link}
                onChange={(e) => setLink(e.target.value)}
                className={inputClass}
                placeholder="https://codeforces.com/contest/1850/problem/C"
              />
            </Field>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Title" htmlFor="title" hint="Optional">
            <input id="title" value={title} onChange={(e) => setTitle(e.target.value)} className={inputClass} />
          </Field>
          <Field label="Platform" htmlFor="platform">
            <select id="platform" value={platform} onChange={(e) => setPlatform(e.target.value)} className={inputClass}>
              <option value="">{detected ? `Detected: ${detected}` : "Detect from link"}</option>
              <option value="leetcode">LeetCode</option>
              <option value="codeforces">Codeforces</option>
              <option value="other">Other</option>
            </select>
          </Field>
          <Field label="Language" htmlFor="language">
            <select id="language" value={language} onChange={(e) => setLanguage(e.target.value)} className={inputClass}>
              <option value="">Auto-detect</option>
              {LANGUAGES.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <div className="flex items-center gap-3">
          <Button type="submit" variant="primary" disabled={!ready || submit.isPending || noKey}>
            {submit.isPending ? "Sending…" : "Review"}
          </Button>
          <ErrorText error={submit.error} />
        </div>
      </form>
    </div>
  );
}
