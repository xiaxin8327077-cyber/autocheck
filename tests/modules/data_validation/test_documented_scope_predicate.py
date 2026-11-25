from copy import deepcopy

import pytest
from sqlalchemy import update

from auto_check.modules.data_validation.semantic_generation import _normalize_documented_operands
from auto_check.modules.data_validation.storage import DOC_FIELDS
from tests.modules.data_validation.test_ai_latency_pipeline import combined, run
from tests.modules.data_validation.test_ai_service import _rules_with_doc
from tests.modules.data_validation.test_semantic_generation import FIELDS, draft


DOC = [{"field_name": "state", "field_cn": "设备状态", "data_type": "varchar",
        "dictionary": "01-室内运行\n02-室外运行\n03-停用"},
       {"field_name": "temp", "field_cn": "温度", "data_type": "numeric"}]


def repeated_scope(codes=("01", "02")):
    candidate = draft("temp")
    candidate["null_policy"] = "violate"
    candidate["expression"] = {"logic": "all", "conditions": [
        {"left": "state", "op": "in" if len(codes) > 1 else "eq", "right_type": "value",
         "right": list(reversed(codes)) if len(codes) > 1 else codes[0]},
        {"left": "temp", "op": "is_null"}]}
    candidate["semantic_intent"].update(
        metrics=[{"side": "left", "condition_index": i, "term": term, "fields": [name]}
                 for i, (term, name) in enumerate([("设备状态", "state"), ("温度", "temp")])],
        scopes=[{"category": "运行中", "fields": ["state"],
                 "memberships": {"state": {"include": list(codes), "exclude": [v for v in ("01", "02", "03") if v not in codes]}}}])
    return candidate


@pytest.mark.parametrize("codes", [("01",), ("01", "02")])
def test_verified_scope_moves_out_of_the_violation_before_evidence_discovery(codes):
    first = repeated_scope(codes)
    copy = deepcopy(first)
    rules, model = _rules_with_doc([combined(first)], fields=[*FIELDS, ("state", "设备状态", "varchar", ""),
                                                        ("temp", "温度", "numeric", "")])
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "state").values(dictionary=DOC[0]["dictionary"]))
    result = run(rules, "运行中的设备温度不能为空")
    assert result["preview"] and len(model.calls) == 1
    rule = result["preview"]["definition"]
    assert rule["expression"] == {"left": "temp", "op": "is_null"}
    assert [m["fields"] for m in rule["semantic_intent"]["metrics"]] == [["temp"]]
    assert rule["filters"] == [{"table": "base", "field": "state", "op": "eq" if len(codes) == 1 else "in",
                                "value": codes[0] if len(codes) == 1 else list(codes), "confirmed": True}]
    assert first == copy


def test_retained_compound_metrics_keep_their_order_and_choices():
    first = repeated_scope()
    first["expression"]["conditions"] += [{"left": "limit", "op": "is_null"}]
    first["semantic_intent"]["metrics"] += [{"side": "left", "term": "上限", "fields": ["limit", "cap"], "condition_index": 2}]
    first["semantic_intent"]["open_questions"] = ["阈值的单位是否已换算？"]
    extra = [{"field_name": name, "field_cn": name, "data_type": "numeric"} for name in ("limit", "cap")]
    result = _normalize_documented_operands(deepcopy(first), [*DOC, *extra], [])
    assert result["expression"] == {"logic": "all", "conditions": first["expression"]["conditions"][1:]}
    assert [(m["condition_index"], m["fields"]) for m in result["semantic_intent"]["metrics"]] == [
        (0, ["temp"]), (1, ["limit", "cap"])]
    assert result["semantic_intent"]["open_questions"] == first["semantic_intent"]["open_questions"]


@pytest.mark.parametrize("repaired", [True, False])
def test_confirmed_scope_that_makes_a_null_check_impossible_requires_a_repair(repaired):
    first = repeated_scope(("01",))
    first["expression"] = {"left": "state", "op": "is_null"}
    first["semantic_intent"]["metrics"] = [{"side": "left", "term": "设备状态", "fields": ["state"]}]
    corrected = deepcopy(first)
    corrected["expression"]["left"] = "device_type"
    corrected["semantic_intent"]["metrics"] = [{"side": "left", "term": "设备类别", "fields": ["device_type"]}]
    rules, model = _rules_with_doc([combined(first), combined(first), corrected if repaired else first], fields=[
        *FIELDS, ("state", "设备状态", "varchar", ""), ("device_type", "设备类别", "varchar", "")])
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "state").values(dictionary=DOC[0]["dictionary"]))
    result = run(rules, "运行中设备的类别不能为空")
    if repaired:
        assert result["preview"]["definition"]["expression"] == corrected["expression"]
    else:
        assert not result.get("preview") and result["uncertainties"]
    assert any("同一字段" in call["messages"][0]["content"] and "不可能" in call["messages"][0]["content"]
               for call in model.calls[1:])


@pytest.mark.parametrize("case", [
    "any", "different_code", "duplicate_condition", "duplicate_code", "condition_extra", "scope_extra", "group_extra",
    "metric_extra", "ambiguous_metric", "related_scope", "multiple_scopes", "multiple_fields", "incomplete_codes",
    "explicit_filter", "only_scope", "unknown_measure", "invalid_index", "duplicate_metric",
])
def test_unproved_or_ambiguous_repetitions_are_untouched(case):
    first = repeated_scope()
    expr = first["expression"]
    condition, measure = expr["conditions"]
    intent = first["semantic_intent"]
    scope = intent["scopes"][0]
    metric = intent["metrics"][0]
    if case == "any": expr["logic"] = "any"
    if case == "different_code": condition["right"] = ["01", "03"]
    if case == "duplicate_condition": expr["conditions"].insert(1, deepcopy(condition))
    if case == "duplicate_code": condition["right"].append("01")
    if case == "condition_extra": condition["table"] = "base"
    if case == "scope_extra": scope["unless"] = "temp"
    if case == "group_extra": expr["unless"] = "temp"
    if case == "metric_extra": metric["unless"] = "temp"
    if case == "ambiguous_metric": metric["fields"].append("temp")
    if case == "related_scope": scope["table"] = "related"
    if case == "multiple_scopes": intent["scopes"].append(deepcopy(scope))
    if case == "multiple_fields": scope["fields"].append("temp")
    if case == "incomplete_codes": scope["memberships"]["state"]["exclude"] = []
    if case == "explicit_filter": first["filters"] = [{"field": "temp", "op": "gt", "value": 0}]
    if case == "only_scope": expr["conditions"] = [condition]
    if case == "unknown_measure": measure["left"] = "unknown"
    if case == "invalid_index": intent["metrics"][1]["condition_index"] = 3
    if case == "duplicate_metric": intent["metrics"].append(deepcopy(metric))
    expected = deepcopy(first)
    if case == "only_scope":
        # A singleton AND is equivalent to its condition. It must not disappear
        # just because that condition also describes a documented scope.
        expected["expression"] = deepcopy(condition)
    assert _normalize_documented_operands(deepcopy(first), DOC, DOC) == expected
