"""处理脚本生成器单元测试：范围解析、WHERE 安全规则、字面量、多表注释分组。"""

from __future__ import annotations

import pytest

from auto_check.modules.report_special_processing.sql_builder import (
    FieldMapping,
    ScriptGenerationError,
    generate_script,
)
from auto_check.modules.report_special_processing.structured_content import (
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
    projects: tuple[str, ...] = ("金牛1号", "金牛2号"),
    contracts: tuple[str, ...] = (),
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
        projects=projects,
        contracts=contracts,
        fields=fields,
    )


def _mapping(project: str = "project_code", contract: str = "contract_no") -> FieldMapping:
    key = ("ds1", "public", "apply_contract_info")
    return {key: FieldMapping(project_field=project, contract_field=contract)}


def test_parse_scope_values_splits_deduplicates_and_strips():
    assert parse_scope_values("金牛1号、金牛2号；金牛2号， 空值 ", label="项目", field_key="t") == (
        "金牛1号", "金牛2号", "空值",
    )
    assert parse_scope_values(["A", " A ", "B"], label="项目", field_key="t") == ("A", "B")
    assert parse_scope_values(None, label="项目", field_key="t") == ()


def test_generate_project_and_contract_scope_uses_and():
    script = generate_script(_content(_table(contracts=("HT001", "HT002"))), _mapping())
    assert "WHERE project_code IN ('金牛1号', '金牛2号')" in script
    assert "AND contract_no IN ('HT001', 'HT002')" in script


def test_generate_only_project_or_only_contract():
    only_project = generate_script(
        _content(_table(contracts=())), _mapping(),
    )
    assert "AND contract_no" not in only_project
    only_contract = generate_script(
        _content(_table(projects=(), contracts=("C001",))), _mapping(),
    )
    assert "project_code" not in only_contract
    assert "contract_no IN ('C001')" in only_contract


def test_generate_requires_scope_for_update():
    with pytest.raises(ScriptGenerationError) as exc:
        generate_script(_content(_table(projects=(), contracts=())), _mapping())
    assert "请填写项目或合同处理范围" in str(exc.value)


def test_generate_requires_mapping_for_scope():
    with pytest.raises(ScriptGenerationError) as exc:
        generate_script(_content(_table()), {})
    assert "未配置项目定位字段" in str(exc.value)


def test_before_values_participate_in_where():
    script = generate_script(_content(_table()), _mapping())
    assert "SET status = '终止'" in script
    assert "AND status = '正常'" in script


def test_literals_keep_types_and_escape_quotes():
    fields = (
        StructuredField(column_name="amount", chinese_column_name="金额", column_name_source="MANUAL",
                        value_before="100", value_after="120"),
        StructuredField(column_name="remark", chinese_column_name="备注", column_name_source="MANUAL",
                        value_before="it's ok", value_after="done"),
        StructuredField(column_name="deleted", chinese_column_name="删除标记", column_name_source="MANUAL",
                        value_before="false", value_after="true"),
    )
    script = generate_script(_content(_table(fields=fields)), _mapping())
    assert "AND amount = '100'" in script
    assert "amount = '120'" in script
    assert "AND remark = 'it''s ok'" in script
    assert "remark = 'done'" in script


def test_multi_tables_generate_segmented_scripts():
    other = _table(
        table_name="customer_info",
        chinese_table_name="客户信息表",
        projects=("P9",),
        contracts=(),
        fields=(StructuredField(column_name="status", chinese_column_name="状态", column_name_source="MANUAL",
                                value_before="1", value_after="2"),),
    )
    key = ("ds1", "public", "customer_info")
    mappings = {
        ("ds1", "public", "apply_contract_info"): FieldMapping("project_code", "contract_no"),
        key: FieldMapping("project_code", ""),
    }
    script = generate_script(_content(_table(), other), mappings)
    assert script.count("-- 表：") == 2
    assert "UPDATE apply_contract_info" in script
    assert "UPDATE customer_info" in script
    assert "-- 数据源：ds1" in script


def test_generate_rejects_empty_tables():
    content = StructuredContent(datasource_id="", datasource_type="", tables=())
    with pytest.raises(ScriptGenerationError):
        generate_script(content, {})