from auto_check.modules.data_validation.document_evidence import DocumentEvidence
import pytest

from tests.modules.data_validation.test_ai_latency_pipeline import combined, run
from tests.modules.data_validation.test_ai_service import _rules_with_doc
from tests.modules.data_validation.test_document_evidence_anchor_regressions import field
from tests.modules.data_validation.test_documented_ambiguity_fast_review import set_field
from tests.modules.data_validation.test_followup_service_bridge import _add_table
from tests.modules.data_validation.test_semantic_generation import FIELDS, draft


def readings(request, *, duplicate=False, selected="reading", term="累计采集量"):
    tables = [{"id": 1, "table_name": "meters", "table_name_cn": "仪表读数（meters.ktr）"},
              {"id": 2, "table_name": "daily", "table_name_cn": "分户日报"}]
    fields = {1: [field("reading", "累计采集量"), field("opening", "期初累计采集量")],
              2: [field("other", "累计采集量" if duplicate else "期末累计采集量")]}
    index = DocumentEvidence(tables, fields, request)
    groups = index.competing_fields(tables[0], [selected], term, tables, across_tables=True)
    return {name for group in groups for name in group["fields"]}


def test_unique_exact_document_label_excludes_unrequested_periods_across_tables():
    assert readings("累计采集量应大于0") == {"reading"}
    assert readings("仪表读数表的累计采集量应大于0", duplicate=True) == {"reading"}


def test_same_label_in_two_tables_still_has_two_possible_owners():
    assert {"reading", "other"} <= readings("累计采集量应大于0", duplicate=True)


@pytest.mark.parametrize(("subject", "expected"), [
    ("采购", {"purchase_rows"}), ("", {"purchase_rows", "lease_rows"}),
    ("采购和租赁", {"purchase_rows", "lease_rows"}),
])
def test_same_date_label_honors_business_entity_named_in_the_table_caption(subject, expected):
    tables = [{"id": 1, "table_name": "purchase_rows", "table_name_cn": "采购及其他订单明细表", "dimension": "项目＋订单"},
              {"id": 2, "table_name": "lease_rows", "table_name_cn": "租赁明细表", "dimension": "项目＋协议＋序号"}]
    fields = {i: [{"field_name": "expires", "field_cn": "合同到期日", "data_type": "date",
                   "source_field": "end_day"}] for i in (1, 2)}
    index = DocumentEvidence(tables, fields, f"{subject}合同到期日不应晚于预计日期")
    hits = index.competing_fields(tables[0], ["expires"], "合同到期日", tables, across_tables=True)
    assert {hit["table"] for hit in hits} == expected


def test_a_label_inside_an_explicitly_longer_field_name_is_not_a_separate_binding():
    assert "opening" in readings("期初累计采集量应大于0")


def test_bare_measure_without_an_exact_column_still_has_document_alternatives():
    assert {"reading", "opening", "other"} == readings("采集量不得为空", term="采集量")


@pytest.mark.parametrize("peer_alias", ["校准值", "探头读数"])
def test_model_options_respect_exclusive_and_shared_documented_names(peer_alias):
    candidate = draft("amount")
    candidate["semantic_intent"]["metrics"][0].update(term="探头读数", fields=["amount", "balance"])
    rules, _ = _rules_with_doc([combined(candidate), candidate], fields=FIELDS)
    set_field(rules, "amount", logic="业务别名：探头读数。")
    set_field(rules, "balance", logic=f"业务别名：{peer_alias}。")
    result = run(rules, "探头读数低于19时提醒")
    if peer_alias == "探头读数":
        assert {o["value"] for o in result["questions"][0]["options"]} == {"amount", "balance"}
    else:
        assert result["preview"] and not result["questions"]
        assert result["semantic_intent"]["metrics"][0]["fields"] == ["amount"]


@pytest.mark.parametrize(("request_text", "shared_alias", "expected"), [
    ("设备的投用日期不能晚于退役日期", False, {"start", "other_start"}),
    ("设备投用日期不能为空", False, {"start", "other_start"}),
    ("设备的投用日期不能晚于租约的投用日期", False, {"start", "other_start", "lease_start"}),
    ("投用日期不能晚于退役日期", False, {"start", "workflow", "lease_start"}),
    ("设备的投用日期不能晚于退役日期", True, {"start", "other_start", "lease_start"}),
])
def test_cross_table_date_fragments_need_evidence_of_the_requested_entity(request_text, shared_alias, expected):
    tables = [{"id": 1, "table_name": "machines", "dimension": "设备"},
              {"id": 2, "table_name": "leases", "dimension": "租约"}]
    alias = "业务别名：登记启用日期。" if shared_alias else ""
    fields = {1: [{"field_name": "start", "field_cn": "机具启用日期", "source_field_cn": "设备投用日期",
                   "data_type": "date", "logic": alias},
                  {"field_name": "other_start", "field_cn": "机具启用日期_原始", "source_field_cn": "设备投用日期", "data_type": "date"},
                  {"field_name": "workflow", "field_cn": "维护流程投用日期", "data_type": "date"}],
              2: [{"field_name": "lease_start", "field_cn": "租约合同投用日期", "data_type": "date", "logic": alias}]}
    index = DocumentEvidence(tables, fields, request_text)
    groups = index.competing_fields(tables[0], ["start"], "投用日期", tables, across_tables=True)
    assert {n for g in groups for n in g["fields"]} == expected
    assert any("租约合同投用日期" in str(v) for v in index.describe(tables[1]).values())


def test_right_operand_stays_in_its_declared_table_when_another_entity_has_the_same_date():
    candidate = draft("actual")
    candidate["expression"] = {"left": "actual", "op": "gt", "right_type": "field", "right": "due"}
    candidate["semantic_intent"]["metrics"] = [{"side": "left", "term": "检定日期", "fields": ["actual"]},
                                             {"side": "right", "term": "到期日期", "fields": ["due"]}]
    rules, model = _rules_with_doc([combined(candidate), candidate], fields=[
        ("row_id", "记录编号", "varchar", "Y"), ("business_day", "数据日期", "date", ""),
        ("actual", "检定日期", "date", ""), ("due", "到期日期", "date", "")])
    _add_table(rules, name="leases", cn="租约台账", dimension="租约", fields=[("end", "到期日期", "date", "")])
    result = run(rules, "检定日期不得晚于到期日期")
    assert result["preview"] and result["expression"] == candidate["expression"]
    assert len(model.calls) == 1
