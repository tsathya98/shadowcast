"""Built scenario artifacts: JSON documents in Google Cloud Storage (production) or a local directory (development).

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
from pathlib import Path
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


class LocalArtifacts:
    """Artifacts under a local directory, mirroring the bucket layout."""

    def __init__(self, root: Path) -> None:
        """Bind to a root directory.

        Args:
            root: Directory playing the role of the bucket root.
        """
        self._root = root

    def read_json(self, path: str) -> Any:
        """Read and decode one JSON file.

        Args:
            path: File path relative to the root.

        Returns:
            Any: The decoded JSON value.
        """
        return json.loads((self._root / path).read_text(encoding="utf-8"))

    def write_json(self, path: str, data: Any) -> None:
        """Encode and write one JSON file, creating parent directories.

        Args:
            path: File path relative to the root.
            data: JSON-serialisable value.
        """
        target = self._root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding="utf-8")

    def exists(self, path: str) -> bool:
        """Whether a file exists under the root.

        Args:
            path: File path relative to the root.

        Returns:
            bool: ``True`` when the file exists.
        """
        return (self._root / path).is_file()


def artifact_store(settings: Settings) -> ArtifactStore:
    """Choose the artifact store for the current environment.

    Args:
        settings: Resolved settings.

    Returns:
        ArtifactStore: GCS when ``settings.bucket`` is set, otherwise the local artifact directory.
    """
    return GcsArtifacts(settings.bucket) if settings.bucket else LocalArtifacts(settings.artifact_dir)
