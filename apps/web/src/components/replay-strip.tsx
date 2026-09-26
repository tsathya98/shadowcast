"use client";

import { clsx } from "clsx";

import { compactNumber } from "@/lib/format";
import type { ForecastSummary, ReplayMode } from "@/lib/types";

interface ReplayStripProps {
  forecasts: ForecastSummary[];
  mode: ReplayMode;
  onChange: (mode: ReplayMode) => void;
}

/** Switch between the best-track (hindsight) replay and each as-issued ensemble forecast. */
export function ReplayStrip({ forecasts, mode, onChange }: ReplayStripProps) {
  const chip = (active: boolean) =>
    clsx(
      "shrink-0 rounded-lg border px-3 py-1.5 text-left transition-colors",
      active
        ? "border-[var(--accent)] bg-[var(--accent)]/15 text-[var(--text-primary)]"
        : "border-white/10 text-[var(--text-secondary)] hover:border-white/25 hover:text-[var(--text-primary)]",
    );

  return (
    <div className="flex items-stretch gap-2 overflow-x-auto" role="radiogroup" aria-label="Replay mode">
      {forecasts.length > 0 && (
        <span className="self-center pr-1 text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
          ECMWF ensemble as issued
        </span>
      )}
      {forecasts.map((forecast) => {
        const active = mode.kind === "forecast" && mode.key === forecast.key;
        return (
          <button
            key={forecast.key}
            type="button"
            role="radio"
            aria-checked={active}
            className={chip(active)}
            onClick={() => onChange({ kind: "forecast", key: forecast.key })}
          >
            <div className="text-sm font-semibold tabular-nums">T−{Math.round(forecast.lead_h)} h</div>
            <div className="text-[11px] tabular-nums">
              {forecast.members} members · {compactNumber(forecast.assets_likely_gale)} likely gales
            </div>
          </button>
        );
      })}
      <button
        type="button"
        role="radio"
        aria-checked={mode.kind === "best-track"}
        className={chip(mode.kind === "best-track")}
        onClick={() => onChange({ kind: "best-track" })}
      >
        <div className="text-sm font-semibold">Best track</div>
        <div className="text-[11px]">hindsight · backtest</div>
      </button>
    </div>
  );
}
