from copy import deepcopy
from math import prod

import pytest

from auto_check.modules.data_validation.documented_choices import choice_identity
from auto_check.modules.data_validation.semantic_grounding import semantic_coverage_issue
from auto_check.modules.data_validation.storage import DOC_FIELDS
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request, _rules_with_doc


PEERS = ["start_value", "end_value", "mean_value"]
FIELDS = [("code", "记录编号", "varchar", "Y"), ("day", "数据日期", "date", ""),
          *[(key, prefix + "读数", "numeric", "") for key, prefix in zip(PEERS, ("起点", "终点", "平均"))],
          ("form", "分组方式", "varchar", ""), ("orig", "登记分组方式", "varchar", "")]
BOUNDS = [{"left": PEERS[0], "op": op, "right_type": "value", "right": value}
          for op, value in [("gt", 19), ("lt", 2)]]


def analyze(conditions, request, metrics):
    expr = {"logic": "any", "conditions": conditions}
    scope = {"category": "常规", "fields": ["form", "orig"],
             "memberships": {key: {"include": ["1"], "exclude": ["2"]} for key in ("form", "orig")}}
    reply = {"target": {"table": "test_table"}, "draft": {
        "rule_type": "field_compare", "business_key": "code", "rule_name": "读数核查",
        "violation_message": "读数需复核", "null_policy": "skip", "expression": expr,
        "semantic_intent": {"metrics": metrics, "scopes": [scope], "open_questions": []}}}
    service, _ = _rules_with_doc([deepcopy(reply) for _ in range(4)], fields=FIELDS)
    with service.storage.database.begin() as conn:
        conn.execute(DOC_FIELDS.update().where(DOC_FIELDS.c.field_name.in_(["form", "orig"])).values(
            dictionary="1-常规\n2-其他"))
    result = service.parse_rule_request(user(), _request(request_text=request, analysis_protocol=2))
    table, = service.storage.doc_tables(service.storage.active_document()["id"])
    return result, service.storage.doc_fields(table["id"])


@pytest.mark.parametrize("unary", [True, False])
def test_a_generic_measure_and_two_populations_give_six_independent_definitions(unary):
    rows = [{"left": n, "op": "is_null"} for n in PEERS] if unary else BOUNDS
    metrics = [{"term": "读数", "side": "left", "fields": PEERS, "condition_index": index}
               for index in range(1 if unary else len(rows))]
    request = "常规项目，读数不能是空的吧" if unary else "常规项目的读数不得大于19或小于2。"
    result, fields = analyze(rows, request, metrics)
    questions = result["questions"]
    assert prod(len(q["options"]) for q in questions) == 6
    metric, scope = questions
    assert set(o["value"] for o in metric["options"]) == set(PEERS)
    assert metric.get("targets", [metric["id"]]) == (
        ["expression.left"] if unary else ["expression.conditions.0.left", "expression.conditions.1.left"])
    for name in PEERS:
        receipt = choice_identity(result, metric.get("targets", [metric["id"]]), name)
        assert receipt["indices"] == ([0] if unary else [0, 1])
        for opt in scope["options"]:
            expr = {"left": name, "op": "is_null"} if unary else {
                "logic": "any", "conditions": [{**bound, "left": name} for bound in BOUNDS]}
            definition = {**result, "expression": expr, "filters": [opt["selection"]]}
            assert not semantic_coverage_issue(definition, result["semantic_intent"], fields, [])
            if not unary:
                expr["conditions"][1]["left"] = next(n for n in PEERS if n != name)
                assert semantic_coverage_issue(definition, result["semantic_intent"], fields, [])


def test_fields_explicitly_named_together_stay_separate_in_a_compound_check():
    rows = [{"left": n, "op": "is_null"} for n in PEERS]
    metrics = [{"term": label, "side": "left", "fields": [n], "condition_index": i}
               for i, (n, label, _, _) in enumerate(FIELDS[2:5])]
    result, _ = analyze(rows, "常规项目的起点读数、终点读数和平均读数均不能为空。", metrics)
    assert result["expression"] == {"logic": "any", "conditions": rows}


@pytest.mark.parametrize(("term", "count"), [("读数", 3), ("起点读数", 1)])
def test_specific_model_label_cannot_narrow_a_generic_range_metric(term, count):
    metrics = [{"term": "起点读数", "side": "left", "fields": [PEERS[0]], "condition_index": index}
               for index in range(len(BOUNDS))]
    result, _ = analyze(BOUNDS, f"常规项目的{term}不得大于19或小于2。", metrics)
    assert prod(len(q["options"]) for q in result["questions"]) == count * 2
    if count > 1:
        question = next(q for q in result["questions"] if q["id"].startswith("expression."))
        assert [o["value"] for o in question["options"]] == PEERS
        assert question["targets"] == ["expression.conditions.0.left", "expression.conditions.1.left"]


def test_all_measures_requested_are_not_turned_into_a_single_unary_expression():
    rows = [{"left": n, "op": "is_null"} for n in PEERS]
    metrics = [{"term": "读数", "side": "left", "fields": PEERS, "condition_index": i}
               for i in range(len(rows))]
    result, _ = analyze(rows, "常规项目的所有读数均不能为空。", metrics)
    assert result["expression"] == {"logic": "any", "conditions": rows}

@pytest.mark.parametrize("request_text", [
    "常规项目分别检查每种读数，有一个为空就报错。", "常规项目的读数逐项检查，出现空值就报错。",
    "常规项目的读数只要有一个为空就报错。", "常规项目的所有读数均不能为空。"])
def test_explicit_each_measure_keeps_its_own_documented_column_without_substitution(request_text):
    rows = [{"left": n, "op": "is_null"} for n in PEERS]
    metrics = [{"term": "读数", "side": "left", "fields": PEERS, "condition_index": i}
               for i in range(len(rows))]
    result, fields = analyze(rows, request_text, metrics)
    assert result["expression"] == {"logic": "any", "conditions": rows}
    assert [q["id"] for q in result["questions"]] == ["filters.0"]
    assert [m["fields"] for m in result["semantic_intent"]["metrics"]] == [[n] for n in PEERS]
    definition = {**result, "filters": [result["questions"][0]["options"][0]["selection"]],
                  "expression": {"logic":"any","conditions":[rows[0]] * len(rows)}}
    assert semantic_coverage_issue(definition, result["semantic_intent"], fields, [])
