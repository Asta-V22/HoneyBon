import { useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { api, type CaptureMode, type Me } from "../lib/api";
import { useUpdateMe } from "../lib/hooks";

const MODES: { id: CaptureMode; label: string; hint: string }[] = [
  { id: "off", label: "Off", hint: "Submissions are ignored." },
  { id: "capture", label: "Capture", hint: "Submissions go to your review queue." },
  { id: "analyze", label: "Analyze", hint: "Submissions are captured and reviewed automatically." },
];

const icon = (d: ReactNode) => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    {d}
  </svg>
);

const NAV = [
  {
    to: "/today",
    label: "Today",
    icon: icon(
      <>
        <rect x="3" y="5" width="18" height="16" rx="2" />
        <path d="M3 10h18M8 3v4M16 3v4" />
      </>,
    ),
  },
  {
    to: "/library",
    label: "Library",
    icon: icon(
      <>
        <path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z" />
        <path d="M5 17a3 3 0 0 1 3-3h11" />
      </>,
    ),
  },
  { to: "/insights", label: "Insights", icon: icon(<path d="M5 20V11M12 20V5M19 20v-6" />) },
  {
    to: "/paste",
    label: "Paste code",
    icon: icon(
      <>
        <rect x="6" y="4" width="12" height="17" rx="2" />
        <path d="M9 4h6v3H9z" />
      </>,
    ),
  },
  {
    to: "/settings",
    label: "Settings",
    icon: icon(
      <>
        <circle cx="12" cy="12" r="3" />
        <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1" />
      </>,
    ),
  },
];

export function Sidebar({ me }: { me: Me }) {
  const qc = useQueryClient();
  const update = useUpdateMe();
  const mode = me.capture_mode;
  const setMode = (capture_mode: CaptureMode) => update.mutate({ capture_mode });
  const hint = MODES.find((m) => m.id === mode)!.hint;

  return (
    <nav
      aria-label="Main"
      className="box-border flex max-w-full flex-[1_1_232px] flex-col gap-[18px] border-r border-border bg-sidebar px-3.5 py-5"
    >
      <div className="flex items-center gap-2.5 px-2 py-1">
        <div className="flex size-[22px] items-center justify-center rounded-md bg-accent text-[13px] font-semibold text-on-accent">
          H
        </div>
        <span className="text-[15px] font-semibold tracking-tight">Honeybon</span>
      </div>

      <button
        type="button"
        className="flex min-h-9 w-full items-center gap-2 rounded-lg border border-border-strong bg-raised px-2.5 text-left text-[13px] text-text-muted"
      >
        {icon(
          <>
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" />
          </>,
        )}
        <span className="flex-1">Search or jump to…</span>
        <kbd className="rounded border border-border-strong px-1.5 font-mono text-[11px] text-text-faint">
          ⌘K
        </kbd>
      </button>

      <div className="flex flex-col gap-0.5">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex min-h-[38px] items-center gap-2.5 rounded-lg px-2.5 no-underline ${
                isActive
                  ? "bg-selected font-medium text-text"
                  : "text-text-secondary hover:bg-raised hover:text-text"
              }`
            }
          >
            {item.icon}
            {item.label}
          </NavLink>
        ))}
      </div>

      <div className="mt-auto flex flex-col gap-2.5 border-t border-border px-2.5 pt-3.5 pb-1">
        <span id="capture-label" className="text-xs font-medium text-text-muted">
          Auto-capture
        </span>
        <div
          role="group"
          aria-labelledby="capture-label"
          className="flex gap-0.5 rounded-lg border border-border-strong bg-raised p-[3px]"
        >
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              aria-pressed={m.id === mode}
              onClick={() => setMode(m.id)}
              className={`min-h-[30px] flex-1 rounded-md px-1.5 text-xs ${
                m.id === mode ? "bg-selected text-text" : "text-text-muted hover:text-text"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
        <span className="text-xs text-text-muted">{hint}</span>
        <div className="mt-2 flex items-center gap-2">
          {me.avatar_url ? (
            <img src={me.avatar_url} alt="" className="size-5 rounded-full" />
          ) : (
            <span className="size-5 rounded-full bg-chip" aria-hidden />
          )}
          <span className="min-w-0 flex-1 truncate text-xs text-text-secondary">{me.github_login}</span>
          <button
            type="button"
            onClick={async () => {
              await api.logout();
              qc.clear();
              window.location.assign("/");
            }}
            className="text-xs text-text-muted hover:text-text"
          >
            Sign out
          </button>
        </div>
      </div>
    </nav>
  );
}
