import { useState } from "react";

export const VIEWS = [
  { id: "bars", label: "Bars", hint: "Each technique you needed, and how often you used it" },
  { id: "flow", label: "Flow", hint: "What you reached for instead of each needed technique" },
  { id: "heatmap", label: "Heatmap", hint: "Needed technique against the one you used" },
  { id: "progress", label: "Progress", hint: "How often you've used the optimal technique over time" },
] as const;

export type View = (typeof VIEWS)[number]["id"];

const KEY = "hb:insights-view";

/** The chosen view, remembered per browser. Storage may be unavailable; then it's per visit. */
export function useInsightsView(): [View, (v: View) => void] {
  const [view, setView] = useState<View>(() => {
    try {
      const saved = localStorage.getItem(KEY);
      return VIEWS.some((v) => v.id === saved) ? (saved as View) : "bars";
    } catch {
      return "bars";
    }
  });
  const choose = (v: View) => {
    setView(v);
    try {
      localStorage.setItem(KEY, v);
    } catch {
      /* per visit only */
    }
  };
  return [view, choose];
}

export function ViewSwitcher({ view, onChange }: { view: View; onChange: (v: View) => void }) {
  return (
    <div role="group" aria-label="Chart view" className="flex gap-0.5 rounded-lg border border-border-strong bg-raised p-[3px]">
      {VIEWS.map((v) => (
        <button
          key={v.id}
          type="button"
          title={v.hint}
          aria-pressed={v.id === view}
          onClick={() => onChange(v.id)}
          className={`min-h-[30px] rounded-md px-3 text-xs ${v.id === view ? "bg-selected text-text" : "text-text-muted hover:text-text"}`}
        >
          {v.label}
        </button>
      ))}
    </div>
  );
}
