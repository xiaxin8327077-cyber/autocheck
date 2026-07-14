from __future__ import annotations

import copy
from contextlib import contextmanager
from typing import Any

from sqlalchemy.dialects import mysql


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
        self.tables: dict[str, list[dict[str, Any]]] = {
            "data_sources": [],
            "app_settings": [],
            "config_snapshots": [],
            "users": [],
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
        }

    def execute(self, statement: Any, parameters: dict[str, Any] | None = None) -> MemoryResult:
        if isinstance(statement, str):
            raise AssertionError("configuration repository must use SQLAlchemy Core statements")
        compiled = statement.compile(dialect=mysql.dialect())
        sql = str(compiled)
        params = dict(compiled.params)
        if isinstance(parameters, dict):
            params.update(parameters)

        table = statement.get_final_froms()[0] if getattr(statement, "is_select", False) else statement.table
        table_name = table.name
        if getattr(statement, "is_delete", False):
            before = len(self.tables[table_name])
            if not params:
                self.tables[table_name] = []
            elif " IN " in sql.upper():
                ids = next((value for value in params.values() if isinstance(value, list)), [])
                delete_ids = {str(value) for value in ids}
                column = "result_id" if "result_id" in sql else "id"
                self.tables[table_name] = [
                    row for row in self.tables[table_name] if str(row.get(column)) not in delete_ids
                ]
            else:
                filters = self._filters_from_params(params, ("kind", "id", "run_id", "result_id", "key"))
                self.tables[table_name] = [
                    row for row in self.tables[table_name] if not self._matches_filters(row, filters)
                ]
            return MemoryResult(rowcount=before - len(self.tables[table_name]))
        if getattr(statement, "is_insert", False):
            if isinstance(parameters, list):
                for item in parameters:
                    self._insert_row(table_name, table, dict(item))
                return MemoryResult()
            primary_key = self._insert_row(table_name, table, params)
            return MemoryResult(rowcount=1, inserted_primary_key=[primary_key] if primary_key is not None else [])
        if getattr(statement, "is_select", False):
            rows = [dict(row) for row in self.tables[table_name]]
            filters = self._filters_from_params(params, ("kind", "id", "run_id", "result_id", "key"))
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

    def _insert_row(self, table_name: str, table: Any, params: dict[str, Any]) -> Any:
        row = {column.name: params[column.name] for column in table.columns if column.name in params}
        has_id_column = any(column.name == "id" for column in table.columns)
        if has_id_column and "id" not in row:
            row["id"] = len(self.tables[table_name]) + 1
        key_name = "key" if table_name == "app_settings" else ("id" if "id" in row else "")
        if not key_name:
            self.tables[table_name].append(row)
            return None
        existing = next(
            (item for item in self.tables[table_name] if item.get(key_name) == row.get(key_name)),
            None,
        )
        if existing is None:
            self.tables[table_name].append(row)
            return row.get(key_name)
        else:
            created_at = existing.get("created_at")
            existing.update(row)
            if created_at is not None:
                existing["created_at"] = created_at
            return existing.get(key_name)

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
        return all(str(row.get(name)) == str(value) for name, value in filters.items() if name in row)

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
