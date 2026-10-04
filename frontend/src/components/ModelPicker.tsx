import { useEffect, useState } from "react";

import { inputClass } from "./ui";

const OTHER = "__other__";

/** A model dropdown with the provider's known models plus "Other…" for typing any model name. */
export function ModelPicker({
  id,
  models,
  value,
  onChange,
  compact = false,
}: {
  id: string;
  models: string[];
  value: string;
  onChange: (model: string) => void;
  compact?: boolean;
}) {
  const known = models.includes(value);
  const [custom, setCustom] = useState(!known && value !== "");

  // Switching provider swaps the list; keep "Other" open only if the value is still unknown.
  useEffect(() => setCustom(!models.includes(value) && value !== ""), [models, value]);

  const size = compact ? "py-1.5 text-xs" : "";
  return (
    <div className="flex flex-wrap gap-2">
      <select
        id={id}
        value={custom ? OTHER : value}
        onChange={(e) => {
          if (e.target.value === OTHER) {
            setCustom(true);
            onChange("");
          } else {
            setCustom(false);
            onChange(e.target.value);
          }
        }}
        className={`${inputClass} ${size} w-auto font-mono text-xs`}
      >
        {!custom && !value && <option value="">Choose a model</option>}
        {models.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
        <option value={OTHER}>Other…</option>
      </select>
      {custom && (
        <>
          <label htmlFor={`${id}-custom`} className="sr-only">
            Model name
          </label>
          <input
            id={`${id}-custom`}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="Type a model name"
            autoFocus
            className={`${inputClass} ${size} min-w-48 flex-1 font-mono text-xs`}
          />
        </>
      )}
    </div>
  );
}
