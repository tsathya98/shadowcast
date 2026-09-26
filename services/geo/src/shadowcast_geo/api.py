"""ShadowCast geo API: serves built scenarios and computes hazard on demand.

All built artifacts are loaded into memory at startup (a few MB per scenario), so request handlers never block on
storage; on-demand hazard is a small vectorised numpy computation.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from numpy.typing import NDArray

from shadowcast_geo.artifacts import ArtifactStore, artifact_store
from shadowcast_geo.config import Settings
from shadowcast_geo.hazard import Track, track_position, wind_at, wind_timeline
from shadowcast_geo.models import (
    Asset,
    AssetDetail,
    AssetPage,
    HazardSnapshot,
    ScenarioDetail,
    ScenarioSummary,
    StormPosition,
    TimelinePoint,
)


@dataclass(frozen=True)
class LoadedScenario:
    """A built scenario held in memory.

    Attributes:
        detail: Scenario metadata, model and skill.
        fixes: Raw track fix records (for GeoJSON output).
        track: Parsed track for on-demand hazard.
        assets: Assets in rank order.
        by_id: Asset lookup by id.
        lat: Asset latitudes in rank order.
        lon: Asset longitudes in rank order.
        backtest: Backtest artifact.
    """

    detail: ScenarioDetail
    fixes: list[dict[str, Any]]
    track: Track
    assets: list[Asset]
    by_id: dict[str, Asset]
    lat: NDArray[np.float64]
    lon: NDArray[np.float64]
    backtest: dict[str, Any]


def load_scenarios(store: ArtifactStore) -> dict[str, LoadedScenario]:
    """Load every scenario listed in the artifact index.

    Args:
        store: Artifact store.

    Returns:
        dict[str, LoadedScenario]: Scenarios keyed by id (empty when nothing has been built yet).
    """
    if not store.exists("scenarios/index.json"):
        return {}
    loaded: dict[str, LoadedScenario] = {}
    for entry in store.read_json("scenarios/index.json"):
        prefix = f"scenarios/{entry['id']}"
        fixes = store.read_json(f"{prefix}/track.json")
        assets = [Asset.model_validate(record) for record in store.read_json(f"{prefix}/assets.json")]
        loaded[entry["id"]] = LoadedScenario(
            detail=ScenarioDetail.model_validate(store.read_json(f"{prefix}/scenario.json")),
            fixes=fixes,
            track=Track.from_records(fixes),
            assets=assets,
            by_id={asset.asset_id: asset for asset in assets},
            lat=np.array([asset.lat for asset in assets]),
            lon=np.array([asset.lon for asset in assets]),
            backtest=store.read_json(f"{prefix}/backtest.json"),
        )
    return loaded


def create_app(settings: Settings | None = None, store: ArtifactStore | None = None) -> FastAPI:
    """Build the FastAPI application.

    Args:
        settings: Settings (defaults to the environment).
        store: Artifact store (defaults to the one selected by ``settings``).

    Returns:
        FastAPI: The configured application.
    """
    settings = settings or Settings.from_env()
    scenarios: dict[str, LoadedScenario] = {}

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
        scenarios.update(load_scenarios(store or artifact_store(settings)))
        yield

    app = FastAPI(
        title="ShadowCast geo API",
        version="0.1.0",
        summary="Impact-based cyclone forecasting per asset, verified against satellite ground truth.",
        lifespan=lifespan,
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins), allow_methods=["GET"])

    def get(scenario_id: str) -> LoadedScenario:
        if scenario_id not in scenarios:
            raise HTTPException(status_code=404, detail=f"unknown scenario {scenario_id!r}")
        return scenarios[scenario_id]

    @app.get("/health")
    async def health() -> dict[str, Any]:
        """Liveness probe listing the scenarios loaded in memory."""
        return {"status": "ok", "scenarios": sorted(scenarios)}

    @app.get("/scenarios")
    async def list_scenarios() -> list[ScenarioSummary]:
        """Every built scenario."""
        return [ScenarioSummary.model_validate(s.detail.model_dump()) for s in scenarios.values()]

    @app.get("/scenarios/{scenario_id}")
    async def scenario_detail(scenario_id: str) -> ScenarioDetail:
        """Scenario metadata, calibrated outage model and backtest skill."""
        return get(scenario_id).detail

    @app.get("/scenarios/{scenario_id}/track")
    async def track_geojson(scenario_id: str) -> dict[str, Any]:
        """Storm track as a GeoJSON FeatureCollection: the path as a LineString plus one Point per fix."""
        fixes = get(scenario_id).fixes
        line = {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[f["lon"], f["lat"]] for f in fixes]},
            "properties": {"kind": "path"},
        }
        points = [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [f["lon"], f["lat"]]},
                "properties": {"kind": "fix", **{k: v for k, v in f.items() if k not in ("lat", "lon")}},
            }
            for f in fixes
        ]
        return {"type": "FeatureCollection", "features": [line, *points]}

    @app.get("/scenarios/{scenario_id}/assets")
    async def assets(
        scenario_id: str,
        kind: Annotated[list[str] | None, Query(description="Filter by asset kind (repeatable)")] = None,
        min_score: Annotated[float, Query(ge=0, le=1)] = 0.0,
        limit: Annotated[int, Query(ge=1, le=5000)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> AssetPage:
        """Assets in priority order, optionally filtered by kind and minimum score."""
        selected = [a for a in get(scenario_id).assets if (not kind or a.kind in kind) and a.score >= min_score]
        return AssetPage(total=len(selected), items=selected[offset : offset + limit])

    @app.get("/scenarios/{scenario_id}/assets/{asset_id:path}")
    async def asset_detail(scenario_id: str, asset_id: str) -> AssetDetail:
        """One asset with its modelled wind through the storm's life (15-minute steps)."""
        scenario = get(scenario_id)
        asset = scenario.by_id.get(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail=f"unknown asset {asset_id!r}")
        times, winds = wind_timeline(asset.lat, asset.lon, scenario.track)
        timeline = [
            TimelinePoint(
                time=f"{np.datetime_as_string(t, unit='s')}Z", wind_kt=None if np.isnan(w) else round(float(w), 1)
            )
            for t, w in zip(times, winds, strict=True)
        ]
        return AssetDetail(asset=asset, timeline=timeline)

    @app.get("/scenarios/{scenario_id}/hazard")
    async def hazard(
        scenario_id: str, at: Annotated[datetime, Query(description="ISO 8601 time (UTC)")]
    ) -> HazardSnapshot:
        """Modelled wind at every asset (rank order) at one moment, plus the interpolated storm position."""
        scenario = get(scenario_id)
        at_utc = at.astimezone(UTC) if at.tzinfo else at.replace(tzinfo=UTC)
        position = track_position(scenario.track, at_utc)
        winds = wind_at(scenario.lat, scenario.lon, scenario.track, at_utc)
        return HazardSnapshot(
            at=at_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            storm=StormPosition.model_validate(position) if position else None,
            asset_ids=[a.asset_id for a in scenario.assets],
            wind_kt=np.round(winds, 1).tolist(),
        )

    @app.get("/scenarios/{scenario_id}/backtest")
    async def backtest(scenario_id: str) -> dict[str, Any]:
        """Predicted outage probability vs observed night-light loss per substation, with skill metrics."""
        return get(scenario_id).backtest

    return app
