"""structured_content 解析、派生与字段级必填校验测试。"""

from __future__ import annotations

import pytest

from auto_check.modules.report_special_processing.structured_content import (
    StructuredContentError,
    derive_field_name,
    derive_table_name,
    derive_value_after,
    derive_value_before,
    parse_structured_content,
    structured_from_json,
    validate_formal_values,
)


def _content(**updates):
    payload = {
        "datasource_id": "ds1",
        "datasource_type": "postgresql",
        "tables": [{
            "schema": "public",
            "table_name": "t_customer",
            "chinese_table_name": "客户信息表",
            "table_name_source": "DATABASE",
            "fields": [
                {"column_name": "customer_status", "chinese_column_name": "客户状态",
                 "column_name_source": "DATABASE", "value_before": "正常", "value_after": "冻结"},
                {"column_name": "customer_type", "chinese_column_name": "客户类型",
                 "column_name_source": "MANUAL", "value_before": "A", "value_after": "B"},
            ],
        }],
    }
    payload.update(updates)
    return payload


def test_parse_and_derive_strings():
    content = parse_structured_content(_content())
    assert derive_table_name(content) == "客户信息表｜t_customer"
    assert derive_field_name(content) == "客户状态｜customer_status；客户类型｜customer_type"
    assert derive_value_before(content) == "正常\nA"
    assert derive_value_after(content) == "冻结\nB"
    json_text = content.to_json()
    assert "customer_status" in json_text
    assert structured_from_json(json_text).datasource_id == "ds1"


def test_parse_preserves_stable_item_ids_for_semantic_audit_matching():
    payload = _content()
    payload["tables"][0]["item_id"] = "table-audit-1"
    payload["tables"][0]["conditions"] = [{
        "item_id": "condition-audit-1",
        "column_name": "customer_id",
        "chinese_column_name": "客户编号",
        "operator": "=",
        "values": ["C001"],
    }]
    payload["tables"][0]["fields"][0]["item_id"] = "field-audit-1"

    content = parse_structured_content(payload)
    serialized = content.to_dict()

    assert serialized["tables"][0]["item_id"] == "table-audit-1"
    assert serialized["tables"][0]["conditions"][0]["item_id"] == "condition-audit-1"
    assert serialized["tables"][0]["conditions"][0]["chinese_column_name"] == "客户编号"
    assert serialized["tables"][0]["fields"][0]["item_id"] == "field-audit-1"


def test_parse_rejects_invalid_stable_item_id():
    payload = _content()
    payload["tables"][0]["item_id"] = "bad id with spaces"

    with pytest.raises(StructuredContentError) as exc:
        parse_structured_content(payload)

    assert exc.value.fields["structured_content"] == "内部条目标识无效"


def test_derive_none_for_legacy():
    assert derive_table_name(None) is None
    assert derive_field_name(None) is None
    assert derive_value_before(None) is None


def test_parse_rejects_invalid_payloads():
    with pytest.raises(StructuredContentError) as exc:
        parse_structured_content({**_content(), "datasource_id": ""})
    assert "datasource_id" in exc.value.fields
    with pytest.raises(StructuredContentError) as exc:
        parse_structured_content({**_content(), "datasource_type": "oracle"})
    assert "datasource_id" in exc.value.fields
    with pytest.raises(StructuredContentError) as exc:
        parse_structured_content({**_content(), "tables": []})
    assert "table_name" in exc.value.fields
    # 物理名必须是真实标识符，不允许手工拼双语串
    with pytest.raises(StructuredContentError):
        parse_structured_content({**_content(), "tables": [
            {**_content()["tables"][0], "table_name": "中文名｜t_customer"},
        ]})
    # 表内字段不能为空
    with pytest.raises(StructuredContentError) as exc:
        parse_structured_content({**_content(), "tables": [
            {**_content()["tables"][0], "fields": []},
        ]})
    assert "field_name" in exc.value.fields
    # 同表字段不能重复
    with pytest.raises(StructuredContentError):
        parse_structured_content({**_content(), "tables": [
            {**_content()["tables"][0], "fields": [
                _content()["tables"][0]["fields"][0],
                _content()["tables"][0]["fields"][0],
            ]},
        ]})


def test_parse_requires_manual_chinese_names():
    bad = _content()
    bad["tables"][0]["chinese_table_name"] = ""
    bad["tables"][0]["table_name_source"] = "MANUAL"
    with pytest.raises(StructuredContentError) as exc:
        parse_structured_content(bad)
    assert "table_name" in exc.value.fields


def test_parse_table_and_field_limits():
    many_tables = {**_content(), "tables": [
        {**_content()["tables"][0], "table_name": f"t_{i}"} for i in range(6)
    ]}
    with pytest.raises(StructuredContentError) as exc:
        parse_structured_content(many_tables)
    assert "table_name" in exc.value.fields
    many_fields = {**_content(), "tables": [{
        **_content()["tables"][0],
        "fields": [
            {**_content()["tables"][0]["fields"][0], "column_name": f"c_{i}"}
            for i in range(6)
        ],
    }]}
    with pytest.raises(StructuredContentError) as exc:
        parse_structured_content(many_fields)
    assert "field_name" in exc.value.fields


def test_validate_formal_values_reports_field_labels():
    content = parse_structured_content({**_content(), "tables": [{
        **_content()["tables"][0],
        "fields": [{
            "column_name": "customer_status", "chinese_column_name": "客户状态",
            "column_name_source": "DATABASE", "value_before": "", "value_after": "冻结",
        }],
    }]})
    with pytest.raises(StructuredContentError) as exc:
        validate_formal_values(content)
    assert exc.value.fields["value_before"] == "客户状态：请输入修改前内容"
    assert "value_after" not in exc.value.fields


def test_structured_from_json_tolerates_bad_data():
    assert structured_from_json(None) is None
    assert structured_from_json("not-json") is None
    assert structured_from_json('{"datasource_id": ""}') is None
