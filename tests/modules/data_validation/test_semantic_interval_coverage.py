import pytest

from auto_check.modules.data_validation.parallel_checks import parse_numeric_group
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request, _rules_with_doc, _select_payload
from tests.modules.data_validation.test_semantic_generation import FIELDS, draft


@pytest.mark.parametrize(("qualifier", "operators"), [
    ("，含边界", ("lt", "gt")), (",包含两个边界", ("lt", "gt")),
    ("（不含两端）", ("lte", "gte")), ("，不包含两个端点", ("lte", "gte")),
])
def test_documented_interval_endpoint_phrases(qualifier, operators):
    assert parse_numeric_group("压力应在-2到8.5之间" + qualifier) == (
        "any", [("压力", operators[0], -2), ("压力", operators[1], 8.5)])
    assert not parse_numeric_group("压力应在-2至8.5千帕之间" + qualifier)


@pytest.mark.parametrize(("field", "label"), [("p", "压力"), ("t", "温度")])
@pytest.mark.parametrize(("first_complete", "repair_complete"), [(True, False), (False, True), (False, False)])
def test_verified_interval_keeps_both_ends_or_requests_a_bounded_repair(field, label, first_complete, repair_complete):
    def rule(complete):
        candidate = draft(field)
        conditions = [{"left": field, "op": op, "right_type": "value", "right": value}
                      for op, value in (("gt", 17), ("lt", -4))]
        candidate["expression"] = {"logic": "any", "conditions": conditions} if complete else conditions[0]
        candidate["semantic_intent"]["metrics"][0]["term"] = label
        return candidate

    rules, model = _rules_with_doc([{**_select_payload(), "draft": rule(first_complete)}, rule(repair_complete)],
                                   fields=[*FIELDS, (field, label, "numeric", "")])
    result = rules.parse_rule_request(user(), _request(request_text=f"{label}应在-4至17之间，包含两个边界", analysis_protocol=2))
    assert len(model.calls) == (1 if first_complete else 2)
    if first_complete or repair_complete:
        assert result["preview"]["definition"]["expression"] == rule(True)["expression"]
    else:
        assert not result.get("preview") and result["uncertainties"]
