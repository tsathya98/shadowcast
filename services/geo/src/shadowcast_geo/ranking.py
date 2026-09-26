"""Turn per-asset hazard into a ranked, explained priority list.

``score = P(outage) * criticality / 5``. Probability comes from the calibrated outage model; criticality encodes the
consequence of losing that kind of asset. Every rank carries the plain-language reasons behind it.
"""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from shadowcast_geo.calibration import OutageModel
from shadowcast_geo.config import CRITICALITY, LOW_LYING_M

KIND_LABELS = {
    "hospital": "hospital",
    "cyclone_shelter": "cyclone shelter",
    "health_centre": "health centre",
    "substation": "power substation",
    "power_plant": "power plant",
    "clinic": "clinic",
    "water_works": "water works",
    "fire_station": "fire station",
    "police": "police station",
    "school": "school",
}


def rank_assets(
    assets: pd.DataFrame, model: OutageModel, landfall: datetime, reference_bands: list[dict[str, float]]
) -> pd.DataFrame:
    """Score, rank and explain every asset.

    Args:
        assets: One row per asset with ``kind``, ``peak_wind_kt``, ``peak_time``, ``min_dist_km``, ``band_kt``,
            ``band_entry`` and optionally ``population`` and ``elevation_m``.
        model: Calibrated outage model.
        landfall: Official landfall time, used to express lead time.
        reference_bands: Loss-by-wind-band summary from the reference backtest, quoted in the reasons.

    Returns:
        pd.DataFrame: ``assets`` plus ``criticality``, ``p_outage``, ``score``, ``rank`` (1 = highest priority) and
        ``reasons`` (list of strings), sorted by rank.
    """
    ranked = assets.copy()
    ranked["criticality"] = ranked["kind"].map(CRITICALITY).fillna(1).astype(int)
    ranked["p_outage"] = model.predict(ranked["peak_wind_kt"].to_numpy(dtype=float))
    ranked["score"] = ranked["p_outage"] * ranked["criticality"] / 5.0
    population = ranked["population"] if "population" in ranked else pd.Series(0.0, index=ranked.index)
    ranked = ranked.assign(_population=population.fillna(0.0)).sort_values(
        ["score", "_population"], ascending=False, kind="mergesort"
    )
    ranked["rank"] = np.arange(1, len(ranked) + 1)
    ranked["reasons"] = [_reasons(row, model, landfall, reference_bands) for row in ranked.to_dict("records")]
    return ranked.drop(columns="_population").reset_index(drop=True)


def _reasons(
    row: Mapping[Hashable, Any], model: OutageModel, landfall: datetime, reference_bands: list[dict[str, float]]
) -> list[str]:
    """Build the plain-language explanation for one asset.

    Args:
        row: Asset record (see :func:`rank_assets`), including ``criticality`` and ``p_outage``.
        model: Calibrated outage model (quoted for provenance).
        landfall: Official landfall time.
        reference_bands: Loss-by-wind-band summary from the reference backtest.

    Returns:
        list[str]: Reasons, most important first.
    """
    wind = row["peak_wind_kt"]
    if not np.isfinite(wind):
        return ["No modelled wind at this location for this storm"]
    reasons = [
        f"Modelled peak wind {wind:.0f} kt around {pd.Timestamp(row['peak_time']):%d %b %H:%M} UTC; "
        f"storm centre passes {row['min_dist_km']:.0f} km away",
        f"Grid-outage probability {row['p_outage']:.0%} (model fitted on {model.trained_on}, AUC {model.auc:.2f})",
    ]
    band = next((b for b in reference_bands if b["low_kt"] < wind <= b["high_kt"]), None)
    if band:
        reasons.append(
            f"In the {model.trained_on} backtest, assets modelled at {band['low_kt']:.0f}-{band['high_kt']:.0f} kt "
            f"lost a median {band['median']:.0f}% of their night lights"
        )
    if row["band_kt"]:
        entry = pd.Timestamp(row["band_entry"]).tz_localize("UTC")
        lead_h = (pd.Timestamp(landfall) - entry).total_seconds() / 3600
        reasons.append(
            f"Inside the {row['band_kt']}-kt wind radius from {entry:%d %b %H:%M} UTC ({lead_h:+.0f} h to landfall)"
        )
    population = row.get("population")
    if population is not None and np.isfinite(population) and population > 0:
        reasons.append(f"About {population:,.0f} people live within 2 km")
    elevation = row.get("elevation_m")
    if elevation is not None and np.isfinite(elevation) and elevation < LOW_LYING_M:
        reasons.append(f"Low-lying: {elevation:.1f} m above sea level (surge and flood exposure)")
    reasons.append(f"Criticality {row['criticality']}/5 as a {KIND_LABELS.get(row['kind'], row['kind'])}")
    return reasons
