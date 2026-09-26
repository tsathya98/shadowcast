from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pandas as pd
import pytest

from shadowcast_geo import build
from shadowcast_geo.artifacts import LocalArtifacts
from shadowcast_geo.calibration import OutageModel
from shadowcast_geo.config import SCENARIOS, Settings
from tests.conftest import make_fixes

SUBSTATION_LONS = [86.02, 86.05, 86.1, 86.2, 86.4, 86.8, 87.2, 87.6]


@pytest.fixture
def pipeline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> LocalArtifacts:
    """Stub every external input: synthetic track, eight substations and night lights that fade near the track."""
    frame = pd.DataFrame(
        {
            "asset_id": [f"osm:node/{i}" for i in range(len(SUBSTATION_LONS))] + ["osdma:PURI:19.5,86.3"],
            "kind": ["substation"] * len(SUBSTATION_LONS) + ["cyclone_shelter"],
            "name": [f"Sub {i}" for i in range(len(SUBSTATION_LONS))] + ["Shelter"],
            "source": ["OpenStreetMap"] * len(SUBSTATION_LONS) + ["OSDMA (MCS)"],
            "lat": [19.5] * (len(SUBSTATION_LONS) + 1),
            "lon": [*SUBSTATION_LONS, 86.3],
        }
    )

    def nightlights(points: pd.DataFrame, pre: object, post: object) -> pd.DataFrame:
        loss = np.where(points["lon"] < 86.3, 85.0, 5.0)
        return pd.DataFrame({"ntl_pre": 5.0, "ntl_post": 5.0 * (1 - loss / 100), "loss_pct": loss}, index=points.index)

    def best_track(*_: object) -> list[dict[str, Any]]:
        return make_fixes()

    def assets(*_: object) -> pd.DataFrame:
        return frame

    def enrich(points: pd.DataFrame) -> pd.DataFrame:
        return points.assign(population=1500.0, elevation_m=4.0)

    def initialize(project: str) -> None:
        assert project == "argmax-cyclone-2026"

    monkeypatch.setattr(build, "load_best_track", best_track)
    monkeypatch.setattr(build, "load_assets", assets)
    monkeypatch.setattr(build.earth, "initialize", initialize)
    monkeypatch.setattr(build.earth, "enrich", enrich)
    monkeypatch.setattr(build.earth, "nightlight_loss", nightlights)
    monkeypatch.setenv("GEO_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.delenv("GEO_BUCKET", raising=False)
    return LocalArtifacts(tmp_path / "artifacts")


def test_main_builds_every_scenario(pipeline: LocalArtifacts) -> None:
    assert build.main([]) == 0

    index = pipeline.read_json("scenarios/index.json")
    assert [entry["id"] for entry in index] == list(SCENARIOS)
    model = pipeline.read_json("models/outage.json")
    assert model["model"]["trained_on"] == "fani-2019"
    assert model["model"]["auc"] == 1.0
    fani = pipeline.read_json("scenarios/fani-2019/scenario.json")
    assert fani["skill"]["out_of_sample"] is False
    assert fani["asset_counts"] == {"substation": 8, "cyclone_shelter": 1}
    dana = pipeline.read_json("scenarios/dana-2024/scenario.json")
    assert dana["skill"]["out_of_sample"] is True
    assets: list[dict[str, Any]] = pipeline.read_json("scenarios/fani-2019/assets.json")
    assert [a["rank"] for a in assets] == list(range(1, 10))
    assert assets[0]["peak_time"].endswith("Z")
    assert {a["kind"] for a in assets if a["observed_loss_pct"] is None} == {"cyclone_shelter"}
    backtest = pipeline.read_json("scenarios/fani-2019/backtest.json")
    assert len(backtest["substations"]) == 8
    assert pipeline.read_json("scenarios/fani-2019/track.json") == make_fixes()


def test_main_rebuilds_one_scenario_with_stored_model(pipeline: LocalArtifacts) -> None:
    build.main(["fani-2019"])

    assert build.main(["dana-2024"]) == 0

    assert [entry["id"] for entry in pipeline.read_json("scenarios/index.json")] == ["fani-2019", "dana-2024"]


def test_main_rejects_unknown_scenario(pipeline: LocalArtifacts) -> None:
    with pytest.raises(SystemExit):
        build.main(["atlantis-2030"])


def test_non_reference_scenario_requires_model(pipeline: LocalArtifacts, settings: Settings) -> None:
    with httpx.Client() as client, pytest.raises(ValueError, match="needs the reference outage model"):
        build.build_scenario(SCENARIOS["dana-2024"], client, settings, pipeline, None)


def test_json_safe() -> None:
    value = {"a": np.float64(1.5), "b": [float("nan"), np.int64(2), (float("inf"), "x")], 3: None}

    assert build.json_safe(value) == {"a": 1.5, "b": [None, 2, [None, "x"]], "3": None}


def test_frame_records(model: OutageModel) -> None:
    frame = pd.DataFrame(
        {
            "asset_id": ["x"],
            "peak_wind_kt": [101.26],
            "peak_time": [pd.Timestamp("2019-05-03T03:00:00")],
            "band_entry": [pd.NaT],
            "p_outage": [np.float64(0.123456)],
        }
    )

    records = build.frame_records(frame, ["asset_id", "peak_wind_kt", "peak_time", "band_entry", "p_outage", "absent"])

    assert records == [
        {
            "asset_id": "x",
            "peak_wind_kt": 101.3,
            "peak_time": "2019-05-03T03:00:00Z",
            "band_entry": None,
            "p_outage": 0.1235,
        }
    ]
