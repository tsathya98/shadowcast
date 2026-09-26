from datetime import date
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from shadowcast_geo import earth

POINTS = pd.DataFrame({"lat": [19.8, 20.1], "lon": [85.8, 86.0]}, index=[10, 11])


@pytest.fixture
def ee(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock(name="ee")
    monkeypatch.setattr(earth, "ee", mock)
    return mock


def _features(*properties: dict[str, float | None]) -> dict[str, list[dict[str, dict[str, float | None]]]]:
    return {"features": [{"properties": {"i": i, **p}} for i, p in enumerate(properties)]}


def test_initialize(ee: MagicMock) -> None:
    earth.initialize("argmax-cyclone-2026")

    ee.Initialize.assert_called_once_with(project="argmax-cyclone-2026")


def test_enrich_adds_population_and_elevation(ee: MagicMock) -> None:
    population = ee.ImageCollection.return_value.filter.return_value.mosaic.return_value.select.return_value
    elevation = ee.ImageCollection.return_value.select.return_value.mosaic.return_value
    population.reduceRegions.return_value.getInfo.return_value = _features({"sum": 1200.0}, {"sum": None})
    elevation.reduceRegions.return_value.getInfo.return_value = _features({"mean": 3.5})

    enriched = earth.enrich(POINTS)

    assert enriched["population"].iloc[0] == 1200.0
    assert np.isnan(enriched["population"].iloc[1])
    assert enriched["elevation_m"].tolist()[0] == 3.5
    assert np.isnan(enriched["elevation_m"].iloc[1])
    ee.Geometry.Point.return_value.buffer.assert_called_with(2000)


def test_nightlight_loss(ee: MagicMock) -> None:
    window = ee.ImageCollection.return_value.map.return_value.filterDate.return_value.median.return_value
    stacked = window.rename.return_value.addBands.return_value
    stacked.reduceRegions.return_value.getInfo.return_value = _features(
        {"pre": 10.0, "post": 1.0}, {"pre": 2.0, "post": 2.0}
    )

    result = earth.nightlight_loss(POINTS, (date(2019, 4, 20), date(2019, 5, 2)), (date(2019, 5, 4), date(2019, 5, 11)))

    assert result.index.tolist() == [10, 11]
    assert result["loss_pct"].tolist() == [90.0, 0.0]
    window_calls = ee.ImageCollection.return_value.map.return_value.filterDate.call_args_list
    assert [c.args for c in window_calls] == [("2019-04-20", "2019-05-02"), ("2019-05-04", "2019-05-11")]

    high_quality = ee.ImageCollection.return_value.map.call_args.args[0]
    image = MagicMock(name="image")
    high_quality(image)
    image.select.assert_any_call("Mandatory_Quality_Flag")
    image.select.return_value.lte.assert_called_once_with(1)
