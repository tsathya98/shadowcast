"use client";

import { ArrowLeft } from "lucide-react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useAssetDetail } from "@/lib/api";
import { compactNumber, kindLabel, knots, percent, utcAndIst } from "@/lib/format";
import type { Asset, ForecastAsset } from "@/lib/types";

interface AssetDetailProps {
  scenarioId: string;
  asset: Asset | ForecastAsset;
  onBack: () => void;
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg bg-white/5 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">{label}</div>
      <div className="font-mono text-lg tabular-nums text-[var(--text-primary)]">{value}</div>
      {hint && <div className="text-[11px] text-[var(--text-secondary)]">{hint}</div>}
    </div>
  );
}

/** Wind at the asset through the storm's life (best-track replay), with gale and hurricane-force references. */
function WindChart({ scenarioId, assetId }: { scenarioId: string; assetId: string }) {
  const { data, isLoading } = useAssetDetail(scenarioId, assetId);
  if (isLoading || !data) return <div className="h-40 animate-pulse rounded-lg bg-white/5" />;
  const points = data.timeline.map((p) => ({ t: Date.parse(p.time), wind: p.wind_kt }));
  const hours = (ms: number) => new Date(ms).toISOString().slice(8, 13).replace("T", " ") + "Z";
  return (
    <div className="h-44" aria-label="Modelled wind at this asset over time">
      <ResponsiveContainer>
        <LineChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
          <CartesianGrid stroke="rgb(255 255 255 / 0.06)" vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            domain={["dataMin", "dataMax"]}
            tickFormatter={hours}
            tick={{ fontSize: 10, fill: "var(--text-muted)" }}
            stroke="transparent"
            minTickGap={40}
          />
          <YAxis unit=" kt" tick={{ fontSize: 10, fill: "var(--text-muted)" }} stroke="transparent" width={56} />
          <ReferenceLine
            y={34}
            stroke="var(--text-muted)"
            strokeDasharray="4 4"
            label={{ value: "gale", fill: "var(--text-muted)", fontSize: 10, position: "insideTopLeft" }}
          />
          <ReferenceLine
            y={64}
            stroke="var(--text-muted)"
            strokeDasharray="4 4"
            label={{ value: "hurricane force", fill: "var(--text-muted)", fontSize: 10, position: "insideTopLeft" }}
          />
          <Tooltip
            contentStyle={{
              background: "var(--surface-2)",
              border: "1px solid rgb(255 255 255 / 0.1)",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelFormatter={(value) => utcAndIst(new Date(Number(value)).toISOString())}
            formatter={(value) => [knots(Number(value)), "wind"]}
          />
          <Line dataKey="wind" stroke="var(--series-1)" strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function AssetDetail({ scenarioId, asset, onBack }: AssetDetailProps) {
  const forecast = "p34" in asset ? (asset as ForecastAsset) : null;
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-4 pb-4">
      <button
        type="button"
        onClick={onBack}
        className="mb-3 flex items-center gap-1 self-start text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
      >
        <ArrowLeft className="size-4" /> Back to priorities
      </button>
      <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">
        #{asset.rank} · {kindLabel(asset.kind)} · {asset.source}
      </div>
      <h2 className="mt-0.5 text-lg font-semibold text-[var(--text-primary)]">
        {asset.name ?? `Unnamed ${kindLabel(asset.kind).toLowerCase()}`}
      </h2>

      <div className="mt-3 grid grid-cols-2 gap-2">
        <Stat
          label="Grid-outage probability"
          value={percent(asset.p_outage)}
          hint={`criticality ${asset.criticality}/5`}
        />
        {forecast ? (
          <Stat
            label="Members bringing gales"
            value={percent(forecast.p34)}
            hint={`hurricane-force ${percent(forecast.p64)}`}
          />
        ) : (
          <Stat
            label="Peak modelled wind"
            value={knots(asset.peak_wind_kt)}
            hint={`${Math.round(asset.min_dist_km)} km from centre`}
          />
        )}
        <Stat label="Gales arrive" value={asset.gale_arrival ? utcAndIst(asset.gale_arrival).split(" · ")[0] : "–"} />
        <Stat
          label="People within 2 km"
          value={compactNumber(asset.population)}
          hint={asset.elevation_m != null ? `${asset.elevation_m.toFixed(1)} m elevation` : undefined}
        />
      </div>

      {forecast ? (
        <p className="mt-3 text-sm text-[var(--text-secondary)]">
          Ensemble peak wind {knots(forecast.wind_p10)}–{knots(forecast.wind_p90)} (10–90%), median{" "}
          {knots(forecast.peak_wind_kt)}, across {forecast.members} members.
        </p>
      ) : (
        <div className="mt-4">
          <div className="mb-1 text-xs uppercase tracking-wide text-[var(--text-muted)]">
            Modelled wind at this asset
          </div>
          <WindChart scenarioId={scenarioId} assetId={asset.asset_id} />
        </div>
      )}

      {asset.observed_loss_pct != null && (
        <p className="mt-3 rounded-lg border border-white/10 px-3 py-2 text-sm text-[var(--text-secondary)]">
          Observed after landfall (VIIRS night lights around this substation):{" "}
          {asset.observed_loss_pct >= 0 ? (
            <>
              fell <span className="font-mono text-[var(--text-primary)]">{Math.round(asset.observed_loss_pct)}%</span>
            </>
          ) : (
            <>no loss ({Math.round(-asset.observed_loss_pct)}% brighter)</>
          )}
          .
        </p>
      )}

      <h3 className="mt-4 text-xs uppercase tracking-wide text-[var(--text-muted)]">Why it ranks here</h3>
      <ul className="mt-1.5 space-y-1.5">
        {asset.reasons.map((reason) => (
          <li key={reason} className="flex gap-2 text-sm leading-snug text-[var(--text-secondary)]">
            <span className="mt-1.5 size-1 shrink-0 rounded-full bg-[var(--text-muted)]" aria-hidden />
            {reason}
          </li>
        ))}
      </ul>
    </div>
  );
}
