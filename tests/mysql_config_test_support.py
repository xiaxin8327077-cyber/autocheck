from __future__ import annotations

import copy
from contextlib import contextmanager
from typing import Any

from sqlalchemy.dialects import mysql
from sqlalchemy.sql.elements import TextClause


class MemoryResult:
    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        scalar: Any = None,
        rowcount: int = 0,
        inserted_primary_key: list[Any] | None = None,
    ):
        self._rows = rows or []
        self._scalar = scalar
        self.rowcount = rowcount
        self.inserted_primary_key = inserted_primary_key or []

    def mappings(self) -> "MemoryResult":
        return self

    def all(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> Any:
        return self._scalar


class MySqlContractConnection:
    """In-memory executor that compiles repository statements as MySQL SQL."""

    def __init__(self):
        self.executed_sql: list[str] = []
        self.tables: dict[str, list[dict[str, Any]]] = {
            "data_sources": [],
            "app_settings": [],
            "config_snapshots": [],
            "users": [],
            "user_interface_preferences": [],
            "system_interface_preferences": [],
            "role_capability_settings": [],
            "role_definitions": [],
            "run_headers": [],
            "reconcile_runs": [],
            "reconcile_run_counts": [],
            "reconcile_results": [],
            "reconcile_result_details": [],
            "reconcile_delta_results": [],
            "db_validation_runs": [],
            "db_validation_selected_tables": [],
            "db_validation_warnings": [],
            "db_validation_result_rows": [],
            "flow_chain_runs": [],
            "flow_chain_run_steps": [],
            "flow_chain_run_logs": [],
            "flow_chain_run_details": [],
            "report_nav_processes": [],
            "report_nav_process_months": [],
            "report_nav_steps": [],
            "report_nav_step_dependencies": [],
            "report_nav_step_sources": [],
            "report_nav_step_fields": [],
            "report_nav_step_values": [],
            "report_nav_step_overrides": [],
            "report_nav_step_snapshots": [],
            "report_nav_process_snapshots": [],
            "report_nav_card_snapshots": [],
            "report_nav_card_manual_values": [],
            "report_nav_card_manual_history": [],
            "report_nav_monthly_schedules": [],
            "report_nav_work_calendar": [],
            "report_nav_stat_runs": [],
            "report_nav_scheduler_state": [],
            "report_nav_card_provider_states": [],
            "system_notifications": [],
            "system_notification_recipients": [],
        }

    def execute(self, statement: Any, parameters: dict[str, Any] | None = None) -> MemoryResult:
        if isinstance(statement, TextClause):
            return self._execute_text(statement.text, dict(parameters or {}))
        if isinstance(statement, str):
            raise AssertionError("configuration repository must use SQLAlchemy Core statements")
        compiled = statement.compile(dialect=mysql.dialect())
        sql = str(compiled)
        self.executed_sql.append(sql)
        params = dict(compiled.params)
        if isinstance(parameters, dict):
            params.update(parameters)

        table = statement.get_final_froms()[0] if getattr(statement, "is_select", False) else statement.table
        table_name = table.name
        if getattr(statement, "is_delete", False):
            before = len(self.tables[table_name])
            if not params:
                self.tables[table_name] = []
            elif " NOT IN " in sql.upper():
                normalized_sql = sql.upper()
                column = next(
                    (
                        item.name
                        for item in table.columns
                        if f".{item.name.upper()} NOT IN " in normalized_sql
                    ),
                    None,
                )
                if column is None:
                    raise AssertionError(f"unsupported NOT IN statement: {sql}")
                active_ids = {
                    str(value)
                    for value in next(
                        (
                            value
                            for value in params.values()
                            if isinstance(value, (list, tuple, set))
                        ),
                        [],
                    )
                }
                self.tables[table_name] = [
                    row
                    for row in self.tables[table_name]
                    if str(row.get(column)) in active_ids
                ]
            elif " IN " in sql.upper():
                ids = next(
                    (
                        value
                        for value in params.values()
                        if isinstance(value, (list, tuple, set))
                    ),
                    [],
                )
                delete_ids = {str(value) for value in ids}
                normalized_sql = sql.upper()
                column = next(
                    (
                        item.name
                        for item in table.columns
                        if f".{item.name.upper()} IN " in normalized_sql
                        or f"{item.name.upper()} IN " in normalized_sql
                    ),
                    None,
                )
                if column is None:
                    column = "result_id" if "result_id" in sql else "id"
                self.tables[table_name] = [
                    row for row in self.tables[table_name] if str(row.get(column)) not in delete_ids
                ]
            else:
                filters = self._filters_from_params(
                    params,
                    (
                        "kind",
                        "id",
                        "run_id",
                        "result_id",
                        "key",
                        "report_month",
                        "step_code",
                        "process_code",
                        "stat_period",
                        "card_code",
                        "user_id",
                        "notification_id",
                        "source_module",
                        "event_type",
                        "dedupe_hash",
                    ),
                )
                self.tables[table_name] = [
                    row for row in self.tables[table_name] if not self._matches_filters(row, filters)
                ]
            return MemoryResult(rowcount=before - len(self.tables[table_name]))
        if getattr(statement, "is_update", False):
            in_param_keys: set[str] = set()
            if " IN " in sql.upper():
                # UPDATE ... SET col=:col WHERE col IN (:col_1) 会把 SET 与 IN
                # 都编进 params；不能把 SET 值当过滤条件，否则会误匹配全表。
                in_items = [
                    (key, value)
                    for key, value in params.items()
                    if isinstance(value, (list, tuple, set))
                ]
                if len(in_items) != 1:
                    raise AssertionError(f"unsupported UPDATE IN statement: {sql}")
                in_key, in_values = in_items[0]
                column = in_key.rsplit("_", 1)[0] if "_" in in_key else in_key
                filters = {column: in_values}
                in_param_keys.add(in_key)
            else:
                filters = self._filters_from_params(
                    params,
                    (
                        "kind",
                        "id",
                        "run_id",
                        "result_id",
                        "key",
                        "report_month",
                        "step_code",
                        "process_code",
                        "stat_period",
                        "card_code",
                        "user_id",
                        "role_code",
                        "role",
                        "notification_id",
                        "source_module",
                        "event_type",
                        "dedupe_hash",
                    ),
                )
                # Handle IS NULL conditions that don't generate params
                if " IS NULL" in sql.upper() and "cleared_at" not in filters:
                    filters["cleared_at"] = None
            matched = [row for row in self.tables[table_name] if self._matches_filters(row, filters)]
            for row in matched:
                for key, value in params.items():
                    if key in in_param_keys or isinstance(value, (list, tuple, set)):
                        continue
                    if key in row:
                        row[key] = value
            return MemoryResult(rowcount=len(matched))
        if getattr(statement, "is_insert", False):
            if isinstance(parameters, list):
                for item in parameters:
                    self._insert_row(table_name, table, dict(item))
                return MemoryResult()
            update_names = None
            post_values_clause = getattr(statement, "_post_values_clause", None)
            if post_values_clause is not None:
                update_names = frozenset(post_values_clause.update)
            primary_key = self._insert_row(
                table_name,
                table,
                params,
                update_names=update_names,
            )
            return MemoryResult(rowcount=1, inserted_primary_key=[primary_key] if primary_key is not None else [])
        if getattr(statement, "is_select", False):
            rows = [dict(row) for row in self.tables[table_name]]
            filters = self._filters_from_params(
                params,
                (
                    "kind",
                    "id",
                    "run_id",
                    "result_id",
                    "key",
                    "report_month",
                    "step_code",
                    "process_code",
                    "stat_period",
                    "card_code",
                    "user_id",
                    "notification_id",
                    "source_module",
                    "event_type",
                    "dedupe_hash",
                    "read_at",
                ),
            )
            # Handle IS NULL conditions that don't generate params
            sql_upper = sql.upper()
            for name in ("read_at", "user_id", "notification_id", "cleared_at"):
                col = f".{name.upper()} IS NULL"
                if col in sql_upper and name not in filters:
                    filters[name] = None
            if filters:
                rows = [row for row in rows if self._matches_filters(row, filters)]
            if "count(" in sql.lower():
                return MemoryResult(scalar=len(rows))
            if table_name == "app_settings" and params:
                key = next(iter(params.values()))
                rows = [row for row in rows if row["key"] == key]
            if table_name == "data_sources":
                rows.sort(key=lambda row: (row["name"], row["id"]))
            if table_name == "config_snapshots":
                rows.sort(key=lambda row: (row["created_at"], row["id"]), reverse=True)
            if table_name == "users":
                rows.sort(key=lambda row: (row["created_at"], row["id"]))
            if table_name == "run_headers":
                if "run_headers.run_date DESC" in sql:
                    rows.sort(key=lambda row: (self._sort_value(row.get("run_date")), self._sort_value(row.get("run_at"))), reverse=True)
                elif "run_headers.run_at DESC" in sql:
                    rows.sort(key=lambda row: (self._sort_value(row.get("run_at")), str(row.get("id", ""))), reverse=True)
            if table_name.endswith("_selected_tables"):
                rows.sort(key=lambda row: row.get("table_order", 0))
            if table_name.endswith("_warnings"):
                rows.sort(key=lambda row: row.get("warning_order", 0))
            return MemoryResult(rows=rows)
        raise AssertionError(f"unsupported SQLAlchemy statement: {statement!r}")

    def _execute_text(self, sql: str, parameters: dict[str, Any]) -> MemoryResult:
        normalized = " ".join(sql.split()).lower()
        if normalized.startswith("insert into report_nav_card_provider_states"):
            rows = self.tables["report_nav_card_provider_states"]
            current = next(
                (
                    row
                    for row in rows
                    if str(row.get("card_code") or "")
                    == str(parameters["card_code"])
                ),
                None,
            )
            if current is None:
                rows.append(
                    {
                        "card_code": parameters["card_code"],
                        "owner": parameters["owner"],
                        "registration_token": parameters["registration_token"],
                        "semantics_version": parameters["semantics_version"],
                        "provider_active": True,
                        "stale": True,
                        "last_attempt_at": None,
                        "last_success_at": None,
                        "last_success_period_key": None,
                        "last_error": None,
                        "updated_at": parameters["updated_at"],
                    }
                )
                return MemoryResult(rowcount=1)
            if str(current.get("owner") or "") != str(parameters["owner"]):
                return MemoryResult(rowcount=0)
            same_semantics = int(current.get("semantics_version") or 0) == int(
                parameters["semantics_version"]
            )
            if not same_semantics:
                current.update(
                    stale=True,
                    last_attempt_at=None,
                    last_success_at=None,
                    last_success_period_key=None,
                    last_error=None,
                )
            current.update(
                registration_token=parameters["registration_token"],
                semantics_version=parameters["semantics_version"],
                provider_active=True,
                updated_at=parameters["updated_at"],
            )
            return MemoryResult(rowcount=1)
        if normalized.startswith("update report_nav_card_provider_states"):
            current = next(
                (
                    row
                    for row in self.tables["report_nav_card_provider_states"]
                    if str(row.get("card_code") or "") == str(parameters["card_code"])
                    and str(row.get("owner") or "") == str(parameters["owner"])
                    and str(row.get("registration_token") or "")
                    == str(parameters["registration_token"])
                ),
                None,
            )
            if current is None:
                return MemoryResult(rowcount=0)
            if "set provider_active=0" in normalized:
                current.update(
                    provider_active=False,
                    stale=True,
                    updated_at=parameters["updated_at"],
                )
            elif "stale=0" in normalized:
                current.update(
                    semantics_version=parameters["semantics_version"],
                    provider_active=True,
                    stale=False,
                    last_attempt_at=parameters["attempted_at"],
                    last_success_at=parameters["attempted_at"],
                    last_success_period_key=parameters["period_key"],
                    last_error=None,
                    updated_at=parameters["attempted_at"],
                )
            else:
                current.update(
                    semantics_version=parameters["semantics_version"],
                    provider_active=True,
                    stale=True,
                    last_attempt_at=parameters["attempted_at"],
                    last_error=parameters["last_error"],
                    updated_at=parameters["attempted_at"],
                )
            return MemoryResult(rowcount=1)
        if normalized.startswith("update report_nav_scheduler_state"):
            row = next((item for item in self.tables["report_nav_scheduler_state"] if item.get("id") == 1), None)
            if row is None:
                return MemoryResult(rowcount=0)
            if "and (lock_until is null or lock_until < :now)" in normalized:
                now = parameters["now"]
                lock_until = row.get("lock_until")
                if not bool(row.get("enabled")) or (lock_until is not None and lock_until >= now):
                    return MemoryResult(rowcount=0)
                row.update(
                    lock_owner=parameters["owner"],
                    lock_until=parameters["lock_until"],
                    last_started_at=now,
                    updated_at=now,
                )
                return MemoryResult(rowcount=1)
            if row.get("lock_owner") != parameters.get("owner"):
                return MemoryResult(rowcount=0)
            row.update(
                lock_owner=None,
                lock_until=None,
                last_finished_at=parameters["finished_at"],
                last_status=parameters["status"],
                last_error=parameters.get("error_message"),
                updated_at=parameters["finished_at"],
            )
            return MemoryResult(rowcount=1)
        raise AssertionError(f"unsupported textual SQL: {sql}")

    def _insert_row(
        self,
        table_name: str,
        table: Any,
        params: dict[str, Any],
        *,
        update_names: frozenset[str] | None = None,
    ) -> Any:
        row = {column.name: params[column.name] for column in table.columns if column.name in params}
        has_id_column = any(column.name == "id" for column in table.columns)
        if has_id_column and "id" not in row:
            row["id"] = len(self.tables[table_name]) + 1
        key_names = self._key_names(table_name, row)
        if not key_names:
            self.tables[table_name].append(row)
            return None
        existing = next(
            (
                item
                for item in self.tables[table_name]
                if all(item.get(key) == row.get(key) for key in key_names)
            ),
            None,
        )
        if existing is None:
            self.tables[table_name].append(row)
            return row.get(key_names[0])
        else:
            created_at = existing.get("created_at")
            update_row = (
                row
                if update_names is None
                else {name: row[name] for name in update_names if name in row}
            )
            existing.update(update_row)
            if created_at is not None:
                existing["created_at"] = created_at
            return existing.get(key_names[0])

    def _key_names(self, table_name: str, row: dict[str, Any]) -> tuple[str, ...]:
        composite_keys = {
            "report_nav_process_months": ("process_code", "month_no"),
            "report_nav_step_dependencies": ("step_code", "depends_on_step_code"),
            "report_nav_step_overrides": ("report_month", "step_code"),
            "report_nav_step_snapshots": ("report_month", "step_code"),
            "report_nav_process_snapshots": ("report_month", "process_code"),
            "report_nav_card_snapshots": ("stat_period", "card_code"),
            "report_nav_card_manual_values": ("stat_period", "card_code"),
            "report_nav_card_manual_history": ("stat_period", "period_key", "card_code"),
            "report_nav_monthly_schedules": ("report_month", "process_code"),
            "report_nav_card_provider_states": ("card_code",),
            "system_notification_recipients": ("notification_id", "user_id"),
        }
        if table_name in composite_keys:
            return composite_keys[table_name]
        if table_name == "app_settings":
            return ("key",)
        if table_name == "user_interface_preferences":
            return ("user_id",)
        if table_name == "system_interface_preferences":
            return ("id",)
        if table_name in {"report_nav_processes"}:
            return ("process_code",)
        if table_name in {"report_nav_steps"}:
            return ("step_code",)
        if table_name == "role_definitions":
            return ("role_code",)
        return ("id",) if "id" in row else ()

    def _filters_from_params(self, params: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
        filters = {}
        for name in names:
            if name in params:
                filters[name] = params[name]
                continue
            matches = [value for key, value in params.items() if key.startswith(f"{name}_")]
            if len(matches) == 1:
                filters[name] = matches[0]
        return filters

    def _matches_filters(self, row: dict[str, Any], filters: dict[str, Any]) -> bool:
        for name, value in filters.items():
            if name not in row:
                continue
            if isinstance(value, (list, tuple, set)):
                if str(row.get(name)) not in {str(item) for item in value}:
                    return False
                continue
            if str(row.get(name)) != str(value):
                return False
        return True

    def _sort_value(self, value: Any) -> str:
        return "" if value is None else str(value)


class MemoryApplicationDatabase:
    def __init__(self):
        self.connection = MySqlContractConnection()
        self.transaction_count = 0

    @contextmanager
    def connect(self):
        yield self.connection

    @contextmanager
    def transaction(self):
        before = copy.deepcopy(self.connection.tables)
        self.transaction_count += 1
        try:
            yield self.connection
        except Exception:
            self.connection.tables = before
            raise

    def test_connection(self) -> None:
        pass

    def validate_schema(self) -> None:
        pass

    def close(self) -> None:
        pass
