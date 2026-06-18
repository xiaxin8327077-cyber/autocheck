from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from auto_check.app.db import qualified_name


@dataclass(frozen=True)
class TableFieldCatalog:
    by_table: dict[str, dict[str, str]]
    unmapped_field_count: int = 0

    def field_for(self, table_name: str, chinese_name: str) -> str:
        try:
            return self.by_table[table_name][chinese_name]
        except KeyError as exc:
            raise KeyError(f"{table_name}.{chinese_name}") from exc

    def fields_for_table(self, table_name: str) -> dict[str, str]:
        if table_name not in self.by_table:
            raise KeyError(table_name)
        return dict(self.by_table[table_name])


class FieldMetadataLoader:
    def __init__(
        self,
        client: Any,
        *,
        baseinfo_table: str = "xt_reg_table_baseinfo",
        field_info_table: str = "xt_reg_table_field_info",
        sys_manage_id: str = "",
        classification_id: str = "",
    ):
        self.client = client
        self.baseinfo_table = baseinfo_table
        self.field_info_table = field_info_table
        self.sys_manage_ids = _split_semicolon_values(sys_manage_id)
        self.classification_ids = _split_semicolon_values(classification_id)

    def load(self) -> TableFieldCatalog:
        baseinfo_where = ["COALESCE(table_name_en, '') <> ''"]
        baseinfo_params: list[str] = []
        if self.sys_manage_ids:
            baseinfo_where.append(f"sys_manage_id IN ({_placeholders(len(self.sys_manage_ids))})")
            baseinfo_params.extend(self.sys_manage_ids)
        if self.classification_ids:
            baseinfo_where.append(f"classification_id IN ({_placeholders(len(self.classification_ids))})")
            baseinfo_params.extend(self.classification_ids)
        baseinfo_sql = (
            f"SELECT id, table_name_en FROM {qualified_name(self.client.config, self.baseinfo_table)} "
            f"WHERE {' AND '.join(baseinfo_where)}"
        )
        base_rows = self.client.fetch_all(baseinfo_sql, tuple(baseinfo_params))
        id_to_table = {str(row["id"]): str(row["table_name_en"]) for row in base_rows}
        if not id_to_table:
            return TableFieldCatalog(by_table={}, unmapped_field_count=0)
        field_table_ids = tuple(id_to_table)
        field_sql = (
            f"SELECT table_id, field_propert, field_name, sort FROM {qualified_name(self.client.config, self.field_info_table)} "
            "WHERE COALESCE(field_propert, '') <> '' "
            "AND COALESCE(field_name, '') <> '' "
            f"AND table_id IN ({_placeholders(len(field_table_ids))})"
        )
        field_rows = sorted(
            self.client.fetch_all(field_sql, field_table_ids),
            key=lambda row: (str(row.get("table_id", "")), _sort_value(row.get("sort"))),
        )
        by_table: dict[str, dict[str, str]] = {}
        for row in field_rows:
            table_name = id_to_table.get(str(row.get("table_id", "")))
            if table_name is None:
                continue
            by_table.setdefault(table_name, {})[str(row["field_name"])] = str(row["field_propert"])
        return TableFieldCatalog(by_table=by_table, unmapped_field_count=0)


def _sort_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _split_semicolon_values(value: str) -> tuple[str, ...]:
    parts = [part.strip() for part in str(value or "").split(";")]
    return tuple(part for part in parts if part)


def _placeholders(count: int) -> str:
    return ", ".join(["%s"] * count)
