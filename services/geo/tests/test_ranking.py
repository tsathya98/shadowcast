from datetime import UTC, datetime

import numpy as np
import pandas as pd

from shadowcast_geo.calibration import OutageModel
from shadowcast_geo.ranking import rank_assets

LANDFALL = datetime(2019, 5, 3, 3, 30, tzinfo=UTC)
BANDS = [{"low_kt": 100.0, "high_kt": 130.0, "n": 36.0, "p25": 70.0, "median": 82.0, "p75": 90.0}]


def _frame(**overrides: list[object]) -> pd.DataFrame:
    base: dict[str, list[object]] = {
        "asset_id": ["a", "b", "c", "d"],
        "kind": ["school", "hospital", "hospital", "unknown_kind"],
        "peak_wind_kt": [115.0, 115.0, 115.0, np.nan],
        "peak_time": [pd.Timestamp("2019-05-03T03:00:00")] * 4,
        "min_dist_km": [20.0, 20.0, 20.0, 400.0],
        "band_kt": [64, 64, 0, 0],
        "band_entry": [pd.Timestamp("2019-05-02T21:00:00"), pd.Timestamp("2019-05-02T21:00:00"), pd.NaT, pd.NaT],
        "population": [1000.0, 500.0, 9000.0, np.nan],
        "elevation_m": [3.2, 12.0, np.nan, 1.0],
    }
    return pd.DataFrame({**base, **overrides})


def test_rank_orders_by_score_then_population(model: OutageModel) -> None:
    ranked = rank_assets(_frame(), model, LANDFALL, BANDS)

    assert ranked["asset_id"].tolist() == ["c", "b", "a", "d"]
    assert ranked["rank"].tolist() == [1, 2, 3, 4]
    assert ranked.loc[0, "criticality"] == 5
    assert ranked.loc[3, "criticality"] == 1
    assert ranked.loc[0, "score"] == ranked.loc[0, "p_outage"]


def test_reasons_cover_every_signal(model: OutageModel) -> None:
    ranked = rank_assets(_frame(), model, LANDFALL, BANDS)
    reasons: dict[str, list[str]] = dict(zip(ranked["asset_id"], ranked["reasons"], strict=True))

    school = reasons["a"]
    assert school[0].startswith("Modelled peak wind 115 kt around 03 May 03:00 UTC")
    assert "model fitted on fani-2019" in school[1]
    assert "lost a median 82% of their night lights" in school[2]
    assert "Inside the 64-kt wind radius from 02 May 21:00 UTC (+6 h to landfall)" in school
    assert "About 1,000 people live within 2 km" in school
    assert any(r.startswith("Low-lying: 3.2 m") for r in school)
    assert school[-1] == "Criticality 2/5 as a school"
    assert not any("wind radius" in r for r in reasons["c"])
    assert reasons["d"] == ["No modelled wind at this location for this storm"]


def test_rank_without_population_or_band_match(model: OutageModel) -> None:
    frame = _frame(peak_wind_kt=[70.0, 70.0, 70.0, 70.0]).drop(columns=["population", "elevation_m"])

    ranked = rank_assets(frame, model, LANDFALL, BANDS)

    assert len(ranked) == 4
    assert not any("lost a median" in r for reasons in ranked["reasons"] for r in reasons)
    assert not any("people live" in r for reasons in ranked["reasons"] for r in reasons)
