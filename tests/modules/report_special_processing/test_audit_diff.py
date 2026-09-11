from __future__ import annotations

from auto_check.modules.report_special_processing.audit_diff import build_structured_audit_diff


def _field(item_id: str, column: str, before: str = "1", after: str = "2") -> dict:
    return {
        "item_id": item_id,
        "column_name": column,
        "chinese_column_name": {"jrname": "法人金融机构名称", "datejg": "数据管理机构"}.get(column, ""),
        "column_name_source": "DATABASE",
        "value_before": before,
        "value_after": after,
    }


def _condition(item_id: str, column: str, operator: str = "=", values=None) -> dict:
    return {
        "item_id": item_id,
        "column_name": column,
        "operator": operator,
        "values": list(values or ["江苏信托"]),
    }


def _table(item_id: str, name: str, *, datasource: str = "ass_man_reg", conditions=None, fields=None) -> dict:
    return {
        "item_id": item_id,
        "datasource_id": datasource,
        "datasource_name": datasource,
        "datasource_type": "postgresql",
        "schema": "public",
        "table_name": name,
        "chinese_table_name": f"{name}中文名",
        "table_name_source": "DATABASE",
        "limit_report_period": True,
        "report_period_field": "datedate",
        "report_period_field_source": "AUTO",
        "conditions": list(conditions or []),
        "fields": list(fields or []),
    }


def _content(*tables: dict) -> dict:
    return {"datasource_id": "ass_man_reg", "datasource_type": "postgresql", "tables": list(tables)}


def test_builds_modified_condition_and_field_changes_inside_one_table():
    old = _content(_table(
        "table-1", "alarm_hand_count",
        conditions=[_condition("condition-1", "jrname")],
        fields=[_field("field-1", "datejg", "10", "20")],
    ))
    new = _content(_table(
        "table-1", "alarm_hand_count",
        conditions=[_condition("condition-1", "jrname", "IN", ["江苏信托", "33"])],
        fields=[_field("field-1", "datejg", "10", "t")],
    ))

    result = build_structured_audit_diff(old, new)

    assert result["change_count"] == 3
    assert result["affected_tables"] == 1
    table = result["tables"][0]
    assert table["change"] == "modified"
    assert table["change_count"] == 3
    assert [item["key"] for item in table["conditions"][0]["changes"]] == ["operator", "values"]
    assert table["fields"][0]["changes"] == [{
        "key": "value_after", "old": "20", "new": "t",
    }]


def test_adds_and_removes_tables_as_single_business_changes_with_snapshots():
    kept = _table("table-1", "alarm_hand_count", fields=[_field("field-1", "datejg")])
    removed = _table("table-2", "table_b", fields=[_field("field-2", "jrname")])
    added = _table("table-3", "table_a", datasource="reg-report-analysis", fields=[_field("field-3", "datejg")])

    result = build_structured_audit_diff(_content(kept, removed), _content(kept, added))

    assert result["change_count"] == 2
    assert result["added_tables"] == 1
    assert result["removed_tables"] == 1
    assert [item["change"] for item in result["tables"]] == ["added", "removed"]
    assert result["tables"][0]["after"]["table_name"] == "table_a"
    assert result["tables"][1]["before"]["table_name"] == "table_b"


def test_table_switch_with_same_item_id_is_table_information_change():
    old = _content(_table("table-1", "alarm_hand_count", fields=[_field("field-1", "datejg")]))
    new = _content(_table("table-1", "alarm_hand_count_2026", fields=[_field("field-1", "datejg")]))

    result = build_structured_audit_diff(old, new)

    assert result["modified_tables"] == 1
    assert result["change_count"] == 2
    assert result["tables"][0]["table_info"] == [
        {"key": "table_name", "old": "alarm_hand_count", "new": "alarm_hand_count_2026"},
        {"key": "chinese_table_name", "old": "alarm_hand_count中文名", "new": "alarm_hand_count_2026中文名"},
    ]


def test_condition_and_field_add_remove_are_semantic_events():
    old = _content(_table(
        "table-1", "alarm_hand_count",
        conditions=[_condition("condition-1", "datedate", values=["2026-08-31"])],
        fields=[_field("field-1", "datejg")],
    ))
    new = _content(_table(
        "table-1", "alarm_hand_count",
        conditions=[_condition("condition-2", "jrname", "IN", ["江苏信托", "33"])],
        fields=[_field("field-2", "jrname")],
    ))

    result = build_structured_audit_diff(old, new)
    table = result["tables"][0]

    assert result["change_count"] == 4
    assert [item["change"] for item in table["conditions"]] == ["added", "removed"]
    assert [item["change"] for item in table["fields"]] == ["added", "removed"]


def test_legacy_objects_match_by_physical_identity_and_ignore_in_value_order():
    old_table = _table("", "alarm_hand_count", conditions=[_condition("", "jrname", "IN", ["A", "B"])], fields=[_field("", "datejg")])
    new_table = _table("table-new", "alarm_hand_count", conditions=[_condition("condition-new", "jrname", "IN", ["B", "A"])], fields=[_field("field-new", "datejg")])

    assert build_structured_audit_diff(_content(old_table), _content(new_table)) is None


def test_different_present_ids_are_not_misread_as_modification():
    old = _content(_table("table-old", "same_table", fields=[_field("field-old", "datejg")]))
    new = _content(_table("table-new", "same_table", fields=[_field("field-new", "datejg")]))

    result = build_structured_audit_diff(old, new)

    assert result["change_count"] == 2
    assert [item["change"] for item in result["tables"]] == ["added", "removed"]


def test_returns_none_for_missing_or_unchanged_structured_content():
    table = _table("table-1", "alarm_hand_count", fields=[_field("field-1", "datejg")])

    assert build_structured_audit_diff(None, None) is None
    assert build_structured_audit_diff(_content(table), _content(table)) is None
