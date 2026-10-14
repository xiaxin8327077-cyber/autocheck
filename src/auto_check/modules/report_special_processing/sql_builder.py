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
- 修改后文本按普通字面量生成，填写 null 得到字符串 'null'。
  仅当用户确认设置为空（value_after_null）时，SET 写成 SQL NULL。
  整数和数值的空修改后也写成 NULL：MySQL 与 PostgreSQL 都不能把空字符串赋给这类字段。
  日期、时间仍按字符串字面量生成。

方言差异：当前 PostgreSQL 与 MySQL 的 UPDATE 与比较运算符语法一致。
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from sqlalchemy.dialects.mysql.base import RESERVED_WORDS_MYSQL as _MYSQL_RESERVED_WORDS
from sqlalchemy.dialects.postgresql.base import RESERVED_WORDS as _PG_RESERVED_WORDS

from .structured_content import (
    CONDITION_OPERATORS,
    CONDITION_OPERATORS_REQUIRING_VALUE,
    StructuredContent,
    StructuredField,
)


class ScriptGenerationError(ValueError):
    """生成脚本失败；message 面向用户，定位到具体的表或字段。"""


def _identifier(name: str, db_type: str) -> str:
    value = str(name)
    dialect = str(db_type or "").strip().lower()
    quote = "`" if dialect == "mysql" else '"'
    is_simple_ascii = re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", value) is not None
    needs_quote = not is_simple_ascii
    if dialect == "mysql":
        needs_quote = needs_quote or value.lower() in _MYSQL_RESERVED_WORDS
    else:
        has_ascii_uppercase = any("A" <= character <= "Z" for character in value)
        needs_quote = needs_quote or has_ascii_uppercase or value.lower() in _PG_RESERVED_WORDS
    return quote + value.replace(quote, quote * 2) + quote if needs_quote else value


def _table_identifier(table: Any, datasource: Mapping[str, str], db_type: str) -> str:
    # 元数据给出的 schema + table_name 是两个原始标识符；表名里的点不能拆分。
    scope = table.schema
    name = table.table_name
    if scope:
        if db_type == "mysql" and datasource.get("database"):
            scope = datasource["database"]
        parts = (scope, name)
    else:
        # 只有没有 schema 快照的历史名称才兼容明确的两段限定写法。
        token = r'"(?:[^"]|"")+"|`(?:[^`]|``)+`|[A-Za-z_][A-Za-z0-9_$#]*'
        match = re.fullmatch(rf'({token})\.({token})', name)
        if match:
            def unquote(part: str) -> str:
                if part[0] in ('"', '`'):
                    return part[1:-1].replace(part[0] * 2, part[0])
                return part
            parts = (unquote(match.group(1)), unquote(match.group(2)))
        else:
            scope = (datasource.get("database") if db_type == "mysql" else datasource.get("schema")) or ""
            parts = (scope, name) if scope else (name,)
    return ".".join(_identifier(part, db_type) for part in parts)


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


_NULL_TOKENS = frozenset({"null", "空", "空白", "空值"})


def _is_null_token(text: str) -> bool:
    token = str(text or "").strip()
    return token.lower() in _NULL_TOKENS


def _is_numeric_type(data_type: str) -> bool:
    """整数和数值。用词边界，避免把 interval、point 当成 int。"""
    return _NUMERIC_TYPE_RE.search(str(data_type or "").strip()) is not None


def _assignment_literal(value: Any, *, clear: bool, data_type: str = "") -> str:
    """修改后按字段类型生成字面量。确认为空时写 NULL；字符串保留原样，含空格。"""
    if clear or value is None:
        return "NULL"
    kind = str(data_type or "").strip().lower()
    raw = str(value)
    text = raw.strip()
    if _is_numeric_type(kind):
        if not text or _is_null_token(text):
            return "NULL"
        try:
            float(text)
        except ValueError:
            return _literal(raw)
        return text
    if kind and any(token in kind for token in _DATE_TYPES):
        return _literal((text or raw)[:10])
    return _literal(raw)


_NUMERIC_TYPE_RE = re.compile(
    r"\b(?:tinyint|smallint|mediumint|bigint|bigserial|smallserial|serial|integer|"
    r"int2|int4|int8|int|decimal|numeric|number|money|float4|float8|float|"
    r"double precision|double|real)\b",
    re.IGNORECASE,
)
_DATE_TYPES = ("date", "time", "timestamp")


def _typed_literal(value: Any, data_type: str) -> str:
    """按字段类型生成字面量：数值不加引号，日期/时间按日期串，其余字符串安全处理。"""
    if value is None:
        return "NULL"
    kind = str(data_type or "").strip().lower()
    text = str(value).strip()
    if _is_numeric_type(kind):
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


def _report_period_text(report_period: str) -> str:
    """报送期统一为 YYYY-MM-DD 文本。"""
    value = str(report_period or "").strip()
    if not value:
        raise ScriptGenerationError("缺少所属报送期，无法生成报送期条件")
    compact = value.replace("-", "")[:8]
    if len(compact) == 8 and compact.isdigit():
        return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"
    return value[:10]


def _report_period_literal(report_period: str) -> str:
    """报送期 = 所属报送期：所有字段类型统一输出 YYYY-MM-DD。"""
    return _literal(_report_period_text(report_period))


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
    db_type: str,
) -> str:
    display = chinese_table_name or table_name
    where: list[str] = []
    # 1. 报送期条件（仅限制报送期且已确定报送期字段时）
    if limit_report_period:
        if not report_period_field:
            raise ScriptGenerationError(f"“{display}”：未能确定当前表的报送期字段，请填写报送期字段")
        where.append(
            f"{_identifier(report_period_field, db_type)} = {_report_period_literal(report_period)}"
        )
    # 2. 处理范围条件（条件字段 + 运算符 + 条件值，行间 AND）
    for condition in conditions:
        column = str(condition.get("column_name") or "")
        operator = str(condition.get("operator") or "=").strip().upper()
        values = tuple(condition.get("values") or ())
        if not column:
            raise ScriptGenerationError(f"“{display}”：请至少配置一条有效的处理范围条件")
        requires_value = operator in CONDITION_OPERATORS_REQUIRING_VALUE
        if not values and requires_value:
            raise ScriptGenerationError(f"“{display}”：请至少配置一条有效的处理范围条件")
        where.append(
            _condition_clause(_identifier(column, db_type), operator, values, field_types.get(column, ""))
        )
    if not where:
        raise ScriptGenerationError(f"“{display}”：请至少配置一条处理范围")
    # 3. SET 修改字段（修改前仅作业务信息保存，不参与 WHERE 校验）
    set_parts: list[str] = []
    for field in fields:
        set_parts.append(
            f"{_identifier(field.column_name, db_type)} = "
            f"{_assignment_literal(field.value_after, clear=field.value_after_null, data_type=field_types.get(field.column_name, ''))}"
        )
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
    datasources: Mapping[str, Mapping[str, str]] | None = None,
) -> str:
    """逐表生成 UPDATE 语句，段首带数据源与表注释分组。

    field_types: {datasource_id: {table_name: {column_name: data_type}}} 由前端基于
    已缓存的表字段元数据提供，用于条件值字面量格式判断（仅影响生成文本）。
    datasources 为应用配置中的脱敏类型与范围，用于空 Schema 回退及 MySQL database。
    """
    if not content.tables:
        raise ScriptGenerationError("请至少选择一张处理表")
    kinds: dict[str, dict[str, dict[str, str]]] = {
        str(ds): {str(table): dict(types) for table, types in items.items()}
        for ds, items in dict(field_types or {}).items()
    }
    segments: list[str] = []
    for table in content.tables:
        datasource = (datasources or {}).get(table.datasource_id or content.datasource_id, {})
        db_type = datasource.get("db_type") or table.datasource_type or content.datasource_type
        table_kinds = (
            kinds.get(table.datasource_id, {}).get(str(table.table_name), {})
        )
        sql = _build_table_sql(
            table_name=_table_identifier(table, datasource, db_type),
            chinese_table_name=table.chinese_table_name,
            limit_report_period=table.limit_report_period,
            report_period_field=table.report_period_field,
            report_period=report_period,
            conditions=[item.to_dict() for item in table.conditions],
            field_types=table_kinds,
            fields=table.fields,
            db_type=db_type,
        )
        segments.append(
            f"-- 数据源：{table.datasource_name or table.datasource_id}\n"
            f"-- 表：{table.table_name}（{table.chinese_table_name or '未命名'}）\n"
            f"{sql}"
        )
    return "\n\n".join(segments)


def build_distinct_value_query(
    *,
    db_type: str,
    schema: str,
    table_name: str,
    column_name: str,
    conditions: Sequence[Mapping[str, Any]],
    report_period_field: str = "",
    report_period: str = "",
    limit_report_period: bool = False,
) -> tuple[str, tuple[Any, ...]]:
    """按与处理脚本相同的条件生成只读 DISTINCT 查询，最多两行以判断当前值是否一致。"""
    if not str(table_name or "").strip() or not str(column_name or "").strip():
        raise ScriptGenerationError("请先选择处理表和修改字段")
    where: list[str] = []
    params: list[Any] = []
    if limit_report_period:
        if not str(report_period_field or "").strip():
            raise ScriptGenerationError("请先确定报送期字段")
        where.append(f"{_identifier(report_period_field, db_type)} = %s")
        params.append(_report_period_text(report_period))
    for condition in conditions:
        column = str(condition.get("column_name") or "").strip()
        operator = str(condition.get("operator") or "=").strip().upper()
        values = tuple(str(item) for item in (condition.get("values") or ()) if str(item) != "")
        if not column:
            continue
        if operator not in CONDITION_OPERATORS:
            raise ScriptGenerationError("条件运算符无效")
        quoted = _identifier(column, db_type)
        if operator in ("IS NULL", "IS NOT NULL"):
            where.append(f"{quoted} {operator}")
            continue
        if operator in CONDITION_OPERATORS_REQUIRING_VALUE and not values:
            continue
        if operator == "LIKE":
            like = values[0]
            if not like.startswith("%") and not like.endswith("%"):
                like = f"%{like}%"
            where.append(f"{quoted} LIKE %s")
            params.append(like)
            continue
        if operator == "IN":
            where.append(f"{quoted} IN ({', '.join(['%s'] * len(values))})")
            params.extend(values)
            continue
        where.append(f"{quoted} {operator} %s")
        params.append(values[0])
    if not where:
        raise ScriptGenerationError("请至少配置一条处理范围")
    table = _identifier(schema, db_type) + "." + _identifier(table_name, db_type) if schema else _identifier(table_name, db_type)
    sql = (
        f"SELECT DISTINCT {_identifier(column_name, db_type)} AS current_value "
        f"FROM {table} WHERE {' AND '.join(where)} LIMIT 2"
    )
    return sql, tuple(params)
