from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import Connection, Engine


CURRENT_APP_SCHEMA_VERSION = 1


def _columns(*names: str) -> frozenset[str]:
    return frozenset(names)


EXPECTED_APP_SCHEMA: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "app_schema_version": _columns("version", "applied_at"),
        "data_sources": _columns(
            "id",
            "name",
            "db_type",
            "host",
            "port",
            "database_name",
            "schema_name",
            "username",
            "password_encrypted",
            "is_default",
            "created_at",
            "updated_at",
        ),
        "app_settings": _columns("key", "value_json", "updated_at"),
        "users": _columns(
            "id",
            "username",
            "display_name",
            "role",
            "password_hash",
            "enabled",
            "created_at",
            "updated_at",
            "last_login_at",
        ),
        "config_snapshots": _columns("id", "fingerprint", "payload_json", "created_at"),
        "run_headers": _columns(
            "id",
            "kind",
            "run_date",
            "run_at",
            "finished_at",
            "status",
            "executor_id",
            "executor_username",
            "executor_name",
            "config_fingerprint",
            "payload_json",
        ),
        "reconcile_runs": _columns(
            "id",
            "config_name",
            "dws_source_name",
            "rule_version",
            "baseline_id",
            "baseline_run_at",
            "baseline_count",
            "total_count",
            "added_count",
            "removed_count",
        ),
        "reconcile_run_counts": _columns("run_id", "count_type", "label", "count_value"),
        "reconcile_results": _columns(
            "id",
            "run_id",
            "result_order",
            "project_code",
            "project_name",
            "asset_total",
            "liability_equity_total",
            "received_trust_balance",
            "difference",
            "direction",
            "difference_reason",
            "match_status",
            "valuation_asset_total",
            "payload_json",
        ),
        "reconcile_result_details": _columns(
            "id", "result_id", "detail_order", "kind", "specific_reason", "data_json"
        ),
        "reconcile_delta_results": _columns("run_id", "delta_type", "result_order", "payload_json"),
        "db_validation_runs": _columns(
            "id",
            "report_date",
            "result_count",
            "warning_count",
            "table_count",
            "enable_public_info_check",
            "enable_template_check",
            "excel_filename",
            "excel_path",
            "download_url",
        ),
        "db_validation_selected_tables": _columns("run_id", "table_order", "table_code"),
        "db_validation_warnings": _columns("run_id", "warning_order", "message"),
        "db_validation_result_rows": _columns(
            "id",
            "run_id",
            "row_order",
            "table_code",
            "rule_id",
            "severity",
            "message",
            "detail",
            "payload_json",
        ),
        "flow_chain_runs": _columns(
            "id",
            "chain_id",
            "chain_name",
            "is_multi_chain",
            "trigger_type",
            "executor_name",
            "status",
            "error",
            "step_count",
            "duration_seconds",
        ),
        "flow_chain_run_steps": _columns(
            "id",
            "run_id",
            "step_order",
            "flow_id",
            "name",
            "status",
            "sp_task_id",
            "start_time",
            "end_time",
            "duration_seconds",
            "payload_json",
        ),
        "flow_chain_run_logs": _columns(
            "id", "run_id", "log_order", "log_time", "message", "progress", "step", "payload_json"
        ),
        "flow_chain_run_details": _columns(
            "id",
            "run_id",
            "chain_order",
            "chain_name",
            "status",
            "step_count",
            "duration_seconds",
            "error",
            "payload_json",
        ),
        "storage_migration_runs": _columns(
            "id",
            "source_type",
            "source_path",
            "source_key",
            "source_fingerprint",
            "migrated_count",
            "skipped_count",
            "status",
            "message",
            "started_at",
            "finished_at",
        ),
    }
)


class ApplicationSchemaError(RuntimeError):
    """The manually provisioned application schema is missing or incompatible."""


@dataclass(frozen=True)
class ApplicationDatabaseConfig:
    host: str
    port: int
    database: str
    username: str
    password: str
    charset: str = "utf8mb4"
    connect_timeout: int = 10
    pool_size: int = 5
    pool_max_overflow: int = 5
    ssl: bool = False


class ApplicationDatabase:
    def __init__(self, config: ApplicationDatabaseConfig, *, engine: Engine | None = None):
        self.config = config
        self._engine = engine or _create_application_engine(config)

    @classmethod
    def from_config_path(cls, config_path: str | Path) -> ApplicationDatabase:
        config = _load_application_database_config(config_path)
        return cls(config)

    def test_connection(self) -> None:
        with self.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()

    def validate_schema(self) -> None:
        with self.connect() as connection:
            table_rows = connection.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = :database
                    """
                ),
                {"database": self.config.database},
            ).all()
            column_rows = connection.execute(
                text(
                    """
                    SELECT table_name, column_name
                    FROM information_schema.columns
                    WHERE table_schema = :database
                    """
                ),
                {"database": self.config.database},
            ).all()

            actual_tables = {str(row[0]) for row in table_rows}
            missing_tables = sorted(set(EXPECTED_APP_SCHEMA) - actual_tables)
            if missing_tables:
                raise ApplicationSchemaError(f"应用数据库缺少表：{', '.join(missing_tables)}")

            actual_columns: dict[str, set[str]] = {}
            for table_name, column_name in column_rows:
                actual_columns.setdefault(str(table_name), set()).add(str(column_name))
            missing_columns = sorted(
                f"{table_name}.{column_name}"
                for table_name, expected_columns in EXPECTED_APP_SCHEMA.items()
                for column_name in expected_columns - actual_columns.get(table_name, set())
            )
            if missing_columns:
                raise ApplicationSchemaError(f"应用数据库缺少字段：{', '.join(missing_columns)}")

            actual_version = connection.execute(
                text("SELECT MAX(version) FROM app_schema_version")
            ).scalar_one_or_none()
            if actual_version != CURRENT_APP_SCHEMA_VERSION:
                raise ApplicationSchemaError(
                    "应用数据库结构版本不匹配："
                    f"当前 {actual_version!r}，要求 {CURRENT_APP_SCHEMA_VERSION}"
                )

    @contextmanager
    def connect(self) -> Iterator[Connection]:
        with self._engine.connect() as connection:
            yield connection

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        with self._engine.begin() as connection:
            yield connection

    def close(self) -> None:
        self._engine.dispose()


def _load_application_database_config(config_path: str | Path) -> ApplicationDatabaseConfig:
    path = Path(config_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取应用数据库配置：{path}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("config.json 顶层必须是对象")
    node = payload.get("app_database")
    if not isinstance(node, Mapping):
        raise ValueError("config.json 缺少 app_database 配置节点")
    if node.get("backend") != "mysql":
        raise ValueError("app_database.backend 仅支持 mysql")

    host = _required_text(node, "host")
    database = _required_text(node, "database")
    username = _required_text(node, "username")
    password = _required_string(node, "password")
    charset = _optional_text(node, "charset", "utf8mb4")
    port = _integer(node, "port", 3306, minimum=1, maximum=65535)
    connect_timeout = _integer(node, "connect_timeout", 10, minimum=1)
    pool_size = _integer(node, "pool_size", 5, minimum=1)
    pool_max_overflow = _integer(node, "pool_max_overflow", 5, minimum=0)
    ssl = node.get("ssl", False)
    if not isinstance(ssl, bool):
        raise ValueError("app_database.ssl 必须是布尔值")

    return ApplicationDatabaseConfig(
        host=host,
        port=port,
        database=database,
        username=username,
        password=password,
        charset=charset,
        connect_timeout=connect_timeout,
        pool_size=pool_size,
        pool_max_overflow=pool_max_overflow,
        ssl=ssl,
    )


def _create_application_engine(config: ApplicationDatabaseConfig) -> Engine:
    url = URL.create(
        "mysql+pymysql",
        username=config.username,
        password=config.password,
        host=config.host,
        port=config.port,
        database=config.database,
        query={"charset": config.charset},
    )
    connect_args: dict[str, Any] = {"connect_timeout": config.connect_timeout}
    if config.ssl:
        connect_args["ssl"] = {"check_hostname": False}
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=config.pool_size,
        max_overflow=config.pool_max_overflow,
        connect_args=connect_args,
    )


def _required_text(node: Mapping[str, object], key: str) -> str:
    value = _required_string(node, key).strip()
    if not value:
        raise ValueError(f"app_database.{key} 不能为空")
    return value


def _required_string(node: Mapping[str, object], key: str) -> str:
    value = node.get(key)
    if not isinstance(value, str):
        raise ValueError(f"app_database.{key} 必须是字符串")
    return value


def _optional_text(node: Mapping[str, object], key: str, default: str) -> str:
    value = node.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"app_database.{key} 必须是非空字符串")
    return value.strip()


def _integer(
    node: Mapping[str, object],
    key: str,
    default: int,
    *,
    minimum: int,
    maximum: int | None = None,
) -> int:
    value = node.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"app_database.{key} 必须是整数")
    if value < minimum or (maximum is not None and value > maximum):
        bounds = f"{minimum}..{maximum}" if maximum is not None else f">= {minimum}"
        raise ValueError(f"app_database.{key} 必须在 {bounds} 范围内")
    return value
