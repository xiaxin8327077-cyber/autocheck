from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from auto_check.app.db import qualified_name
from auto_check.db_validation.mapping_models import CrossTableMapping


@dataclass(frozen=True)
class TableFieldCatalog:
    by_table: dict[str, dict[str, str]]
    unmapped_field_count: int = 0
    table_mappings: dict[tuple[str, str, str], str] | None = None
    cross_table_mappings: dict[tuple[str, str], tuple[CrossTableMapping, ...]] | None = None

    def table_for(self, relation_type: str, logical_code: str, scope_code: str = "") -> str:
        mappings = self.table_mappings or {}
        try:
            return mappings[(relation_type, logical_code, scope_code)]
        except KeyError as exc:
            raise KeyError(f"{relation_type}.{logical_code}.{scope_code}") from exc

    def field_for(self, table_name: str, chinese_name: str) -> str:
        field_name = self.resolve_field(table_name, chinese_name)
        if field_name:
            return field_name
        raise KeyError(f"{table_name}.{chinese_name}")

    def fields_for_table(self, table_name: str) -> dict[str, str]:
        if table_name not in self.by_table:
            raise KeyError(table_name)
        return dict(self.by_table[table_name])

    def resolve_field(self, table_name: str, field_name: str) -> str:
        """Resolve Chinese → English using exact, then controlled semantic matching."""
        if not field_name:
            return ""
        fields = self.by_table.get(table_name) or {}
        matched_name = match_chinese_field_name(field_name, fields)
        if matched_name:
            return str(fields[matched_name])
        return ""

    def cross_table_mappings_for(self, logical_code: str, scope_code: str) -> tuple[CrossTableMapping, ...]:
        mappings = self.cross_table_mappings or {}
        return mappings.get((str(logical_code).upper(), str(scope_code)), ())


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


_CHINESE_FIELD_SEPARATORS = re.compile(r"[\s_\-—－/（）()【】\[\]：:，,。·]+")


def match_chinese_field_name(requested_name: str, candidate_names: Any) -> str:
    """Return one high-confidence metadata name, or empty when none/ambiguous.

    Matching is deliberately limited to stable business-name variations. It does
    not use arbitrary substring or edit-distance matching. Latin letters in the
    Chinese name are compared case-insensitively.
    """
    requested = str(requested_name or "").strip()
    candidates = [str(name or "").strip() for name in candidate_names if str(name or "").strip()]
    if not requested or not candidates:
        return ""
    if requested in candidates:
        return requested

    requested_variants = _chinese_field_variants(requested)
    scored: list[tuple[int, str]] = []
    for candidate in candidates:
        candidate_variants = _chinese_field_variants(candidate)
        shared = set(requested_variants).intersection(candidate_variants)
        if not shared:
            continue
        score = max(100 - requested_variants[key] - candidate_variants[key] for key in shared)
        scored.append((score, candidate))
    if not scored:
        return ""
    best_score = max(score for score, _ in scored)
    winners = sorted({candidate for score, candidate in scored if score == best_score})
    return winners[0] if len(winners) == 1 else ""


def _chinese_field_variants(value: str) -> dict[str, int]:
    normalized = _CHINESE_FIELD_SEPARATORS.sub("", str(value or "").strip()).replace("日期", "日").casefold()
    if not normalized:
        return {}
    variants = {normalized: 0}
    pending = [(normalized, 0)]
    while pending:
        current, penalty = pending.pop()
        transformations: list[tuple[str, int]] = []
        if current.startswith("产品") and len(current) > 3:
            transformations.append((current[2:], penalty + 8))
        if current.endswith("代码") and len(current) > 3:
            transformations.append((current[:-2], penalty + 12))
        for transformed, transformed_penalty in transformations:
            if not transformed or transformed_penalty >= variants.get(transformed, 10_000):
                continue
            variants[transformed] = transformed_penalty
            pending.append((transformed, transformed_penalty))
    return variants


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
