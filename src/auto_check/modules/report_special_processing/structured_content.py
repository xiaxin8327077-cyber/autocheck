"""数据源 → 处理表 → 处理字段 → 修改前/修改后 的结构化内容模型。

新记录以本模块的 JSON 结构为唯一事实来源（存储于 structured_content_json 列），
并派生既有的 table_name（双语规范串）、field_name（分组规范串）、
value_before / value_after（按字段顺序 \n 聚合）字符串，保证台账、导出、
通知、审计等既有链路无需理解新结构即可继续工作。

修改前/修改后的“同上”仅是前端展示标记（与上一字段值相等时显示），保存时始终写入真实值。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

MAX_STRUCTURED_TABLES = 5
MAX_STRUCTURED_FIELDS_PER_TABLE = 5
MAX_PHYSICAL_NAME_LEN = 128
MAX_CHINESE_NAME_LEN = 100
MAX_FIELD_VALUE_LEN = 128
MAX_STRUCTURED_JSON_CHARS = 20000

SUPPORTED_DATASOURCE_TYPES = ("postgresql", "mysql")
NAME_SOURCE_DATABASE = "DATABASE"
NAME_SOURCE_MANUAL = "MANUAL"

# 物理对象名限制为常规标识符字符，禁止混入双语规范串/分组串的分隔符。
_PHYSICAL_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#]{0,127}$")


class StructuredContentError(ValueError):
    """结构化内容校验失败；fields 为 {表单字段键: 用户可读消息}。"""

    def __init__(self, fields: dict[str, str]) -> None:
        super().__init__("；".join(fields.values()) or "结构化内容无效")
        self.fields = fields


def _text(value: Any, *, max_len: int, message: str) -> str:
    text = str(value if value is not None else "").strip()
    if len(text) > max_len:
        raise StructuredContentError({"structured_content": message})
    return text


def _physical_name(value: Any, *, label: str) -> str:
    name = _text(value, max_len=MAX_PHYSICAL_NAME_LEN, message=f"{label}过长")
    if not name:
        raise StructuredContentError({"structured_content": f"{label}不能为空"})
    if not _PHYSICAL_NAME_RE.match(name):
        raise StructuredContentError({"structured_content": f"{label}必须是数据库中的真实物理名称"})
    return name


@dataclass(frozen=True)
class StructuredField:
    column_name: str
    chinese_column_name: str
    column_name_source: str  # DATABASE | MANUAL
    value_before: str = ""
    value_after: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "column_name": self.column_name,
            "chinese_column_name": self.chinese_column_name,
            "column_name_source": self.column_name_source,
            "value_before": self.value_before,
            "value_after": self.value_after,
        }

    @property
    def display_name(self) -> str:
        return self.chinese_column_name or self.column_name


@dataclass(frozen=True)
class StructuredCondition:
    """处理范围条件：条件字段 + 解析后的条件值列表（“、”“；”分隔，去空去重）。"""

    column_name: str
    values: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "column_name": self.column_name,
            "values": list(self.values),
        }


@dataclass(frozen=True)
class StructuredTable:
    table_name: str
    chinese_table_name: str
    table_name_source: str  # DATABASE | MANUAL
    schema: str = ""
    # 表级数据源：不同处理表可来自不同数据源；为空时继承 StructuredContent 顶层。
    datasource_id: str = ""
    datasource_type: str = ""
    # 处理范围：通用数据条件（条件字段 + 条件值），默认至少一条有效条件。
    conditions: tuple[StructuredCondition, ...] = ()
    # 限制报送期：仅该表为 True 时生成报送期 WHERE 条件；
    # report_period_field_source：AUTO（按系统字典匹配词自动识别）| MANUAL（人工选择）。
    limit_report_period: bool = True
    report_period_field: str = ""
    report_period_field_source: str = ""
    # 兼容旧数据：早期版本的项目/合同处理范围（保存后不再产出）。
    projects: tuple[str, ...] = ()
    contracts: tuple[str, ...] = ()
    fields: tuple[StructuredField, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "table_name": self.table_name,
            "chinese_table_name": self.chinese_table_name,
            "table_name_source": self.table_name_source,
            "datasource_id": self.datasource_id,
            "datasource_type": self.datasource_type,
            "conditions": [item.to_dict() for item in self.conditions],
            "limit_report_period": self.limit_report_period,
            "report_period_field": self.report_period_field,
            "report_period_field_source": self.report_period_field_source,
            "projects": list(self.projects),
            "contracts": list(self.contracts),
            "fields": [item.to_dict() for item in self.fields],
        }

    @property
    def display_name(self) -> str:
        return self.chinese_table_name or self.table_name


@dataclass(frozen=True)
class StructuredContent:
    datasource_id: str
    datasource_type: str
    tables: tuple[StructuredTable, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "datasource_id": self.datasource_id,
            "datasource_type": self.datasource_type,
            "tables": [item.to_dict() for item in self.tables],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))

    def flattened_fields(self) -> tuple[tuple[StructuredTable, StructuredField], ...]:
        result: list[tuple[StructuredTable, StructuredField]] = []
        for table in self.tables:
            for field in table.fields:
                result.append((table, field))
        return tuple(result)


def _parse_name_source(value: Any, *, label: str, field_key: str) -> str:
    source = str(value or "").strip().upper()
    if source not in (NAME_SOURCE_DATABASE, NAME_SOURCE_MANUAL):
        raise StructuredContentError({field_key: f"{label}名称来源无效"})
    return source


def _require_chinese_name(chinese: str, source: str, *, label: str, field_key: str) -> None:
    # DATABASE 来源允许中文名为空（物理名兜底展示）；MANUAL 来源必填中文名。
    if source == NAME_SOURCE_MANUAL and not chinese:
        raise StructuredContentError({field_key: f"请输入{label}中文名"})


MAX_SCOPE_VALUES = 200

def parse_scope_values(value: Any, *, label: str, field_key: str) -> tuple[str, ...]:
    """解析处理范围（项目/合同）：支持“、”“；”“,”分隔，去除首尾空格、空值与重复项。"""
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        raw_items = [str(item or "").strip() for item in value]
    elif isinstance(value, str):
        raw_items = re.split(r"[、；,;，]", value)
    else:
        raise StructuredContentError({field_key: f"{label}处理范围格式无效"})
    seen: set[str] = set()
    result: list[str] = []
    for item in raw_items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        if len(text) > 200:
            raise StructuredContentError({field_key: f"{label}单项过长"})
        seen.add(text)
        result.append(text)
    if len(result) > MAX_SCOPE_VALUES:
        raise StructuredContentError({field_key: f"{label}数量过多，最多 {MAX_SCOPE_VALUES} 项"})
    return tuple(result)


def parse_structured_content(payload: Any) -> StructuredContent:
    """校验并解析前端提交的 structured_content 对象。"""
    if payload is None:
        raise StructuredContentError({"structured_content": "缺少结构化处理内容"})
    if not isinstance(payload, Mapping):
        raise StructuredContentError({"structured_content": "结构化处理内容格式无效"})
    try:
        json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        raise StructuredContentError({"structured_content": "结构化处理内容格式无效"}) from None
    if len(json.dumps(payload, ensure_ascii=False)) > MAX_STRUCTURED_JSON_CHARS:
        raise StructuredContentError({"structured_content": "结构化处理内容过大"})

    datasource_id = _text(payload.get("datasource_id"), max_len=64, message="数据源标识过长")
    if not datasource_id:
        raise StructuredContentError({"datasource_id": "请选择数据源"})
    datasource_type = str(payload.get("datasource_type") or "").strip().lower()
    if datasource_type not in SUPPORTED_DATASOURCE_TYPES:
        raise StructuredContentError({"datasource_id": "数据源类型暂不支持，仅支持 PostgreSQL / MySQL"})

    raw_tables = payload.get("tables")
    if not isinstance(raw_tables, Sequence) or isinstance(raw_tables, (str, bytes)):
        raise StructuredContentError({"structured_content": "处理表列表无效"})
    if len(raw_tables) > MAX_STRUCTURED_TABLES:
        raise StructuredContentError({"table_name": f"最多选择 {MAX_STRUCTURED_TABLES} 张处理表"})

    tables: list[StructuredTable] = []
    seen_tables: set[str] = set()
    for raw_table in raw_tables:
        if not isinstance(raw_table, Mapping):
            raise StructuredContentError({"structured_content": "处理表数据无效"})
        table_name = _physical_name(raw_table.get("table_name"), label="处理表")
        if table_name in seen_tables:
            raise StructuredContentError({"table_name": f"处理表 {table_name} 重复"})
        seen_tables.add(table_name)
        schema = _text(raw_table.get("schema"), max_len=MAX_PHYSICAL_NAME_LEN, message="架构名过长")
        chinese_table = _text(
            raw_table.get("chinese_table_name"), max_len=MAX_CHINESE_NAME_LEN, message="中文表名过长",
        )
        table_source = _parse_name_source(
            raw_table.get("table_name_source"), label="表", field_key="table_name",
        )
        _require_chinese_name(chinese_table, table_source, label="表", field_key="table_name")
        # 表级数据源（多表可来自不同数据源）；缺省时继承顶层。
        table_datasource_id = _text(
            raw_table.get("datasource_id"), max_len=64, message="数据源标识过长",
        ) or datasource_id
        table_datasource_type = str(
            raw_table.get("datasource_type") or datasource_type or ""
        ).strip().lower()
        if table_datasource_type not in SUPPORTED_DATASOURCE_TYPES:
            raise StructuredContentError({
                "table_name": "数据源类型暂不支持，仅支持 PostgreSQL / MySQL",
            })
        # 处理范围：通用数据条件（条件字段 + 条件值）。
        # 空行（字段与值均为空）视为未使用直接跳过；只填一半的行明确报错。
        conditions: list[StructuredCondition] = []
        raw_conditions = raw_table.get("conditions")
        if raw_conditions is not None:
            if not isinstance(raw_conditions, Sequence) or isinstance(raw_conditions, (str, bytes)):
                raise StructuredContentError({"table_name": "处理范围条件列表无效"})
            if len(raw_conditions) > 20:
                raise StructuredContentError({"table_name": "处理范围条件过多，最多 20 条"})
            seen_condition_columns: set[str] = set()
            for raw_condition in raw_conditions:
                if not isinstance(raw_condition, Mapping):
                    raise StructuredContentError({"table_name": "处理范围条件数据无效"})
                condition_column = _text(
                    raw_condition.get("column_name"), max_len=MAX_PHYSICAL_NAME_LEN,
                    message="处理范围字段名过长",
                )
                condition_values = parse_scope_values(
                    raw_condition.get("values"), label="处理范围条件值", field_key="table_name",
                )
                if not condition_column and not condition_values:
                    continue  # 未使用的空条件行
                if not condition_column:
                    raise StructuredContentError({"table_name": "请选择处理范围字段"})
                if not condition_values:
                    raise StructuredContentError({"table_name": "请输入处理范围条件值"})
                if condition_column in seen_condition_columns:
                    raise StructuredContentError({"table_name": f"处理范围字段 {condition_column} 重复"})
                seen_condition_columns.add(condition_column)
                conditions.append(StructuredCondition(
                    column_name=condition_column, values=condition_values,
                ))
        # 限制报送期：仅 limit_report_period=True 时需要报送期字段。
        limit_report_period = bool(raw_table.get("limit_report_period", True))
        report_period_field = _text(
            raw_table.get("report_period_field"), max_len=MAX_PHYSICAL_NAME_LEN,
            message="报送期字段名过长",
        )
        report_period_field_source = str(
            raw_table.get("report_period_field_source") or ""
        ).strip().upper()
        if report_period_field_source not in ("AUTO", "MANUAL", ""):
            raise StructuredContentError({"table_name": "报送期字段来源无效"})
        if report_period_field and not _PHYSICAL_NAME_RE.match(report_period_field):
            raise StructuredContentError({"table_name": "报送期字段必须是数据库中的真实物理名称"})

        raw_fields = raw_table.get("fields")
        if not isinstance(raw_fields, Sequence) or isinstance(raw_fields, (str, bytes)):
            raise StructuredContentError({"field_name": f"“{chinese_table or table_name}”的字段列表无效"})
        if not raw_fields:
            raise StructuredContentError({
                "field_name": f"请至少为“{chinese_table or table_name}”选择一个关联字段",
            })
        if len(raw_fields) > MAX_STRUCTURED_FIELDS_PER_TABLE:
            raise StructuredContentError({
                "field_name": f"“{chinese_table or table_name}”最多选择 {MAX_STRUCTURED_FIELDS_PER_TABLE} 个字段",
            })

        fields: list[StructuredField] = []
        seen_columns: set[str] = set()
        for raw_field in raw_fields:
            if not isinstance(raw_field, Mapping):
                raise StructuredContentError({"field_name": "关联字段数据无效"})
            column_name = _physical_name(raw_field.get("column_name"), label="处理字段")
            if column_name in seen_columns:
                raise StructuredContentError({"field_name": f"关联字段 {column_name} 重复"})
            seen_columns.add(column_name)
            chinese_column = _text(
                raw_field.get("chinese_column_name"), max_len=MAX_CHINESE_NAME_LEN, message="中文字段名过长",
            )
            column_source = _parse_name_source(
                raw_field.get("column_name_source"), label="字段", field_key="field_name",
            )
            _require_chinese_name(chinese_column, column_source, label="字段", field_key="field_name")
            value_before = _text(raw_field.get("value_before"), max_len=MAX_FIELD_VALUE_LEN, message="修改前内容过长")
            value_after = _text(raw_field.get("value_after"), max_len=MAX_FIELD_VALUE_LEN, message="修改后内容过长")
            fields.append(StructuredField(
                column_name=column_name,
                chinese_column_name=chinese_column,
                column_name_source=column_source,
                value_before=value_before,
                value_after=value_after,
            ))
        tables.append(StructuredTable(
            table_name=table_name,
            chinese_table_name=chinese_table,
            table_name_source=table_source,
            schema=schema,
            datasource_id=table_datasource_id,
            datasource_type=table_datasource_type,
            conditions=tuple(conditions),
            limit_report_period=limit_report_period,
            report_period_field=report_period_field,
            report_period_field_source=report_period_field_source,
            fields=tuple(fields),
        ))

    if not tables:
        raise StructuredContentError({"table_name": "请选择至少一张处理表"})

    return StructuredContent(
        datasource_id=datasource_id,
        datasource_type=datasource_type,
        tables=tuple(tables),
    )


def structured_from_json(raw: Any) -> StructuredContent | None:
    """反序列化存储列；非法或缺失返回 None（记录按历史模式处理）。"""
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return None
    try:
        return parse_structured_content(payload)
    except StructuredContentError:
        return None


def derive_table_name(content: StructuredContent | None) -> str | None:
    if content is None:
        return None
    return "；".join(
        f"{table.chinese_table_name or table.table_name}｜{table.table_name}"
        for table in content.tables
    )


def derive_field_name(content: StructuredContent | None) -> str | None:
    if content is None:
        return None
    return "；；".join(
        "；".join(
            f"{field.chinese_column_name or field.column_name}｜{field.column_name}"
            for field in table.fields
        )
        for table in content.tables
    )


def derive_value_before(content: StructuredContent | None) -> str | None:
    if content is None:
        return None
    return "\n".join(field.value_before for _, field in content.flattened_fields())


def derive_value_after(content: StructuredContent | None) -> str | None:
    if content is None:
        return None
    return "\n".join(field.value_after for _, field in content.flattened_fields())


def validate_formal_values(content: StructuredContent) -> None:
    """正式保存：处理范围必填、每个字段的修改前/修改后必填，错误定位到具体表/字段。"""
    errors: dict[str, str] = {}
    for table in content.tables:
        if not table.conditions:
            errors.setdefault(
                "table_name",
                f"请至少为“{table.chinese_table_name or table.table_name}”配置一条处理范围",
            )
    for _, field in content.flattened_fields():
        label = field.display_name
        if not field.value_before:
            errors.setdefault("value_before", f"{label}：请输入修改前内容")
        if not field.value_after:
            errors.setdefault("value_after", f"{label}：请输入修改后内容")
    if errors:
        raise StructuredContentError(errors)
