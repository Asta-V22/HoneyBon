import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, type CaptureMode, type Me, type SubmissionListItem } from "../lib/api";
import { useUpdateMe } from "../lib/hooks";
import { StatusChip } from "./StatusChip";

export const IS_MAC = /mac|iphone|ipad/i.test(navigator.platform || navigator.userAgent);
export const PALETTE_SHORTCUT = IS_MAC ? "⌘K" : "Ctrl K";

interface Item {
  id: string;
  group: "Problems" | "Recent problems" | "Go to" | "Capture mode";
  label: string;
  hint?: string;
  submission?: SubmissionListItem;
  run: () => void;
}

const PAGES = [
  { to: "/today", label: "Today" },
  { to: "/library", label: "Library" },
  { to: "/insights", label: "Insights" },
  { to: "/import", label: "Import from GitHub" },
  { to: "/paste", label: "Paste code" },
  { to: "/settings", label: "Settings" },
];

const MODES: { id: CaptureMode; label: string }[] = [
  { id: "off", label: "Off" },
  { id: "capture", label: "Capture" },
  { id: "analyze", label: "Analyze" },
];

/** ⌘K / Ctrl+K anywhere opens it; also the sidebar's search button. */
export function useCommandPalette(): [boolean, (open: boolean) => void] {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return [open, setOpen];
}

const matches = (text: string, q: string) => text.toLowerCase().includes(q.toLowerCase());

/** One entry per problem: its latest submission (the list comes newest first). */
function latestPerProblem(items: SubmissionListItem[], max: number): SubmissionListItem[] {
  const seen = new Set<string>();
  return items.filter((s) => !seen.has(s.problem.id) && seen.add(s.problem.id)).slice(0, max);
}

export function CommandPalette({ me, open, onClose }: { me: Me; open: boolean; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const update = useUpdateMe();
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [active, setActive] = useState(0);

  useEffect(() => {
    const d = dialog.current;
    if (!d) return;
    if (open && !d.open) {
      setQuery("");
      setDebounced("");
      setActive(0);
      d.showModal();
      input.current?.focus();
    } else if (!open && d.open) {
      d.close();
    }
  }, [open]);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query.trim()), 150);
    return () => clearTimeout(timer);
  }, [query]);

  const { data, isFetching } = useQuery({
    queryKey: ["palette", debounced],
    queryFn: () => api.submissions({ q: debounced || undefined, limit: debounced ? 60 : 30 }),
    enabled: open,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });

  const items = useMemo<Item[]>(() => {
    const q = query.trim();
    const go = (to: string) => () => {
      onClose();
      navigate(to);
    };
    const problems: Item[] = latestPerProblem(data?.items ?? [], q ? 8 : 5).map((s) => ({
      id: `p:${s.id}`,
      group: q ? "Problems" : "Recent problems",
      label: s.problem.title ?? s.problem.slug,
      hint: s.problem.difficulty ?? undefined,
      submission: s,
      run: go(`/review/${s.id}`),
    }));
    const pages: Item[] = PAGES.filter((p) => !q || matches(p.label, q)).map((p) => ({
      id: `g:${p.to}`,
      group: "Go to",
      label: p.label,
      run: go(p.to),
    }));
    const modes: Item[] = MODES.filter(
      (m) => !q || matches(`capture mode ${m.label} auto-capture`, q),
    ).map((m) => ({
      id: `m:${m.id}`,
      group: "Capture mode",
      label: `Set auto-capture to ${m.label}`,
      hint: me.capture_mode === m.id ? "current" : undefined,
      run: () => {
        update.mutate({ capture_mode: m.id });
        onClose();
      },
    }));
    // While typing, problems are what people look for; otherwise pages come first.
    return q ? [...problems, ...pages, ...modes] : [...pages, ...problems, ...modes];
  }, [data, query, me.capture_mode, navigate, onClose, update]);

  useEffect(() => setActive(0), [query]);
  useEffect(() => setActive((i) => Math.min(i, Math.max(0, items.length - 1))), [items.length]);
  useEffect(() => {
    list.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown" || (e.ctrlKey && e.key === "n")) {
      setActive((i) => (items.length ? (i + 1) % items.length : 0));
    } else if (e.key === "ArrowUp" || (e.ctrlKey && e.key === "p")) {
      setActive((i) => (items.length ? (i - 1 + items.length) % items.length : 0));
    } else if (e.key === "Enter") {
      items[active]?.run();
    } else {
      return;
    }
    e.preventDefault();
  };

  const typing = query.trim() !== debounced || (isFetching && !!debounced);

  return (
    <dialog
      ref={dialog}
      aria-label="Search or jump to"
      onClose={onClose}
      onClick={(e) => e.target === dialog.current && onClose()}
      className="mx-auto mt-[12vh] w-[min(640px,calc(100vw-32px))] overflow-hidden rounded-xl border border-border-strong bg-surface p-0 text-text shadow-2xl backdrop:bg-black/50"
    >
      <div className="flex items-center gap-2.5 border-b border-border px-4">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" className="shrink-0 text-text-muted" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
        <input
          ref={input}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Search problems, pages and actions…"
          role="combobox"
          aria-expanded="true"
          aria-controls="palette-list"
          aria-activedescendant={items[active] ? `palette-${active}` : undefined}
          aria-autocomplete="list"
          className="min-h-12 flex-1 bg-transparent text-[15px] text-text placeholder:text-text-faint focus:outline-none"
        />
        {typing && <span className="size-1.5 animate-pulse rounded-full bg-accent" aria-hidden />}
        <kbd className="rounded border border-border-strong px-1.5 font-mono text-[11px] text-text-faint">Esc</kbd>
      </div>

      <ul ref={list} id="palette-list" role="listbox" aria-label="Results" className="max-h-[min(420px,60vh)] overflow-y-auto p-2">
        {items.length === 0 && !typing && (
          <li className="px-3 py-6 text-center text-sm text-text-muted">Nothing matches “{query.trim()}”.</li>
        )}
        {items.map((item, i) => (
          <PaletteRow
            key={item.id}
            item={item}
            index={i}
            active={i === active}
            first={i === 0 || items[i - 1].group !== item.group}
            onHover={() => setActive(i)}
          />
        ))}
      </ul>

      <div className="flex gap-4 border-t border-border px-4 py-2 text-[11px] text-text-faint">
        <span>↑↓ to move</span>
        <span>Enter to open</span>
        <span className="ml-auto">{PALETTE_SHORTCUT} to toggle</span>
      </div>
    </dialog>
  );
}

function PaletteRow({
  item,
  index,
  active,
  first,
  onHover,
}: {
  item: Item;
  index: number;
  active: boolean;
  first: boolean;
  onHover: () => void;
}) {
  return (
    <>
      {first && (
        <li role="presentation" className="px-3 pt-2.5 pb-1 text-[11px] font-medium text-text-faint first:pt-1">
          {item.group}
        </li>
      )}
      <li
        id={`palette-${index}`}
        data-index={index}
        role="option"
        aria-selected={active}
        onMouseMove={onHover}
        onClick={item.run}
        className={`flex min-h-10 cursor-pointer items-center gap-3 rounded-lg px-3 text-sm ${
          active ? "bg-selected text-text" : "text-text-secondary"
        }`}
      >
        <span className="min-w-0 flex-1 truncate">{item.label}</span>
        {item.hint && <span className="text-xs text-text-muted">{item.hint}</span>}
        {item.submission && <StatusChip status={item.submission.status} />}
      </li>
    </>
  );
}
