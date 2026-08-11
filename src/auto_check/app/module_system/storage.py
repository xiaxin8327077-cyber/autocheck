from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from .contracts import ModuleManifest, ModuleStatus

if TYPE_CHECKING:
    from .schema import ModuleMigration


class ModuleStateStore:
    """Persist module discovery state and isolated migration history."""

    def __init__(self, database: Any) -> None:
        self._database = database

    def load_enabled(self, module_id: str) -> bool | None:
        with self._database.transaction() as connection:
            value = connection.execute(
                text("SELECT enabled FROM app_modules WHERE module_id = :module_id"),
                {"module_id": module_id},
            ).scalar_one_or_none()
        return None if value is None else bool(value)

    def save_discovered(self, manifest: ModuleManifest) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO app_modules (
                        module_id, module_version, enabled, status, last_error, installed_at, updated_at
                    ) VALUES (
                        :module_id, :module_version, :enabled, :status, :last_error,
                        CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6)
                    )
                    ON DUPLICATE KEY UPDATE
                        module_version = :module_version,
                        updated_at = CURRENT_TIMESTAMP(6)
                    """
                ),
                {
                    "module_id": manifest.id,
                    "module_version": manifest.version,
                    "enabled": True,
                    "status": ModuleStatus.DISCOVERED.value,
                    "last_error": "",
                },
            )

    def set_enabled(self, module_id: str, enabled: bool) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                text(
                    """
                    UPDATE app_modules
                    SET enabled = :enabled, updated_at = CURRENT_TIMESTAMP(6)
                    WHERE module_id = :module_id
                    """
                ),
                {"module_id": module_id, "enabled": enabled},
            )

    def set_status(self, module_id: str, status: ModuleStatus, error: str = "") -> None:
        with self._database.transaction() as connection:
            connection.execute(
                text(
                    """
                    UPDATE app_modules
                    SET status = :status, last_error = :last_error, updated_at = CURRENT_TIMESTAMP(6)
                    WHERE module_id = :module_id
                    """
                ),
                {
                    "module_id": module_id,
                    "status": status.value,
                    "last_error": error,
                },
            )

    def load_schema_version(self, module_id: str) -> tuple[int, str] | None:
        with self._database.transaction() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT schema_version, checksum
                    FROM app_module_schema_versions
                    WHERE module_id = :module_id
                    """
                ),
                {"module_id": module_id},
            ).first()
        if row is None:
            return None
        return int(row[0]), str(row[1])

    def load_completed_migrations(self, module_id: str) -> tuple[tuple[int, str], ...]:
        with self._database.transaction() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT to_version, checksum
                    FROM app_module_migration_history
                    WHERE module_id = :module_id AND status = :status
                    ORDER BY to_version, id
                    """
                ),
                {"module_id": module_id, "status": "completed"},
            ).all()
        return tuple((int(row[0]), str(row[1])) for row in rows)

    def record_migration_started(self, module_id: str, migration: ModuleMigration) -> int:
        with self._database.transaction() as connection:
            from_version = connection.execute(
                text(
                    """
                    SELECT schema_version FROM app_module_schema_versions
                    WHERE module_id = :module_id
                    """
                ),
                {"module_id": module_id},
            ).scalar_one_or_none()
            result = connection.execute(
                text(
                    """
                    INSERT INTO app_module_migration_history (
                        module_id, from_version, to_version, status, checksum, started_at
                    ) VALUES (
                        :module_id, :from_version, :to_version, :status, :checksum,
                        CURRENT_TIMESTAMP(6)
                    )
                    """
                ),
                {
                    "module_id": module_id,
                    "from_version": 0 if from_version is None else int(from_version),
                    "to_version": migration.version,
                    "status": "running",
                    "checksum": migration.checksum,
                },
            )
        history_id = result.lastrowid
        if history_id is None:
            raise RuntimeError("无法创建模块迁移历史记录")
        return int(history_id)

    def record_migration_completed(self, history_id: int, migration: ModuleMigration) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO app_module_schema_versions (
                        module_id, schema_version, applied_at, checksum
                    ) SELECT module_id, :schema_version, CURRENT_TIMESTAMP(6), :checksum
                    FROM app_module_migration_history
                    WHERE id = :history_id
                    ON DUPLICATE KEY UPDATE
                        schema_version = :schema_version,
                        applied_at = CURRENT_TIMESTAMP(6),
                        checksum = :checksum
                    """
                ),
                {
                    "history_id": history_id,
                    "schema_version": migration.version,
                    "checksum": migration.checksum,
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE app_module_migration_history
                    SET status = :status, finished_at = CURRENT_TIMESTAMP(6), error_message = NULL
                    WHERE id = :history_id
                    """
                ),
                {"history_id": history_id, "status": "completed"},
            )

    def record_migration_failed(self, history_id: int, error: str) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                text(
                    """
                    UPDATE app_module_migration_history
                    SET status = :status, finished_at = CURRENT_TIMESTAMP(6), error_message = :error
                    WHERE id = :history_id
                    """
                ),
                {"history_id": history_id, "status": "failed", "error": error},
            )
