from copy import deepcopy

import pytest

from tests.modules.data_validation.test_ai_suggestions import _build, _candidate


REQUEST = "参与配送的经营数量，不得大于19"


def candidate():
    definition = _candidate(expression={"left": "qty", "op": "gt", "right_type": "value", "right": 19},
                            filters=[{"table": "base", "field": "name", "op": "eq", "value": "参与", "confirmed": True}])
    return {**definition, "preview": {"definition": deepcopy(definition), "sql_preview": "SELECT 1"}}


def advice(**changes):
    return {"category": "coverage_gap", "kind": "field_compare_binary", "title": "参与配送的经营数量不得大于19",
            "reason": "核查已确定对象", "preconditions": [], "limitations": [], "references": [
                {"table_name": "ops_daily", "field_name": "qty"},
                {"table_name": "ops_daily", "field_name": "name"}], **changes}


def test_literal_copy_of_current_request_and_its_previewed_fields_is_not_an_independent_suggestion():
    assert _build([advice()], candidates=[candidate()], request_text=REQUEST, model_only=True) == []


@pytest.mark.parametrize("mutation", ["other_field", "different_condition", "different_case", "period", "unreviewed", "quoted"])
def test_distinct_or_unverified_proposals_are_not_removed_by_literal_request_deduplication(mutation):
    main = candidate()
    proposal = advice()
    request = REQUEST
    if mutation == "other_field":
        proposal["references"] = [{"table_name": "ops_detail", "field_name": "qty_total"}]
    elif mutation == "different_condition":
        proposal["title"] = "参与配送的经营数量不得小于19"
    elif mutation == "different_case":
        request += " ABC"
        proposal["title"] += " abc"
    elif mutation == "period":
        proposal["category"] = "period"
    elif mutation == "unreviewed":
        main.pop("preview")
    else:
        request = '名称不得包含“A,B”'
        proposal["title"] = '名称不得包含“AB”'
    assert len(_build([proposal], candidates=[main], request_text=request, model_only=True)) == 1
