import { useState } from "react";

import { techniqueLabel, type InsightItem } from "../../lib/api";
import { flowLinks, OTHER, OUTCOME_LABELS, type Flow, type FlowLink, type FlowNode, type Selection } from "../../lib/insightViews";
import { Card } from "../ui";
import { Legend, OUTCOME_STROKE } from "./Legend";

const W = 880;
const NODE_W = 8;
const LABEL_W = 170; // room for the labels outside each column
const GAP = 10;
const MIN_H = 240;

const linkKey = (l: FlowLink) => `${l.needed}|${l.used}|${l.outcome}`;
const name = (id: string) => (id === OTHER ? "Other" : techniqueLabel(id));

interface Placed extends FlowNode {
  y: number;
  h: number;
}

function place(nodes: FlowNode[], total: number, height: number): Map<string, Placed> {
  const unit = (height - GAP * Math.max(0, nodes.length - 1)) / total;
  const out = new Map<string, Placed>();
  let y = 0;
  for (const n of nodes) {
    const h = Math.max(2, n.count * unit);
    out.set(n.id, { ...n, y, h });
    y += h + GAP;
  }
  return out;
}

interface Ribbon {
  link: FlowLink;
  y0: number; // top at the left node
  h0: number;
  y1: number; // top at the right node
  h1: number;
}

/** Stacks each node's ribbons in the order of the nodes on the other side, so they cross least. */
function layoutRibbons(flow: Flow, left: Map<string, Placed>, right: Map<string, Placed>): Ribbon[] {
  const leftIndex = new Map(flow.left.map((n, i) => [n.id, i]));
  const rightIndex = new Map(flow.right.map((n, i) => [n.id, i]));
  const scale = (node: Placed) => node.h / node.count;
  const out = new Map<string, number>();
  const into = new Map<string, number>();
  const ribbons = new Map<FlowLink, Ribbon>();
  const byLeft = [...flow.links].sort(
    (a, b) => leftIndex.get(a.needed)! - leftIndex.get(b.needed)! || rightIndex.get(a.used)! - rightIndex.get(b.used)!,
  );
  for (const link of byLeft) {
    const l = left.get(link.needed)!;
    const h0 = link.count * scale(l);
    const y0 = l.y + (out.get(link.needed) ?? 0);
    out.set(link.needed, (out.get(link.needed) ?? 0) + h0);
    ribbons.set(link, { link, y0, h0, y1: 0, h1: 0 });
  }
  const byRight = [...flow.links].sort(
    (a, b) => rightIndex.get(a.used)! - rightIndex.get(b.used)! || leftIndex.get(a.needed)! - leftIndex.get(b.needed)!,
  );
  for (const link of byRight) {
    const r = right.get(link.used)!;
    const ribbon = ribbons.get(link)!;
    ribbon.h1 = link.count * scale(r);
    ribbon.y1 = r.y + (into.get(link.used) ?? 0);
    into.set(link.used, (into.get(link.used) ?? 0) + ribbon.h1);
  }
  return byLeft.map((link) => ribbons.get(link)!);
}

/** Needed techniques (left) flow into the ones used (right). Straight across = a match. */
export function FlowChart({
  items,
  selection,
  onSelect,
}: {
  items: InsightItem[];
  selection: Selection;
  onSelect: (s: Selection) => void;
}) {
  const flow = flowLinks(items);
  const [hover, setHover] = useState<FlowLink | null>(null);
  const total = items.length;
  const height = Math.max(MIN_H, Math.max(flow.left.length, flow.right.length) * 30);
  const left = place(flow.left, total, height);
  const right = place(flow.right, total, height);
  const ribbons = layoutRibbons(flow, left, right);

  const x0 = LABEL_W + NODE_W;
  const x1 = W - LABEL_W - NODE_W;
  const mid = (x0 + x1) / 2;
  const selected = (link: FlowLink) =>
    typeof selection === "object" &&
    selection.kind === "flow" &&
    selection.label === linkKey(link);
  const describe = (link: FlowLink) =>
    `${name(link.needed)} needed → ${name(link.used)} used: ${link.count} problem${link.count === 1 ? "" : "s"}` +
    ` · ${OUTCOME_LABELS[link.outcome].toLowerCase()}`;

  return (
    <Card className="flex flex-col gap-3 p-4">
      <Legend />
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 -14 ${W} ${height + 22}`}
          width={W}
          className="mx-auto block h-auto max-w-full min-w-[600px]"
          role="img"
          aria-label="Flow from the technique each problem needed to the one you used"
          onMouseLeave={() => setHover(null)}
        >
          <text x={LABEL_W + NODE_W} y={-4} textAnchor="end" className="fill-text-faint text-[11px]">
            needed
          </text>
          <text x={W - LABEL_W - NODE_W} y={-4} className="fill-text-faint text-[11px]">
            used
          </text>
          {ribbons.map(({ link, y0, h0, y1, h1 }) => {
            const dim = hover && hover !== link;
            const on = hover === link || selected(link);
            return (
              <path
                key={linkKey(link)}
                d={`M${x0},${y0} C${mid},${y0} ${mid},${y1} ${x1},${y1} L${x1},${y1 + h1} C${mid},${y1 + h1} ${mid},${y0 + h0} ${x0},${y0 + h0} Z`}
                fill={OUTCOME_STROKE[link.outcome]}
                fillOpacity={on ? 0.85 : dim ? 0.12 : 0.45}
                stroke="var(--surface)"
                strokeWidth={1}
                className="cursor-pointer transition-[fill-opacity]"
                onMouseEnter={() => setHover(link)}
                onClick={() =>
                  onSelect({
                    kind: "flow",
                    needed: left.get(link.needed)!.members,
                    used: right.get(link.used)!.members,
                    outcome: link.outcome,
                    label: linkKey(link),
                  })
                }
              >
                <title>{describe(link)}</title>
              </path>
            );
          })}
          {[...left.values()].map((n) => (
            <g key={`l${n.id}`}>
              <rect x={LABEL_W} y={n.y} width={NODE_W} height={n.h} rx={2} className="fill-text-muted" />
              <text x={LABEL_W - 8} y={n.y + n.h / 2} dy="0.35em" textAnchor="end" className="fill-text-secondary text-[12px]">
                {name(n.id)} <tspan className="fill-text-faint">{n.count}</tspan>
              </text>
            </g>
          ))}
          {[...right.values()].map((n) => (
            <g key={`r${n.id}`}>
              <rect x={W - LABEL_W - NODE_W} y={n.y} width={NODE_W} height={n.h} rx={2} className="fill-text-muted" />
              <text x={W - LABEL_W + 8} y={n.y + n.h / 2} dy="0.35em" className="fill-text-secondary text-[12px]">
                {name(n.id)} <tspan className="fill-text-faint">{n.count}</tspan>
              </text>
            </g>
          ))}
        </svg>
      </div>
      <p className="min-h-5 text-xs text-text-muted" aria-live="polite">
        {hover ? describe(hover) : "Hover a ribbon for details; click it to list its problems. Blue ribbons are problems where you used the technique."}
      </p>
      <ul className="sr-only">
        {flow.links.map((l) => (
          <li key={linkKey(l)}>{describe(l)}</li>
        ))}
      </ul>
    </Card>
  );
}
