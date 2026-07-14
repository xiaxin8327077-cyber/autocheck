from __future__ import annotations

from pathlib import Path
from typing import Any


def migrate_legacy_histories(config_path: str | Path) -> dict[str, int]:
    """Legacy runtime history migration is disabled after MySQL storage cutover."""

    raise RuntimeError("legacy SQLite history migration is disabled")


def build_legacy_history_migration_status(config_path: str | Path) -> dict[str, Any]:
    """Return a stable disabled status without reading local SQLite files."""

    return {
        "can_migrate": False,
        "completed": True,
        "has_legacy_sources": False,
        "source_count": 0,
        "existing_count": 0,
        "pending_count": 0,
        "failed_count": 0,
        "completed_count": 0,
        "status_text": "旧 SQLite 历史迁移已停用，请使用离线导出工具完成人工迁移",
        "sources": [],
    }
