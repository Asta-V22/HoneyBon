import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api, PROVIDER_LABELS, type ChatMessage, type ChatThread, type Me, type Submission } from "../lib/api";
import { ModelPicker } from "./ModelPicker";
import { Prose } from "./Prose";
import { Button, ErrorText, inputClass } from "./ui";

function useThread(submissionId: string) {
  const qc = useQueryClient();
  const key = ["thread", submissionId];
  const query = useQuery({ queryKey: key, queryFn: () => api.thread(submissionId) });
  const streaming = query.data?.messages.find((m) => m.status === "streaming");

  // Stream the in-progress reply: each "text" event carries the full text so far.
  useEffect(() => {
    if (!streaming) return;
    const source = new EventSource(`/api/chat/messages/${streaming.id}/events`);
    const setText = (text: string) =>
      qc.setQueryData<ChatThread>(key, (t) =>
        t && { ...t, messages: t.messages.map((m) => (m.id === streaming.id ? { ...m, content: text } : m)) },
      );
    source.addEventListener("ready", () => qc.invalidateQueries({ queryKey: key }));
    source.onmessage = (e) => {
      const event = JSON.parse(e.data);
      if (event.type === "text") setText(event.text);
      if (event.type === "done" || event.type === "failed") {
        source.close();
        qc.invalidateQueries({ queryKey: key });
      }
    };
    return () => source.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streaming?.id, submissionId, qc]);

  return { ...query, streaming };
}

function initialModel(me: Me, sub: Submission, thread?: ChatThread): [string, string] {
  const saved = new Set(me.providers.map((p) => p.provider));
  const lastReply = [...(thread?.messages ?? [])].reverse().find((m) => m.role === "assistant" && m.provider);
  for (const c of [lastReply, sub.review]) {
    if (c?.provider && c.model && saved.has(c.provider)) return [c.provider, c.model];
  }
  const provider = me.default_provider && saved.has(me.default_provider) ? me.default_provider : me.providers[0]?.provider ?? "";
  const model = provider === me.default_provider && me.default_model ? me.default_model : me.provider_models[provider]?.[0] ?? "";
  return [provider, model];
}

export function DiscussionPanel({
  sub,
  me,
  quote,
  onQuoteChange,
  onClose,
  focusKey,
}: {
  sub: Submission;
  me: Me;
  quote: string;
  onQuoteChange: (q: string) => void;
  onClose: () => void;
  focusKey: number;
}) {
  const qc = useQueryClient();
  const { data: thread, error, streaming } = useThread(sub.id);
  const [draft, setDraft] = useState("");
  const [choice, setChoice] = useState<[string, string] | null>(null);
  const [provider, model] = choice ?? initialModel(me, sub, thread);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const send = useMutation({
    mutationFn: () =>
      api.sendChat(sub.id, {
        content: draft.trim(),
        quoted_selection: quote || undefined,
        provider,
        model: model.trim(),
      }),
    onSuccess: (data) => {
      qc.setQueryData(["thread", sub.id], data);
      setDraft("");
      onQuoteChange("");
    },
  });

  useEffect(() => inputRef.current?.focus(), [focusKey]);
  const last = thread?.messages.at(-1);
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [thread?.messages.length, last?.content]);

  const canSend = draft.trim() && model.trim() && provider && !streaming && !send.isPending;
  const messages = thread?.messages ?? [];

  return (
    <aside
      aria-label="Discussion"
      className="fixed inset-0 z-30 flex flex-col bg-bg lg:sticky lg:top-6 lg:z-auto lg:h-[calc(100vh-48px)] lg:rounded-xl lg:border lg:border-border lg:bg-surface"
    >
      <header className="flex flex-col gap-2.5 border-b border-border px-4 py-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium">Discuss</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close discussion"
            className="rounded-md p-1 text-text-muted hover:bg-raised hover:text-text"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
              <path d="M6 6l12 12M18 6 6 18" />
            </svg>
          </button>
        </div>
        <div className="flex flex-wrap gap-1.5" aria-label="Context the model sees">
          {[sub.problem.title ?? sub.problem.slug, "Your code", sub.review?.review_json ? "Review" : null]
            .filter(Boolean)
            .map((c) => (
              <span key={c} className="rounded-full border border-border-strong bg-chip px-2 py-0.5 text-[11px] text-text-secondary">
                {c}
              </span>
            ))}
        </div>
      </header>

      <div ref={listRef} className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-4" aria-live="polite">
        <ErrorText error={error} />
        {thread && thread.summarized_messages > 0 && (
          <p className="text-center text-[11px] text-text-faint">
            {thread.summarized_messages} earlier messages are summarized for the model
          </p>
        )}
        {messages.length === 0 && (
          <p className="text-sm text-text-muted">
            Ask anything about this problem. The model already has your code and the review. Select lines in the
            code or a tier to quote them.
          </p>
        )}
        {messages.map((m) => (
          <MessageView key={m.id} message={m} />
        ))}
      </div>

      <form
        className="flex flex-col gap-2 border-t border-border p-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (canSend) send.mutate();
        }}
      >
        {quote && (
          <div className="flex items-start gap-2 rounded-lg border border-border bg-raised px-2.5 py-2">
            <pre className="max-h-24 min-w-0 flex-1 overflow-auto font-mono text-[11.5px] whitespace-pre-wrap text-text-secondary">
              {quote}
            </pre>
            <button
              type="button"
              onClick={() => onQuoteChange("")}
              aria-label="Remove quoted selection"
              className="text-xs text-text-muted hover:text-text"
            >
              ✕
            </button>
          </div>
        )}
        <label htmlFor="chat-input" className="sr-only">
          Message
        </label>
        <textarea
          id="chat-input"
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (canSend) send.mutate();
            }
          }}
          rows={3}
          placeholder={streaming ? "Waiting for the reply…" : "Ask a follow-up (Enter to send, Shift+Enter for a new line)"}
          className={`${inputClass} resize-none`}
        />
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor="chat-provider" className="sr-only">
            Provider
          </label>
          <select
            id="chat-provider"
            value={provider}
            onChange={(e) => setChoice([e.target.value, me.provider_models[e.target.value]?.[0] ?? ""])}
            className={`${inputClass} w-auto py-1.5 text-xs`}
          >
            {me.providers.map((p) => (
              <option key={p.provider} value={p.provider}>
                {PROVIDER_LABELS[p.provider] ?? p.provider}
              </option>
            ))}
          </select>
          <ModelPicker
            id="chat-model"
            models={me.provider_models[provider] ?? []}
            value={model}
            onChange={(m) => setChoice([provider, m])}
            compact
          />
          <Button type="submit" variant="primary" disabled={!canSend} className="ml-auto">
            Send
          </Button>
        </div>
        <ErrorText error={send.error} />
      </form>
    </aside>
  );
}

function MessageView({ message: m }: { message: ChatMessage }) {
  if (m.role === "user") {
    return (
      <div className="flex flex-col items-end gap-1.5">
        {m.quoted_selection && (
          <pre className="max-h-32 max-w-[90%] overflow-auto rounded-lg border border-border bg-raised px-2.5 py-1.5 font-mono text-[11.5px] whitespace-pre-wrap text-text-muted">
            {m.quoted_selection}
          </pre>
        )}
        <p className="max-w-[90%] rounded-lg bg-selected px-3 py-2 text-sm whitespace-pre-wrap">{m.content}</p>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1.5">
      {m.content ? (
        <Prose className="text-sm">{m.content}</Prose>
      ) : m.status === "streaming" ? (
        <span className="flex items-center gap-2 text-sm text-text-muted">
          <span className="size-1.5 animate-pulse rounded-full bg-accent" aria-hidden /> Thinking…
        </span>
      ) : null}
      {m.status === "failed" && <p className="text-sm text-attention-text">{m.error}</p>}
      {m.model && m.status !== "streaming" && <p className="font-mono text-[11px] text-text-faint">{m.model}</p>}
    </div>
  );
}
