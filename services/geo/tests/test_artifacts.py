import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from shadowcast_geo.artifacts import GcsArtifacts, LocalArtifacts, artifact_store
from shadowcast_geo.config import Settings


def test_local_roundtrip_and_exists(tmp_path: Path) -> None:
    store = LocalArtifacts(tmp_path)

    store.write_json("scenarios/fani-2019/scenario.json", {"id": "fani-2019", "storm": "Fani ବାତ୍ୟା"})

    assert store.exists("scenarios/fani-2019/scenario.json")
    assert not store.exists("scenarios/missing.json")
    assert store.read_json("scenarios/fani-2019/scenario.json")["storm"] == "Fani ବାତ୍ୟା"


def test_local_rejects_non_finite_numbers(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Out of range float"):
        LocalArtifacts(tmp_path).write_json("x.json", {"auc": float("nan")})


def test_gcs_read_write_exists() -> None:
    client = MagicMock()
    blob = client.bucket.return_value.blob.return_value
    blob.download_as_bytes.return_value = b'{"id": "dana-2024"}'
    blob.exists.return_value = True
    store = GcsArtifacts("scenarios-bucket", client=client)

    store.write_json("scenarios/index.json", [{"id": "dana-2024"}])

    client.bucket.assert_called_once_with("scenarios-bucket")
    blob.upload_from_string.assert_called_once_with(json.dumps([{"id": "dana-2024"}]), content_type="application/json")
    assert store.read_json("scenarios/index.json") == {"id": "dana-2024"}
    assert store.exists("scenarios/index.json") is True


def test_artifact_store_selection(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    gcs = MagicMock(name="GcsArtifacts")
    monkeypatch.setattr("shadowcast_geo.artifacts.GcsArtifacts", gcs)

    assert isinstance(artifact_store(settings), LocalArtifacts)
    assert artifact_store(Settings(bucket="b")) is gcs.return_value
    gcs.assert_called_once_with("b")
