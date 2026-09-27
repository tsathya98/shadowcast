"""Built scenario artifacts: JSON documents in Google Cloud Storage, the service's only store.

Layout::

    scenarios/index.json                 scenario summaries
    scenarios/{id}/scenario.json         metadata, calibration and backtest skill
    scenarios/{id}/track.json            storm track fixes
    scenarios/{id}/assets.json           ranked assets with hazard, probability and reasons
    scenarios/{id}/backtest.json         per-substation predicted vs observed night-light loss
    models/outage.json                   calibrated outage model
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from google.cloud import storage

from shadowcast_geo.config import Settings


class ArtifactStore(Protocol):
    """Reads and writes JSON artifacts by relative path."""

    def read_json(self, path: str) -> Any:
        """Read one JSON document.

        Args:
            path: Artifact path relative to the store root.

        Returns:
            Any: The decoded JSON value.
        """
        ...

    def write_json(self, path: str, data: Any) -> None:
        """Write one JSON document.

        Args:
            path: Artifact path relative to the store root.
            data: JSON-serialisable value.
        """
        ...

    def exists(self, path: str) -> bool:
        """Whether an artifact exists.

        Args:
            path: Artifact path relative to the store root.

        Returns:
            bool: ``True`` when the artifact exists.
        """
        ...


class GcsArtifacts:
    """Artifacts in a Google Cloud Storage bucket, via Application Default Credentials."""

    def __init__(self, bucket: str, client: storage.Client | None = None) -> None:
        """Bind to a bucket.

        Args:
            bucket: Bucket name (without ``gs://``).
            client: Optional pre-built client.
        """
        self._bucket = (client or storage.Client()).bucket(bucket)

    def read_json(self, path: str) -> Any:
        """Download and decode one JSON object.

        Args:
            path: Object name.

        Returns:
            Any: The decoded JSON value.
        """
        return json.loads(self._bucket.blob(path).download_as_bytes())

    def write_json(self, path: str, data: Any) -> None:
        """Encode and upload one JSON object.

        Args:
            path: Object name.
            data: JSON-serialisable value.
        """
        body = json.dumps(data, ensure_ascii=False, allow_nan=False)
        # google-cloud-storage ships incomplete type hints for upload_from_string's optional parameters.
        self._bucket.blob(path).upload_from_string(body, content_type="application/json")  # pyright: ignore[reportUnknownMemberType]

    def exists(self, path: str) -> bool:
        """Whether an object exists in the bucket.

        Args:
            path: Object name.

        Returns:
            bool: ``True`` when the object exists.
        """
        return bool(self._bucket.blob(path).exists())


def artifact_store(settings: Settings) -> ArtifactStore:
    """The artifact store for these settings.

    Args:
        settings: Resolved settings.

    Returns:
        ArtifactStore: The scenario bucket.
    """
    return GcsArtifacts(settings.bucket)
