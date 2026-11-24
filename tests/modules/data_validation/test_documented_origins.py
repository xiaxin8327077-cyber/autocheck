from copy import deepcopy
from types import SimpleNamespace

import pytest

from auto_check.modules.data_validation.document_evidence import DocumentEvidence
from auto_check.modules.data_validation.documented_origins import prefer_document_origin


def fixture(request="产品期末得分不能包含%或‰"):
    def field(name, label, dtype, *, key="", source=None):
        row = {"field_name": name, "field_cn": label, "data_type": dtype, "is_pk": key}
        if source:
            row.update(logic="直取", source_table="mart.products\nreport.products_YYYY_MM", source_field=f"{source}\n{source}")
        return row
    owner = {"id": 1, "table_name": "products", "table_name_cn": "产品快照", "dimension": "产品", "data_source_name": "test"}
    detail = {"id": 2, "table_name": "purchases", "table_name_cn": "申购明细表", "dimension": "产品＋合同", "data_source_name": "test"}
    tables = [owner, detail]
    fields = {1: [field("product_key", "产品编号", "varchar", key="Y"), field("day", "数据日期", "date"),
                  field("score", "产品当前得分", "numeric"), field("class", "产品分类", "varchar")],
              2: [field("contract", "合同号", "varchar", key="Y"), field("owner", "产品编号", "varchar", key="Y", source="product_key"),
                  field("rdate", "数据日期", "date", source="day"), field("copy", "期末得分", "numeric", source="score")]}
    analysis = SimpleNamespace(index=DocumentEvidence(tables, fields, request), fields=fields,
                               resolve=lambda target, category: next(t for t in tables if t["table_name"] == target["table"]))
    selection = {"target": {"table": "purchases"}, "related_target": {"table": "products"}}
    plan = {"rule_type": "field_compare", "rule_name": "得分检查", "null_policy": "skip", "business_key": "contract",
            "project_driver": {"version": 1, "table_role": "related"},
            "expression": {"left": "copy", "op": "contains_any", "right_type": "value", "right": ["%", "‰"]},
            "semantic_intent": {"metrics": [{"side": "left", "term": "期末得分", "fields": ["copy"]}],
                                "scopes": [], "open_questions": []},
            "join": {"table_name": "products", "on": [{"left": "owner", "right": "product_key"}, {"left": "rdate", "right": "day"}],
                     "report_date_field": "day", "relationship_confirmed": True, "unmatched_policy": "exclude"}}
    return analysis, selection, plan


@pytest.mark.parametrize("with_join", [False, True])
def test_single_copy_predicate_keeps_literals_and_document_scope_on_origin(with_join):
    analysis, selection, plan = fixture()
    if with_join:
        plan["filters"] = [{"table": "related", "field": "class", "op": "eq", "value": "02"}]
        plan["semantic_intent"]["scopes"] = [{"category": "专业", "table": "related", "fields": ["class"],
                                              "memberships": {"class": {"include": ["02"], "exclude": ["1"]}}}]
    else:
        plan.pop("join")
        selection.pop("related_target")
    original = deepcopy(plan)
    result = prefer_document_origin(analysis, selection, plan)
    assert result["target"] == {"table": "products"} and result["related_target"] is None
    assert result["expression"] == {**original["expression"], "left": "score"} and result["null_policy"] == "skip"
    assert result["semantic_intent"]["metrics"][0]["fields"] == ["score"]
    assert not {"business_key", "join", "project_driver"}.intersection(result) and plan == original
    if with_join:
        assert result["filters"] == [{**original["filters"][0], "table": "base"}]
        assert result["semantic_intent"]["scopes"] == [{**original["semantic_intent"]["scopes"][0], "table": "base"}]


@pytest.mark.parametrize("predicate", [{"op": "is_null"}, {"op": "lt", "right_type": "value", "right": 7.5}])
def test_unary_and_threshold_keep_their_operators_and_literals(predicate):
    analysis, selection, plan = fixture("产品本期得分校验")
    plan["expression"] = {"left": "copy", **predicate}
    result = prefer_document_origin(analysis, selection, plan)
    assert result["expression"] == {"left": "score", **predicate}


@pytest.mark.parametrize("case", ["named", "named_side", "physical", "scope", "filter", "formula", "aggregate", "bad_key", "mixed_source", "alternatives"])
def test_independent_detail_requirements_or_unproven_origin_keep_entire_plan(case):
    request = {"named": "申购明细的期末得分不能包含%", "named_side": "申购端的期末得分不能包含%",
               "physical": "purchases.copy不能包含%"}.get(case, "期末得分不能包含%")
    analysis, selection, plan = fixture(request)
    if case == "scope":
        plan["semantic_intent"]["scopes"] = [{"category": "合同", "fields": ["contract"]}]
    if case == "filter":
        plan["filters"] = [{"field": "contract", "op": "eq", "value": "X"}]
    if case == "formula":
        plan["expression"].update(right_type="formula", right={"op": "+", "left": {"field": "copy"}, "right": {"value": 1}})
    if case == "aggregate":
        plan["join"]["right_aggregate"] = "sum"
    if case == "bad_key":
        plan["join"]["on"][0]["left"] = "contract"
    if case == "mixed_source":
        analysis.fields[2][-1]["source_field"] = "score\nother"
    if case == "alternatives":
        plan["semantic_intent"]["metrics"][0]["fields"].append("another_independent_measure")
    assert prefer_document_origin(analysis, selection, plan) is plan
