import { Link } from "react-router-dom";

import { techniqueLabel, type InsightCard } from "../lib/api";
import { Card } from "./ui";

/** The single strongest avoidance pattern, shown on Today and Insights. */
export function InsightCardView({ card, compact = false }: { card: InsightCard; compact?: boolean }) {
  const technique = techniqueLabel(card.technique).toLowerCase();
  return (
    <Card className="flex flex-col gap-2 border-attention/40 p-5">
      <p className="text-xs font-medium text-attention-text">Your strongest pattern</p>
      <p className="text-[15px] leading-relaxed text-text">
        You avoid <strong>{technique}</strong>: in {card.avoided} of {card.out_of} problems where it was optimal, you
        used something else, most often {techniqueLabel(card.usual_instead).toLowerCase()}.
        {card.worse > 0 &&
          ` ${card.worse === card.avoided ? "Every one" : `${card.worse} of them`} ended with a worse complexity.`}
      </p>
      {!compact && (
        <p className="text-xs text-text-muted">
          Problems where the AI and LeetCode's tags disagree are left out of this.
        </p>
      )}
      {compact && (
        <Link to="/insights" className="text-[13px] text-accent-text">
          See the problems in Insights
        </Link>
      )}
    </Card>
  );
}
