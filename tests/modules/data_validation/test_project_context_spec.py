import pytest

from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.project_context import (
    infer_project_context,
    normalize_project_context,
    project_output_columns,
    project_row_status,
    project_semantics_required,
)
from auto_check.modules.data_validation.query_spec import (
    is_new_spec,
    query_ready,
    validate_query_spec,
)


def _field(name, cn, data_type="varchar", **extra):
    return {"field_name": name, "field_cn": cn, "data_type": data_type, **extra}


BASE_FIELDS = [
    _field("contract_no", "合同编号"),
    _field("project_code", "项目编号"),
    _field("amount", "金额", "decimal"),
    _field("report_date", "报送日期", "date"),
]
BASE_WITH_NAME = BASE_FIELDS + [_field("project_name", "项目名称")]
DIM_FIELDS = [
    _field("project_code", "项目编号", is_pk="Y"),
    _field("project_name", "项目名称"),
    _field("report_date", "报送日期", "date", is_pk="Y"),
]


def _definition(**overrides):
    definition = {
        "rule_type": "field_compare",
        "table_name": "contract",
        "business_key": "contract_no",
        "report_date_field": "report_date",
        "expression": {"left": "amount", "op": "gt", "right_type": "value", "right": 0},
        "null_policy": "skip",
        "equality_policy": "allow_equal",
    }
    definition.update(overrides)
    return definition


def test_normalize_base_and_lookup_strict_shapes():
    base = normalize_project_context({
        "mode": "base", "code_field": "project_code", "name_field": "project_name",
    })
    assert base["confirmed"] is False
    assert project_output_columns(base) == ["project_code", "project_name", "project_name_status"]
    lookup = normalize_project_context({
        "mode": "lookup", "code_field": "project_code", "name_field": "project_name",
        "table_name": "dim_project", "key": {"left": "project_code", "right": "project_code"},
        "date_field": "report_date",
        "unique_evidence": {"kind": "pk", "fields": ["project_code", "report_date"], "confirmed": True},
        "confirmed": True,
    })
    assert lookup["unique_evidence"]["confirmed"] is True
    with pytest.raises(AppError):
        normalize_project_context({"mode": "lookup", "code_field": "a", "name_field": "b", "table_name": "t",
                                   "key": {"left": "a", "right": "c"}, "unique_evidence": {"kind": "pk", "fields": []}})
    with pytest.raises(AppError):
        normalize_project_context({"mode": "lookup", "code_field": "a", "name_field": "b", "table_name": "t",
                                   "key": {"left": "a", "right": "c"}, "date_field": "d",
                                   "unique_evidence": {"kind": "pk", "fields": ["c", "d", "contract_id"], "confirmed": True}})


def test_infer_prefers_base_fields_from_documented_chinese_evidence():
    result = infer_project_context(_definition(), None, BASE_WITH_NAME, [], {})
    assert result["required"] is True
    assert result["context"]["mode"] == "base"
    assert result["context"]["code_field"] == "project_code"
    assert result["context"]["name_field"] == "project_name"


def test_infer_does_not_guess_from_physical_names_alone():
    fields = [_field("project_code", "编号"), _field("project_name", "名称")]
    result = infer_project_context(_definition(name="项目金额检查"), None, fields, [], {})
    assert result["context"] is None
    assert "缺少项目编号和项目名称的字段说明" in result["uncertainties"][0]
    assert "文档快照" in result["uncertainties"][0]


def test_infer_lookup_only_with_unique_document_evidence_and_real_options():
    dim_table = {"id": 7, "table_name": "dim_project", "table_name_cn": "项目维度表", "dimension": "项目"}
    result = infer_project_context(
        _definition(), {"id": 1, "table_name": "contract"}, BASE_FIELDS,
        [{"id": 1, "table_name": "contract"}, dim_table], {7: DIM_FIELDS},
    )
    assert result["context"]["mode"] == "lookup"
    assert result["context"]["table_name"] == "dim_project"
    assert result["context"]["unique_evidence"]["kind"] == "pk"
    assert [field["field_name"] for field in result["project_columns"]] == ["project_code", "project_name", "report_date"]

    other = {"id": 8, "table_name": "dim_project_2", "table_name_cn": "项目维度表2", "dimension": "项目"}
    multi = infer_project_context(
        _definition(), {"id": 1, "table_name": "contract"}, BASE_FIELDS,
        [{"id": 1}, dim_table, other], {7: DIM_FIELDS, 8: DIM_FIELDS},
    )
    assert multi["context"] is None
    assert multi["questions"][0]["id"] == "project_context.table_name"
    assert {option["value"] for option in multi["questions"][0]["options"]} == {"dim_project", "dim_project_2"}

    no_dim = infer_project_context(
        _definition(), {"id": 1, "table_name": "contract"}, BASE_FIELDS,
        [{"id": 1}], {},
    )
    assert no_dim["context"] is None
    assert "缺少项目名称字段" in no_dim["uncertainties"][0]
    assert "按项目编号唯一对应" in no_dim["uncertainties"][0]


def test_query_ready_and_new_spec_gate_context_confirmation():
    definition = _definition(project_context={
        "mode": "base", "code_field": "project_code", "name_field": "project_name",
        "confirmed": False,
    })
    assert is_new_spec(definition) is True
    assert query_ready(definition) is False
    definition["project_context"]["confirmed"] = True
    assert query_ready(definition) is True


def test_two_table_limit_rejects_third_table_and_allows_same_physical_reuse():
    context = {
        "mode": "lookup", "code_field": "project_code", "name_field": "project_name",
        "table_name": "other_dim", "key": {"left": "project_code", "right": "code"},
        "date_field": "report_date",
        "unique_evidence": {"kind": "pk", "fields": ["code", "report_date"], "confirmed": True},
        "confirmed": True,
    }
    with pytest.raises(AppError):
        validate_query_spec(_definition(project_context=context, join={
            "table_name": "detail", "on": [{"left": "project_code", "right": "project_code"}],
            "report_date_field": "report_date", "unmatched_policy": "exclude",
            "relationship_confirmed": True,
        }))
    reused = validate_query_spec(_definition(project_context={**context, "table_name": "detail",
                                                             "key": {"left": "project_code", "right": "project_code"},
                                                             "unique_evidence": {"kind": "pk",
                                                                                 "fields": ["project_code", "report_date"],
                                                                                 "confirmed": True}},
                                   join={"table_name": "detail",
                                          "on": [{"left": "project_code", "right": "project_code"}],
                                          "report_date_field": "report_date", "unmatched_policy": "exclude",
                                          "relationship_confirmed": True}))
    assert reused["project_context"]["table_name"] == "detail"


def test_row_status_mapping_is_never_fabricated():
    assert project_row_status(mode="base", code="P1", name="项目") == "ok"
    assert project_row_status(mode="base", code=None, name="项目") == "missing_code"
    assert project_row_status(mode="base", code="P1", name=None) == "missing_null"
    assert project_row_status(mode="lookup", code="P1", name="项目", match_count=1) == "ok"
    assert project_row_status(mode="lookup", code="P1", name=None, match_count=0) == "missing_reference"
    assert project_row_status(mode="lookup", code="P1", name=None, match_count=3) == "duplicate"
    assert project_semantics_required({"name": "项目开始日校验"}, None) is True


def test_preview_whitelists_validates_and_hashes_project_context():
    from auto_check.modules.data_validation.candidate_preview import preview_definition

    columns = [
        {"column_name": "contract_no", "comment": "合同编号", "data_type": "varchar"},
        {"column_name": "project_code", "comment": "项目编号", "data_type": "varchar"},
        {"column_name": "project_name", "comment": "项目名称", "data_type": "varchar"},
        {"column_name": "amount", "comment": "金额", "data_type": "decimal"},
        {"column_name": "report_date", "comment": "报送日期", "data_type": "date"},
    ]
    definition = _definition(dialect="mysql", project_context={
        "mode": "base", "code_field": "project_code", "name_field": "project_name", "confirmed": True,
    })
    preview = preview_definition(definition, columns)
    assert "t.`project_code` AS `项目编号`" in preview["sql_preview"]
    assert "t.`project_name` AS `项目名称`" in preview["sql_preview"]
    without = preview_definition(_definition(dialect="mysql"), columns)
    assert preview["content_sha256"] != without["content_sha256"]

    dim_columns = [
        {"column_name": "project_code", "comment": "项目编号", "data_type": "varchar"},
        {"column_name": "project_name", "comment": "项目名称", "data_type": "varchar"},
        {"column_name": "report_date", "comment": "报送日期", "data_type": "date"},
    ]
    lookup = _definition(dialect="mysql", expression={"left": "amount", "op": "gt", "right_type": "value", "right": 0},
                         project_context={
                             "mode": "lookup", "code_field": "project_code", "name_field": "project_name",
                             "table_name": "dim_project", "key": {"left": "project_code", "right": "project_code"},
                             "date_field": "report_date",
                             "unique_evidence": {"kind": "pk", "fields": ["project_code", "report_date"], "confirmed": True},
                             "confirmed": False,
                         })
    with pytest.raises(AppError):
        preview_definition(lookup, columns)
    preview = preview_definition(lookup, columns, project_columns=dim_columns)
    assert "COUNT(*) = 1 THEN MAX(p.`project_name`)" in preview["sql_preview"]
    result = preview
    assert result["project_columns"][0]["column_name"] == "project_code"
    # confirmed=false：允许编译预览，但合成用例必须全部 not_run。
    from auto_check.modules.data_validation.candidate_preview import run_preview_cases
    evidence = run_preview_cases(preview)
    assert evidence["not_run_count"] == len(evidence["cases"]) and evidence["failed_count"] == 0
