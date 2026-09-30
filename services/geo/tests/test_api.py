from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shadowcast_geo.api import create_app
from shadowcast_geo.config import Settings
from tests.conftest import MemoryArtifacts


@pytest.fixture
def client(store: MemoryArtifacts) -> Iterator[TestClient]:
    with TestClient(create_app(Settings(allowed_origins=("https://shadowcast.test",)), store, store)) as test_client:
        yield test_client


def test_health_and_scenarios(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok", "scenarios": ["fani-2019"]}
    scenarios = client.get("/scenarios").json()
    assert [s["id"] for s in scenarios] == ["fani-2019"]
    assert "model" not in scenarios[0]
    detail = client.get("/scenarios/fani-2019").json()
    assert detail["skill"]["auc"] == 0.91
    assert detail["track_source"] == "IBTrACS best track"


def test_track_geojson(client: TestClient) -> None:
    features = client.get("/scenarios/fani-2019/track").json()["features"]

    assert features[0]["geometry"]["type"] == "LineString"
    assert len(features[0]["geometry"]["coordinates"]) == 7
    assert features[1]["properties"]["vmax_kt"] == 100.0
    assert "lat" not in features[1]["properties"]


@pytest.mark.parametrize(
    ("query", "expected_ids", "expected_total"),
    [
        ("", ["osm:node/1", "osm:way/2"], 2),
        ("?kind=school", ["osm:way/2"], 1),
        ("?kind=school&kind=hospital&limit=1", ["osm:node/1"], 2),
        ("?min_score=0.5", ["osm:node/1"], 1),
        ("?offset=1", ["osm:way/2"], 2),
        ("?q=PURI", ["osm:node/1"], 1),
        ("?q=way/2", ["osm:way/2"], 1),
    ],
)
def test_assets_filters(client: TestClient, query: str, expected_ids: list[str], expected_total: int) -> None:
    page = client.get(f"/scenarios/fani-2019/assets{query}").json()

    assert [a["asset_id"] for a in page["items"]] == expected_ids
    assert page["total"] == expected_total
    assert "extra_field" not in page["items"][0]


def test_asset_detail_with_slash_in_id(client: TestClient) -> None:
    detail = client.get("/scenarios/fani-2019/assets/osm:way/2").json()

    assert detail["asset"]["asset_id"] == "osm:way/2"
    assert [p["time"] for p in detail["timeline"]][:2] == ["2019-05-02T12:00:00Z", "2019-05-02T12:15:00Z"]
    assert len(detail["timeline"]) == 73
    assert max(p["wind_kt"] for p in detail["timeline"]) > 50


def test_hazard_snapshot(client: TestClient) -> None:
    inside = client.get("/scenarios/fani-2019/hazard", params={"at": "2019-05-03T02:30:00+05:30"}).json()
    naive = client.get("/scenarios/fani-2019/hazard", params={"at": "2019-05-02T21:00:00"}).json()
    outside = client.get("/scenarios/fani-2019/hazard", params={"at": "2020-01-01T00:00:00Z"}).json()

    assert inside["at"] == "2019-05-02T21:00:00Z"
    assert inside["storm"]["lat"] == pytest.approx(19.5)
    assert inside["asset_ids"] == ["osm:node/1", "osm:way/2"]
    assert inside["wind_kt"][0] < 5 < inside["wind_kt"][1]  # the near asset sits in the calm eye at this instant
    assert naive["wind_kt"] == inside["wind_kt"]
    assert outside["storm"] is None
    assert outside["wind_kt"] == [0.0, 0.0]


def test_evidence_images(client: TestClient) -> None:
    image = client.get("/scenarios/fani-2019/evidence/night-lights-post.png")

    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    assert image.content == b"png:night-lights-post"
    assert client.get("/scenarios/fani-2019/evidence/elsewhere.png").status_code == 404


def test_live_digest_is_cached(client: TestClient, store: MemoryArtifacts) -> None:
    assert client.get("/live").json() == {"run_at": None, "cyclones": [], "warnings": []}

    store.write_json("manifests/2026/09/27/0615Z.json", {})
    assert client.get("/live").json()["run_at"] is None  # served from the cache until the TTL passes


def test_roads(client: TestClient) -> None:
    assert client.get("/scenarios/fani-2019/roads").json()["type"] == "FeatureCollection"
    assert client.get("/scenarios/fani-2019").json()["roads"]["km_cut"] == 10


def test_surge(client: TestClient) -> None:
    assert client.get("/scenarios/fani-2019/surge").json()[0]["peak_m"] == 1.5
    assert client.get("/scenarios/fani-2019").json()["surge"]["peak_m"] == 1.5
    assert client.get("/scenarios/fani-2019").json()["rain"]["spearman"] == 0.7


def test_backtest_and_cors_and_gzip(client: TestClient) -> None:
    response = client.get("/scenarios/fani-2019/backtest", headers={"Origin": "https://shadowcast.test"})

    assert response.json()["skill"]["auc"] == 0.91
    assert response.headers["access-control-allow-origin"] == "https://shadowcast.test"
    track = client.get("/scenarios/fani-2019/track", headers={"Accept-Encoding": "gzip"})
    assert track.headers["content-encoding"] == "gzip"


@pytest.mark.parametrize(
    "path",
    [
        "/scenarios/nope",
        "/scenarios/nope/track",
        "/scenarios/fani-2019/assets/osm:node/404",
        "/scenarios/nope/backtest",
    ],
)
def test_not_found(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 404


def test_empty_store_serves_no_scenarios(tmp_path: Path) -> None:
    empty_store = MemoryArtifacts()
    with TestClient(create_app(Settings(), empty_store, empty_store)) as empty:
        assert empty.get("/health").json() == {"status": "ok", "scenarios": []}
        assert empty.get("/scenarios").json() == []


def test_forecast_replay_endpoints(client: TestClient) -> None:
    listing = client.get("/scenarios/fani-2019/forecasts").json()
    assert [(f["key"], f["lead_h"], f["members"]) for f in listing] == [("20190501T12Z", 39.5, 52)]

    tracks = client.get("/scenarios/fani-2019/forecasts/20190501T12Z/tracks").json()["features"]
    assert [t["properties"]["member"] for t in tracks] == [1, 2]
    assert tracks[1]["properties"]["max_vmax_kt"] == 80.0
    assert len(tracks[0]["geometry"]["coordinates"]) == len(tracks[0]["properties"]["times"]) == 7

    page = client.get("/scenarios/fani-2019/forecasts/20190501T12Z/assets", params={"kind": "hospital"}).json()
    assert page["total"] == 1
    assert page["items"][0]["p64"] == 0.25
    assert page["items"][0]["gale_arrival"] == "2019-05-02T18:00:00Z"
    assert client.get("/scenarios/fani-2019/forecasts/20190501T12Z/assets?kind=school").json()["total"] == 0


@pytest.mark.parametrize("path", ["/scenarios/fani-2019/forecasts/19000101T00Z/tracks", "/scenarios/nope/forecasts"])
def test_forecast_not_found(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 404


def test_invalid_query_is_rejected(client: TestClient) -> None:
    assert client.get("/scenarios/fani-2019/assets?limit=0").status_code == 422
