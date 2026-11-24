import pytest

from auto_check.modules.data_validation.document_evidence import DocumentEvidence
from tests.modules.data_validation.test_document_evidence_anchor_regressions import field


def index(request_text, *, exact_copy=False):
    tables = [{"id": 1, "table_name": "shipments", "table_name_cn": "运单信息", "dimension": "运单"},
              {"id": 2, "table_name": "parcels", "table_name_cn": "包裹明细表", "dimension": "包裹"}]
    fields = {1: [field("loading", "当前实际载重", "业务别名：运单实装重量。"),
                  field("state", "运输状态", dictionary="Y-在途\nN-到站")],
              2: [field("parcel_mass", "结存重量", "业务别名：包裹实装质量。")]}
    if exact_copy:
        copy = field("final", "期末净载荷", "直取")
        copy.update(source_table="mart.shipments\narchive.shipments_YYYY_MM", source_field="loading\nloading")
        fields[2].append(copy)
    return DocumentEvidence(tables, fields, request_text), tables


@pytest.mark.parametrize("request_text", ["在途运单实装重量不得小于0", "在途运单的实装重量不得小于0",
                                         "运单已到站，但是实装重量不为0"])
def test_scoped_entity_leaves_independent_metric_grains_for_review(request_text):
    evidence, tables = index(request_text)
    assert not evidence.exact_metric_field(tables[0], "loading", "运单实装重量")
    hits = evidence.competing_fields(tables[0], ["loading"], "运单实装重量", tables, across_tables=True)
    assert {(h["table"], n) for h in hits for n in h["fields"]} == {("shipments","loading"),("parcels","parcel_mass")}


@pytest.mark.parametrize("request_text", ["运单实装重量不得小于0", "在途运单的运单实装重量不得小于0",
                                         "在途运单表的实装重量不得小于0", "运单端实装重量不为0"])
def test_explicit_metric_grain_limits_the_comparison(request_text):
    evidence, tables = index(request_text)
    hits = evidence.competing_fields(tables[0], ["loading"], "运单实装重量", tables, across_tables=True)
    assert [(h["table"], h["fields"]) for h in hits] == [("shipments", ["loading"])]


def test_exact_copied_label_exposes_its_documented_origin_without_spurious_other_grain():
    evidence, tables = index("产品期末净载荷不能包含符号", exact_copy=True)
    note, = [n for n in evidence.describe(tables[1]).get("request_field_evidence", []) if n["field"] == "final"]
    assert note["direct_sources"] == [["mart.shipments","loading"], ["archive.shipments_YYYY_MM","loading"]]
    assert note["document_origin"] == {"table":"shipments", "field":"loading", "label":"当前实际载重", "dimension":"运单"}
    assert evidence.authoritative_metric_origin(tables[1], "final") == ("shipments","loading")
    for request_text in ("包裹明细表期末净载荷不能包含符号", "包裹明细的期末净载荷不能包含符号", "parcels.final检查"):
        explicit, owners = index(request_text, exact_copy=True)
        assert explicit.authoritative_metric_origin(owners[1], "final") is None
