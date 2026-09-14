from __future__ import annotations


class VersionConflictError(RuntimeError):
    """Raised when an optimistic-lock version is stale."""
