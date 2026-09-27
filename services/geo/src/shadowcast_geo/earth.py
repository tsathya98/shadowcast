"""Earth Engine enrichment (population, elevation) and night-light ground truth, used at build time.

Every function issues a single ``reduceRegions`` call per layer over all assets, so a build makes a handful of
server-side requests regardless of asset count.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import ee
import numpy as np
import pandas as pd

from shadowcast_geo.config import (
    BATHYMETRY,
    BATHYMETRY_BAND,
    BATHYMETRY_MARGIN_DEG,
    COASTAL_DTM,
    ELEVATION,
    NIGHT_LIGHTS,
    NIGHT_LIGHTS_BAND,
    NIGHT_LIGHTS_QUALITY_BAND,
    NIGHT_LIGHTS_RADIUS_M,
    POPULATION,
    POPULATION_RADIUS_M,
    POPULATION_YEAR,
)
from shadowcast_geo.surge import Grid

RELIEF_CELL_DEG = 1.0 / 60.0  # ETOPO1's native 1 arc-minute


def initialize(project: str) -> None:
    """Initialise Earth Engine with Application Default Credentials.

    Args:
        project: Google Cloud project registered for Earth Engine.
    """
    ee.Initialize(project=project)


def _reduce(
    points: pd.DataFrame, image: Any, reducer: Any, scale: float, buffer_m: float = 0
) -> dict[int, dict[str, Any]]:
    """Reduce an image over every asset point (optionally buffered) in one request.

    Args:
        points: Frame with ``lat`` and ``lon`` columns; its positional index identifies each feature.
        image: Earth Engine image to reduce.
        reducer: Earth Engine reducer.
        scale: Nominal scale in metres.
        buffer_m: Buffer radius around each point; 0 samples the point itself.

    Returns:
        dict[int, dict[str, Any]]: Reducer outputs keyed by positional index.
    """
    features = ee.FeatureCollection(
        [
            ee.Feature(
                ee.Geometry.Point([lon, lat]).buffer(buffer_m) if buffer_m else ee.Geometry.Point([lon, lat]), {"i": i}
            )
            for i, (lat, lon) in enumerate(zip(points["lat"], points["lon"], strict=True))
        ]
    )
    result = image.reduceRegions(collection=features, reducer=reducer, scale=scale).getInfo()
    return {int(f["properties"]["i"]): f["properties"] for f in result["features"]}


def enrich(assets: pd.DataFrame) -> pd.DataFrame:
    """Add population within ``POPULATION_RADIUS_M`` (WorldPop) and ground elevation per asset.

    Elevation is bare earth from DeltaDTM along the low coast, where storm surge matters, and the Copernicus surface
    model inland.

    Args:
        assets: Frame with ``lat`` and ``lon``.

    Returns:
        pd.DataFrame: A copy with ``population`` (people) and ``elevation_m`` columns (NaN where unavailable).
    """
    population = (
        ee.ImageCollection(POPULATION)
        .filter(ee.Filter.And(ee.Filter.eq("country", "IND"), ee.Filter.eq("year", POPULATION_YEAR)))
        .mosaic()
        .select("population")
    )
    surface = ee.ImageCollection(ELEVATION).select("DEM").mosaic()
    elevation = ee.Image(COASTAL_DTM).rename("DEM").unmask(surface)  # DeltaDTM covers the low coast only
    people = _reduce(assets, population, ee.Reducer.sum(), 100, POPULATION_RADIUS_M)
    height = _reduce(assets, elevation, ee.Reducer.mean(), 30)
    enriched = assets.copy()
    enriched["population"] = [people.get(i, {}).get("sum", np.nan) for i in range(len(assets))]
    enriched["elevation_m"] = [height.get(i, {}).get("mean", np.nan) for i in range(len(assets))]
    return enriched.astype({"population": float, "elevation_m": float})


def nightlight_loss(points: pd.DataFrame, pre: tuple[date, date], post: tuple[date, date]) -> pd.DataFrame:
    """Observed night-light radiance before and after a storm around each point, and the percentage lost.

    Uses VIIRS VNP46A2 raw BRDF-corrected radiance masked to high-quality retrievals. The gap-filled band is not
    used: it carries pre-storm values into cloudy post-landfall nights and hides blackouts.

    Args:
        points: Frame with ``lat`` and ``lon``.
        pre: ``(start, end)`` of the pre-storm window (end exclusive).
        post: ``(start, end)`` of the post-landfall window (end exclusive).

    Returns:
        pd.DataFrame: Same index as ``points`` with ``ntl_pre``, ``ntl_post`` (nW/cm2/sr, window medians averaged
        over a ``NIGHT_LIGHTS_RADIUS_M`` buffer) and ``loss_pct``.
    """

    def high_quality(image: Any) -> Any:
        return image.select(NIGHT_LIGHTS_BAND).updateMask(image.select(NIGHT_LIGHTS_QUALITY_BAND).lte(1))

    collection = ee.ImageCollection(NIGHT_LIGHTS).map(high_quality)
    window = [collection.filterDate(start.isoformat(), end.isoformat()).median() for start, end in (pre, post)]
    stats = _reduce(
        points,
        window[0].rename("pre").addBands(window[1].rename("post")),
        ee.Reducer.mean(),
        500,
        NIGHT_LIGHTS_RADIUS_M,
    )
    frame = pd.DataFrame(
        {
            "ntl_pre": [stats.get(i, {}).get("pre", np.nan) for i in range(len(points))],
            "ntl_post": [stats.get(i, {}).get("post", np.nan) for i in range(len(points))],
        },
        index=points.index,
        dtype=float,
    )
    frame["loss_pct"] = 100.0 * (1.0 - frame["ntl_post"] / frame["ntl_pre"])
    return frame


def relief(bbox: tuple[float, float, float, float]) -> Grid:
    """Land elevation and sea-floor depth around a region, for the storm-surge transects.

    Args:
        bbox: ``(south, west, north, east)`` of the region; ``BATHYMETRY_MARGIN_DEG`` is added on every side so
            offshore transects reach the shelf edge.

    Returns:
        Grid: ETOPO1 bedrock relief in metres (negative below sea level) at 1 arc-minute, north-up.
    """
    south, west, north, east = bbox
    north, west = north + BATHYMETRY_MARGIN_DEG, west - BATHYMETRY_MARGIN_DEG
    width = round((east + BATHYMETRY_MARGIN_DEG - west) / RELIEF_CELL_DEG)
    height = round((north - south + BATHYMETRY_MARGIN_DEG) / RELIEF_CELL_DEG)
    pixels = ee.data.computePixels(  # pyright: ignore[reportPrivateImportUsage]
        {
            "expression": ee.Image(BATHYMETRY).select(BATHYMETRY_BAND).toFloat(),
            "fileFormat": "NUMPY_NDARRAY",
            "grid": {
                "dimensions": {"width": width, "height": height},
                "affineTransform": {
                    "scaleX": RELIEF_CELL_DEG,
                    "shearX": 0,
                    "translateX": west,
                    "shearY": 0,
                    "scaleY": -RELIEF_CELL_DEG,
                    "translateY": north,
                },
                "crsCode": "EPSG:4326",
            },
        }
    )
    return Grid(
        cells=np.asarray(pixels[BATHYMETRY_BAND], dtype=np.float64), north=north, west=west, cell_deg=RELIEF_CELL_DEG
    )
