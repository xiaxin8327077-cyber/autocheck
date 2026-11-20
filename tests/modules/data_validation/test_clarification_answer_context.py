import pytest

from auto_check.modules.data_validation.contracts import AppError
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_latency_pipeline import combined
from tests.modules.data_validation.test_ai_service import _request, _rules_with_doc
from tests.modules.data_validation.test_semantic_generation import FIELDS, draft


ANSWER = {"question_id": "supplement.0", "context": "指标核对", "question": "还要检查其他口径吗？", "answer": "没有"}


def test_answers_bind_to_the_original_request_and_partition_model_result_reuse():
    rules, model = _rules_with_doc([combined(draft()), combined(draft()), combined(draft())], fields=FIELDS)
    payload = _request(analysis_protocol=2, request_text="份额低于19要复核", reasoning_enabled=True)
    results = []
    for answers in ([], [ANSWER], [{**ANSWER, "answer": "另行检查"}], [ANSWER]):
        result = rules.parse_rule_request(user(), {**payload, "clarification_answers": answers})
        assert result["clarification_answers"] == answers and result["description"] == payload["request_text"]
        results.append(result)
    assert len(model.calls) == 3
    assert len({r["analysis_context"] for r in results}) == 3 and results[-1]["analysis_reused"]
    assert ANSWER["question"] in model.calls[1]["messages"][0]["content"]
    assert '"answer":"没有"' in model.calls[1]["messages"][0]["content"]
    assert "本次需求原文" in model.calls[1]["messages"][0]["content"]


def test_preview_can_use_owned_snapshot_answers_and_rejects_a_different_answer(monkeypatch):
    rules, _ = _rules_with_doc([combined(draft())], fields=FIELDS)
    request = _request(analysis_protocol=2, request_text="份额低于19要复核", clarification_answers=[ANSWER])
    original = rules.parse_rule_request(user(), request)
    monkeypatch.setattr(rules.analyses, "completed_result", lambda *_: original)
    payload = {"definition": original, "analysis_id": "completed", "analysis_context": original["analysis_context"],
               "model_id": request["model_id"], "analysis_request_text": request["request_text"]}
    assert rules.preview_candidate(user(), payload, return_questions=True)["sql_preview"]
    with pytest.raises(AppError, match="ANALYSIS_CONTEXT_CHANGED"):
        rules.preview_candidate(user(), {**payload, "clarification_answers": []}, return_questions=True)
    with pytest.raises(AppError, match="ANALYSIS_CONTEXT_CHANGED"):
        rules.preview_candidate(user(), {**payload, "analysis_request_text": "核查另一指标"}, return_questions=True)


def test_revisions_inherit_answers_only_for_the_same_source_request_and_owner(monkeypatch):
    rules, _ = _rules_with_doc([combined(draft())], fields=FIELDS)
    request = _request(analysis_protocol=2, request_text="份额低于19要复核")
    start = rules.start_analysis(user(), {**request, "clarification_answers": [ANSWER]})
    rules.analyses.join()
    payload = {**request, "revision_of": start["analysis_id"]}
    assert rules._analysis_inputs(user(), payload)["clarification_answers"] == [ANSWER]
    assert rules._analysis_inputs(user("other"), payload)["clarification_answers"] == []
    assert rules._analysis_inputs(user(), {**payload, "request_text": "份额低于20要复核"})["clarification_answers"] == []
    assert rules._analysis_inputs(user(), {**payload, "clarification_answers": []})["clarification_answers"] == []
    previous = rules.analyses.completed_result(user(), start["analysis_id"])
    monkeypatch.setattr(rules.analyses, "completed_result", lambda *_: {**previous, "source_id": "different"})
    assert rules._analysis_inputs(user(), payload)["clarification_answers"] == []


@pytest.mark.parametrize("answers", [None, "没有", [{"question": "还要吗？", "answer": False}]])
def test_invalid_answer_shape_is_rejected_before_any_model_call(answers):
    rules, model = _rules_with_doc([], fields=FIELDS)
    with pytest.raises(AppError, match="VALIDATION_ERROR"):
        rules._analysis_inputs(user(), _request(analysis_protocol=2, clarification_answers=answers))
    assert not model.calls
