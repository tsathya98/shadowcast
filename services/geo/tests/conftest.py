"""Shared fixtures: a synthetic northbound cyclone, a small asset table and fast-retry settings."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from shadowcast_geo.calibration import OutageModel
from shadowcast_geo.config import Settings
from shadowcast_geo.hazard import Track
from shadowcast_geo.surge import Grid

START = datetime(2019, 5, 2, 12, tzinfo=UTC)


class MemoryArtifacts:
    """In-memory stand-in for the scenario bucket, with the same strict-JSON round trip."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def read_bytes(self, path: str) -> bytes:
        return self.objects[path]

    def write_bytes(self, path: str, body: bytes, content_type: str) -> None:
        self.objects[path] = body

    def names(self, prefix: str) -> list[str]:
        return sorted(name for name in self.objects if name.startswith(prefix))

    def read_json(self, path: str) -> Any:
        return json.loads(self.objects[path])

    def write_json(self, path: str, data: Any) -> None:
        self.objects[path] = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()

    def exists(self, path: str) -> bool:
        return path in self.objects


CELL_DEG = 1.0 / 60.0


def east_facing_coast(coast_lon: float = 86.0, slope_m_per_km: float = 1.0, lagoon: bool = False) -> Grid:
    """Relief with land west of ``coast_lon`` (10 m) and sea east of it deepening linearly offshore, 17-23N.

    ``lagoon`` adds a closed body of water on land, whose shore is not open coast.
    """
    lon = 83.0 + (np.arange(420) + 0.5) * CELL_DEG
    offshore_km = (lon - coast_lon) * 111.0 * np.cos(np.radians(19.5))
    values = np.tile(np.where(lon < coast_lon, 10.0, -np.maximum(offshore_km, 0.5) * slope_m_per_km), (360, 1))
    if lagoon:
        values[150:160, 100:120] = -2.0
    return Grid(cells=values, north=23.0, west=83.0, cell_deg=CELL_DEG)


def make_fixes(n: int = 7, lon: float = 86.0, vmax: float = 100.0, start: datetime = START) -> list[dict[str, Any]]:
    """A storm moving due north along ``lon`` from 18N, one fix every 3 hours from ``start``."""
    return [
        {
            "time": (start + timedelta(hours=3 * i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "lat": 18.0 + 0.5 * i,
            "lon": lon,
            "vmax_kt": vmax,
            "rmw_km": 30.0,
            "r34_km": [200.0, 200.0, 200.0, 200.0],
            "r50_km": [120.0, 120.0, 120.0, 120.0],
            "r64_km": [60.0, None, 60.0, 60.0],
        }
        for i in range(n)
    ]


@pytest.fixture
def fixes() -> list[dict[str, Any]]:
    return make_fixes()


@pytest.fixture
def track(fixes: list[dict[str, Any]]) -> Track:
    return Track.from_records(fixes)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(bucket="test-bucket", cache_dir=tmp_path / "cache", max_attempts=2, retry_backoff_s=0.0)


@pytest.fixture
def model() -> OutageModel:
    return OutageModel(intercept=-12.8, slope=0.128, trained_on="fani-2019", n=200, auc=0.91, brier=0.09)


@pytest.fixture
def assets() -> pd.DataFrame:
    """Four assets at increasing distance east of the synthetic track."""
    return pd.DataFrame(
        {
            "asset_id": ["osm:node/1", "osm:node/2", "osdma:PURI:19.5,86.2", "osm:way/4"],
            "kind": ["substation", "hospital", "cyclone_shelter", "school"],
            "name": ["Near substation", "Mid hospital", "Shelter", None],
            "source": ["OpenStreetMap", "OpenStreetMap", "OSDMA (MCS)", "OpenStreetMap"],
            "lat": [19.5, 19.5, 19.5, 19.5],
            "lon": [86.05, 86.4, 86.2, 88.5],
        }
    )


def make_asset(
    asset_id: str, rank: int, kind: str, score: float, lon: float, name: str | None = None
) -> dict[str, Any]:
    return {
        "asset_id": asset_id, "rank": rank, "kind": kind, "name": name, "source": "OpenStreetMap",
        "lat": 19.5, "lon": lon, "peak_wind_kt": 110.0, "peak_time": "2019-05-02T21:00:00Z", "min_dist_km": 5.0,
        "closest_time": "2019-05-02T21:00:00Z", "band_kt": 64, "band_entry": "2019-05-02T18:00:00Z",
        "population": 1000.0, "elevation_m": 3.0, "criticality": 5, "p_outage": 0.9, "score": score,
        "observed_loss_pct": None, "reasons": ["Modelled peak wind 110 kt"], "extra_field": "ignored",
    }  # fmt: skip


@pytest.fixture
def store() -> MemoryArtifacts:
    artifacts = MemoryArtifacts()
    region = {"id": "odisha-coast", "name": "Odisha coast", "bbox": [19.0, 84.4, 21.7, 87.6]}
    summary = {"id": "fani-2019", "storm": "Fani", "season": 2019, "region": region,
               "landfall": "2019-05-03T03:30:00Z", "peak_vmax_kt": 150.0}  # fmt: skip
    artifacts.write_json("scenarios/index.json", [summary])
    artifacts.write_json("scenarios/fani-2019/scenario.json", {
        **summary, "track_source": "IBTrACS best track", "asset_counts": {"hospital": 1, "school": 1},
        "model": {"intercept": -12.8, "slope": 0.128}, "skill": {"auc": 0.91, "out_of_sample": False},
        "loss_by_band": [{"low_kt": 100.0, "high_kt": 130.0, "n": 36.0, "median": 82.0}],
        "rain": {"model": "R-CLIPER", "truth": "GPM IMERG", "n": 2, "spearman": 0.7, "median_ratio": 1.2,
                 "max_modelled_mm": 180.0, "max_observed_mm": 150.0, "extreme_sites": 0},
        "insurance": {"terms": "illustrative", "districts": []},
        "roads": {"roads": 1, "km": 10, "km_cut": 10, "km_at_risk": 0, "first_closure": "2019-05-02T22:00:00Z",
                  "cut_by_surge": 0},
        "surge": {"peak_m": 1.5, "lat": 19.8, "lon": 85.8, "time": "2019-05-03T03:00:00Z", "coast_points": 1,
                  "flooded_sites": 0, "method": "1D wind setup"},
        "forecasts": [{"key": "20190501T12Z", "issued": "2019-05-01T12:00:00Z", "lead_h": 39.5, "storm_id": "01B",
                       "members": 52, "assets_likely_gale": 1, "assets_likely_hurricane": 0, "max_p_outage": 0.4,
                       "source": "ECMWF IFS ensemble"}],
        "built_at": "2026-09-26T00:00:00Z",
    })  # fmt: skip
    artifacts.write_json("scenarios/fani-2019/track.json", make_fixes())
    artifacts.write_json("scenarios/fani-2019/assets.json", [
        make_asset("osm:node/1", 1, "hospital", 0.9, 86.05, "District Hospital Puri"),
        make_asset("osm:way/2", 2, "school", 0.36, 86.4),
    ])  # fmt: skip
    artifacts.write_json("scenarios/fani-2019/backtest.json", {"skill": {"auc": 0.91}, "substations": []})
    artifacts.write_json("scenarios/fani-2019/roads.json", {"type": "FeatureCollection", "features": []})
    for name in ("night-lights-pre", "night-lights-post"):
        artifacts.write_bytes(f"scenarios/fani-2019/evidence/{name}.png", f"png:{name}".encode(), "image/png")
    artifacts.write_json("scenarios/fani-2019/surge.json", [
        {"lat": 19.8, "lon": 85.8, "peak_m": 1.5, "setup_m": 0.8, "barometer_m": 0.7,
         "peak_time": "2019-05-03T03:00:00Z"},
    ])  # fmt: skip
    forecast_asset = {**make_asset("osm:node/1", 1, "hospital", 0.4, 86.05), "p34": 0.9, "p64": 0.25, "wind_p10": 40.0,
                      "wind_p90": 80.0, "members": 52, "p_rain": 0.1,
                      "gale_arrival": "2019-05-02T18:00:00Z"}  # fmt: skip
    artifacts.write_json("scenarios/fani-2019/forecasts/20190501T12Z/assets.json", [forecast_asset])
    artifacts.write_json(
        "scenarios/fani-2019/forecasts/20190501T12Z/tracks.json",
        [{"member": 1, "fixes": make_fixes()}, {"member": 2, "fixes": make_fixes(lon=86.5, vmax=80.0)}],
    )
    return artifacts


class FakeLiveSession:
    """Scripted Gemini Live session: each turn is released once the officer has sent some audio."""

    def __init__(self, turns: list[list[Any]], hang: bool = False) -> None:
        self.turns = turns
        self.hang = hang
        self.audio: list[bytes] = []
        self.tool_responses: list[Any] = []
        self.heard = asyncio.Event()

    async def send_realtime_input(self, *, audio: Any) -> None:
        self.audio.append(audio.data)
        self.heard.set()

    async def send_tool_response(self, *, function_responses: list[Any]) -> None:
        self.tool_responses.extend(function_responses)

    async def receive(self) -> AsyncIterator[Any]:
        await self.heard.wait()
        if self.hang:
            await asyncio.Event().wait()
        if self.turns:
            for message in self.turns.pop(0):
                yield message


class FakeLiveClient:
    """Stand-in for ``google.genai.Client``: ``client.aio.live.connect`` opens the scripted session or fails."""

    def __init__(self, session: FakeLiveSession | None = None, error: Exception | None = None) -> None:
        self.session = session
        self.error = error
        self.configs: list[tuple[str, Any]] = []
        self.aio = SimpleNamespace(live=SimpleNamespace(connect=self.connect))

    @asynccontextmanager
    async def connect(self, *, model: str, config: Any) -> AsyncGenerator[FakeLiveSession | None, None]:
        if self.error:
            raise self.error
        self.configs.append((model, config))
        yield self.session
