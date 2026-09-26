"use client";

import { Pause, Play } from "lucide-react";
import { useEffect } from "react";

import { leadLabel, utcAndIst } from "@/lib/format";

interface TimelineProps {
  start: number;
  end: number;
  value: number;
  landfall: string;
  playing: boolean;
  onChange: (ms: number) => void;
  onPlayingChange: (playing: boolean) => void;
}

const STEP_MS = 15 * 60 * 1000; // matches the hazard model's densified track
const TICK_MS = 120; // playback advances one 15-minute step per tick

export function Timeline({ start, end, value, landfall, playing, onChange, onPlayingChange }: TimelineProps) {
  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => {
      const next = value + STEP_MS;
      if (next > end) onPlayingChange(false);
      else onChange(next);
    }, TICK_MS);
    return () => clearInterval(timer);
  }, [playing, value, end, onChange, onPlayingChange]);

  const iso = new Date(value).toISOString();
  const landfallPct = ((Date.parse(landfall) - start) / (end - start)) * 100;

  return (
    <div className="flex items-center gap-4 border-t border-white/10 bg-[var(--surface-1)] px-4 py-3">
      <button
        type="button"
        onClick={() => onPlayingChange(!playing)}
        className="grid size-9 shrink-0 place-items-center rounded-full bg-white/10 text-[var(--text-primary)] hover:bg-white/20"
        aria-label={playing ? "Pause replay" : "Play replay"}
      >
        {playing ? <Pause className="size-4" /> : <Play className="size-4" />}
      </button>
      <div className="relative flex-1">
        <input
          type="range"
          min={start}
          max={end}
          step={STEP_MS}
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
          className="w-full accent-[var(--accent)]"
          aria-label="Replay time"
        />
        {landfallPct >= 0 && landfallPct <= 100 && (
          <span
            className="pointer-events-none absolute -top-3 -translate-x-1/2 text-[10px] font-medium uppercase tracking-wide text-[var(--text-secondary)]"
            style={{ left: `${landfallPct}%` }}
          >
            landfall
          </span>
        )}
      </div>
      <div className="w-80 shrink-0 text-right">
        <div className="font-mono text-sm tabular-nums text-[var(--text-primary)]">{utcAndIst(iso)}</div>
        <div className="text-xs text-[var(--text-secondary)]">{leadLabel(iso, landfall)} to landfall</div>
      </div>
    </div>
  );
}
