"""处理脚本生成器：根据结构化内容生成逐表 UPDATE SQL（仅生成文本，绝不执行）。

安全规则：
- 每张表至少一条有效处理范围条件（条件字段 + 条件值），否则拒绝生成——禁止无 WHERE 的 UPDATE；
- 处理范围条件行之间使用 AND；单值生成 `=`、多值生成 `IN (...)`；
- 限制报送期（limit_report_period=True）时，报送期字段出处：
  ① 自动识别（前端按系统字典下发的匹配词优先级识别，来源 AUTO）或 ② 人工选择（来源 MANUAL）；
  报送期日期取记录级“所属报送期”，按字段数据类型生成字面量（日期型 YYYY-MM-DD、字符型 YYYYMMDD）；
- WHERE 条件顺序：报送期 → 处理范围 → 修改前校验；
- 每个有“修改前”的字段都作为 WHERE 校验条件；值按字面量安全生成。

方言差异：当前 PostgreSQL 与 MySQL 的 UPDATE 语法一致；日期字面量按数据类型区分。
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .structured_content import StructuredContent, StructuredField


class ScriptGenerationError(ValueError):
    """生成脚本失败；message 面向用户，定位到具体的表或字段。"""


def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (bytes, bytearray)):
        raise ScriptGenerationError("处理脚本不支持二进制值")
    return "'" + str(value).replace("'", "''") + "'"


def _in_clause(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(_literal(value) for value in values)})"


def _value_equals(column: str, values: Sequence[str]) -> str:
    # 单值用等号，多值用 IN，避免 IN 单值带来语义噪音。
    if len(values) == 1:
        return f"{column} = {_literal(values[0])}"
    return _in_clause(column, values)


def _is_date_like(data_type: str) -> bool:
    """字段类型是否按日期字面量匹配（DATE/DATETIME/TIMESTAMP 等）。"""
    kind = str(data_type or "").strip().lower()
    if not kind:
        return True  # 未知类型按日期处理（YYYY-MM-DD）
    if any(token in kind for token in ("date", "time", "timestamp")):
        return True
    return False


def _report_period_literal(report_period: str, data_type: str) -> str:
    """报送期 = 所属报送期：日期型输出 YYYY-MM-DD，字符型输出 YYYYMMDD。"""
    value = str(report_period or "").strip()
    if not value:
        raise ScriptGenerationError("缺少所属报送期，无法生成报送期条件")
    if _is_date_like(data_type):
        return _literal(value[:10])
    return _literal(value.replace("-", "")[:8])


def _build_table_sql(
    *,
    table_name: str,
    chinese_table_name: str,
    limit_report_period: bool,
    report_period_field: str,
    report_period: str,
    conditions: Sequence[Mapping[str, Any]],
    field_types: Mapping[str, str],
    fields: Sequence[StructuredField],
) -> str:
    display = chinese_table_name or table_name
    where: list[str] = []
    # 1. 报送期条件（仅限制报送期且已确定报送期字段时）
    if limit_report_period:
        if not report_period_field:
            raise ScriptGenerationError(f"“{display}”：未能确定当前表的报送期字段，请填写报送期字段")
        where.append(
            f"{report_period_field} = {_report_period_literal(report_period, field_types.get(report_period_field, ''))}"
        )
    # 2. 处理范围条件（条件字段 + 条件值，行间 AND）
    for condition in conditions:
        column = str(condition.get("column_name") or "").strip()
        values = tuple(condition.get("values") or ())
        if not column or not values:
            raise ScriptGenerationError(f"“{display}”：请至少配置一条有效的处理范围条件")
        where.append(_value_equals(column, values))
    if not where:
        raise ScriptGenerationError(f"“{display}”：请至少配置一条处理范围")
    # 3. 修改前校验条件 + SET
    set_parts: list[str] = []
    for field in fields:
        if field.value_before is not None and str(field.value_before) != "":
            where.append(f"{field.column_name} = {_literal(field.value_before)}")
        set_parts.append(f"{field.column_name} = {_literal(field.value_after)}")
    if not set_parts:
        raise ScriptGenerationError(f"“{display}”：请至少选择并填写一个修改字段")
    lines = [
        f"UPDATE {table_name}",
        f"SET {', '.join(set_parts)}",
        f"WHERE {' AND '.join(where)};",
    ]
    return "\n".join(lines)


def generate_script(
    content: StructuredContent,
    *,
    report_period: str = "",
    field_types: Mapping[str, Mapping[str, str]] | None = None,
) -> str:
    """逐表生成 UPDATE 语句，段首带数据源与表注释分组。

    field_types: {datasource_id: {table_name: {column_name: data_type}}} 由前端基于
    已缓存的表字段元数据提供，用于报送期日期字面量格式判断（仅影响生成文本）。
    """
    if not content.tables:
        raise ScriptGenerationError("请至少选择一张处理表")
    kinds: dict[str, dict[str, dict[str, str]]] = {
        str(ds): {str(table): dict(types) for table, types in items.items()}
        for ds, items in dict(field_types or {}).items()
    }
    segments: list[str] = []
    for table in content.tables:
        table_kinds = (
            kinds.get(table.datasource_id, {}).get(str(table.table_name), {})
        )
        sql = _build_table_sql(
            table_name=table.table_name,
            chinese_table_name=table.chinese_table_name,
            limit_report_period=table.limit_report_period,
            report_period_field=table.report_period_field,
            report_period=report_period,
            conditions=[item.to_dict() for item in table.conditions],
            field_types=table_kinds,
            fields=table.fields,
        )
        segments.append(
            f"-- 数据源：{table.datasource_id}\n"
            f"-- 表：{table.table_name}（{table.chinese_table_name or '未命名'}）\n"
            f"{sql}"
        )
    return "\n\n".join(segments)
