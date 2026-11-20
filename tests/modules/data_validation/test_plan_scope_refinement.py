import pytest

from auto_check.modules.data_validation.documented_choices import ScopeEvidenceRequired, plan_facts, verify_prior_facts


def sensor_facts(*, scope_code=None, filter_code=None):
    fields = [
        {"field_name": "pressure", "data_type": "decimal"},
        {"field_name": "mode", "data_type": "varchar", "dictionary": "01=在线\n02=离线"},
        {"field_name": "zone", "data_type": "varchar", "dictionary": "A=一区\nB=二区"},
    ]
    scopes = []
    if scope_code:
        scopes.append({"category": "检查对象", "fields": ["mode"], "memberships": {"mode": {
            "include": [scope_code], "exclude": [code for code in ("01", "02") if code != scope_code],
        }}})
    filters = [{"field": "zone", "op": "eq", "value": filter_code}] if filter_code else []
    draft = {"rule_type": "field_compare", "semantic_intent": {"scopes": scopes}, "filters": filters,
             "expression": {"left": "pressure", "op": "lt", "right_type": "value", "right": 5}, "null_policy": "skip"}
    return plan_facts(draft, {"id": 1}, None, {1: fields}, None)


@pytest.mark.parametrize("added", [{"scope_code": "01"}, {"filter_code": "A"}])
def test_document_review_can_add_scope_or_filter_missing_from_first_draft(added):
    verify_prior_facts([sensor_facts(**added)], [sensor_facts()])


@pytest.mark.parametrize("changed", [
    {"scope_code": None, "filter_code": "A"},
    {"scope_code": "02", "filter_code": "A"},
    {"scope_code": "01", "filter_code": None},
    {"scope_code": "01", "filter_code": "B"},
])
def test_document_review_preserves_previously_bound_scope_and_filter(changed):
    with pytest.raises(ScopeEvidenceRequired):
        verify_prior_facts([sensor_facts(**changed)], [sensor_facts(scope_code="01", filter_code="A")])
