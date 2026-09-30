"use client";

import { useState } from "react";

import { compactNumber } from "@/lib/format";
import { AS_MODELLED, type WhatIf } from "@/lib/whatif";

interface WhatIfCardProps {
  value: WhatIf;
  onChange: (value: WhatIf) => void;
  /** Sites at ≥50% outage, and flooded sites, for the modelled storm and under the what-if. */
  counts: { outage: [number, number]; flooded: [number, number] };
}

const SLIDERS = [
  {
    key: "wind",
    label: "Storm intensity",
    min: 0.7,
    max: 1.3,
    step: 0.05,
    show: (v: number) => `${v >= 1 ? "+" : ""}${Math.round((v - 1) * 100)}%`,
  },
  { key: "tide_m", label: "High tide", min: 0, max: 2, step: 0.25, show: (v: number) => `+${v.toFixed(2)} m` },
  {
    key: "rain",
    label: "Rainfall",
    min: 0.5,
    max: 2,
    step: 0.1,
    show: (v: number) => `${v >= 1 ? "+" : ""}${Math.round((v - 1) * 100)}%`,
  },
] as const;

/** Stress-test the storm: scale its winds and rain, add a high tide, and watch the map and the ranking move. */
export function WhatIfCard({ value, onChange, counts }: WhatIfCardProps) {
  const [open, setOpen] = useState(false);
  const changed = value.wind !== 1 || value.tide_m !== 0 || value.rain !== 1;

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="segment glass !px-3 !py-1.5">
        What-if simulation{changed ? " · on" : ""}
      </button>
    );
  }
  return (
    <div className="glass w-80 rounded-2xl p-3">
      <div className="flex items-center justify-between">
        <span className="label">What-if simulation</span>
        <div className="flex gap-1">
          <button type="button" className="segment" disabled={!changed} onClick={() => onChange(AS_MODELLED)}>
            Reset
          </button>
          <button type="button" className="segment" onClick={() => setOpen(false)} aria-label="Hide what-if">
            Hide
          </button>
        </div>
      </div>
      {SLIDERS.map((slider) => (
        <label key={slider.key} className="mt-2.5 block text-xs text-[var(--text-secondary)]">
          <span className="flex justify-between">
            {slider.label}
            <span className="readout text-[var(--text-primary)]">{slider.show(value[slider.key])}</span>
          </span>
          <input
            type="range"
            min={slider.min}
            max={slider.max}
            step={slider.step}
            value={value[slider.key]}
            onChange={(event) => onChange({ ...value, [slider.key]: Number(event.target.value) })}
            className="mt-1 w-full accent-[var(--accent)]"
          />
        </label>
      ))}
      <p className="mt-2.5 text-xs text-[var(--text-secondary)]">
        ≥50% outage{" "}
        <span className="readout text-[var(--text-primary)]">
          {compactNumber(counts.outage[0])} → {compactNumber(counts.outage[1])}
        </span>{" "}
        · flooded{" "}
        <span className="readout text-[var(--text-primary)]">
          {compactNumber(counts.flooded[0])} → {compactNumber(counts.flooded[1])}
        </span>
      </p>
      <p className="label mt-1.5 normal-case">
        Trained outage model re-run at the new winds; surge grows with wind², plus the tide
      </p>
    </div>
  );
}
