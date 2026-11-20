from copy import deepcopy

from tests.modules.data_validation.test_ai_latency_pipeline import combined, run
from tests.modules.data_validation.test_ai_service import _rules_with_doc
from tests.modules.data_validation.test_semantic_generation import FIELDS, draft


def test_full_document_review_does_not_require_an_exclusion_report_for_every_search_hit():
    fields = [(name, "本期测量值" if name == "balance" else cn, kind, pk) for name, cn, kind, pk in FIELDS]
    fields += [("opening_reading", "期初测量值", "numeric", "")]
    first = draft("balance")
    first["semantic_intent"]["metrics"][0]["term"] = "测量值"
    selected = deepcopy(first)
    selected["semantic_intent"]["metrics"][0]["term"] = "本期测量值"
    rules, model = _rules_with_doc([{**combined(first), "expand_evidence": True}, selected], fields=fields)

    result = run(rules, "本期测量值低于19要核实")

    assert result["preview"] and not result["questions"]
    assert len(model.calls) == 2
    assert "opening_reading" in model.calls[1]["messages"][0]["content"]


def test_model_can_preserve_a_real_field_choice_after_document_review():
    first = draft("balance")
    first["semantic_intent"]["metrics"][0]["term"] = "余额"
    reviewed = deepcopy(first)
    reviewed["semantic_intent"]["metrics"][0]["fields"] = ["balance", "opening_balance"]
    rules, model = _rules_with_doc([{**combined(first), "expand_evidence": True}, reviewed],
                                 fields=[*FIELDS, ("opening_balance", "期初余额", "numeric", "")])
    result = run(rules, "余额低于19要核实")
    assert not result["preview"]
    assert {o["value"] for o in result["questions"][0]["options"]} == {"balance", "opening_balance"}
    assert len(model.calls) == 2
