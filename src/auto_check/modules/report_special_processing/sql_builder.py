"""处理脚本生成器：根据结构化内容生成逐表 UPDATE SQL（仅生成文本，绝不执行）。

安全规则：
- 每张表至少一条有效处理范围条件（条件字段 + 运算符 + 条件值），否则拒绝生成——禁止无 WHERE 的 UPDATE；
- 处理范围条件行之间使用 AND；
- 条件运算符支持：=、<>、>、>=、<、<=、LIKE、IN、IS NULL、IS NOT NULL；
  IS NULL / IS NOT NULL 不需要条件值；LIKE 自动把业务值包装为 %值%；IN 支持多个值；
- 限制报送期（limit_report_period=True）时，报送期字段出处：
  ① 自动识别（前端按系统字典下发的匹配词优先级识别，来源 AUTO）或 ② 人工选择（来源 MANUAL）；
  报送期日期取记录级“所属报送期”，统一生成 YYYY-MM-DD 字面量；
- WHERE 条件顺序：报送期 → 处理范围；
- 条件值按字段数据类型生成字面量：varchar/char/text 加引号并转义，数值不加引号，
  日期/时间按日期串；未知类型按字符串安全处理。

方言差异：当前 PostgreSQL 与 MySQL 的 UPDATE 与比较运算符语法一致。
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .structured_content import (
    CONDITION_OPERATORS,
    CONDITION_OPERATORS_REQUIRING_VALUE,
    StructuredContent,
    StructuredField,
)


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


_NUMERIC_TYPES = ("int", "decimal", "numeric", "float", "double", "real", "number", "money")
_DATE_TYPES = ("date", "time", "timestamp")


def _typed_literal(value: Any, data_type: str) -> str:
    """按字段类型生成字面量：数值不加引号，日期/时间按日期串，其余字符串安全处理。"""
    if value is None:
        return "NULL"
    kind = str(data_type or "").strip().lower()
    text = str(value).strip()
    if kind and any(token in kind for token in _NUMERIC_TYPES):
        # 数值字段：仅接受合法数值，否则按字符串兜底（避免生成非法 SQL）。
        try:
            float(text)
        except ValueError:
            return _literal(text)
        return text
    if kind and any(token in kind for token in _DATE_TYPES):
        return _literal(text[:10])
    return _literal(text)


def _in_clause(column: str, values: Sequence[str], data_type: str) -> str:
    return f"{column} IN ({', '.join(_typed_literal(value, data_type) for value in values)})"


def _condition_clause(column: str, operator: str, values: Sequence[str], data_type: str) -> str:
    operator = str(operator or "=").strip().upper()
    if operator not in CONDITION_OPERATORS:
        raise ScriptGenerationError("条件运算符无效")
    if operator in ("IS NULL", "IS NOT NULL"):
        # 不需要条件值（模型已在保存时清除值）。
        return f"{column} {operator}"
    if operator == "LIKE":
        if not values:
            raise ScriptGenerationError(f"“{column}”模糊匹配需要填写条件值")
        like = str(values[0])
        # 业务值直接包装为 %值%，不允许用户自带完整 LIKE 片段二次拼接。
        if not like.startswith("%") and not like.endswith("%"):
            like = f"%{like}%"
        return f"{column} LIKE {_literal(like)}"
    if operator == "IN":
        if not values:
            raise ScriptGenerationError(f"“{column}”属于多个值需要填写条件值")
        return _in_clause(column, values, data_type)
    # 比较运算符：单值语义，多个值时取首个有效值
    if not values:
        raise ScriptGenerationError(f"“{column}”需要填写条件值")
    return f"{column} {operator} {_typed_literal(values[0], data_type)}"


def _report_period_literal(report_period: str) -> str:
    """报送期 = 所属报送期：所有字段类型统一输出 YYYY-MM-DD。"""
    value = str(report_period or "").strip()
    if not value:
        raise ScriptGenerationError("缺少所属报送期，无法生成报送期条件")
    compact = value.replace("-", "")[:8]
    if len(compact) == 8 and compact.isdigit():
        value = f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"
    else:
        value = value[:10]
    return _literal(value)


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
            f"{report_period_field} = {_report_period_literal(report_period)}"
        )
    # 2. 处理范围条件（条件字段 + 运算符 + 条件值，行间 AND）
    for condition in conditions:
        column = str(condition.get("column_name") or "").strip()
        operator = str(condition.get("operator") or "=").strip().upper()
        values = tuple(condition.get("values") or ())
        if not column:
            raise ScriptGenerationError(f"“{display}”：请至少配置一条有效的处理范围条件")
        requires_value = operator in CONDITION_OPERATORS_REQUIRING_VALUE
        if not values and requires_value:
            raise ScriptGenerationError(f"“{display}”：请至少配置一条有效的处理范围条件")
        where.append(
            _condition_clause(column, operator, values, field_types.get(column, ""))
        )
    if not where:
        raise ScriptGenerationError(f"“{display}”：请至少配置一条处理范围")
    # 3. SET 修改字段（修改前仅作业务信息保存，不参与 WHERE 校验）
    set_parts: list[str] = []
    for field in fields:
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
    已缓存的表字段元数据提供，用于条件值字面量格式判断（仅影响生成文本）。
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
            f"-- 数据源：{table.datasource_name or table.datasource_id}\n"
            f"-- 表：{table.table_name}（{table.chinese_table_name or '未命名'}）\n"
            f"{sql}"
        )
    return "\n\n".join(segments)
