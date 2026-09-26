"use client";

/**
 * Data hooks for the geo API. Requests go through the `/api/geo` rewrite (see next.config.ts), so the browser only
 * talks to this origin and the API location stays server-side configuration.
 */
import useSWR, { type SWRConfiguration } from "swr";

import type {
  Asset,
  AssetDetail,
  Backtest,
  ForecastAsset,
  HazardSnapshot,
  Page,
  ReplayMode,
  ScenarioDetail,
  TrackFeatureCollection,
} from "./types";

export const GEO_PREFIX = "/api/geo";

/** Fetch JSON from the geo API, raising with the server's message on non-2xx responses. */
export async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${GEO_PREFIX}${path}`);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}: ${await response.text()}`);
  }
  return (await response.json()) as T;
}

const STATIC: SWRConfiguration = { revalidateOnFocus: false, revalidateIfStale: false, dedupingInterval: 60_000 };

export function useScenario(id: string) {
  return useSWR<ScenarioDetail>(`/scenarios/${id}`, fetchJson, STATIC);
}

export function useTrack(id: string) {
  return useSWR<TrackFeatureCollection>(`/scenarios/${id}/track`, fetchJson, STATIC);
}

/** Every asset in rank order for the selected replay (the full list feeds the map; ~250 kB gzipped). */
export function useAssets(id: string, mode: ReplayMode) {
  const path = mode.kind === "forecast" ? `/scenarios/${id}/forecasts/${mode.key}/assets` : `/scenarios/${id}/assets`;
  return useSWR<Page<Asset | ForecastAsset>>(`${path}?limit=5000`, fetchJson, { ...STATIC, keepPreviousData: true });
}

export function useForecastTracks(id: string, mode: ReplayMode) {
  const key = mode.kind === "forecast" ? `/scenarios/${id}/forecasts/${mode.key}/tracks` : null;
  return useSWR<TrackFeatureCollection>(key, fetchJson, STATIC);
}

export function useAssetDetail(id: string, assetId: string | null) {
  return useSWR<AssetDetail>(assetId ? `/scenarios/${id}/assets/${assetId}` : null, fetchJson, STATIC);
}

export function useBacktest(id: string) {
  return useSWR<Backtest>(`/scenarios/${id}/backtest`, fetchJson, STATIC);
}

/** Wind at every asset at one moment; `at` should be quantised by the caller so scrubbing reuses cached snapshots. */
export function useHazard(id: string, at: string | null) {
  return useSWR<HazardSnapshot>(at ? `/scenarios/${id}/hazard?at=${encodeURIComponent(at)}` : null, fetchJson, {
    ...STATIC,
    keepPreviousData: true,
  });
}
