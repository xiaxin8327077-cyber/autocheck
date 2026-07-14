from __future__ import annotations

import copy
from contextlib import contextmanager
from typing import Any

from sqlalchemy.dialects import mysql


class MemoryResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, scalar: Any = None):
        self._rows = rows or []
        self._scalar = scalar

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
        }

    def execute(self, statement: Any, parameters: dict[str, Any] | None = None) -> MemoryResult:
        if isinstance(statement, str):
            raise AssertionError("configuration repository must use SQLAlchemy Core statements")
        compiled = statement.compile(dialect=mysql.dialect())
        sql = str(compiled)
        params = dict(compiled.params)
        if parameters:
            params.update(parameters)

        table = statement.get_final_froms()[0] if getattr(statement, "is_select", False) else statement.table
        table_name = table.name
        if getattr(statement, "is_delete", False):
            retained_ids = next((value for value in params.values() if isinstance(value, list)), None)
            if retained_ids is None:
                self.tables[table_name] = []
            else:
                retained = {str(value) for value in retained_ids}
                self.tables[table_name] = [
                    row for row in self.tables[table_name] if str(row.get("id")) in retained
                ]
            return MemoryResult()
        if getattr(statement, "is_insert", False):
            row = {column.name: params[column.name] for column in table.columns if column.name in params}
            if table_name == "config_snapshots" and "id" not in row:
                row["id"] = len(self.tables[table_name]) + 1
            key_name = "key" if table_name == "app_settings" else "id"
            existing = next(
                (item for item in self.tables[table_name] if item.get(key_name) == row.get(key_name)),
                None,
            )
            if existing is None:
                self.tables[table_name].append(row)
            else:
                created_at = existing.get("created_at")
                existing.update(row)
                if created_at is not None:
                    existing["created_at"] = created_at
            return MemoryResult()
        if getattr(statement, "is_select", False):
            rows = [dict(row) for row in self.tables[table_name]]
            if "count(" in sql.lower():
                return MemoryResult(scalar=len(rows))
            if table_name == "app_settings" and params:
                key = next(iter(params.values()))
                rows = [row for row in rows if row["key"] == key]
            if table_name == "data_sources":
                rows.sort(key=lambda row: (row["name"], row["id"]))
            if table_name == "config_snapshots":
                rows.sort(key=lambda row: (row["created_at"], row["id"]), reverse=True)
            return MemoryResult(rows=rows)
        raise AssertionError(f"unsupported SQLAlchemy statement: {statement!r}")


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
