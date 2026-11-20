import json

import pytest

from auto_check.modules.data_validation.document_evidence import DocumentEvidence
from tests.modules.data_validation.test_document_evidence_anchor_regressions import field


TABLES = [{"id": 1, "table_name": "readings", "table_name_cn": "设备记录", "dimension": "设备"},
          {"id": 2, "table_name": "parts", "table_name_cn": "配件记录", "dimension": "配件"}]


def views(fields, request):
    index = DocumentEvidence(TABLES, fields, request)
    return [index.describe(t) for t in TABLES]


def test_request_marks_registered_alias_without_marking_converted_or_incidental_mentions():
    fields = {1: [field("weight", "测得质量", "业务别名：载荷、净载荷。定义：直接测量。"),
                  field("tons", "测得质量折吨", "由净载荷单位换算。")], 2: []}
    first, _ = views(fields, "设备净载荷应为正")
    notes = first.get("request_field_evidence", [])
    assert {"field": "weight", "registered_alias": "净载荷"} in notes
    assert all(note["field"] != "tons" for note in notes)
    assert any(row[0] == "tons" for row in first.get("fields", [])) or "测得质量折吨" in first["directory"]


def test_explicit_reordered_qualifier_adds_its_full_dictionary_within_a_bounded_budget():
    dictionary = "1-封闭\n2-开放"
    fields = {1: [field(f"other{i}", "类型", dictionary=dictionary) for i in range(9)]
                 + [field("mode", "运行方式", dictionary=dictionary),
                    field("orig", "运行方式_原始", dictionary=dictionary)], 2: []}
    first, _ = views(fields, "原始运行方式为封闭的设备")
    assert {"field": "orig", "request_label": "原始运行方式"} in first.get("request_field_evidence", [])
    row = next(row for row in first["fields"] if row[0] == "orig")
    assert first["shared_dictionaries"][row[3]["dictionary_ref"]] == dictionary
    generic, _ = views(fields, "封闭设备")
    assert not generic.get("request_field_evidence")


def test_direct_snapshot_evidence_keeps_grain_and_cannot_be_fabricated_by_crossed_source_lines():
    focus = field("total", "累计读数")
    direct = field("copied", "期末累计读数", "直取")
    direct.update(source_table="stage.readings\narchive.readings_YYYY_MM", source_field="total\ntotal")
    crossed = {**direct, "field_name": "crossed", "source_field": "old_value\ntotal"}
    transformed = {**direct, "field_name": "adjusted", "logic": "直取后重新计量"}
    first, second = views({1: [focus], 2: [direct, crossed, transformed]}, "查设备累计读数")
    assert second["dimension"] == "配件"
    notes = second.get("request_field_evidence", [])
    assert notes == [{"field": "copied", "direct_sources": [
        ["stage.readings", "total"], ["archive.readings_YYYY_MM", "total"]]}]
    assert all("direct_sources" not in row for row in first.get("request_field_evidence", []))


def test_additional_evidence_is_bounded_for_many_matching_aliases():
    fields = {i: [field(f"m{n}", f"称重{n}", "业务别名：净载荷。") for n in range(75)] for i in (1, 2)}
    result = views(fields, "设备净载荷为负")
    payloads = [json.dumps({"request_field_evidence": t["request_field_evidence"]},
                           ensure_ascii=False, separators=(",", ":")).encode() for t in result if t.get("request_field_evidence")]
    assert payloads and sum(map(len, payloads)) <= 800


@pytest.mark.parametrize(("request_text", "selected", "expected"), [
    ("原始运行方式为净值型时校验", "original", set()),
    ("原始运行方式为净值型时校验", "mode", {"mode", "original"}),
    ("净值型时校验", "original", {"mode", "original"}),
    ("原始运行方式或运行方式为净值型时校验", "original", {"mode", "original"}),
])
def test_explicit_qualified_scope_cannot_expand_to_or_hide_another_document_field(request_text, selected, expected):
    choices = [field("mode", "运行方式", dictionary="1-净值型\n2-其他"),
               field("original", "运行方式_原始", dictionary="1-净值型\n2-其他")]
    evidence = DocumentEvidence(TABLES, {1: choices, 2: []}, request_text)
    hits = evidence.competing_fields(TABLES[0], [selected], "净值型", TABLES, category=True)
    assert {name for hit in hits for name in hit["fields"]} == expected
