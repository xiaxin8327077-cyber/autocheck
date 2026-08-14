from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TableMapping:
    relation_type: str
    logical_code: str
    scope_code: str
    automatic_table_name: str
    override_table_name: str | None = None
    mapping_status: str = "mapped"
    status_message: str = ""
    refreshed_at: str = ""

    @property
    def effective_table_name(self) -> str:
        return self.override_table_name or self.automatic_table_name

    def to_payload(self) -> dict[str, Any]:
        return {
            "relation_type": self.relation_type,
            "logical_code": self.logical_code,
            "scope_code": self.scope_code,
            "automatic_table_name": self.automatic_table_name,
            "override_table_name": self.override_table_name or "",
            "effective_table_name": self.effective_table_name,
            "mapping_status": self.mapping_status,
            "status_message": self.status_message,
            "refreshed_at": self.refreshed_at,
        }


@dataclass(frozen=True)
class FieldMapping:
    relation_type: str
    logical_code: str
    scope_code: str
    chinese_name: str
    automatic_field_name: str | None
    override_field_name: str | None = None
    mapping_status: str = "mapped"
    is_required: bool = False
    status_message: str = ""

    @property
    def effective_field_name(self) -> str | None:
        return self.override_field_name or self.automatic_field_name


@dataclass(frozen=True)
class CrossTableMapping:
    mapping_code: str
    logical_code: str
    scope_code: str
    automatic_detail_field_name: str
    automatic_template_table_name: str
    automatic_template_field_name: str
    override_detail_field_name: str | None = None
    override_template_table_name: str | None = None
    override_template_field_name: str | None = None
    mapping_status: str = "mapped"
    status_message: str = ""
    refreshed_at: str = ""

    @property
    def effective_detail_field_name(self) -> str:
        # 逐笔字段是跨表映射的固定基准，历史人工覆盖不再参与生效值。
        return self.automatic_detail_field_name

    @property
    def effective_template_table_name(self) -> str:
        return self.override_template_table_name or self.automatic_template_table_name

    @property
    def effective_template_field_name(self) -> str:
        return self.override_template_field_name or self.automatic_template_field_name

    @property
    def difference_fields(self) -> tuple[str, ...]:
        differences: list[str] = []
        if self.override_template_table_name and self.override_template_table_name != self.automatic_template_table_name:
            differences.append("template_table")
        if self.override_template_field_name and self.override_template_field_name != self.automatic_template_field_name:
            differences.append("template_field")
        return tuple(differences)

    def to_payload(self) -> dict[str, Any]:
        return {
            "mapping_code": self.mapping_code,
            "relation_type": "cross_table",
            "logical_code": self.logical_code,
            "scope_code": self.scope_code,
            "automatic_detail_field_name": self.automatic_detail_field_name,
            "override_detail_field_name": "",
            "effective_detail_field_name": self.effective_detail_field_name,
            "automatic_template_table_name": self.automatic_template_table_name,
            "override_template_table_name": self.override_template_table_name or "",
            "effective_template_table_name": self.effective_template_table_name,
            "automatic_template_field_name": self.automatic_template_field_name,
            "override_template_field_name": self.override_template_field_name or "",
            "effective_template_field_name": self.effective_template_field_name,
            "mapping_status": self.mapping_status,
            "status_message": self.status_message,
            "difference_fields": list(self.difference_fields),
            "difference_status": "different" if self.difference_fields else "",
            "refreshed_at": self.refreshed_at,
        }
