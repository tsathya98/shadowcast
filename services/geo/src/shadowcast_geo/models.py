"""API response schemas (these also document the OpenAPI contract consumed by the ShadowCast console)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Schema(BaseModel):
    """Base schema: tolerate extra artifact fields so older clients keep working as artifacts grow."""

    model_config = ConfigDict(extra="ignore")


class RegionOut(Schema):
    """Study area."""

    id: str
    name: str
    bbox: list[float] = Field(description="south, west, north, east (degrees)")


class ScenarioSummary(Schema):
    """Scenario listing entry."""

    id: str
    storm: str
    season: int
    region: RegionOut
    landfall: str
    peak_vmax_kt: float


class ForecastSummary(Schema):
    """One as-issued ensemble forecast replayed for a scenario."""

    key: str = Field(description="Identifier used in URLs, e.g. 20241023T00Z")
    issued: str
    lead_h: float = Field(description="Hours from issue to observed landfall")
    storm_id: str
    members: int
    assets_likely_gale: int = Field(description="Assets where at least half the members bring 34 kt winds")
    assets_likely_hurricane: int = Field(description="Assets where at least half the members bring 64 kt winds")
    max_p_outage: float
    source: str


class ScenarioDetail(ScenarioSummary):
    """Scenario metadata, outage model, backtest skill and available forecast replays."""

    track_source: str
    asset_counts: dict[str, int]
    model: dict[str, Any] = Field(description="Calibrated outage model: intercept, slope, trained_on, n, auc, brier")
    skill: dict[str, Any] = Field(description="Backtest skill on this scenario; out_of_sample marks held-out storms")
    loss_by_band: list[dict[str, float]]
    forecasts: list[ForecastSummary] = []
    built_at: str


class Asset(Schema):
    """One ranked asset with its hazard, outage probability and reasons."""

    asset_id: str
    rank: int
    kind: str
    name: str | None
    source: str
    lat: float
    lon: float
    peak_wind_kt: float | None
    peak_time: str | None
    min_dist_km: float
    closest_time: str | None
    band_kt: int = Field(description="Strongest wind-radius band entered (34/50/64 kt); 0 if none")
    band_entry: str | None
    gale_arrival: str | None = Field(default=None, description="First time the modelled wind reaches 34 kt")
    population: float | None
    elevation_m: float | None
    terrain_factor: float = Field(default=1.0, description="10 m wind over this terrain relative to open sea")
    criticality: int
    p_outage: float
    score: float
    observed_loss_pct: float | None = Field(default=None, description="Observed night-light loss (substations)")
    reasons: list[str]


class ForecastAsset(Asset):
    """An asset ranked under an ensemble forecast; ``peak_wind_kt`` is the member median."""

    p34: float = Field(description="Share of ensemble members bringing gale-force (34 kt) wind")
    p64: float = Field(description="Share of ensemble members bringing hurricane-force (64 kt) wind")
    wind_p10: float
    wind_p90: float
    members: int


class AssetPage(Schema):
    """A filtered, rank-ordered slice of assets."""

    total: int
    items: list[Asset]


class ForecastAssetPage(Schema):
    """A filtered, rank-ordered slice of assets under one ensemble forecast."""

    total: int
    items: list[ForecastAsset]


class TimelinePoint(Schema):
    """Modelled wind at an asset for one track fix."""

    time: str
    wind_kt: float | None


class AssetDetail(Schema):
    """One asset with its wind timeline."""

    asset: Asset
    timeline: list[TimelinePoint]


class StormPosition(Schema):
    """Interpolated storm centre and intensity."""

    lat: float
    lon: float
    vmax_kt: float
    rmw_km: float


class HazardSnapshot(Schema):
    """Modelled wind at every asset at one moment (for the console's timeline scrubber)."""

    at: str
    storm: StormPosition | None
    asset_ids: list[str]
    wind_kt: list[float]
