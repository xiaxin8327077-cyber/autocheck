"""报表集市层文档解析：把 Excel 规整为「数据源 / 表 / 字段」快照。

文档约定（2026-11 版本）：
- 表结构页表头出现在第 6 或第 7 行，列名有两套写法，按同义词映射；
- 第 1 行 A 列为表英文名，第 2 行「表名」为中文名，第 3/4/5/6 行含数据来源/维度/数据范围/采集周期；
- `人行结果表_表X-X` 为统计模板、`附录` 为代码字典，均不进入表/字段目录；
- 归属数据源按 sheet 前缀规则：`集市层_` → 监管报送集市，`人行_` → 监管报表，其余默认监管报表（规则可覆盖）；
- 字段类型为空时按字符串（varchar）处理，仅保留真正无法识别的类型告警。
"""

from __future__ import annotations

import io
import re
from typing import Any

from openpyxl import load_workbook

DEFAULT_SOURCE_RULES: list[dict[str, Any]] = [
    {"sheet_prefix": "集市层_", "data_source_name": "监管报送集市", "sort_order": 0},
    {"sheet_prefix": "人行_", "data_source_name": "监管报表", "sort_order": 1},
    {"sheet_prefix": "", "data_source_name": "监管报表", "sort_order": 100},
]

SKIP_PREFIXES = ("人行结果表_表", "附录")

FIELD_KEYS = {"字段名", "集市层字段名"}
CN_KEYS = {"字段名（中文）", "集市层字段名（中文）"}
TYPE_KEYS = {"字段类型"}
PK_KEYS = {"主键"}
NULLABLE_KEYS = {"能否为空"}
DEFAULT_KEYS = {"默认值"}
DICT_KEYS = {"字典"}
LOGIC_KEYS = {"逻辑", "取数逻辑"}
SOURCE_TABLE_KEYS = {"公共层表名（英文）", "明细层表名（英文）"}
SOURCE_FIELD_KEYS = {"公共层字段（英文）", "公共层字段中文", "明细层字段（英文）", "明细层字段中文"}
SOURCE_TABLE_CN_KEYS = {"公共层表名（中文）"}

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _normalize_type(raw: str) -> tuple[str, bool]:
    text = _text(raw).lower().replace("varhcar", "varchar")
    if not text:
        # 文档未写类型时按字符串处理，不再要求人工确认。
        return "varchar", True
    allowed = {
        "varchar", "char", "text", "numeric", "decimal", "date", "timestamp", "datetime",
        "int", "int4", "integer", "bigint", "smallint", "boolean", "bool", "float", "double",
    }
    base = re.split(r"[\s(]", text, 1)[0]
    if base not in allowed:
        return text, False
    return text, True


def is_pbc_report_sheet(sheet_name: str) -> bool:
    return sheet_name.startswith(("人行_", "人行报送_", "人行明细表_", "人行底稿_", "人行结果表_"))


def _match_source(sheet_name: str, rules: list[dict[str, Any]]) -> str:
    ordered = sorted(rules or DEFAULT_SOURCE_RULES, key=lambda item: int(item.get("sort_order") or 0))
    for rule in ordered:
        prefix = str(rule.get("sheet_prefix") or "")
        if not prefix or sheet_name.startswith(prefix):
            return str(rule.get("data_source_name") or "")
    return "监管报表"


def _find_header(rows: list[list[str]]) -> tuple[int, dict[str, int]] | tuple[None, dict[str, int]]:
    for index, values in enumerate(rows[:12]):
        if any(value in FIELD_KEYS for value in values):
            cols: dict[str, int] = {}

            def pick(keys: set[str], name: str) -> None:
                for position, value in enumerate(values):
                    if value in keys:
                        cols.setdefault(name, position)
                        return

            pick(FIELD_KEYS, "field")
            pick(CN_KEYS, "cn")
            pick(TYPE_KEYS, "type")
            pick(PK_KEYS, "pk")
            pick(NULLABLE_KEYS, "nullable")
            pick(DEFAULT_KEYS, "default")
            pick(DICT_KEYS, "dictionary")
            pick(LOGIC_KEYS, "logic")
            pick(SOURCE_TABLE_KEYS, "source_table")
            pick(SOURCE_FIELD_KEYS, "source_field")
            pick(SOURCE_TABLE_CN_KEYS, "source_table_cn")
            return index, cols
    return None, {}


def _meta_value(rows: list[list[str]], label: str, lookahead: int = 8) -> str:
    for values in rows[:lookahead]:
        for position, value in enumerate(values):
            if value == label and position + 2 < len(values):
                candidate = values[position + 2]
                if candidate:
                    return candidate
            if value == label:
                for candidate in values[position + 1:]:
                    if candidate:
                        return candidate
    return ""


def parse_workbook(content: bytes, *, rules: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    tables: list[dict[str, Any]] = []
    warnings: list[str] = []
    try:
        for sheet_name in workbook.sheetnames:
            if sheet_name.startswith(SKIP_PREFIXES):
                continue
            worksheet = workbook[sheet_name]
            rows: list[list[str]] = [
                [_text(value) for value in row]
                for row in worksheet.iter_rows(values_only=True)
            ]
            header_index, cols = _find_header(rows)
            if header_index is None or "field" not in cols:
                warnings.append(f"跳过无字段表头的 sheet：{sheet_name}")
                continue
            table_en = rows[0][0] if rows and rows[0] else ""
            if not _NAME.fullmatch(table_en):
                warnings.append(f"跳过无法识别表英文名的 sheet：{sheet_name}")
                continue
            fields: list[dict[str, Any]] = []
            seen: set[str] = set()
            for values in rows[header_index + 1:]:
                field_index = cols.get("field")
                if field_index is None or field_index >= len(values):
                    continue
                field_name = values[field_index]
                if not _NAME.fullmatch(field_name) or field_name in seen:
                    continue

                def cell(name: str) -> str:
                    position = cols.get(name)
                    return values[position] if position is not None and position < len(values) else ""

                seen.add(field_name)
                raw_type = cell("type")
                data_type, type_ok = _normalize_type(raw_type)
                if not type_ok:
                    warnings.append(
                        f"{table_en}.{field_name} 字段类型为“{raw_type or '空'}”，需在设置中确认"
                    )
                fields.append({
                    "field_name": field_name,
                    "field_cn": cell("cn"),
                    "data_type": data_type,
                    "is_pk": "Y" if cell("pk").upper() == "Y" else "",
                    "nullable": "Y" if cell("nullable").upper() in {"Y", "是"} else ("N" if cell("nullable") else ""),
                    "default_value": cell("default"),
                    "dictionary": cell("dictionary"),
                    "logic": cell("logic"),
                    "source_table": cell("source_table"),
                    "source_field": cell("source_field"),
                    "source_field_cn": cell("source_field_cn"),
                    "source_table_cn": cell("source_table_cn"),
                })
            if not fields:
                warnings.append(f"{table_en} 未识别到字段，已跳过（sheet：{sheet_name}）")
                continue
            table_cn = _meta_value(rows, "表名")
            tables.append({
                "data_source_name": _match_source(sheet_name, rules or DEFAULT_SOURCE_RULES),
                "table_name": table_en,
                "table_name_cn": table_cn or sheet_name.split("_", 1)[-1],
                "sheet_name": sheet_name,
                "source_desc": _meta_value(rows, "数据来源"),
                "dimension": _meta_value(rows, "维度", lookahead=6),
                "period": _meta_value(rows, "采集周期", lookahead=8),
                "scope": _meta_value(rows, "数据范围", lookahead=8),
                "fields": fields,
            })
    finally:
        workbook.close()
    return {
        "tables": tables,
        "warnings": warnings,
        "table_count": len(tables),
        "field_count": sum(len(table["fields"]) for table in tables),
    }
