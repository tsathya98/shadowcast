/** Response types of the ShadowCast geo API (mirrors services/geo/src/shadowcast_geo/models.py). */

export interface Region {
  id: string;
  name: string;
  /** south, west, north, east (degrees) */
  bbox: [number, number, number, number];
}

export interface ScenarioSummary {
  id: string;
  storm: string;
  season: number;
  region: Region;
  landfall: string;
  peak_vmax_kt: number;
}

export interface OutageModel {
  intercept: number;
  slope: number;
  trained_on: string;
  n: number;
  auc: number | null;
  brier: number | null;
}

/** Spatial cross-validation on the reference storm: each south-to-north block of coast held out in turn. */
export interface SpatialHoldout {
  folds: number;
  n: number;
  auc: number | null;
  brier: number | null;
  blocks: { lat_min: number; lat_max: number; n: number; observed_outage_rate: number; auc: number | null }[];
}

export interface Skill {
  n: number;
  observed_outage_rate: number | null;
  auc: number | null;
  brier: number | null;
  spearman: number | null;
  out_of_sample: boolean;
  spatial_holdout?: SpatialHoldout;
}

export interface LossBand {
  low_kt: number;
  high_kt: number;
  n: number;
  p25: number;
  median: number;
  p75: number;
}

export interface ForecastSummary {
  key: string;
  issued: string;
  lead_h: number;
  storm_id: string;
  members: number;
  assets_likely_gale: number;
  assets_likely_hurricane: number;
  max_p_outage: number;
  source: string;
}

export interface ScenarioDetail extends ScenarioSummary {
  track_source: string;
  asset_counts: Record<string, number>;
  model: OutageModel;
  skill: Skill;
  loss_by_band: LossBand[];
  forecasts: ForecastSummary[];
  built_at: string;
}

export interface Asset {
  asset_id: string;
  rank: number;
  kind: string;
  name: string | null;
  source: string;
  lat: number;
  lon: number;
  peak_wind_kt: number | null;
  peak_time: string | null;
  min_dist_km: number;
  closest_time: string | null;
  band_kt: number;
  band_entry: string | null;
  gale_arrival: string | null;
  population: number | null;
  elevation_m: number | null;
  criticality: number;
  p_outage: number;
  score: number;
  observed_loss_pct: number | null;
  reasons: string[];
}

export interface ForecastAsset extends Asset {
  p34: number;
  p64: number;
  wind_p10: number;
  wind_p90: number;
  members: number;
}

export interface Page<T> {
  total: number;
  items: T[];
}

export interface TimelinePoint {
  time: string;
  wind_kt: number | null;
}

export interface AssetDetail {
  asset: Asset;
  timeline: TimelinePoint[];
}

export interface StormPosition {
  lat: number;
  lon: number;
  vmax_kt: number;
  rmw_km: number;
}

export interface HazardSnapshot {
  at: string;
  storm: StormPosition | null;
  asset_ids: string[];
  wind_kt: number[];
}

export interface TrackFeatureCollection {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    geometry: { type: "LineString" | "Point"; coordinates: number[][] | number[] };
    properties: Record<string, unknown>;
  }[];
}

export interface BacktestSubstation {
  asset_id: string;
  name: string | null;
  lat: number;
  lon: number;
  peak_wind_kt: number | null;
  p_outage: number;
  ntl_pre: number | null;
  ntl_post: number | null;
  loss_pct: number | null;
  lit: boolean;
}

export interface Backtest {
  skill: Skill;
  loss_by_band: LossBand[];
  substations: BacktestSubstation[];
}

/** Either the best-track replay or one as-issued ensemble forecast. */
export type ReplayMode = { kind: "best-track" } | { kind: "forecast"; key: string };
