"""Artifact stores: Google Cloud Storage in production, the local filesystem for development."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol

from google.cloud import storage


class ArtifactStore(Protocol):
    """Destination for archived artifacts."""

    async def put(self, path: str, body: bytes, content_type: str) -> None:
        """Write one object.

        Args:
            path: Object path relative to the archive root, using ``/`` separators.
            body: Object bytes.
            content_type: MIME type to record with the object.
        """
        ...


class GcsStore:
    """Writes artifacts to a Google Cloud Storage bucket using Application Default Credentials."""

    def __init__(self, bucket: str, client: storage.Client | None = None) -> None:
        """Bind the store to a bucket.

        Args:
            bucket: Bucket name (without ``gs://``).
            client: Optional pre-built client; defaults to one using Application Default Credentials.
        """
        self._bucket = (client or storage.Client()).bucket(bucket)

    async def put(self, path: str, body: bytes, content_type: str) -> None:
        """Upload one object without blocking the event loop (the GCS client is synchronous).

        Args:
            path: Object name inside the bucket.
            body: Object bytes.
            content_type: MIME type stored as the object's ``Content-Type``.
        """
        blob = self._bucket.blob(path)
        # google-cloud-storage ships incomplete type hints for upload_from_string's optional parameters.
        await asyncio.to_thread(blob.upload_from_string, body, content_type=content_type)  # pyright: ignore[reportUnknownArgumentType]


class LocalStore:
    """Writes artifacts under a local directory, mirroring the bucket layout."""

    def __init__(self, root: Path) -> None:
        """Bind the store to a root directory.

        Args:
            root: Directory that plays the role of the bucket root.
        """
        self._root = root

    async def put(self, path: str, body: bytes, content_type: str) -> None:
        """Write one file, creating parent directories as needed.

        Args:
            path: File path relative to the root, using ``/`` separators.
            body: File bytes.
            content_type: Ignored locally; accepted for interface parity with :class:`GcsStore`.
        """
        target = self._root / path
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_bytes, body)
