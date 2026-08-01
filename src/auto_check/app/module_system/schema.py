from __future__ import annotations

import hashlib
import importlib.resources
import re
from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .contracts import ModuleManifest
from .storage import ModuleStateStore


_MIGRATION_NAME = re.compile(r"(?P<version>\d{3,})_(?P<name>[A-Za-z0-9][A-Za-z0-9_-]*)\.sql$")
_STATEMENT_BREAK = re.compile(r"(?m)^\s*-- module-statement-break\s*$")
_CONNECTION_STRING = re.compile(r"\b(?:mysql|postgres(?:ql)?)(?:\+[\w-]+)?://[^\s'\"]+", re.I)


class ModuleMigrationError(RuntimeError):
    """Raised when isolated module migration cannot safely continue."""


class ModuleSchemaError(RuntimeError):
    """Raised when a module-owned table is incompatible with its declaration."""


@dataclass(frozen=True)
class ModuleMigration:
    version: int
    name: str
    checksum: str
    statements: tuple[str, ...]


def load_module_migrations(package_name: str) -> tuple[ModuleMigration, ...]:
    """Read numbered migrations from one trusted, installed module package."""

    try:
        migrations_dir = importlib.resources.files(package_name).joinpath("migrations")
    except ModuleNotFoundError as exc:
        raise ModuleMigrationError("无法加载模块迁移文件") from None

    if not migrations_dir.is_dir():
        return ()

    discovered: list[ModuleMigration] = []
    for path in migrations_dir.iterdir():
        if not path.is_file() or not path.name.endswith(".sql"):
            continue
        match = _MIGRATION_NAME.fullmatch(path.name)
        if match is None:
            raise ModuleMigrationError("模块迁移文件名必须使用 001_name.sql 格式")
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise ModuleMigrationError("无法读取模块迁移文件") from None
        statements = tuple(
            section.strip()
            for section in _STATEMENT_BREAK.split(content.decode("utf-8"))
            if section.strip()
        )
        discovered.append(
            ModuleMigration(
                version=int(match.group("version")),
                name=match.group("name"),
                checksum=hashlib.sha256(content).hexdigest(),
                statements=statements,
            )
        )

    discovered.sort(key=lambda item: item.version)
    if len({item.version for item in discovered}) != len(discovered):
        raise ModuleMigrationError("模块迁移版本重复")
    return tuple(discovered)


class ModuleMigrationRunner:
    def __init__(self, database: Any, schema_registry: ModuleSchemaRegistry | None = None) -> None:
        self._database = database
        self._store = ModuleStateStore(database)
        self._schema_registry = schema_registry

    def run(self, manifest: ModuleManifest, package_name: str) -> int:
        lock_name = f"auto_check_module_{manifest.id}"
        with self._database.connect() as lock_connection:
            lock_acquired = False
            primary_error: ModuleMigrationError | None = None
            try:
                lock_acquired = (
                    lock_connection.execute(
                        text("SELECT GET_LOCK(:lock_name, 10)"), {"lock_name": lock_name}
                    ).scalar_one()
                    == 1
                )
                if not lock_acquired:
                    raise ModuleMigrationError("无法获取模块迁移锁")

                migrations = load_module_migrations(package_name)
                self._validate_migrations(manifest, migrations)
                current_version = self._validate_applied_checksums(manifest, migrations)
                for migration in migrations[current_version:]:
                    history_id = self._store.record_migration_started(manifest.id, migration)
                    try:
                        with self._database.transaction() as connection:
                            for statement in migration.statements:
                                connection.execute(text(statement))
                        if (
                            self._schema_registry is not None
                            and migration.version == manifest.schema_version
                        ):
                            self._schema_registry.validate(lock_connection)
                        self._store.record_migration_completed(history_id, migration)
                    except Exception as exc:
                        message = _sanitize_error(exc)
                        try:
                            self._store.record_migration_failed(history_id, message)
                        except Exception:
                            raise ModuleMigrationError(
                                "模块迁移失败，且无法保存失败审计记录"
                            ) from None
                        raise ModuleMigrationError(f"模块迁移失败：{message}") from None

                if self._schema_registry is not None and current_version == manifest.schema_version:
                    self._validate_existing_schema(manifest, migrations, lock_connection)
                return manifest.schema_version
            except ModuleMigrationError as exc:
                primary_error = exc
                raise
            except Exception as exc:
                primary_error = ModuleMigrationError(f"模块迁移失败：{_sanitize_error(exc)}")
                raise primary_error from None
            finally:
                if lock_acquired:
                    try:
                        released = lock_connection.execute(
                            text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": lock_name}
                        ).scalar_one()
                        if released != 1:
                            raise RuntimeError("模块迁移锁未确认释放")
                    except Exception:
                        cleanup_status = _invalidate_connection(lock_connection)
                        lock_release_error = f"模块迁移锁释放失败{cleanup_status}"
                        if primary_error is not None:
                            raise ModuleMigrationError(
                                f"{primary_error}；且{lock_release_error}"
                            ) from None
                        raise ModuleMigrationError(lock_release_error) from None

    @staticmethod
    def _validate_migrations(manifest: ModuleManifest, migrations: tuple[ModuleMigration, ...]) -> None:
        versions = tuple(item.version for item in migrations)
        expected = tuple(range(1, manifest.schema_version + 1))
        if versions != expected:
            raise ModuleMigrationError("模块迁移版本必须从 001 连续到目标版本")

    def _validate_applied_checksums(
        self, manifest: ModuleManifest, migrations: tuple[ModuleMigration, ...]
    ) -> int:
        applied = self._store.load_schema_version(manifest.id)
        completed_migrations = self._store.load_completed_migrations(manifest.id)
        if applied is None:
            if completed_migrations:
                raise ModuleMigrationError("已应用模块迁移版本不一致")
            return 0
        version, checksum = applied
        if version < 0 or version > manifest.schema_version:
            raise ModuleMigrationError("模块已应用版本与目标版本不一致")
        if version == 0:
            if completed_migrations:
                raise ModuleMigrationError("已应用模块迁移版本不一致")
            return 0
        expected = migrations[version - 1]
        if expected.version != version or expected.checksum != checksum:
            raise ModuleMigrationError("已应用模块迁移摘要不一致")
        completed_versions = tuple(item[0] for item in completed_migrations)
        if completed_versions != tuple(range(1, version + 1)):
            raise ModuleMigrationError("已应用模块迁移版本不一致")
        for completed_version, completed_checksum in completed_migrations:
            completed_migration = migrations[completed_version - 1]
            if completed_migration.checksum != completed_checksum:
                raise ModuleMigrationError("已应用模块迁移摘要不一致")
        return version

    def _validate_existing_schema(
        self,
        manifest: ModuleManifest,
        migrations: tuple[ModuleMigration, ...],
        connection: Any,
    ) -> None:
        try:
            self._schema_registry.validate(connection)
        except Exception as exc:
            checksum = migrations[-1].checksum if migrations else hashlib.sha256(b"").hexdigest()
            audit_migration = ModuleMigration(
                manifest.schema_version,
                "schema_validation",
                checksum,
                (),
            )
            message = _sanitize_error(exc)
            try:
                history_id = self._store.record_migration_started(manifest.id, audit_migration)
                self._store.record_migration_failed(history_id, message)
            except Exception:
                raise ModuleMigrationError("模块 schema 校验失败，且无法保存失败审计记录") from None
            raise ModuleMigrationError(f"模块迁移失败：{message}") from None


class ModuleSchemaRegistry:
    """Collect and validate the tables owned by a single module."""

    def __init__(self) -> None:
        self._tables: dict[str, frozenset[str]] = {}

    def add(self, table_name: str, columns: Iterable[str]) -> None:
        normalized_name = table_name.strip()
        normalized_columns = frozenset(column.strip() for column in columns if column.strip())
        if not normalized_name or not normalized_columns:
            raise ValueError("模块表名和字段不能为空")
        if normalized_name in self._tables:
            raise ValueError(f"模块表重复注册：{normalized_name}")
        self._tables[normalized_name] = normalized_columns

    def validate(self, connection: Any) -> None:
        rows = connection.execute(
            text(
                """
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = DATABASE()
                """
            )
        ).all()
        actual_columns: dict[str, set[str]] = {}
        for table_name, column_name in rows:
            actual_columns.setdefault(str(table_name), set()).add(str(column_name))
        missing = sorted(
            f"{table_name}.{column_name}"
            for table_name, expected_columns in self._tables.items()
            for column_name in expected_columns - actual_columns.get(table_name, set())
        )
        if missing:
            raise ModuleSchemaError(f"模块数据库缺少字段：{', '.join(missing)}")


def _sanitize_error(error: Exception) -> str:
    if isinstance(error, SQLAlchemyError):
        return f"数据库执行错误（{type(error).__name__}）"
    message = _CONNECTION_STRING.sub("[连接信息]", str(error)).strip()
    message = re.sub(r"\s*\[SQL:.*?\]", "", message, flags=re.DOTALL)
    message = re.sub(r"\s*\[parameters:.*?\]", "", message, flags=re.DOTALL)
    if len(message) > 500:
        message = f"{message[:500]}…"
    return message or "未知迁移错误"


def _invalidate_connection(connection: Any) -> str:
    try:
        connection.invalidate()
    except Exception:
        try:
            connection.close()
        except Exception:
            return "，且无法使迁移锁连接失效且无法关闭连接"
        return "，且无法使迁移锁连接失效，已尝试关闭连接"
    return ""
