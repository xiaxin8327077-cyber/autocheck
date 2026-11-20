from copy import deepcopy

import pytest

from tests.modules.data_validation.test_ai_latency_pipeline import combined, run
from tests.modules.data_validation.test_ai_service import _rules_with_doc
from tests.modules.data_validation.test_documented_ambiguity_fast_review import set_field
from tests.modules.data_validation.test_semantic_generation import FIELDS, draft
from auto_check.modules.data_validation.document_evidence import DocumentEvidence
from auto_check.modules.data_validation.semantic_generation import SemanticAnalysis
from types import SimpleNamespace


@pytest.mark.parametrize(("first_label", "request_text", "choices"), [
    ("设备模式", "分段运行的份额不得大于余额", {"mode", "recorded"}),
    ("设备模式", "按原始设备模式选取分段运行的记录，份额不得大于余额", {"recorded"}),
    ("包装类别", "按原始设备模式选取分段运行的记录，份额不得大于余额", {"recorded"}),
])
def test_reviewed_category_uses_documented_peer_choices_or_explicit_field(first_label, request_text, choices):
    first = draft("amount")
    first["expression"] = {"left": "amount", "op": "gt", "right_type": "field", "right": "balance"}
    first["semantic_intent"]["metrics"] = [
        {"side": "left", "term": "份额", "fields": ["amount"]},
        {"side": "right", "term": "余额", "fields": ["balance"]}]
    membership = {"include": ["3"], "exclude": ["8"]}
    first["semantic_intent"]["scopes"] = [
        {"category": "分段运行", "fields": ["mode"], "memberships": {"mode": membership}}]
    reviewed = deepcopy(first)
    reviewed["semantic_intent"]["scopes"][0].update(fields=["recorded"], memberships={"recorded": membership})
    rules, _ = _rules_with_doc([{**combined(first), "expand_evidence": True}, reviewed], fields=[
        *FIELDS, ("mode", first_label, "varchar", ""), ("recorded", "设备模式_原始", "varchar", "")])
    for name in ("mode", "recorded"):
        set_field(rules, name, dictionary="3-分段运行\n8-连续运行")
    result = run(rules, request_text)
    if len(choices) == 1:
        assert result["preview"] and result["filters"][0]["field"] == "recorded"
    else:
        question, = result["questions"]
        assert {o["selection"]["field"] for o in question["options"]} == choices


@pytest.mark.parametrize(("request_text", "term", "other", "required"), [
    ("巡检的读数需要复核", "巡检", "非巡检", True),
    ("巡检的读数需要复核", "巡检", "巡检", False),
    ("非巡检的读数需要复核", "巡检", "非巡检", False),
    ("巡检设备的读数需要复核", "巡检", "非巡检", False),
    ("是否巡检需要确认", "是", "其他", False),
])
def test_request_scope_requires_an_exact_unique_dictionary_label(request_text, term, other, required):
    table = {"id": 1, "table_name": "meters"}
    fields = {1: [{"field_name": "work", "field_cn": "作业类别", "data_type": "varchar",
                   "dictionary": f"4-{term}\n5-维护"},
                  {"field_name": "inspection", "field_cn": "登记类别", "dictionary": f"X-{other}\nY-日常"}]}
    index = DocumentEvidence([table], fields, request_text)
    analysis = SimpleNamespace(index=index, fields=fields, request=request_text)
    check = {"kind": "scopes", "first_seen": True, "table_id": 1, "field": "work", "term": term}
    assert SemanticAnalysis.required_interpretation(analysis, check) is required
