from __future__ import annotations

import json
import ssl
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
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
        "user_interface_preferences": _columns("user_id", "radius_px", "updated_at"),
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
        "report_nav_processes": _columns(
            "process_code",
            "process_name",
            "display_order",
            "enabled",
            "allow_manual_step_completion",
        ),
        "report_nav_process_months": _columns("process_code", "month_no"),
        "report_nav_steps": _columns(
            "step_code",
            "process_code",
            "step_name",
            "display_order",
            "evaluator_key",
            "enabled",
            "default_completed",
            "manual_completion_allowed",
        ),
        "report_nav_step_dependencies": _columns("step_code", "depends_on_step_code"),
        "report_nav_step_sources": _columns(
            "id",
            "step_code",
            "source_role",
            "data_source_name",
            "table_name",
            "display_order",
            "enabled",
        ),
        "report_nav_step_fields": _columns("id", "step_source_id", "field_role", "column_name"),
        "report_nav_step_values": _columns(
            "id", "step_code", "value_role", "value_text", "value_type", "display_order"
        ),
        "report_nav_step_overrides": _columns(
            "report_month",
            "step_code",
            "completed",
            "operator_id",
            "operator_username",
            "operator_name",
            "created_at",
            "updated_at",
        ),
        "report_nav_step_snapshots": _columns(
            "report_month",
            "step_code",
            "auto_status",
            "effective_status",
            "completion_source",
            "status_message",
            "error_message",
            "auto_completed_at",
            "evaluated_at",
            "run_id",
        ),
        "report_nav_process_snapshots": _columns(
            "report_month",
            "process_code",
            "total_steps",
            "completed_steps",
            "status",
            "completed_at",
            "evaluated_at",
            "run_id",
        ),
        "report_nav_card_snapshots": _columns(
            "stat_period",
            "card_code",
            "total_count",
            "completed_count",
            "incomplete_count",
            "completion_rate",
            "evaluated_at",
            "run_id",
        ),
        "report_nav_card_manual_values": _columns(
            "stat_period",
            "card_code",
            "completed_count",
            "incomplete_count",
            "operator_id",
            "operator_username",
            "operator_name",
            "updated_at",
        ),
        "report_nav_monthly_schedules": _columns(
            "report_month",
            "process_code",
            "report_date",
            "source_type",
            "source_year",
            "updated_by",
            "updated_at",
        ),
        "report_nav_stat_runs": _columns(
            "id",
            "trigger_type",
            "report_month",
            "business_report_date",
            "started_at",
            "finished_at",
            "status",
            "completed_processes",
            "failed_steps",
            "error_message",
        ),
        "report_nav_scheduler_state": _columns(
            "id",
            "enabled",
            "interval_minutes",
            "next_run_at",
            "lock_owner",
            "lock_until",
            "last_started_at",
            "last_finished_at",
            "last_status",
            "last_error",
            "updated_at",
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
    password: str = field(repr=False)
    charset: str = "utf8mb4"
    connect_timeout: int = 10
    pool_size: int = 5
    pool_max_overflow: int = 5
    ssl: bool = False
    ssl_ca: str = ""


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
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
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
    ssl_ca_value = node.get("ssl_ca", "")
    if not isinstance(ssl_ca_value, str):
        raise ValueError("app_database.ssl_ca 必须是字符串")
    ssl_ca = ssl_ca_value.strip()
    if ssl and not ssl_ca:
        raise ValueError("app_database.ssl=true 时必须提供非空 ssl_ca")

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
        ssl_ca=ssl_ca,
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
        connect_args["ssl"] = {
            "ca": config.ssl_ca,
            "check_hostname": True,
            "verify_mode": ssl.CERT_REQUIRED,
        }
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
