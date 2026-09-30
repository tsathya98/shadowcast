import type { Asset, OutageModel } from "@/lib/types";

/** Inland surge attenuation, as in the geo service: 1 m per 14.5 km (US Army Corps of Engineers 1963). */
const SURGE_DECAY_M_PER_KM = 1 / 14.5;

export interface WhatIf {
  /** Multiplier on the modelled winds (1 = the storm as modelled). */
  wind: number;
  /** Extra coastal water level in metres: high tide or sea-level rise, which the surge model leaves out. */
  tide_m: number;
  /** Multiplier on the modelled storm-total rain. */
  rain: number;
}

export const AS_MODELLED: WhatIf = { wind: 1, tide_m: 0, rain: 1 };

/**
 * Re-score every asset under a stronger or weaker storm, a higher sea and more or less rain, and re-rank them.
 *
 * Outage comes from the trained model at the scaled wind. Surge scales with the wind squared (both wind setup and the
 * inverse barometer do), the tide adds on top at the coast, and the level decays inland and is compared with the
 * ground exactly as the geo service does. Rain scales directly. Reasons are left as they were for the modelled storm.
 *
 * @param assets Best-track assets in rank order.
 * @param model The trained outage model (logistic in peak wind).
 * @param whatIf The scenario to apply.
 * @returns The same assets, re-scored and sorted by the new rank; the input when `whatIf` is the modelled storm.
 */
export function applyWhatIf(assets: Asset[], model: OutageModel, whatIf: WhatIf): Asset[] {
  if (whatIf.wind === 1 && whatIf.tide_m === 0 && whatIf.rain === 1) return assets;
  const setup = whatIf.wind ** 2;
  return assets
    .map((asset) => {
      const wind = asset.peak_wind_kt == null ? null : asset.peak_wind_kt * whatIf.wind;
      const p = 1 / (1 + Math.exp(-Math.min(60, Math.max(-60, model.intercept + model.slope * (wind ?? 0)))));
      const surge = asset.surge_m == null ? null : asset.surge_m * setup + whatIf.tide_m;
      const flood =
        surge == null || asset.coast_km == null || asset.elevation_m == null
          ? asset.flood_m
          : Math.max(surge - SURGE_DECAY_M_PER_KM * asset.coast_km - asset.elevation_m, 0);
      return {
        ...asset,
        peak_wind_kt: wind,
        p_outage: p,
        score: (p * asset.criticality) / 5,
        surge_m: surge,
        flood_m: flood,
        rain_mm: asset.rain_mm == null ? asset.rain_mm : asset.rain_mm * whatIf.rain,
      };
    })
    .sort((a, b) => b.score - a.score || (b.population ?? 0) - (a.population ?? 0))
    .map((asset, i) => ({ ...asset, rank: i + 1 }));
}
