from copy import deepcopy

import pytest

from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request
from tests.modules.data_validation.test_compared_grain_evidence import KEY, compared_sources
from tests.modules.data_validation.test_supplement_adoption import analyze_suggestion


# Parallel analyses returned these rewrites in two separate model responses.
@pytest.mark.parametrize(("first_title", "final_title"), [
    ("项目实收与募集期末实收份额跨维度差异核对", "项目端4001实收余额与募集端期末实收份额汇总差异核对"),
    ("项目实收信托与募集期末实收份额差异核对", "项目实收信托与募集期末实收份额汇总差异核对"),
])
def test_complete_suggestion_revision_replaces_earlier_advice_live_and_in_cache(first_title, final_title):
    original = advice(first_title, "同一项目、同一期间的汇总一致性", ["确认允许差额"])
    revised = advice(final_title, "同键同日合计，差额非零即异常", [])
    rules, model, request = scenario([original], {"ai_suggestions": [revised]})
    for _ in range(2):
        result = rules.parse_rule_request(user(), request)
        assert [item["title"] for item in result["ai_suggestions"]] == [final_title]
        assert result["ai_suggestions"][0]["adoption"] == {"operations": ["sum"], "preconditions": []}
    assert len(model.calls) == 3
    assert first_title in model.calls[1]["messages"][0]["content"]
    cached = rules.storage.cached_analysis_result(rules._analysis_inputs(user(), request)["context"], request["request_text"])
    assert "ai_suggestions" not in cached["selection"]
    assert [item["title"] for item in cached["draft"]["ai_suggestions"]] == [final_title]


def advice(title, reason, preconditions):
    return {"kind": "aggregate_consistency", "category": "consistency", "operations": ["sum"],
            "title": title, "reason": reason, "preconditions": preconditions, "references": [
                {"table_name": "project_snapshot", "field_name": "project_received"},
                {"table_name": "funding_rows", "field_name": "funding_received"}]}


def scenario(previous, update):
    template, model, request = compared_sources(shared_alias=True, join_keys=[KEY])
    original = deepcopy(model.payloads[0])
    first = {key: value for key, value in original.items() if key != "draft"}
    # The final dedicated review returns the complete, corrected list.
    final = deepcopy(update.get("ai_suggestions", previous))
    model.payloads[:] = [{**first, "ai_suggestions": previous}, {**original["draft"], **update},
                        {"ai_suggestions": final}]
    return template, model, request


def test_full_revision_preserves_independent_proposals_with_the_same_operation_and_fields():
    pending = advice("核实订单合计", "按期间确认差额口径", [])
    current = advice("已结算订单合计", "仅已结算订单，零容差", [])
    other = advice("待结算订单合计", "仅待结算订单，容差为五个单位", [])
    rules, model, request = scenario([pending], {"ai_suggestions": [current, other]})
    result = rules.parse_rule_request(user(), request)
    assert [s["title"] for s in result["ai_suggestions"]] == [current["title"], other["title"]]
    assert len(model.calls) == 3


@pytest.mark.parametrize(("update", "retained"), [({}, True), ({"ai_suggestions": []}, False)])
def test_omitted_list_retains_previous_advice_but_explicit_empty_clears_it(update, retained):
    previous = advice("核实同日合计", "比较原始金额", [])
    rules, model, request = scenario([previous], update)
    result = rules.parse_rule_request(user(), request)
    assert [s["title"] for s in result["ai_suggestions"]] == ([previous["title"]] if retained else [])
    assert len(model.calls) == (3 if retained else 2)


@pytest.mark.parametrize("cleared", [False, True])
def test_cached_final_list_overrides_earlier_plan_advice(cleared):
    rules, _ = analyze_suggestion()
    request = _request(request_text="存续项目的实收不得小于0", analysis_protocol=2)
    context = rules._analysis_inputs(user(), request)["context"]
    cached = rules.storage.cached_analysis_result(context, request["request_text"])
    assert len(cached["draft"]["plans"]) == 2
    stale = advice("先前范围", "待复核", [])
    final = advice("最终范围", "同日已核实", [])
    cached["draft"]["plans"][0]["ai_suggestions"] = [stale]
    cached["draft"]["ai_suggestions"] = [] if cleared else [final]
    rules.storage.remember_analysis_result(context, request["request_text"], cached)
    # An explicit empty list allows the existing documented supplement stage to run.
    rules.model.payloads.append({"ai_suggestions": []})
    result = rules.parse_rule_request(user(), request)
    assert [s["title"] for s in result["ai_suggestions"]] == ([] if cleared else ["最终范围"])
