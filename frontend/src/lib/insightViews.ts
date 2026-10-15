// Shapes the Insights items for each view. Pure functions; every view reads the same filtered items.

import type { InsightItem } from "./api";

/** How a problem was solved relative to the technique it needed. */
export type Outcome = "match" | "same" | "worse";

export const outcomeOf = (i: InsightItem): Outcome => (i.match ? "match" : i.worse ? "worse" : "same");

export const OUTCOME_LABELS: Record<Outcome, string> = {
  match: "Used it",
  same: "Another technique, same complexity",
  worse: "Another technique, worse complexity",
};

// ---------------------------------------------------------------- bars

export interface TechniqueBar {
  needed: string;
  total: number;
  match: number;
  same: number;
  worse: number;
  /** The technique most often used instead, if any. */
  usualInstead: string | null;
}

/** One bar per needed technique, the most-avoided first (ties: more problems first). */
export function techniqueBars(items: InsightItem[]): TechniqueBar[] {
  const bars = new Map<string, TechniqueBar & { instead: Map<string, number> }>();
  for (const i of items) {
    const bar = bars.get(i.needed) ?? { needed: i.needed, total: 0, match: 0, same: 0, worse: 0, usualInstead: null, instead: new Map() };
    bar.total += 1;
    bar[outcomeOf(i)] += 1;
    if (!i.match) bar.instead.set(i.used, (bar.instead.get(i.used) ?? 0) + 1);
    bars.set(i.needed, bar);
  }
  return [...bars.values()]
    .map(({ instead, ...bar }) => ({
      ...bar,
      usualInstead: [...instead.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0]?.[0] ?? null,
    }))
    .sort((a, b) => a.match / a.total - b.match / b.total || b.total - a.total || a.needed.localeCompare(b.needed));
}

// ---------------------------------------------------------------- flow

export const OTHER = "__other__";

export interface FlowLink {
  needed: string;
  used: string;
  count: number;
  outcome: Outcome; // one link per outcome, so a folded "Other" never mixes colours
}

export interface FlowNode {
  id: string; // a technique, or OTHER
  count: number;
  members: string[]; // the techniques it stands for
}

export interface Flow {
  left: FlowNode[];
  right: FlowNode[];
  links: FlowLink[];
}

/** Needed -> used links. Beyond `top` techniques a side, the rest fold into OTHER. */
export function flowLinks(items: InsightItem[], top = 12): Flow {
  const ranked = (key: (i: InsightItem) => string) => {
    const counts = new Map<string, number>();
    for (const i of items) counts.set(key(i), (counts.get(key(i)) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([id]) => id);
  };
  // Room for `top` nodes a side; one goes to OTHER when anything has to fold.
  const fit = (ids: string[]) => new Set(ids.length > top ? ids.slice(0, top - 1) : ids);
  const keepLeft = fit(ranked((i) => i.needed));
  // The right keeps the techniques used most: what you reach for instead matters as much as
  // the matches, and the ordering below still lines matches up straight across.
  const keepRight = fit(ranked((i) => i.used));
  const links = new Map<string, FlowLink>();
  const left = new Map<string, number>();
  const right = new Map<string, number>();
  const members = { left: new Map<string, Set<string>>(), right: new Map<string, Set<string>>() };
  const add = (side: Map<string, Set<string>>, node: string, technique: string) =>
    side.set(node, (side.get(node) ?? new Set()).add(technique));
  for (const i of items) {
    const n = keepLeft.has(i.needed) ? i.needed : OTHER;
    const u = keepRight.has(i.used) ? i.used : OTHER;
    left.set(n, (left.get(n) ?? 0) + 1);
    right.set(u, (right.get(u) ?? 0) + 1);
    add(members.left, n, i.needed);
    add(members.right, u, i.used);
    const outcome = outcomeOf(i);
    const key = `${n}|${u}|${outcome}`;
    const link = links.get(key) ?? { needed: n, used: u, count: 0, outcome };
    link.count += 1;
    links.set(key, link);
  }
  // Left: largest first, OTHER last. Right: a technique sits level with itself on the left, so
  // matches run straight across; techniques never needed come after, largest first.
  const node = (side: Map<string, Set<string>>) => ([id, count]: [string, number]): FlowNode => ({
    id,
    count,
    members: [...(side.get(id) ?? [])],
  });
  const leftNodes = [...left.entries()]
    .sort((a, b) => Number(a[0] === OTHER) - Number(b[0] === OTHER) || b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(node(members.left));
  const leftIndex = new Map(leftNodes.map((n, i) => [n.id, n.id === OTHER ? Infinity : i]));
  const rank = (id: string) => (id === OTHER ? Infinity : (leftIndex.get(id) ?? leftNodes.length - 0.5));
  const rightNodes = [...right.entries()]
    .sort((a, b) => rank(a[0]) - rank(b[0]) || Number(a[0] === OTHER) - Number(b[0] === OTHER) || b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(node(members.right));
  return { left: leftNodes, right: rightNodes, links: [...links.values()] };
}

// ---------------------------------------------------------------- progress

export const BASELINE = "baseline";

export interface ProgressPoint {
  key: string; // "baseline" or "YYYY-MM"
  label: string;
  total: number;
  matchRate: number; // 0..1
  worseRate: number; // 0..1
}

const monthKey = (iso: string) => iso.slice(0, 7);

function point(key: string, label: string, group: InsightItem[]): ProgressPoint {
  return {
    key,
    label,
    total: group.length,
    matchRate: group.filter((i) => i.match).length / group.length,
    worseRate: group.filter((i) => !i.match && i.worse).length / group.length,
  };
}

/**
 * Imports carry no real solve date, so they form one "Before Honeybon" baseline; the rest are
 * grouped by calendar month (UTC), oldest first.
 */
export function monthlyProgress(items: InsightItem[]): { baseline: ProgressPoint | null; months: ProgressPoint[] } {
  const imported = items.filter((i) => i.source === "import");
  const byMonth = new Map<string, InsightItem[]>();
  for (const i of items) {
    if (i.source === "import" || !i.solved_at) continue;
    const key = monthKey(i.solved_at);
    byMonth.set(key, [...(byMonth.get(key) ?? []), i]);
  }
  const months = [...byMonth.keys()].sort().map((key) => point(key, monthLabel(key), byMonth.get(key)!));
  return { baseline: imported.length ? point(BASELINE, "Before Honeybon", imported) : null, months };
}

export function monthLabel(key: string): string {
  const [y, m] = key.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleString(undefined, { month: "short", year: "numeric", timeZone: "UTC" });
}

export function inProgressGroup(i: InsightItem, key: string): boolean {
  return key === BASELINE ? i.source === "import" : i.source !== "import" && !!i.solved_at && monthKey(i.solved_at) === key;
}

// ---------------------------------------------------------------- selection (drives the problem list)

export type Selection =
  | "worse"
  | "low"
  | { kind: "cell"; needed: string; used: string }
  | { kind: "flow"; needed: string[]; used: string[]; outcome: Outcome; label: string }
  | { kind: "bar"; needed: string; outcome: Outcome }
  | { kind: "month"; key: string };

export function filterItems(items: InsightItem[], s: Selection): InsightItem[] {
  if (s === "worse") return items.filter((i) => !i.match && i.worse);
  if (s === "low") return items.filter((i) => i.low_confidence);
  if (s.kind === "cell") return items.filter((i) => i.needed === s.needed && i.used === s.used);
  if (s.kind === "flow") {
    return items.filter((i) => s.needed.includes(i.needed) && s.used.includes(i.used) && outcomeOf(i) === s.outcome);
  }
  if (s.kind === "bar") return items.filter((i) => i.needed === s.needed && outcomeOf(i) === s.outcome);
  return items.filter((i) => inProgressGroup(i, s.key));
}
