from __future__ import annotations

import hashlib
import importlib.resources
import re
from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import text

from auto_check.app.app_database import EXPECTED_APP_SCHEMA
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
                                if self._schema_registry is not None:
                                    self._schema_registry.validate_statement(statement)
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

    def __init__(self, module_id: str | None = None, *, table_prefix: str | None = None) -> None:
        if module_id is not None and not re.fullmatch(r"[a-z][a-z0-9_]*", module_id):
            raise ValueError("模块 ID 不合法")
        prefix = table_prefix if table_prefix is not None else (f"{module_id}_" if module_id else None)
        if prefix is not None and not re.fullmatch(r"[a-z][a-z0-9_]*_", prefix):
            raise ValueError("模块表前缀不合法")
        self._module_id = module_id
        self._table_prefix = prefix
        self._tables: dict[str, frozenset[str]] = {}

    @property
    def declared_table_names(self) -> frozenset[str]:
        return frozenset(self._tables)

    def add(self, table_name: str, columns: Iterable[str]) -> None:
        normalized_name = table_name.strip()
        normalized_columns = frozenset(column.strip() for column in columns if column.strip())
        if not normalized_name or not normalized_columns:
            raise ValueError("模块表名和字段不能为空")
        if normalized_name in EXPECTED_APP_SCHEMA:
            raise ValueError("模块不能声明核心应用表")
        if self._table_prefix is not None and not normalized_name.startswith(self._table_prefix):
            raise ValueError("模块表必须使用模块命名空间前缀")
        if normalized_name in self._tables:
            raise ValueError(f"模块表重复注册：{normalized_name}")
        self._tables[normalized_name] = normalized_columns

    def validate_statement(self, statement: str) -> None:
        """Allow only a small, analyzable DDL subset over this module's table prefix."""
        tokens = _sql_tokens(statement)
        if tokens[-1:] == (";",):
            tokens = tokens[:-1]
        if not tokens or ";" in tokens:
            raise ModuleMigrationError("模块迁移 SQL 不可安全分析")
        upper = [token.upper() for token in tokens]
        if any(
            token
            in {
                "PROCEDURE",
                "FUNCTION",
                "VIEW",
                "TRIGGER",
                "PREPARE",
                "EXECUTE",
                "CALL",
                "SELECT",
                "JOIN",
                "AS",
                "LIKE",
            }
            for token in upper
        ):
            raise ModuleMigrationError("模块迁移 SQL 不可安全分析")
        references: list[str] = []
        if upper[:2] == ["CREATE", "TABLE"]:
            table_index = 5 if upper[2:5] == ["IF", "NOT", "EXISTS"] else 2
            references.append(_table_after(tokens, table_index))
        elif upper[:2] == ["ALTER", "TABLE"]:
            if any(token in {"RENAME", "EXCHANGE", "WITH"} for token in upper[3:]):
                raise ModuleMigrationError("模块迁移 SQL 不可安全分析")
            references.append(_table_after(tokens, 2))
        elif upper[:2] == ["DROP", "TABLE"]:
            table_index = 4 if upper[2:4] == ["IF", "EXISTS"] else 2
            references.extend(_drop_table_targets(tokens, table_index))
        elif upper[:2] == ["CREATE", "INDEX"] or (
            len(upper) >= 3
            and upper[0] == "CREATE"
            and upper[1] in {"UNIQUE", "FULLTEXT", "SPATIAL"}
            and upper[2] == "INDEX"
        ):
            references.append(_table_after(tokens, _require_token(upper, "ON") + 1))
        elif upper[:2] == ["DROP", "INDEX"]:
            references.append(_table_after(tokens, _require_token(upper, "ON") + 1))
        else:
            raise ModuleMigrationError("模块迁移 SQL 不可安全分析")
        for index, token in enumerate(upper):
            if token == "REFERENCES":
                references.append(_table_after(tokens, index + 1))
        for table_name in references:
            if not self._owns_table(table_name):
                raise ModuleMigrationError("模块迁移 SQL 引用了未声明或越界的数据表")

    def _owns_table(self, table_name: str) -> bool:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", table_name):
            return False
        if table_name in EXPECTED_APP_SCHEMA:
            return False
        if self._table_prefix is None:
            return table_name in self._tables
        return table_name.startswith(self._table_prefix)

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


def _sql_tokens(statement: str) -> tuple[str, ...]:
    tokens: list[str] = []
    index = 0
    while index < len(statement):
        char = statement[index]
        if char.isspace():
            index += 1
        elif statement.startswith("--", index):
            newline = statement.find("\n", index)
            index = len(statement) if newline < 0 else newline + 1
        elif char == "`":
            end = statement.find("`", index + 1)
            if end < 0:
                raise ModuleMigrationError("模块迁移 SQL 不可安全分析")
            identifier = statement[index + 1 : end]
            if not re.fullmatch(r"[a-z][a-z0-9_]*", identifier):
                raise ModuleMigrationError("模块迁移 SQL 不可安全分析")
            tokens.append(identifier)
            index = end + 1
        elif char in "'\"":
            index = _consume_sql_string(statement, index, char)
            tokens.append("STRING")
        elif char.isalpha() or char == "_":
            end = index + 1
            while end < len(statement) and (statement[end].isalnum() or statement[end] == "_"):
                end += 1
            tokens.append(statement[index:end])
            index = end
        elif char.isdigit():
            end = index + 1
            while end < len(statement) and statement[end].isdigit():
                end += 1
            tokens.append(statement[index:end])
            index = end
        elif char in "(),.=*+-/<>;":
            tokens.append(char)
            index += 1
        else:
            raise ModuleMigrationError("模块迁移 SQL 不可安全分析")
    return tuple(tokens)


def _require_token(tokens: list[str], token: str) -> int:
    try:
        return tokens.index(token)
    except ValueError:
        raise ModuleMigrationError("模块迁移 SQL 不可安全分析") from None


def _consume_sql_string(statement: str, index: int, quote: str) -> int:
    cursor = index + 1
    while cursor < len(statement):
        if statement[cursor] == "\\":
            cursor += 2
            continue
        if statement[cursor] == quote:
            if cursor + 1 < len(statement) and statement[cursor + 1] == quote:
                cursor += 2
                continue
            return cursor + 1
        cursor += 1
    raise ModuleMigrationError("模块迁移 SQL 不可安全分析")


def _drop_table_targets(tokens: tuple[str, ...], index: int) -> tuple[str, ...]:
    targets: list[str] = []
    while index < len(tokens):
        targets.append(_table_after(tokens, index))
        index += 1
        if index == len(tokens):
            break
        if tokens[index].upper() in {"RESTRICT", "CASCADE"} and index == len(tokens) - 1:
            break
        if tokens[index] != ",":
            raise ModuleMigrationError("模块迁移 SQL 不可安全分析")
        index += 1
    return tuple(targets)


def _table_after(tokens: tuple[str, ...], index: int) -> str:
    if index >= len(tokens) or tokens[index] in {".", "(", ")", ","}:
        raise ModuleMigrationError("模块迁移 SQL 不可安全分析")
    if index + 1 < len(tokens) and tokens[index + 1] == ".":
        raise ModuleMigrationError("模块迁移 SQL 不可安全分析")
    return tokens[index]


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
