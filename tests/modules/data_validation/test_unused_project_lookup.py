from copy import deepcopy
from types import SimpleNamespace

import pytest

from auto_check.modules.data_validation.document_evidence import DocumentEvidence
from auto_check.modules.data_validation.documented_origins import drop_unused_project_lookup
from tests.modules.data_validation.test_project_driver_binding import document_parts


def example(request="项目已结束，但是总额不为17"):
    tables, fields = document_parts()
    project, detail = tables[:2]
    owner_day = next(f for f in fields[2] if f["field_name"] == "day")
    owner_day.update(source_table="mart.project_snapshot", source_field="day", logic="直取")
    exp = {"left": "project_total", "op": "neq", "right_type": "value", "right": 17}
    base = {"project_driver": {"version": 1, "table_role": "base"}, "rule_type": "field_compare",
            "target": {"table":"project_snapshot"}, "expression": exp, "null_policy":"zero",
            "semantic_intent": {"metrics": [{"side":"left", "term":"项目总额", "fields":["project_total"]}],
                "scopes": [{"category":"项目已结束", "fields":["transfer_flag"],
                            "memberships":{"transfer_flag":{"include":["1"],"exclude":["2"]}}}], "open_questions":[]}}
    plan = deepcopy(base)
    plan.update(related_target={"table": "asset_rows"}, join={"table_name": "asset_rows", "report_date_field": "day",
                "on":[{"left":"project_key","right":"owner_ref"}, {"left":"day","right":"day"}], "unmatched_policy":"exclude"})
    evidence = [{"kind":"metrics", "candidates":[{"table":"asset_rows", "table_id":2, "fields":["amount"]}]}]
    analysis = SimpleNamespace(fields=fields, tables=tables, request=request, index=DocumentEvidence(tables, fields, request),
        competing_evidence=evidence, initial_proposal=base,
        resolve=lambda t, category: next(r for r in tables if r["table_name"] == t["table"]))
    return analysis, base, plan


def test_join_added_only_for_metric_review_preserves_single_project_and_resolved_dictionary():
    analysis, original, plan = example()
    original["semantic_intent"]["scopes"][0]["memberships"]["transfer_flag"] = {"include":["已结束"], "exclude":["存续"]}
    expected = deepcopy(plan)
    result = drop_unused_project_lookup(analysis, {"target":original["target"]}, plan)
    assert "join" not in result and result["related_target"] is None
    assert result["expression"] == plan["expression"] and result["semantic_intent"] == plan["semantic_intent"]
    assert expected == plan


@pytest.mark.parametrize("case", ("existence", "named", "extra_predicate", "existing", "other_metric", "filter",
                                  "right_field", "scope", "aggregate", "bad_keys", "no_evidence", "not_proven"))
def test_meaningful_or_unproven_lookup_stays_intact(case):
    request = {"existence":"项目已结束且发生过认购，但是总额不为17", "named":"资产明细中项目已结束，但是总额不为17",
               "extra_predicate":"项目已结束，但是总额不为17，同时开通电子渠道"}.get(case, "项目已结束，但是总额不为17")
    analysis, original, plan = example(request)
    if case == "existing": original["join"] = deepcopy(plan["join"])
    if case == "other_metric": original["expression"]["left"] = "project_received"
    if case == "filter": plan["filters"] = [{"table":"related","field":"amount","op":"gt","value":0}]
    if case == "right_field": plan["expression"].update(right_table="related",right_type="field",right="amount")
    if case == "scope": plan["semantic_intent"]["scopes"][0]["table"] = "related"
    if case == "aggregate": plan["join"]["right_aggregate"] = "sum"
    if case == "bad_keys": plan["join"]["on"][0]["right"] = "row_id"
    if case == "no_evidence": analysis.competing_evidence.clear()
    if case == "not_proven": analysis.fields[1][1]["is_pk"] = ""
    assert drop_unused_project_lookup(analysis, {"target":original["target"]}, plan) is plan
