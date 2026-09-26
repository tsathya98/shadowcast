"use client";

import { clsx } from "clsx";
import dynamic from "next/dynamic";
import Image from "next/image";
import { useCallback, useMemo, useState } from "react";

import { AssetDetail } from "@/components/asset-detail";
import { AssetList } from "@/components/asset-list";
import { BacktestPanel } from "@/components/backtest-panel";
import { PreparePanel } from "@/components/prepare-panel";
import { ReplayStrip } from "@/components/replay-strip";
import { Timeline } from "@/components/timeline";
import { useAssets, useForecastTracks, useHazard, useScenario, useTrack } from "@/lib/api";
import { type ColorBy, kindLabel, rgbCss, riskColor } from "@/lib/format";
import type { ReplayMode, ScenarioSummary } from "@/lib/types";

// deck.gl and the Maps JS API need the browser: never render the map on the server.
const MapView = dynamic(() => import("@/components/map-view").then((m) => m.MapView), {
  ssr: false,
  loading: () => <div className="absolute inset-0 animate-pulse bg-white/5" />,
});

const QUANTUM_MS = 15 * 60 * 1000;
const LEGENDS: Record<ColorBy, string> = {
  risk: "Grid-outage probability",
  gales: "Ensemble members bringing gales (34 kt)",
  wind: "Modelled wind now (0–120 kt)",
};

interface ConsoleProps {
  scenarios: ScenarioSummary[];
  mapsApiKey: string;
}

export function Console({ scenarios, mapsApiKey }: ConsoleProps) {
  const [scenarioId, setScenarioId] = useState(scenarios[0].id);
  const [mode, setMode] = useState<ReplayMode>({ kind: "best-track" });
  const [tab, setTab] = useState<"prioritise" | "prepare" | "prove">("prioritise");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [colorBy, setColorBy] = useState<ColorBy>("risk");
  const [scrub, setScrub] = useState<{ scenarioId: string; ms: number } | null>(null);
  const [playing, setPlaying] = useState(false);

  const { data: scenario, error: scenarioError } = useScenario(scenarioId);
  const { data: track } = useTrack(scenarioId);
  const { data: page, isLoading: assetsLoading } = useAssets(scenarioId, mode);
  const { data: members } = useForecastTracks(scenarioId, mode);

  const span = useMemo(() => {
    const times = (track?.features ?? [])
      .map((f) => f.properties.time)
      .filter((t): t is string => typeof t === "string")
      .map(Date.parse);
    return times.length ? { start: Math.min(...times), end: Math.max(...times) } : null;
  }, [track]);

  // Each scenario opens at landfall; once the user scrubs, their position wins until the scenario changes.
  const landfallMs = scenario && span ? Math.min(span.end, Math.max(span.start, Date.parse(scenario.landfall))) : null;
  const timeMs = scrub?.scenarioId === scenarioId ? scrub.ms : landfallMs;
  const setTimeMs = useCallback((ms: number) => setScrub({ scenarioId, ms }), [scenarioId]);

  const quantised = timeMs == null ? null : new Date(Math.round(timeMs / QUANTUM_MS) * QUANTUM_MS).toISOString();
  const { data: hazard } = useHazard(scenarioId, mode.kind === "best-track" ? quantised : null);
  const windById = useMemo(
    () => (hazard ? new Map(hazard.asset_ids.map((id, i) => [id, hazard.wind_kt[i]] as [string, number])) : null),
    [hazard],
  );

  const assets = useMemo(() => page?.items ?? [], [page]);
  const selected = assets.find((a) => a.asset_id === selectedId) ?? null;

  const changeScenario = (id: string) => {
    setScenarioId(id);
    setMode({ kind: "best-track" });
    setColorBy("risk");
    setSelectedId(null);
    setPlaying(false);
  };
  const changeMode = (next: ReplayMode) => {
    setMode(next);
    setColorBy(next.kind === "forecast" ? "gales" : "risk");
    setSelectedId(null);
  };
  // Selecting on the map opens the asset, except while talking to the analyst, where it sets "this asset".
  const select = useCallback((id: string | null) => {
    setSelectedId(id);
    if (id) setTab((current) => (current === "prepare" ? current : "prioritise"));
  }, []);
  const openAsset = useCallback((id: string) => {
    setSelectedId(id);
    setTab("prioritise");
  }, []);

  if (scenarioError) {
    return (
      <div className="grid h-dvh place-items-center text-[var(--text-secondary)]">
        Could not load the scenario: {String(scenarioError.message)}
      </div>
    );
  }

  const colorOptions: ColorBy[] = mode.kind === "forecast" ? ["gales", "risk"] : ["risk", "wind"];
  const forecastKey = mode.kind === "forecast" ? mode.key : null;
  const suggestions = [
    selected
      ? `Why is ${selected.name ?? kindLabel(selected.kind)} ranked #${selected.rank}?`
      : "Which hospitals and cyclone shelters are most at risk?",
    forecastKey
      ? "How far do the ensemble members agree, and what could still change?"
      : "How well did the model predict where the lights went out?",
    "Draft an advisory for the five highest-priority assets in English, Hindi and Odia",
  ];

  return (
    <div className="grid h-dvh grid-rows-[auto_1fr_auto] bg-[var(--surface-0)] text-[var(--text-primary)]">
      <header className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-white/10 bg-[var(--surface-1)] px-4 py-3">
        <div className="flex items-center gap-2">
          <Image src="/logo.svg" alt="" width={28} height={28} priority />
          <span className="text-lg font-semibold tracking-tight">ShadowCast</span>
          <span className="hidden text-xs text-[var(--text-muted)] md:inline">
            see the storm&apos;s shadow before it falls
          </span>
        </div>
        <label className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
          Storm
          <select
            value={scenarioId}
            onChange={(event) => changeScenario(event.target.value)}
            className="rounded-md border border-white/15 bg-[var(--surface-2)] px-2 py-1 text-[var(--text-primary)]"
          >
            {scenarios.map((s) => (
              <option key={s.id} value={s.id}>
                {s.storm} {s.season} · {s.region.name}
              </option>
            ))}
          </select>
        </label>
        <div className="min-w-0 flex-1">
          <ReplayStrip forecasts={scenario?.forecasts ?? []} mode={mode} onChange={changeMode} />
        </div>
      </header>

      <main className="grid min-h-0 grid-cols-1 lg:grid-cols-[1fr_26rem]">
        <section className="relative min-h-[50vh]" aria-label="Map of assets and storm">
          {scenario && (
            <MapView
              apiKey={mapsApiKey}
              region={scenario.region}
              assets={assets}
              colorBy={colorBy}
              windById={windById}
              track={track}
              members={members}
              storm={mode.kind === "best-track" ? (hazard?.storm ?? null) : null}
              selectedId={selectedId}
              onSelect={select}
            />
          )}
          <div className="pointer-events-auto absolute bottom-4 left-4 w-72 rounded-xl border border-white/10 bg-[var(--surface-1)]/90 p-3 backdrop-blur">
            <div className="mb-2 flex gap-1" role="radiogroup" aria-label="Colour assets by">
              {colorOptions.map((option) => (
                <button
                  key={option}
                  type="button"
                  role="radio"
                  aria-checked={colorBy === option}
                  onClick={() => setColorBy(option)}
                  className={clsx(
                    "rounded-md px-2 py-0.5 text-xs",
                    colorBy === option
                      ? "bg-white/15 text-[var(--text-primary)]"
                      : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
                  )}
                >
                  {option === "risk" ? "Outage risk" : option === "gales" ? "Gale chance" : "Wind now"}
                </button>
              ))}
            </div>
            <div className="text-xs text-[var(--text-secondary)]">{LEGENDS[colorBy]}</div>
            <div
              className="mt-1.5 h-2 rounded-full"
              style={{
                background: `linear-gradient(90deg, ${[0, 0.25, 0.5, 0.75, 1].map((t) => rgbCss(riskColor(t))).join(", ")})`,
              }}
              aria-hidden
            />
            <div className="mt-1 flex justify-between font-mono text-[10px] text-[var(--text-muted)]">
              <span>{colorBy === "wind" ? "0 kt" : "0%"}</span>
              <span>{colorBy === "wind" ? "120 kt" : "100%"}</span>
            </div>
            {mode.kind === "forecast" && (
              <div className="mt-2 flex items-center gap-2 text-[11px] text-[var(--text-secondary)]">
                <span className="h-0.5 w-5 bg-[var(--series-1)]" aria-hidden /> ECMWF ensemble members
              </div>
            )}
          </div>
        </section>

        <aside className="flex min-h-0 flex-col border-l border-white/10 bg-[var(--surface-1)]">
          <div className="flex gap-4 px-4 pt-3" role="tablist">
            {(["prioritise", "prepare", "prove"] as const).map((name) => (
              <button
                key={name}
                type="button"
                role="tab"
                aria-selected={tab === name}
                onClick={() => setTab(name)}
                className={clsx(
                  "border-b-2 pb-2 text-sm font-medium capitalize",
                  tab === name
                    ? "border-[var(--accent)] text-[var(--text-primary)]"
                    : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
                )}
              >
                {name}
              </button>
            ))}
          </div>
          {/* Kept mounted while hidden so the conversation survives tab switches; a new replay starts a new one. */}
          <div className={clsx("min-h-0 flex-1 flex-col pt-3", tab === "prepare" ? "flex" : "hidden")}>
            <PreparePanel
              key={`${scenarioId}:${forecastKey ?? "best-track"}`}
              context={{ scenarioId, forecastKey, selectedAssetId: selectedId }}
              suggestions={suggestions}
              onSelectAsset={openAsset}
            />
          </div>
          <div className={clsx("min-h-0 flex-1 flex-col pt-3", tab === "prepare" ? "hidden" : "flex")}>
            {tab === "prove" && scenario ? (
              <BacktestPanel scenario={scenario} />
            ) : selected ? (
              <AssetDetail scenarioId={scenarioId} asset={selected} onBack={() => setSelectedId(null)} />
            ) : assetsLoading && !page ? (
              <div className="space-y-2 px-4">
                {Array.from({ length: 8 }, (_, i) => (
                  <div key={i} className="h-11 animate-pulse rounded bg-white/5" />
                ))}
              </div>
            ) : (
              <>
                <p className="px-4 pb-2 text-xs text-[var(--text-secondary)]">
                  {page?.total ?? 0} assets ranked by{" "}
                  {mode.kind === "forecast"
                    ? "outage risk, then gale chance × criticality"
                    : "grid-outage probability × criticality"}
                </p>
                <AssetList assets={assets} colorBy={colorBy} selectedId={selectedId} onSelect={select} />
              </>
            )}
          </div>
        </aside>
      </main>

      {scenario && span && timeMs != null && (
        <Timeline
          start={span.start}
          end={span.end}
          value={timeMs}
          landfall={scenario.landfall}
          playing={playing}
          onChange={setTimeMs}
          onPlayingChange={setPlaying}
        />
      )}
    </div>
  );
}
