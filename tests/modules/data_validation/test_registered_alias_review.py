import pytest

from auto_check.modules.data_validation.document_evidence import DocumentEvidence
from tests.modules.data_validation.test_ai_latency_pipeline import combined, run
from tests.modules.data_validation.test_document_evidence_anchor_regressions import field
from tests.modules.data_validation.test_documented_ambiguity_fast_review import set_field, warehouse, warehouse_draft


def deposit_candidates(request, *, same_alias_peer=False):
    tables = [{"id": 1, "table_name": "ledgers"}, {"id": 2, "table_name": "contracts"}]
    fields = {
        1: [field("total_paid", "本期归集额", "业务别名：账簿缴存金额。")],
        2: [field("paid_units", "交付份数", "业务别名：合同缴存份额。"),
            field("fee", "服务费", "业务别名：项目服务金额。"),
            field("index_value", "收益指数", "业务别名：收益指数。定义：按缴存金额折算。")],
    }
    if same_alias_peer:
        tables.append({"id": 3, "table_name": "payments"})
        fields[3] = [field("settled", "结算额", "业务别名：支付缴存金额。")]
    evidence = DocumentEvidence(tables, fields, request)
    return evidence.competing_fields(tables[0], ["total_paid"], "缴存金额", tables, across_tables=True)


def test_partial_registered_alias_is_only_a_model_review_candidate():
    groups = deposit_candidates("项目的缴存金额应大于零")
    assert [(g["table"], g["fields"]) for g in groups] == [
        ("ledgers", ["total_paid"]), ("contracts", ["paid_units"])]
    assert groups[1]["requires_model_review"]


def test_explicit_physical_field_does_not_reopen_a_partial_alias():
    groups = deposit_candidates("项目的缴存金额字段 total_paid 应大于零")
    assert [(g["table"], g["fields"]) for g in groups] == [("ledgers", ["total_paid"])]


def test_a_stronger_peer_keeps_precedence_and_does_not_hide_a_second_available_dimension():
    groups = deposit_candidates("项目的缴存金额应大于零", same_alias_peer=True)
    assert [(g["table"], bool(g.get("requires_model_review"))) for g in groups] == [
        ("ledgers", False), ("payments", False), ("contracts", True)]


@pytest.mark.parametrize("peer_alias", ["合同缴存份额", "历史缴存金额折算份额"])
def test_model_can_keep_only_the_requested_unit_after_reviewing_a_related_alias(peer_alias):
    first = warehouse_draft()
    first["semantic_intent"]["metrics"][0]["term"] = "缴存金额"
    rules, model = warehouse([combined(first), first])
    set_field(rules, "balance", field_cn="本期缴存金额", logic="业务别名：账簿缴存金额。单位：元。")
    set_field(rules, "volume", logic=f"业务别名：{peer_alias}。单位：份。仅记录交付份数。")

    result = run(rules, "在途且优先级高于3的缴存金额应大于0")

    assert len(model.calls) == 2
    assert "仅记录交付份数" in model.calls[1]["messages"][0]["content"]
    assert result["table_name"] == "test_table" and result["expression"] == first["expression"]
    assert not result.get("candidate_options")
