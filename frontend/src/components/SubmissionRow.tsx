import { Link } from "react-router-dom";

import { techniqueLabel, type SubmissionListItem } from "../lib/api";
import { Chip, StatusChip } from "./StatusChip";

export function SubmissionRow({ item, active, time }: { item: SubmissionListItem; active: boolean; time: string }) {
  const r = item.review;
  const matched = r?.used_technique ? r.optimal_techniques.includes(r.used_technique) : false;
  const worse = r
    ? r.time_class !== r.optimal_time_class ||
      (r.optimal_space_class != null && r.space_class !== r.optimal_space_class)
    : false;
  return (
    <Link
      to={`/review/${item.id}`}
      aria-current={active || undefined}
      className={`flex flex-wrap items-center gap-x-3.5 gap-y-2 border-b border-divider px-4 py-3.5 text-text no-underline last:border-b-0 hover:bg-raised ${
        active ? "bg-selected" : ""
      }`}
    >
      <div className="min-w-0 flex-[1_1_220px]">
        <div className="truncate font-medium">{item.problem.title ?? item.problem.slug}</div>
        <div className="text-[12.5px] text-text-muted">
          {[item.problem.difficulty, item.language, item.problem.platform].filter(Boolean).join(" · ")}
        </div>
      </div>
      {r?.used_technique &&
        (matched && !worse ? (
          <Chip>{techniqueLabel(r.used_technique)} · match</Chip>
        ) : (
          <Chip attention={worse}>
            {techniqueLabel(r.used_technique)} → {r.optimal_techniques.map(techniqueLabel).join(" / ")}
          </Chip>
        ))}
      <StatusChip status={item.status} />
      <span className="font-mono text-xs text-text-faint">{time}</span>
    </Link>
  );
}
