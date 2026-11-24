from copy import deepcopy

import pytest

from auto_check.modules.data_validation.query_samples import evaluate_case_with_kind
from auto_check.modules.data_validation.project_driver import DRIVER_VERSION
from tests.modules.data_validation.test_ai_service import _request
from tests.modules.data_validation.test_project_driver_binding import DAY, document_tables, make_rules
from tests.modules.data_validation.support import user


def analyze_project_metric(detail_key, model_role="base"):
    project, _, funding, _ = document_tables()
    project_fields = {f["field_name"]: f for f in project["fields"]}
    funding_fields = {f["field_name"]: f for f in funding["fields"]}
    project_fields["transfer_flag"].update(field_cn="项目状态", dictionary="1-存续\n2-终止")
    project_fields["project_received"]["logic"] = "业务别名：项目实收。"
    funding_fields["funding_received"]["logic"] = "业务别名：募集实收。"
    funding_fields["day"].update(source_table="mart.project_snapshot", source_field="day")
    funding_fields["funding_owner"]["field_name"] = detail_key
    model_draft = {
        "rule_name": "存续项目实收非负", "rule_type": "field_compare",
        "business_key": "project_key", "project_driver": {"version": 1, "table_role": model_role},
        "expression": {"left": "project_received", "op": "lt", "right_type": "value", "right": 0},
        "violation_message": "实收小于零", "null_policy": "zero",
        "semantic_intent": {
            "metrics": [{"side": "left", "term": "项目实收", "fields": ["project_received"]}],
            "scopes": [{"table": "base", "category": "存续", "fields": ["transfer_flag"],
                        "memberships": {"transfer_flag": {"include": ["1"], "exclude": ["2"]}}}],
            "open_questions": [],
        },
    }
    reply = {"target": {"table": "project_snapshot"}, "draft": model_draft}
    detail = deepcopy(model_draft)
    detail.update(target={"table": "funding_rows"}, related_target={"table": "project_snapshot"},
                  join={"table_name": "project_snapshot", "on": [{"left": detail_key, "right": "project_key"}],
                        "report_date_field": "day", "unmatched_policy": "exclude", "relationship_confirmed": True})
    detail.pop("project_driver")
    if detail_key != "project_key":
        detail.pop("business_key")
    detail["expression"]["left"] = "funding_received"
    detail["semantic_intent"]["metrics"][0].update(term="募集实收", fields=["funding_received"])
    detail["semantic_intent"]["scopes"][0]["table"] = "related"
    rules, model = make_rules([reply, {"plans": [model_draft, detail]}], tables=[project, funding])
    result = rules.parse_rule_request(user(), _request(request_text="存续项目的实收不得小于0", analysis_protocol=2))
    assert len(model.calls) == (2 if model_role == "base" else 1)
    return result


@pytest.mark.parametrize(("detail_key", "locator"), [("project_key", "project_key"), ("funding_owner", "funding_id")])
def test_documented_second_grain_rebinds_project_driver_and_business_key(detail_key, locator):
    result = analyze_project_metric(detail_key)
    candidates = {o["candidate"]["table_name"]: o["candidate"] for o in result.get("candidate_options", [])}
    assert set(candidates) == {"project_snapshot", "funding_rows"}, result.get("uncertainties")
    for name, role, field, key in [("project_snapshot", "base", "project_received", "project_key"),
                                    ("funding_rows", "related", "funding_received", locator)]:
        definition = candidates[name]["preview"]["definition"]
        assert definition["project_driver"] == {"version": DRIVER_VERSION, "table_role": role}
        assert definition["business_key"] == key
        assert definition["expression"] == {"left": field, "op": "lt", "right_type": "value", "right": 0}
        assert definition["semantic_intent"]["expected_expression"] == definition["expression"]
        assert definition["null_policy"] == "zero"
        assert definition["filters"] == [
            {"table": role, "field": "transfer_flag", "op": "eq", "value": "1", "confirmed": True}]
    detail = candidates["funding_rows"]["preview"]["definition"]
    assert detail["join"]["on"] == [{"left": detail_key, "right": "project_key"}]
    assert 'FROM "project_snapshot" AS p INNER JOIN "funding_rows" AS d' in candidates["funding_rows"]["preview"]["sql_preview"]
    project = {"day": DAY, "project_key": "A", "project_name": "甲", "transfer_flag": "1"}
    row = {"day": DAY, detail_key: "A", "funding_id": "F", "funding_received": None}
    for rows, expected in [([], (0, None)), ([{**row, "day": "2026-10-31"}], (0, None)),
                           ([row], (0, None)), ([{**row, "funding_received": -1}], (1, "numeric"))]:
        assert evaluate_case_with_kind(detail, {"report_date": DAY, "project": project, "details": rows}) == expected


def test_model_declared_wrong_driver_on_original_grain_still_blocks_sql():
    result = analyze_project_metric("project_key", model_role="related")
    assert result["uncertainties"] and not result.get("preview")
    assert all(not o["candidate"].get("preview") for o in result.get("candidate_options", []))
