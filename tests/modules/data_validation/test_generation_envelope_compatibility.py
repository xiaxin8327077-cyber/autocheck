import pytest

from auto_check.modules.data_validation.contracts import AppError
from tests.modules.data_validation.test_ai_latency_pipeline import combined, run
from tests.modules.data_validation.test_ai_service import _rules_with_doc, _select_payload
from tests.modules.data_validation.test_semantic_generation import FIELDS, draft


def test_generation_accepts_the_same_unambiguous_envelope_as_selection():
    rules, model = _rules_with_doc([_select_payload(), combined(draft())], fields=FIELDS)
    result = run(rules, "份额低于19要核实")
    assert result["preview"] and result["expression"]["right"] == 19
    assert len(model.calls) == 2


def test_generation_does_not_merge_conflicting_inner_and_outer_targets():
    reply = combined(draft())
    reply["draft"]["target"] = {"table": "not_the_selected_table"}
    rules, _ = _rules_with_doc([_select_payload(), reply], fields=FIELDS)
    with pytest.raises(AppError, match="MODEL_RESPONSE_INVALID"):
        run(rules, "份额低于19要核实")
