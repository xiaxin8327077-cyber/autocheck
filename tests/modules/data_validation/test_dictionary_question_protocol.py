import pytest

from auto_check.modules.data_validation.ai_service import model_judgment, pending_judgment_reviews
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.prompt_defaults import RULE_OUTPUT_CONTRACT, SELECT_OUTPUT_CONTRACT


REFERENCE = {"table": "contracts", "field": "contract_type", "category": "标准合同"}
EVIDENCE = {"table": "contracts", "fields": {"contract_type"}, "category": "标准合同"}
OTHER = "账龄按签约日还是生效日？"


@pytest.mark.parametrize("stage,contract", [("select_table", SELECT_OUTPUT_CONTRACT),
                                            ("generate_rule", RULE_OUTPUT_CONTRACT)])
def test_only_confirmed_dictionary_reference_resolves(stage, contract):
    assert "dictionary_questions" in contract and "verified_category_filter" in contract
    other_refs = [{**REFERENCE, key: value} for key, value in (
        ("table", "other_contracts"), ("field", "current_type"), ("category", "其他合同"))]
    payload = {"uncertainties": [OTHER], "dictionary_questions": [REFERENCE, REFERENCE, *other_refs]}
    judgment = model_judgment(payload, stage=stage)
    assert len(judgment["uncertainties"]) == 5
    assert judgment["dictionary_questions"] == [REFERENCE, *other_refs]
    assert pending_judgment_reviews(judgment) == judgment["uncertainties"]
    assert pending_judgment_reviews(judgment, **EVIDENCE) == [OTHER, *judgment["uncertainties"][2:]]
    assert pending_judgment_reviews(judgment, **{**EVIDENCE, "fields": {"contract_type", "current_type"}}) == [
        OTHER, judgment["uncertainties"][2], judgment["uncertainties"][4],
    ]


def test_free_text_remains_independent_even_when_identical_to_rendered_reference():
    judgment = model_judgment({"dictionary_questions": [REFERENCE]}, stage="select_table")
    same_text = judgment["uncertainties"][0]
    model_payload = {"uncertainty": same_text, "dictionary_questions": [REFERENCE]}
    judgment = model_judgment(model_payload, stage="select_table")
    assert pending_judgment_reviews(judgment, **EVIDENCE) == [same_text]
    legacy = model_judgment({"uncertainties": [OTHER]}, stage="generate_rule")
    assert pending_judgment_reviews(legacy, **EVIDENCE) == [OTHER]


@pytest.mark.parametrize("empty", [None, [], {}, "", " "])
def test_empty_optional_questions_do_not_affect_existing_reviews(empty):
    judgment = model_judgment({"uncertainties": [OTHER], "dictionary_questions": empty}, stage="generate_rule")
    assert pending_judgment_reviews(judgment) == [OTHER]


def test_single_object_is_normalized_and_partial_questions_do_not_cancel_valid_bindings():
    assert model_judgment({"dictionary_questions": REFERENCE}, stage="select_table")["dictionary_questions"] == [REFERENCE]
    incomplete = {"field": "missing_table_field", "category": "其他类别"}
    judgment = model_judgment({"uncertainties": [OTHER], "dictionary_questions": [
        REFERENCE, incomplete, "还需确认清算字典", False, {**REFERENCE, "confirmed": True},
    ]}, stage="generate_rule")
    remaining = pending_judgment_reviews(judgment, **EVIDENCE)
    assert OTHER in remaining
    assert any("missing_table_field" in note and "表名" in note for note in remaining)
    assert any("还需确认清算字典" in note for note in remaining)
    assert any("未提供" in note for note in remaining)
    assert any("contracts" in note and "附加" in note for note in remaining)
    assert len(remaining) == len(judgment["uncertainties"]) - 1


@pytest.mark.parametrize("invalid", [[{**REFERENCE, "category": "项" * 2001}], [REFERENCE] * 101])
def test_oversized_dictionary_questions_follow_existing_resource_limits(invalid):
    with pytest.raises(AppError) as exc:
        model_judgment({"dictionary_questions": invalid}, stage="generate_rule")
    assert exc.value.code == "MODEL_RESPONSE_INVALID"
