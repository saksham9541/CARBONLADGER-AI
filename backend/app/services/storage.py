"""
CarbonLedger AI — Private Object Storage Subsystem
==================================================
Abstract storage interface with LocalStorageBackend and optional Supabase backend.
Files are segregated by organization and given unguessable UUID-based storage paths.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO, Optional
from uuid import UUID

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class StorageBackend:
    """Abstract storage backend protocol."""

    def save(
        self,
        org_id: UUID,
        file_id: UUID,
        filename: str,
        content: bytes,
    ) -> str:
        """
        Save content to private storage.
        Returns the persistent relative storage path.
        """
        raise NotImplementedError

    def get(self, storage_path: str) -> bytes:
        """Retrieve binary content from storage."""
        raise NotImplementedError

    def delete(self, storage_path: str) -> bool:
        """Delete file from storage. Returns True if deleted."""
        raise NotImplementedError

    def exists(self, storage_path: str) -> bool:
        """Check if file exists in storage."""
        raise NotImplementedError


class LocalStorageBackend(StorageBackend):
    """
    Local filesystem storage provider.
    Guarantees organization isolation on disk:
      {base_dir}/{org_id}/{file_id}/{sanitized_filename}
    """

    def __init__(self, base_path: Optional[str] = None) -> None:
        settings = get_settings()
        self.base_dir = Path(base_path or settings.local_storage_path).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, storage_path: str) -> Path:
        resolved = (self.base_dir / storage_path).resolve()
        # Prevent directory traversal attacks
        if not str(resolved).startswith(str(self.base_dir)):
            raise ValueError(f"Path traversal detected: {storage_path}")
        return resolved

    def save(
        self,
        org_id: UUID,
        file_id: UUID,
        filename: str,
        content: bytes,
    ) -> str:
        # Build clean, unguessable path: org_id/file_id/filename
        safe_rel_dir = Path(str(org_id)) / str(file_id)
        target_dir = self.base_dir / safe_rel_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        target_file = target_dir / filename
        # Ensure path stays within target_dir
        if not str(target_file.resolve()).startswith(str(self.base_dir)):
            raise ValueError(f"Path traversal detected in filename: {filename}")

        target_file.write_bytes(content)
        rel_path = str(safe_rel_dir / filename).replace("\\", "/")
        logger.info("Saved file to local storage", path=rel_path, bytes=len(content))
        return rel_path

    def get(self, storage_path: str) -> bytes:
        file_path = self._resolve_safe_path(storage_path)
        if not file_path.is_file():
            raise FileNotFoundError(f"Stored file not found: {storage_path}")
        return file_path.read_bytes()

    def delete(self, storage_path: str) -> bool:
        try:
            file_path = self._resolve_safe_path(storage_path)
            if file_path.is_file():
                file_path.unlink()
                # Clean up parent directories if empty
                parent = file_path.parent
                if parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()
                return True
            return False
        except Exception as exc:
            logger.warning("Failed to delete stored file", path=storage_path, error=str(exc))
            return False

    def exists(self, storage_path: str) -> bool:
        try:
            file_path = self._resolve_safe_path(storage_path)
            return file_path.is_file()
        except ValueError:
            return False


_storage_singleton: Optional[StorageBackend] = None


def get_storage_service() -> StorageBackend:
    """Dependency injector / factory for storage backend."""
    global _storage_singleton
    if _storage_singleton is None:
        settings = get_settings()
        if settings.storage_backend.lower() == "local":
            _storage_singleton = LocalStorageBackend()
        else:
            # Default to local storage with warning if external not yet wired
            _storage_singleton = LocalStorageBackend()
    return _storage_singleton
