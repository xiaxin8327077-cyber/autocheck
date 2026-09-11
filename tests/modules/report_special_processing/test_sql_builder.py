"""处理脚本生成器单元测试：条件运算符、处理范围规则、字段类型字面量、多表注释分组。"""

from __future__ import annotations

import pytest

from auto_check.modules.report_special_processing.sql_builder import (
    ScriptGenerationError,
    generate_script,
)
from auto_check.modules.report_special_processing.structured_content import (
    StructuredCondition,
    StructuredContent,
    StructuredField,
    StructuredTable,
    parse_scope_values,
)


def _content(*tables: StructuredTable) -> StructuredContent:
    return StructuredContent(datasource_id="ds1", datasource_type="postgresql", tables=tables)


def _table(
    *,
    table_name: str = "apply_contract_info",
    chinese_table_name: str = "运用合同信息",
    datasource_name: str = "TCMP生产库",
    limit_report_period: bool = False,
    report_period_field: str = "",
    report_period_field_source: str = "",
    conditions: tuple[StructuredCondition, ...] = (
        StructuredCondition(column_name="project_no", operator="IN", values=("金牛1号", "金牛2号")),
    ),
    fields: tuple[StructuredField, ...] = (
        StructuredField(column_name="status", chinese_column_name="合同状态",
                        column_name_source="MANUAL", value_before="正常", value_after="终止"),
    ),
) -> StructuredTable:
    return StructuredTable(
        table_name=table_name,
        chinese_table_name=chinese_table_name,
        table_name_source="MANUAL",
        schema="public",
        datasource_id="ds1",
        datasource_type="postgresql",
        datasource_name=datasource_name,
        limit_report_period=limit_report_period,
        report_period_field=report_period_field,
        report_period_field_source=report_period_field_source,
        conditions=conditions,
        fields=fields,
    )


def test_parse_scope_values_splits_deduplicates_and_strips():
    assert parse_scope_values("金牛1号、金牛2号；金牛2号， 空值 ", label="项目", field_key="t") == (
        "金牛1号", "金牛2号", "空值",
    )
    assert parse_scope_values(["A", " A ", "B"], label="项目", field_key="t") == ("A", "B")
    assert parse_scope_values(None, label="项目", field_key="t") == ()


def test_generate_single_value_uses_equals_multi_uses_in():
    single = _table(conditions=(StructuredCondition(column_name="project_no", values=("P001",)),))
    script = generate_script(_content(single), report_period="", field_types={})
    assert "project_no = 'P001'" in script
    multi = _table(conditions=(StructuredCondition(column_name="project_no", operator="IN", values=("P001", "P002")),))
    script = generate_script(_content(multi), report_period="", field_types={})
    assert "project_no IN ('P001', 'P002')" in script


def test_generate_comparison_and_like_and_null_operators():
    table = _table(conditions=(
        StructuredCondition(column_name="amount", operator=">", values=("100",)),
        StructuredCondition(column_name="name", operator="LIKE", values=("ABC",)),
        StructuredCondition(column_name="closed_at", operator="IS NULL", values=()),
    ))
    script = generate_script(_content(table), report_period="", field_types={
        "ds1": {"apply_contract_info": {"amount": "decimal"}},
    })
    assert "amount > 100" in script
    assert "name LIKE '%ABC%'" in script
    assert "closed_at IS NULL" in script


def test_literals_keep_types_and_escape_quotes():
    table = _table(
        conditions=(StructuredCondition(column_name="amount", operator="=", values=("100",)),),
        fields=(
            StructuredField(column_name="remark", chinese_column_name="备注", column_name_source="MANUAL",
                            value_before="it's ok", value_after="done"),
        ),
    )
    script = generate_script(_content(table), report_period="", field_types={
        "ds1": {"apply_contract_info": {"amount": "decimal"}},
    })
    assert "remark = 'done'" in script
    assert "WHERE amount = 100" in script


def test_before_values_are_not_merged_into_where():
    table = _table()
    script = generate_script(_content(table), report_period="", field_types={})
    assert "SET status = '终止'" in script
    assert "status = '正常'" not in script
    assert "value_before" not in script


def test_report_period_condition_when_limited():
    table = _table(
        limit_report_period=True,
        report_period_field="d_cldate",
        report_period_field_source="AUTO",
    )
    script = generate_script(_content(table), report_period="2026-08-31", field_types={
        "ds1": {"apply_contract_info": {"d_cldate": "date"}},
    })
    assert "d_cldate = '2026-08-31'" in script
    # 顺序：报送期在前，处理范围在后
    assert script.index("d_cldate") < script.index("project_no")
    # 字符型报送期同样统一使用 YYYY-MM-DD
    table2 = _table(limit_report_period=True, report_period_field="d_cldate", report_period_field_source="AUTO")
    script2 = generate_script(_content(table2), report_period="2026-08-31", field_types={
        "ds1": {"apply_contract_info": {"d_cldate": "varchar"}},
    })
    assert "d_cldate = '2026-08-31'" in script2


def test_limited_without_period_field_rejected():
    with pytest.raises(ScriptGenerationError) as exc:
        generate_script(_content(_table(limit_report_period=True)), report_period="2026-08-31", field_types={})
    assert "未" in str(exc.value)


def test_requires_scope_for_update():
    with pytest.raises(ScriptGenerationError) as exc:
        generate_script(_content(_table(conditions=())), report_period="", field_types={})
    assert "请至少配置一条处理范围" in str(exc.value)


def test_multi_tables_generate_segmented_scripts_with_names():
    other = _table(
        table_name="customer_info",
        chinese_table_name="客户信息表",
        datasource_name="核算库",
        conditions=(StructuredCondition(column_name="contract_no", values=("HT001",)),),
        fields=(StructuredField(column_name="status", chinese_column_name="状态", column_name_source="MANUAL",
                                value_before="1", value_after="2"),),
    )
    script = generate_script(_content(_table(), other), report_period="", field_types={})
    assert script.count("-- 表：") == 2
    assert "-- 数据源：TCMP生产库" in script
    assert "-- 数据源：核算库" in script
    assert "UPDATE apply_contract_info" in script
    assert "UPDATE customer_info" in script


def test_generate_rejects_empty_tables():
    content = StructuredContent(datasource_id="", datasource_type="", tables=())
    with pytest.raises(ScriptGenerationError):
        generate_script(content, report_period="", field_types={})
