"""Offline scenario build.

For each scenario: storm track and assets → deterministic hazard → Earth Engine enrichment → night-light ground truth
→ outage model (fitted on the reference scenario, evaluated out of sample elsewhere) → ranking → JSON artifacts.

Usage: ``python -m shadowcast_geo.build [scenario-id ...]`` (default: every registered scenario, reference first).
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
from datetime import UTC, datetime
from typing import Any, cast

import httpx
import numpy as np
import pandas as pd

from shadowcast_geo import earth
from shadowcast_geo.artifacts import ArtifactStore, artifact_store
from shadowcast_geo.calibration import OutageModel, evaluate, fit_outage_model, loss_by_band
from shadowcast_geo.config import (
    LIT_RADIANCE,
    LOSS_BANDS_KT,
    OUTAGE_LOSS_PCT,
    SCENARIOS,
    USER_AGENT,
    Scenario,
    Settings,
)
from shadowcast_geo.hazard import Track, exposure
from shadowcast_geo.inputs import load_assets, load_best_track
from shadowcast_geo.ranking import rank_assets

logger = logging.getLogger("shadowcast_geo.build")

MODEL_PATH = "models/outage.json"
INDEX_PATH = "scenarios/index.json"
TIME_COLUMNS = ("peak_time", "closest_time", "band_entry")
ASSET_FIELDS = [
    "asset_id",
    "rank",
    "kind",
    "name",
    "source",
    "lat",
    "lon",
    "peak_wind_kt",
    "peak_time",
    "min_dist_km",
    "closest_time",
    "band_kt",
    "band_entry",
    "population",
    "elevation_m",
    "criticality",
    "p_outage",
    "score",
    "observed_loss_pct",
    "reasons",
]
ROUNDING = {
    "peak_wind_kt": 1,
    "min_dist_km": 1,
    "population": 0,
    "elevation_m": 1,
    "p_outage": 4,
    "score": 4,
    "observed_loss_pct": 1,
    "ntl_pre": 3,
    "ntl_post": 3,
    "loss_pct": 1,
}


def json_safe(value: object) -> Any:
    """Recursively convert numpy scalars to Python types and non-finite floats to ``None`` for strict JSON.

    Args:
        value: Any nested structure of dicts, lists, tuples and scalars.

    Returns:
        Any: An equivalent structure that ``json.dumps(..., allow_nan=False)`` accepts.
    """
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in cast("dict[object, object]", value).items()}
    if isinstance(value, list | tuple):
        return [json_safe(v) for v in cast("list[object] | tuple[object, ...]", value)]
    if isinstance(value, np.generic):
        value = cast("object", value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def frame_records(frame: pd.DataFrame, fields: list[str]) -> list[dict[str, Any]]:
    """Render selected columns as JSON-safe records with rounded floats and ``...Z`` ISO timestamps.

    Args:
        frame: Source frame.
        fields: Columns to keep, in output order (missing columns are skipped).

    Returns:
        list[dict[str, Any]]: One record per row.
    """
    out = frame[[f for f in fields if f in frame]].copy()
    for column in TIME_COLUMNS:
        if column in out:
            stamps = pd.to_datetime(out[column])
            out[column] = stamps.dt.strftime("%Y-%m-%dT%H:%M:%SZ").where(stamps.notna(), None)
    out = out.round({k: v for k, v in ROUNDING.items() if k in out})
    return json_safe(out.to_dict("records"))


def build_scenario(
    scenario: Scenario, client: httpx.Client, settings: Settings, store: ArtifactStore, model: OutageModel | None
) -> tuple[OutageModel, dict[str, Any]]:
    """Build and store every artifact for one scenario.

    Args:
        scenario: Scenario to build.
        client: HTTP client for build inputs.
        settings: Settings (cache, retries).
        store: Artifact destination.
        model: Outage model from the reference scenario; ignored (and refitted) when ``scenario.reference``.

    Returns:
        tuple[OutageModel, dict[str, Any]]: The model used and the scenario summary written to the index.

    Raises:
        ValueError: If a non-reference scenario is built without a model.
    """
    logger.info("building %s", scenario.id)
    fixes = load_best_track(client, settings, scenario.storm, scenario.season)
    track = Track.from_records(fixes)
    assets = load_assets(client, settings, scenario.region)
    hazard = exposure(assets["lat"].to_numpy(dtype=float), assets["lon"].to_numpy(dtype=float), track)
    assets = earth.enrich(assets.assign(**hazard))

    substations = assets[assets["kind"] == "substation"]
    truth = substations[["asset_id", "peak_wind_kt"]].join(
        earth.nightlight_loss(substations, scenario.truth_pre, scenario.truth_post)
    )
    truth["lit"] = truth["ntl_pre"] >= LIT_RADIANCE
    lit = truth[truth["lit"] & truth["loss_pct"].notna() & truth["peak_wind_kt"].notna()]
    wind, loss = lit["peak_wind_kt"].to_numpy(dtype=float), lit["loss_pct"].to_numpy(dtype=float)
    bands = loss_by_band(wind, loss, LOSS_BANDS_KT)

    if scenario.reference:
        model = fit_outage_model(wind, loss, OUTAGE_LOSS_PCT, scenario.id)
        store.write_json(MODEL_PATH, json_safe({"model": model.to_dict(), "bands": bands}))
    elif model is None:
        raise ValueError(f"{scenario.id} needs the reference outage model; build the reference scenario first")
    reference_bands = bands if scenario.reference else store.read_json(MODEL_PATH)["bands"]
    skill = {**evaluate(model, wind, loss, OUTAGE_LOSS_PCT), "out_of_sample": not scenario.reference}

    assets = assets.merge(
        truth[["asset_id", "loss_pct"]].rename(columns={"loss_pct": "observed_loss_pct"}), on="asset_id", how="left"
    )
    ranked = rank_assets(assets, model, scenario.landfall, reference_bands)
    backtest = truth.merge(ranked[["asset_id", "name", "lat", "lon", "p_outage"]], on="asset_id")

    summary = json_safe(
        {
            "id": scenario.id,
            "storm": scenario.storm.title(),
            "season": scenario.season,
            "region": {"id": scenario.region.id, "name": scenario.region.name, "bbox": list(scenario.region.bbox)},
            "landfall": scenario.landfall.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "track_source": "IBTrACS best track (JTWC intensity and wind radii)",
            "peak_vmax_kt": float(track.vmax_kt.max()),
            "asset_counts": ranked["kind"].value_counts().to_dict(),
            "model": model.to_dict(),
            "skill": skill,
            "loss_by_band": bands,
            "built_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )
    prefix = f"scenarios/{scenario.id}"
    store.write_json(f"{prefix}/scenario.json", summary)
    store.write_json(f"{prefix}/track.json", fixes)
    store.write_json(f"{prefix}/assets.json", frame_records(ranked, ASSET_FIELDS))
    store.write_json(
        f"{prefix}/backtest.json",
        {
            "skill": skill,
            "loss_by_band": bands,
            "substations": frame_records(
                backtest,
                [
                    "asset_id",
                    "name",
                    "lat",
                    "lon",
                    "peak_wind_kt",
                    "p_outage",
                    "ntl_pre",
                    "ntl_post",
                    "loss_pct",
                    "lit",
                ],
            ),
        },
    )
    logger.info("built %s: %d assets, skill %s", scenario.id, len(ranked), skill)
    return model, summary


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: build the requested scenarios (reference first) and refresh the scenario index.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns:
        int: Process exit code (0 on success).
    """
    parser = argparse.ArgumentParser(description="Build ShadowCast scenario artifacts.")
    parser.add_argument("scenarios", nargs="*", metavar="scenario", help=f"scenario ids: {', '.join(SCENARIOS)}")
    args = parser.parse_args(argv)
    if unknown := sorted(set(args.scenarios) - set(SCENARIOS)):
        parser.error(f"unknown scenario(s): {', '.join(unknown)}")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    settings = Settings.from_env()
    store = artifact_store(settings)
    earth.initialize(settings.ee_project)
    selected = sorted((SCENARIOS[s] for s in (args.scenarios or SCENARIOS)), key=lambda s: not s.reference)
    model = None
    if not any(s.reference for s in selected) and store.exists(MODEL_PATH):
        model = OutageModel(**store.read_json(MODEL_PATH)["model"])

    existing: list[dict[str, Any]] = store.read_json(INDEX_PATH) if store.exists(INDEX_PATH) else []
    index = {entry["id"]: entry for entry in existing}
    with httpx.Client(
        timeout=settings.http_timeout_s, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    ) as client:
        for scenario in selected:
            model, summary = build_scenario(scenario, client, settings, store, model)
            index[scenario.id] = {
                k: summary[k] for k in ("id", "storm", "season", "region", "landfall", "peak_vmax_kt")
            }
    store.write_json(INDEX_PATH, [index[s] for s in SCENARIOS if s in index])
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
