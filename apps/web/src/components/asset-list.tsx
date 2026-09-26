"use client";

import { clsx } from "clsx";
import { useMemo, useState } from "react";

import { assetValue, type ColorBy, kindLabel, percent, rgbCss, riskColor } from "@/lib/format";
import type { Asset, ForecastAsset } from "@/lib/types";

interface AssetListProps {
  assets: (Asset | ForecastAsset)[];
  colorBy: ColorBy;
  selectedId: string | null;
  onSelect: (assetId: string) => void;
}

const PAGE = 50;

export function AssetList({ assets, colorBy, selectedId, onSelect }: AssetListProps) {
  const [kinds, setKinds] = useState<string[]>([]);
  const [visible, setVisible] = useState(PAGE);

  const counts = useMemo(() => {
    const byKind = new Map<string, number>();
    for (const asset of assets) byKind.set(asset.kind, (byKind.get(asset.kind) ?? 0) + 1);
    return [...byKind.entries()].sort((a, b) => b[1] - a[1]);
  }, [assets]);
  const filtered = useMemo(
    () => (kinds.length ? assets.filter((a) => kinds.includes(a.kind)) : assets),
    [assets, kinds],
  );

  const toggle = (kind: string) => {
    setVisible(PAGE);
    setKinds((current) => (current.includes(kind) ? current.filter((k) => k !== kind) : [...current, kind]));
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap gap-1.5 px-4 pb-3" aria-label="Filter by asset kind">
        {counts.map(([kind, count]) => (
          <button
            key={kind}
            type="button"
            aria-pressed={kinds.includes(kind)}
            onClick={() => toggle(kind)}
            className={clsx(
              "rounded-full border px-2.5 py-0.5 text-xs",
              kinds.includes(kind)
                ? "border-[var(--accent)] bg-[var(--accent)]/15 text-[var(--text-primary)]"
                : "border-white/10 text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
            )}
          >
            {kindLabel(kind)} <span className="tabular-nums text-[var(--text-muted)]">{count}</span>
          </button>
        ))}
      </div>
      <ol className="min-h-0 flex-1 overflow-y-auto border-t border-white/10">
        {filtered.slice(0, visible).map((asset) => {
          const value = assetValue(asset, colorBy, null);
          const forecast = "p34" in asset;
          return (
            <li key={asset.asset_id}>
              <button
                type="button"
                onClick={() => onSelect(asset.asset_id)}
                className={clsx(
                  "grid w-full grid-cols-[2.5rem_1fr_auto] items-center gap-3 border-b border-white/5 px-4 py-2.5 text-left hover:bg-white/5",
                  asset.asset_id === selectedId && "bg-white/10",
                )}
              >
                <span className="font-mono text-xs tabular-nums text-[var(--text-muted)]">#{asset.rank}</span>
                <span className="min-w-0">
                  <span className="block truncate text-sm text-[var(--text-primary)]">
                    {asset.name ?? `Unnamed ${kindLabel(asset.kind).toLowerCase()}`}
                  </span>
                  <span className="block text-xs text-[var(--text-secondary)]">
                    {kindLabel(asset.kind)}
                    {forecast ? ` · gales ${percent((asset as ForecastAsset).p34)}` : ""}
                  </span>
                </span>
                <span className="flex items-center gap-2">
                  <span
                    className="size-2.5 rounded-full"
                    style={{ background: rgbCss(riskColor(value)) }}
                    aria-hidden
                  />
                  <span className="w-12 text-right font-mono text-sm tabular-nums text-[var(--text-primary)]">
                    {percent(colorBy === "gales" && forecast ? (asset as ForecastAsset).p34 : asset.p_outage)}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
        {visible < filtered.length && (
          <li className="p-3 text-center">
            <button
              type="button"
              onClick={() => setVisible((v) => v + PAGE)}
              className="text-sm text-[var(--accent)] hover:underline"
            >
              Show {Math.min(PAGE, filtered.length - visible)} more of {filtered.length - visible}
            </button>
          </li>
        )}
      </ol>
    </div>
  );
}
