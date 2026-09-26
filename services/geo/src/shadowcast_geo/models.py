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


class ScenarioDetail(ScenarioSummary):
    """Scenario metadata, outage model and backtest skill."""

    track_source: str
    asset_counts: dict[str, int]
    model: dict[str, Any] = Field(description="Calibrated outage model: intercept, slope, trained_on, n, auc, brier")
    skill: dict[str, Any] = Field(description="Backtest skill on this scenario; out_of_sample marks held-out storms")
    loss_by_band: list[dict[str, float]]
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
    population: float | None
    elevation_m: float | None
    criticality: int
    p_outage: float
    score: float
    observed_loss_pct: float | None = Field(default=None, description="Observed night-light loss (substations)")
    reasons: list[str]


class AssetPage(Schema):
    """A filtered, rank-ordered slice of assets."""

    total: int
    items: list[Asset]


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
