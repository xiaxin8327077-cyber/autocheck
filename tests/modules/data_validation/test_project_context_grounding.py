"""Regression cases for actual document-role grounding, not beautified UI fixtures."""
from copy import deepcopy

import pytest

from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.project_context import (
    infer_project_context, normalize_project_context, project_code_fields,
    project_row_status, validate_project_context_against_columns,
)


def field(name, caption, data_type="varchar", **extra):
    return {"field_name": name, "field_cn": caption, "data_type": data_type, **extra}


BASE = {"id": 1, "table_name": "contracts", "dimension": "合同", "data_source_name": "source_a"}
DIM = {"id": 2, "table_name": "entities", "dimension": "项目", "data_source_name": "source_a"}
BASE_FIELDS = [field("contract_id", "合同编号"), field("entity_id", "项目编号")]
DIM_FIELDS = [field("entity_id", "项目编号", is_pk="Y"), field("entity_name", "项目名称"),
              field("period", "报送日期", "date", is_pk="Y")]


def infer(fields=None, definition=None, dim_fields=None, tables=None):
    return infer_project_context(definition or {}, BASE, fields if fields is not None else BASE_FIELDS,
                                 tables or [BASE, DIM], {2: dim_fields if dim_fields is not None else DIM_FIELDS,
                                                       3: deepcopy(DIM_FIELDS)})


def test_lineage_mentions_do_not_turn_measures_or_names_into_project_codes():
    fields = [field("balance", "金额", "decimal", logic="按项目编号关联后取得金额"),
              field("entity_name", "项目名称", logic="通过项目编号关联获取名称"),
              field("id_name", "项目ID名称")]
    assert project_code_fields(fields) == []
    result = infer(fields)
    assert result["context"] is None
    assert result["required"] is True  # A real name role still needs its real code.
    assert "项目编号" in result["uncertainties"][0]


def test_non_project_columns_are_not_forced_to_supply_project_identity():
    result = infer([field("metric", "指标值", "decimal", logic="与另表项目编号无关的描述")])
    assert result == {"required": False, "context": None, "questions": [],
                      "project_columns": [], "uncertainties": []}


def test_unambiguous_local_projection_needs_no_redundant_confirmation():
    result = infer(BASE_FIELDS + [field("entity_name", "项目名称")])
    assert result["context"] == {"mode": "base", "code_field": "entity_id",
                                 "name_field": "entity_name", "confirmed": True}
    assert result["questions"] == result["uncertainties"] == []


def test_real_code_and_name_choices_resolve_instead_of_repeating_questions():
    fields = BASE_FIELDS + [field("other_id", "监管项目编号"), field("entity_name", "项目名称"),
                            field("short_name", "项目简称")]
    initial = infer(fields)
    assert {q["id"] for q in initial["questions"]} == {
        "project_context.code_field", "project_context.name_field"}
    chosen = infer(fields, {"project_context": {"mode": "base", "code_field": "other_id",
                                               "name_field": "short_name"}})
    assert chosen["questions"] == []
    assert chosen["context"]["code_field"] == "other_id"
    assert chosen["context"]["name_field"] == "short_name"
    assert chosen["context"]["confirmed"] is True
    with pytest.raises(AppError):
        infer(fields, {"project_context": {"mode": "base", "code_field": "made_up"}})


def test_complete_pk_not_a_subset_is_required_for_unique_lookup():
    extra_pk = DIM_FIELDS + [field("line_id", "合同编号", is_pk="Y")]
    result = infer(dim_fields=extra_pk)
    assert result["context"] is None
    assert result["required"] is True
    assert result["uncertainties"]
    # A global PK remains unique after adding a date predicate.
    global_pk = deepcopy(DIM_FIELDS)
    global_pk[-1]["is_pk"] = "N"
    result = infer(dim_fields=global_pk)
    assert result["context"]["unique_evidence"]["fields"] == ["entity_id"]
    normalize_project_context(result["context"])


def test_lookup_table_selection_and_relationship_confirmation_are_consumed():
    other = {**DIM, "id": 3, "table_name": "other_entities"}
    initial = infer(tables=[BASE, DIM, other])
    question = initial["questions"][0]
    assert question["id"] == "project_context.table_name"
    selection = question["options"][1]["selection"]
    selected = infer(definition={"project_context": selection}, tables=[BASE, DIM, other])
    assert selected["context"]["table_name"] == "other_entities"
    assert selected["context"]["unique_evidence"]["confirmed"] is True
    assert selected["questions"][0]["id"] == "project_context.confirmed"
    confirmed = infer(definition={"project_context": {**selected["context"], "confirmed": True}},
                      tables=[BASE, DIM, other])
    assert confirmed["questions"] == []
    assert confirmed["context"]["confirmed"] is True
    with pytest.raises(AppError):
        infer(definition={"project_context": {**selection, "table_name": "not_authorized"}})


def test_multiple_real_period_dates_produce_mapping_choices_not_first_match():
    fields = deepcopy(DIM_FIELDS)
    fields[-1]["is_pk"] = "N"  # project code is globally unique
    fields.append(field("balance_date", "余额日期", "date"))
    result = infer(dim_fields=fields)
    question = result["questions"][0]
    assert question["id"] == "project_context.mapping"
    assert {o["selection"]["date_field"] for o in question["options"]} == {"period", "balance_date"}
    selection = question["options"][1]["selection"]
    chosen = infer(definition={"project_context": selection}, dim_fields=fields)
    assert chosen["context"]["date_field"] == selection["date_field"]
    assert all(q["id"] != "project_context.mapping" for q in chosen["questions"])


def test_cross_source_lookup_is_not_a_candidate_even_with_same_project_roles():
    result = infer(tables=[BASE, {**DIM, "data_source_name": "source_b"}])
    assert result["context"] is None
    assert result["uncertainties"]


def test_numeric_and_text_project_keys_do_not_implicitly_coerce_and_misidentify():
    context = infer()["context"]
    with pytest.raises(AppError):
        validate_project_context_against_columns(context, {"entity_id": "integer"},
                                                {"entity_id": "varchar", "entity_name": "varchar", "period": "date"})


def test_actual_document_boolean_project_flag_is_not_an_entity_identifier():
    risk_flag = field("risk_flag", "风险项目标识", dictionary="0-否;1-是")
    assert project_code_fields([risk_flag]) == []
    assert project_code_fields([field("real_id", "项目标识", is_pk="Y")])[0]["field_name"] == "real_id"
    assert project_code_fields([field("short_name", "项目ID简称")]) == []


def test_actual_primary_project_key_is_not_replaced_by_secondary_project_reference():
    fields = [field("entity_id", "项目编号/信托产品代码", is_pk="Y"),
              field("entity_name", "项目名全称"),
              field("external_id", "政府投资项目代码"),
              field("risk_flag", "风险项目标识", dictionary="0-否;1-是")]
    result = infer(fields)
    assert result["context"]["code_field"] == "entity_id"
    assert result["questions"] == []
    with pytest.raises(AppError):
        infer(fields, {"project_context": {"mode": "base", "code_field": "external_id", "name_field": "entity_name"}})


@pytest.mark.parametrize("count", [-1, 1.5, float("inf"), float("nan"), True])
def test_invalid_match_count_never_pretends_a_unique_project_name(count):
    assert project_row_status(mode="lookup", code="P1", name="真实名称", match_count=count) == "unmapped"
