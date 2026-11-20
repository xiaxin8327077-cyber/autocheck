from copy import deepcopy

from tests.modules.data_validation.test_ai_latency_pipeline import combined, run
from tests.modules.data_validation.test_ai_service import _rules_with_doc
from tests.modules.data_validation.test_semantic_generation import draft


def test_document_review_can_correct_an_unconfirmed_date_comparison():
    first = draft("start_day")
    first.update(null_policy="skip", equality_policy="allow_equal")
    first["expression"] = {"left": "start_day", "op": "lt", "right_type": "field", "right": "end_day"}
    first["semantic_intent"]["metrics"] = [
        {"side": "left", "term": "起始日期", "fields": ["start_day"]},
        {"side": "right", "term": "预计结束日期", "fields": ["end_day"]},
    ]
    corrected = deepcopy(first)
    corrected["expression"]["op"] = "gt"
    rules, model = _rules_with_doc([{**combined(first), "expand_evidence": True}, corrected], fields=[
        ("row_id", "记录编号", "varchar", "Y"), ("business_day", "数据日期", "date", ""),
        ("start_day", "起始日期", "date", ""), ("end_day", "预计结束日期", "date", ""),
    ])
    result = run(rules, "起始日期不得大于预计结束日期")
    assert result["expression"]["op"] == "gt"
    assert result["preview"] and not result["questions"]
    assert len(model.calls) == 2
