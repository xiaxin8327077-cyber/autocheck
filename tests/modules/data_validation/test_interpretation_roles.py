from copy import deepcopy
from types import SimpleNamespace

import pytest

from auto_check.modules.data_validation.document_evidence import DocumentEvidence
from auto_check.modules.data_validation.interpretation_roles import defer_period_metric_choices, deferred_period_fields


TABLES = [{"id": 1, "table_name": "loads", "table_name_cn": "装载记录", "dimension": "货物"}]
FIELDS = {1: [{"field_name": n, "field_cn": label, "data_type": "numeric"} for n, label in
              [("mass", "当前载荷"), ("previous_mass", "期初累计载荷"), ("first_mass", "投运设备首批载荷")]]}
SELECTION = {"target": {"table": "loads"}}


def fixture(request="货物的载荷不能为空"):
    advice = {"category":"period", "kind":"field_compare_unary", "title":"检查投运设备首批载荷",
              "reason":"只对刚投入使用的设备适用", "references":[{"table_name":"loads","field_name":"first_mass"}]}
    model = SimpleNamespace(fields=FIELDS, tables=TABLES, request=request, index=DocumentEvidence(TABLES, FIELDS, request),
                            model_suggestions=[advice], confirmed_checks=[], resolve=lambda target, category: TABLES[0])
    plan = {"rule_type":"field_compare", "expression":{"left":"mass","op":"is_null"},
            "semantic_intent":{"metrics":[{"term":"载荷","side":"left","fields":["mass","previous_mass","first_mass"],
                       "recommended":"first_mass","rule_names":{"mass":"a","previous_mass":"b","first_mass":"c"}}],
                               "scopes":[], "open_questions":[]}}
    return model, plan, advice


def test_only_adoptable_single_field_period_advice_removes_unselected_metric_option():
    model, raw, _ = fixture()
    original = deepcopy(raw)
    assert deferred_period_fields(model, SELECTION, raw) == {(1, "first_mass")}
    result = defer_period_metric_choices(model, SELECTION, raw)
    assert result["expression"] == raw["expression"] and original == raw
    assert result["semantic_intent"]["metrics"] == [{"term":"载荷","side":"left","fields":["mass","previous_mass"],
                                                    "rule_names":{"mass":"a","previous_mass":"b"}}]


@pytest.mark.parametrize("reason", ["consistency", "multiple", "unknown_field", "unknown_table", "no_title", "informational",
                                    "actual_operand", "formula_operand", "other_plan", "owner_selection", "confirmed",
                                    "physical", "full_name", "qualified_short_name"])
def test_unverified_informational_chosen_or_explicit_fields_stay_available(reason):
    requests = {"physical":"FIRST_MASS不能为空", "full_name":"投运设备首批载荷不能为空", "qualified_short_name":"首批载荷不能为空"}
    model, raw, advice = fixture(requests.get(reason, "货物的载荷不能为空"))
    choices = []
    if reason == "consistency": advice["category"] = "consistency"
    if reason == "multiple": advice["references"].append({"table_name":"loads","field_name":"mass"})
    if reason == "unknown_field": advice["references"][0]["field_name"] = "ghost"
    if reason == "unknown_table": advice["references"][0]["table_name"] = "untrusted"
    if reason == "no_title": advice.update(title="", reason="")
    if reason == "informational": advice["kind"] = "review"
    if reason == "actual_operand": raw["expression"].update(op="lt", right_type="field", right="first_mass")
    if reason == "formula_operand": raw["expression"].update(op="lt",right_type="formula",right={"op":"+","left":{"field":"first_mass"},"right":{"value":3}})
    if reason == "other_plan": raw = {"plans":[raw, {**raw,"expression":{"op":"is_null","left":"first_mass"}}]}
    if reason == "owner_selection": choices = [{"selection":"first_mass","binding":{"kind":"metrics","owner":"loads"}}]
    if reason == "confirmed": model.confirmed_checks = [{"kind":"metrics","table_id":1,"field":"first_mass"}]
    assert not deferred_period_fields(model, SELECTION, raw, choices)
    assert defer_period_metric_choices(model, SELECTION, raw, choices) is raw


def test_cached_suggestions_and_display_limit_use_the_same_order_as_materialization():
    model, raw, advice = fixture()
    model.model_suggestions = []
    raw["ai_suggestions"] = [advice]
    assert deferred_period_fields(model, SELECTION, raw) == {(1, "first_mass")}
    model.model_suggestions = [{**advice, "category": "integrity", "title": f"载荷检查 {i}"} for i in range(10)]
    assert not deferred_period_fields(model, SELECTION, raw)


def test_document_classification_resolves_repeated_table_name_like_visible_suggestions():
    model, raw, _ = fixture()
    model.tables = [*TABLES, {**TABLES[0], "id": 2}]
    model.fields = {**FIELDS, 2: FIELDS[1]}
    model.categories = [{"code": "stock"}]
    model.service = SimpleNamespace(_category_tables=lambda tables, codes, categories: [TABLES[0]] if codes == {"stock"} else [])
    assert deferred_period_fields(model, {**SELECTION, "report_category": "stock"}, raw) == {(1, "first_mass")}
    assert not deferred_period_fields(model, SELECTION, raw)


@pytest.mark.parametrize("mutation", ["metrics", "role"])
def test_malformed_other_bindings_are_left_for_the_regular_validator(mutation):
    model, raw, _ = fixture()
    if mutation == "metrics":
        raw["semantic_intent"]["metrics"] = None
    else:
        raw["expression"]["right_table"] = []
        raw["semantic_intent"]["metrics"][0]["side"] = "right"
    assert defer_period_metric_choices(model, SELECTION, raw) is raw
