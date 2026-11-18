"""通用 AI 建议 helper：文档事实驱动、模型输出不信、与主规则门禁隔离。"""

from __future__ import annotations

import json

import pytest

from auto_check.modules.data_validation.ai_suggestions import build_ai_suggestions


def _table(table_id: int, name: str, cn: str, dimension: str = "", scope: str = "") -> dict:
    return {
        "id": table_id, "table_name": name, "table_name_cn": cn, "dimension": dimension,
        "period": "月", "scope": scope, "source_desc": "",
    }


def _field(
    field_id: int, table_id: int, name: str, cn: str, data_type: str,
    is_pk: str = "", nullable: str = "Y", dictionary: str = "", logic: str = "",
) -> dict:
    return {
        "id": field_id, "table_id": table_id, "field_name": name, "field_cn": cn,
        "data_type": data_type, "is_pk": is_pk, "nullable": nullable,
        "dictionary": dictionary, "logic": logic, "default_value": "",
    }


def _candidate(**overrides) -> dict:
    definition = {
        "table_name": "ops_daily",
        "rule_type": "field_compare",
        "expression": {"left": "qty", "op": "eq", "right_type": "value", "right": 0},
        "null_policy": "skip",
        "equality_policy": "allow_equal",
        "business_key": "pid",
        "report_date_field": "",
        "filters": [],
        "join": None,
        "unsupported_requirements": [],
    }
    definition.update(overrides)
    return definition


TABLES = [
    _table(1, "ops_daily", "运营日报"),
    _table(2, "ops_detail", "运营明细"),
]

FIELDS = {
    1: [
        _field(11, 1, "pid", "记录编号", "varchar", is_pk="Y", nullable="N"),
        _field(12, 1, "qty", "经营数量", "decimal", nullable="N"),
        _field(13, 1, "name", "名称", "varchar", nullable="Y", dictionary="名称字典"),
        _field(14, 1, "biz_date", "业务日期", "date", nullable="Y"),
    ],
    2: [
        _field(21, 2, "pid", "记录编号", "varchar", is_pk="Y", nullable="N"),
        _field(22, 2, "qty_total", "经营数量合计", "decimal", nullable="N"),
    ],
}


def _build(model=None, *, candidates=None, tables=None, fields=None, **kwargs) -> list[dict]:
    return build_ai_suggestions(
        model,
        tables=TABLES if tables is None else tables,
        fields_by_table=FIELDS if fields is None else fields,
        candidates=[_candidate()] if candidates is None else candidates,
        **kwargs,
    )


def test_actionable_suggestions_exclude_non_main_keys_and_pending_dictionary():
    fields = {1: [*FIELDS[1], _field(15, 1, "c_projstatus", "项目状态", "varchar", dictionary="1-存续")]}
    candidate = _candidate(filters=[{"table": "base", "field": "c_projstatus", "op": "eq", "value": "1", "confirmed": False}])
    suggestion = {"title": "人工核实当前主字段", "references": [{"table_name": "ops_daily", "field_name": "qty"}],
                  "support_level": "supported"}
    assert _build(model=[suggestion], fields=fields, candidates=[candidate], actionable_only=True) == []
    key_rule = _candidate(expression={"left": "pid", "op": "is_null"})
    result = _build(candidates=[key_rule], actionable_only=True)
    assert [item["kind"] for item in result] == ["unique"]


@pytest.mark.parametrize("mismatch", [None, "grain", "period", "key", "lineage", "logic"])
def test_actionable_same_measure_requires_documented_comparable_fields(mismatch):
    base = {**_table(1, "reg_pub_project_info", "项目信息表", "项目"), "data_source_name": "监管报送集市"}
    other = {**base, "id": 2, "table_name": "project_report_mirror"}
    metric = {**_field(12, 1, "f_endp_amt", "实收信托", "decimal(18,2)"),
              "source_table": "project_source", "source_field": "paid_amount"}
    counterpart = {**metric, "id": 22, "table_id": 2, "field_name": "paid_in_amt"}
    other_key = _field(21, 2, "c_projcode", "项目编号", "varchar", is_pk="Y")
    if mismatch == "grain":
        other["dimension"] = "合同"
    elif mismatch == "period":
        other["period"] = "日"
    elif mismatch == "key":
        other_key["field_name"] = "contract_id"
    elif mismatch == "lineage":
        counterpart["source_field"] = "other_amount"
    elif mismatch == "logic":
        counterpart["logic"] = "按不同币种合计"
    fields = {1: [metric, _field(11, 1, "c_projcode", "项目编号", "varchar", is_pk="Y"),
                  _field(13, 1, "d_cldate", "数据日期", "date")],
              2: [counterpart, other_key, _field(23, 2, "d_cldate", "数据日期", "date")]}
    candidate = _candidate(table_name=base["table_name"], report_date_field="d_cldate",
                           expression={"left": "f_endp_amt", "op": "lt", "right_type": "value", "right": 0})
    result = _build(tables=[base, other], fields=fields, candidates=[candidate], actionable_only=True)
    if mismatch:
        assert result == []
    else:
        assert len(result) == 1 and result[0]["support_level"] == "supported"
        assert result[0]["references"] == [{"table_name": base["table_name"], "field_name": "f_endp_amt"},
                                            {"table_name": other["table_name"], "field_name": "paid_in_amt"}]
        assert "sql" not in result[0] and "definition" not in result[0]


def test_unrelated_business_table_gets_generic_document_suggestions() -> None:
    result = _build()

    assert result
    assert all(item["provenance"] == "document" for item in result)
    blob = json.dumps(result, ensure_ascii=False)
    for forbidden in ("实收", "合同", "余额", "项目"):
        assert forbidden not in blob

    coverage = [item for item in result if item["category"] == "coverage_gap"]
    assert len(coverage) == 1
    assert coverage[0]["references"] == [{"table_name": "ops_daily", "field_name": "qty"}]
    assert coverage[0]["kind"] == "field_compare_unary"
    assert coverage[0]["support_level"] == "needs_confirmation"
    assert coverage[0]["definition"]["expression"] == {"left": "qty", "op": "is_null"}

    integrity = [item for item in result if item["category"] == "integrity"]
    assert len(integrity) == 1
    assert integrity[0]["kind"] == "unique"
    assert integrity[0]["support_level"] == "supported"

    assert [item for item in result if item["category"] == "period"]


def test_single_candidate_has_no_hallucinated_fields_or_tables() -> None:
    result = _build()

    real = {("ops_daily", "pid"), ("ops_daily", "qty")}
    referenced = {
        (item["table_name"], item["field_name"])
        for suggestion in result for item in suggestion["references"]
    }
    assert referenced
    assert referenced <= real
    blob = json.dumps(result, ensure_ascii=False)
    for invented in ("project_code", "contract", "join"):
        assert invented not in blob
    assert all("report_date" != item["field_name"] for item in
               [ref for suggestion in result for ref in suggestion["references"]])


def test_unknown_grain_keeps_consistency_suggestion() -> None:
    candidates = [
        _candidate(table_name="ops_daily"),
        _candidate(
            table_name="ops_detail",
            expression={"left": "qty_total", "op": "eq", "right_type": "value", "right": 0},
        ),
    ]

    result = _build(candidates=candidates)
    consistency = [item for item in result if item["category"] == "consistency"]

    assert consistency
    assert consistency[0]["support_level"] == "needs_confirmation"
    assert any("粒度未标注" in text for text in consistency[0]["preconditions"])
    tables = {ref["table_name"] for ref in consistency[0]["references"]}
    assert tables == {"ops_daily", "ops_detail"}


def test_ktr_real_fields_are_regression_only_not_keyword_logic() -> None:
    tables = [
        _table(1, "reg_pub_project_info", "项目信息表", dimension="项目"),
        _table(2, "reg_pub_ta_pact_info", "资金端合同明细表", dimension="合同"),
        _table(3, "reg_pub_accountbalance_sum", "项目余额汇总表", dimension="余额"),
    ]
    fields = {
        1: [
            _field(11, 1, "c_projcode", "项目编号", "varchar", is_pk="Y", nullable="N"),
            _field(12, 1, "f_endp_amt", "实收信托", "decimal", nullable="N"),
            _field(13, 1, "d_cldate", "数据日期", "date", nullable="Y"),
        ],
        2: [
            _field(21, 2, "c_pactid", "合同编号", "varchar", is_pk="Y", nullable="N"),
            _field(22, 2, "f_actual_scale", "实收信托规模", "decimal", nullable="N"),
            _field(23, 2, "d_cldate", "数据日期", "date", nullable="Y"),
        ],
        3: [
            _field(31, 3, "c_projcode", "项目编号", "varchar", is_pk="Y", nullable="N"),
            _field(32, 3, "f_balan_endp_amt", "实收信托余额", "decimal", nullable="N"),
            _field(33, 3, "d_balancedate", "余额日期", "date", nullable="Y"),
        ],
    }
    candidates = [
        _candidate(
            table_name="reg_pub_project_info", business_key="c_projcode",
            report_date_field="d_cldate",
            expression={"left": "f_endp_amt", "op": "eq", "right_type": "value", "right": 0},
        ),
        _candidate(
            table_name="reg_pub_ta_pact_info", business_key="c_pactid",
            report_date_field="d_cldate",
            expression={"left": "f_actual_scale", "op": "eq", "right_type": "value", "right": 0},
        ),
        _candidate(
            table_name="reg_pub_accountbalance_sum", business_key="c_projcode",
            report_date_field="d_balancedate",
            expression={"left": "f_balan_endp_amt", "op": "eq", "right_type": "value", "right": 0},
        ),
    ]

    result = _build(candidates=candidates, tables=tables, fields=fields)
    consistency = [item for item in result if item["category"] == "consistency"]

    assert consistency
    blob = json.dumps(result, ensure_ascii=False)
    assert "sql" not in blob.lower()
    real = {
        (table["table_name"], field["field_name"])
        for table in tables for field in fields[int(table["id"])]
    }
    assert {
        (ref["table_name"], ref["field_name"])
        for item in result for ref in item["references"]
    } <= real


def test_model_suggestion_recomputes_support_and_ignores_sql_and_definition() -> None:
    model = [{
        "id": "model-1",
        "category": "coverage_gap",
        "kind": "field_compare_unary",
        "title": "检查经营数量非空",
        "reason": "建议补充非空检查",
        "references": [{"table_name": "ops_daily", "field_name": "qty"}],
        "preconditions": ["需确认口径"],
        "limitations": [],
        "support_level": "supported",
        "supported": True,
        "sql": "SELECT * FROM ops_daily",
        "definition": {"rule_type": "custom_sql", "sql": "SELECT 1"},
        "provenance": "model",
    }]

    result = _build(model=model, candidates=[])

    assert len(result) == 1
    item = result[0]
    assert item["provenance"] == "model"
    assert item["support_level"] == "needs_confirmation"
    assert "sql" not in item
    assert "SELECT" not in json.dumps(item, ensure_ascii=False)
    assert item["definition"] == {
        "rule_type": "field_compare",
        "table_name": "ops_daily",
        "expression": {"left": "qty", "op": "is_null"},
        "null_policy": "violate",
        "equality_policy": "allow_equal",
    }
    assert item["id"]


def test_unknown_model_reference_drops_whole_suggestion() -> None:
    base = {
        "title": "检查字段",
        "reason": "建议",
        "references": [{"table_name": "ops_daily", "field_name": "qty"}],
    }

    mixed = dict(base, references=[
        {"table_name": "ops_daily", "field_name": "qty"},
        {"table_name": "ops_daily", "field_name": "missing_field"},
    ])
    assert _build(model=[mixed], candidates=[]) == []

    quoted = dict(base, references=[
        {"table_name": "`ops_daily`", "field_name": "`qty`"},
    ])
    assert _build(model=[quoted], candidates=[]) == []

    wrong_table = dict(base, references=[
        {"table_name": "other_table", "field_name": "qty"},
    ])
    assert _build(model=[wrong_table], candidates=[]) == []


def test_model_claims_do_not_override_capability_decisions() -> None:
    aggregation = [{
        "title": "按项目汇总核对",
        "reason": "需要 SUM 后比较",
        "category": "consistency",
        "references": [{"table_name": "ops_daily", "field_name": "qty"}],
        "support_level": "supported",
        "supported": True,
    }]
    item = _build(model=aggregation, candidates=[])[0]
    assert item["support_level"] == "unsupported"

    unique = [{
        "title": "主键唯一",
        "reason": "建议核实唯一性",
        "category": "integrity",
        "kind": "unique",
        "references": [{"table_name": "ops_daily", "field_name": "pid"}],
        "support_level": "supported",
        "supported": True,
    }]
    item = _build(model=unique, candidates=[])[0]
    assert item["support_level"] == "needs_confirmation"


def test_chinese_business_words_are_not_treated_as_aggregation() -> None:
    tables = [_table(1, "汇总汇总表", "汇总汇总表")]
    fields = {1: [_field(11, 1, "total_amt", "累计金额", "decimal", nullable="N")]}
    model = [{
        "title": "汇总表中累计金额字段非空",
        "reason": "累计金额字段比较",
        "category": "coverage_gap",
        "references": [{"table_name": "汇总汇总表", "field_name": "total_amt"}],
    }]

    item = _build(model=model, candidates=[], tables=tables, fields=fields)[0]
    assert item["support_level"] == "needs_confirmation"
    assert "聚合" not in item["reason"]


def test_model_suggestions_accept_dict_wrapper() -> None:
    model = {"ai_suggestions": [{
        "title": "检查经营数量",
        "reason": "建议",
        "references": [{"table_name": "ops_daily", "field_name": "qty"}],
    }]}
    result = _build(model=model, candidates=[])
    assert len(result) == 1
    assert result[0]["provenance"] == "model"


def test_length_bounds_dedupe_and_limit() -> None:
    long_title = "建" * 200
    model = [{
        "title": long_title,
        "reason": "理由",
        "references": [{"table_name": "ops_daily", "field_name": "qty"}],
        "preconditions": [f"条件{index}" for index in range(10)],
        "limitations": ["局" * 300],
    }]

    result = _build(model=model, candidates=[])
    assert len(result) == 1
    assert len(result[0]["title"]) == 120
    assert len(result[0]["preconditions"]) <= 6
    assert all(len(text) <= 200 for text in result[0]["limitations"])

    duplicated = _build(model=[model[0], model[0]], candidates=[])
    assert len(duplicated) == 1

    limited = _build(limit=1)
    assert len(limited) == 1


def test_existing_rules_are_not_repeated() -> None:
    existing = [{
        "rule_code": "R1",
        "definition": {
            "rule_type": "field_compare",
            "table_name": "ops_daily",
            "expression": {"left": "qty", "op": "is_null"},
        },
    }]

    result = _build(existing_rules=existing)
    assert not any(
        item["category"] == "coverage_gap" and item["references"][0]["field_name"] == "qty"
        for item in result
    )
    assert result


def test_dictionary_and_type_semantics_suggestions() -> None:
    candidates = [
        _candidate(
            filters=[{"table": "base", "field": "name", "op": "eq", "value": "X", "confirmed": False}],
            report_date_field="biz_date",
        ),
        _candidate(
            table_name="ops_detail",
            expression={"left": "qty_total", "op": "eq", "right_type": "value", "right": 0},
            report_date_field="biz_date",
        ),
    ]

    result = _build(candidates=candidates, limit=10)
    dictionary = [item for item in result if item["category"] == "dictionary"]
    assert len(dictionary) == 1
    assert dictionary[0]["references"] == [{"table_name": "ops_daily", "field_name": "name"}]
    assert dictionary[0]["support_level"] == "needs_confirmation"

    mismatch = _candidate(
        expression={"left": "qty", "op": "eq", "right_type": "field", "right": "name"},
        report_date_field="biz_date",
    )
    result = _build(candidates=[mismatch])
    semantics = [item for item in result if item["category"] == "type_semantics"]
    assert semantics
    assert semantics[0]["support_level"] == "needs_confirmation"

    constant = _candidate(
        expression={"left": "name", "op": "eq", "right_type": "value", "right": 0},
        report_date_field="biz_date",
    )
    result = _build(candidates=[constant])
    assert [item for item in result if item["category"] == "type_semantics"]


def test_valid_date_field_avoids_period_suggestion() -> None:
    candidate = _candidate(report_date_field="biz_date")
    result = _build(candidates=[candidate])
    assert not [item for item in result if item["category"] == "period"]


def test_empty_inputs_produce_no_suggestions() -> None:
    assert build_ai_suggestions(
        None, tables=[], fields_by_table={}, candidates=[],
    ) == []
    assert _build(candidates=[]) == []


def test_unsupported_requirements_are_reported_not_hidden() -> None:
    candidate = _candidate(unsupported_requirements=["需要跨数据源关联三表"])
    result = _build(candidates=[candidate])
    unsupported = [item for item in result if item["category"] == "unsupported_requirement"]
    assert unsupported
    assert unsupported[0]["support_level"] == "unsupported"
    assert unsupported[0]["limitations"] == ["需要跨数据源关联三表"]


def test_model_nested_text_fields_do_not_crash() -> None:
    model = [{
        "title": "检查经营数量",
        "reason": ["嵌套理由", {"bad": True}, 7],
        "references": [{"table_name": "ops_daily", "field_name": "qty"}],
        "preconditions": [["嵌套条件"], {"bad": True}, 123, "有效条件"],
        "limitations": [["嵌套限制"], 456, "有效限制"],
        "sql": {"raw": "SELECT 1"},
    }]

    result = _build(model=model, candidates=[])

    assert len(result) == 1
    item = result[0]
    assert item["preconditions"] == ["有效条件"]
    assert item["limitations"] == ["有效限制", "未采纳模型返回的 SQL，建议仅作人工核实"]
    assert "sql" not in item
    assert "SELECT" not in json.dumps(item, ensure_ascii=False)


def test_model_references_over_limit_are_rejected() -> None:
    model = [{
        "title": "检查多个字段",
        "reason": "建议",
        "references": [
            {"table_name": "ops_daily", "field_name": name}
            for name in ("pid", "qty", "name", "biz_date", "extra")
        ],
    }]
    assert _build(model=model, candidates=[]) == []


def test_composite_primary_key_is_one_full_group_suggestion() -> None:
    tables = [_table(1, "ops_composite", "运营复合表")]
    fields = {1: [
        _field(11, 1, "pid", "记录编号", "varchar", is_pk="Y", nullable="N"),
        _field(12, 1, "line_no", "行号", "int", is_pk="Y", nullable="N"),
        _field(13, 1, "qty", "数量", "decimal", nullable="Y"),
    ]}
    candidate = _candidate(
        table_name="ops_composite", expression={"left": "qty", "op": "eq", "right_type": "value", "right": 0},
    )

    result = _build(candidates=[candidate], tables=tables, fields=fields, limit=10)
    integrity = [item for item in result if item["category"] == "integrity"]

    assert len(integrity) == 1
    item = integrity[0]
    assert item["kind"] == "unique"
    assert item["support_level"] == "supported"
    assert [ref["field_name"] for ref in item["references"]] == ["pid", "line_no"]
    assert "记录编号" in item["title"] and "行号" in item["title"]
    assert any("期间" in text for text in item["preconditions"])
    assert any("report_date" in text for text in item["limitations"])


def test_composite_primary_key_over_limit_gives_no_partial_suggestion() -> None:
    tables = [_table(1, "ops_wide", "运营宽表")]
    fields = {1: [
        _field(10 + index, 1, f"pk_{index}", f"主键{index}", "varchar", is_pk="Y", nullable="N")
        for index in range(5)
    ] + [_field(20, 1, "qty", "数量", "decimal", nullable="Y")]}
    candidate = _candidate(
        table_name="ops_wide", expression={"left": "qty", "op": "eq", "right_type": "value", "right": 0},
    )

    result = _build(candidates=[candidate], tables=tables, fields=fields, limit=10)
    assert not [item for item in result if item["category"] == "integrity"]


def test_nullable_non_expression_fields_do_not_trigger_coverage() -> None:
    tables = [_table(1, "ops_mixed", "运营混合表")]
    fields = {1: [
        _field(11, 1, "pid", "记录编号", "varchar", is_pk="Y", nullable="N"),
        _field(12, 1, "qty", "数量", "decimal", nullable="Y"),
        _field(13, 1, "name", "名称", "varchar", nullable="N", dictionary="名称字典"),
        _field(14, 1, "due_date", "到期日期", "date", nullable="N"),
    ]}
    candidate = _candidate(
        table_name="ops_mixed",
        expression={"left": "qty", "op": "eq", "right_type": "value", "right": 0},
        business_key="pid", report_date_field="due_date",
        filters=[{"table": "base", "field": "name", "op": "eq", "value": "X", "confirmed": False}],
    )

    result = _build(candidates=[candidate], tables=tables, fields=fields, limit=10)
    assert not [item for item in result if item["category"] == "coverage_gap"]
    assert [item for item in result if item["category"] == "dictionary"]


def test_scope_fingerprint_prevents_cross_context_dedupe() -> None:
    candidate = _candidate()
    different_scope = [{
        "rule_code": "R1",
        "definition": {
            "rule_type": "field_compare", "table_name": "ops_daily",
            "expression": {"left": "qty", "op": "is_null"},
            "source_id": "src-b",
        },
    }]
    result = _build(candidates=[candidate], existing_rules=different_scope)
    assert [item for item in result if item["category"] == "coverage_gap"]

    same_scope = [{
        "rule_code": "R2",
        "definition": {
            "rule_type": "field_compare", "table_name": "ops_daily",
            "expression": {"left": "qty", "op": "is_null"},
        },
    }]
    result = _build(candidates=[candidate], existing_rules=same_scope)
    assert not [
        item for item in result
        if item["category"] == "coverage_gap" and item["references"][0]["field_name"] == "qty"
    ]


def test_numeric_zero_policy_gap_rules() -> None:
    covered = _candidate(
        null_policy="zero",
        expression={"left": "qty", "op": "gte", "right_type": "value", "right": 0},
    )
    result = _build(candidates=[covered], limit=10)
    coverage = [item for item in result if item["category"] == "coverage_gap"]
    assert len(coverage) == 1
    assert "已判异常" in coverage[0]["reason"]
    assert "跳过" not in coverage[0]["title"] + coverage[0]["reason"]

    missing = _candidate(
        null_policy="zero",
        expression={"left": "qty", "op": "gt", "right_type": "value", "right": 0},
    )
    result = _build(candidates=[missing], limit=10)
    coverage = [item for item in result if item["category"] == "coverage_gap"]
    assert len(coverage) == 1
    item = coverage[0]
    assert "未判异常" in item["reason"]
    assert "按 0 参与比较" in item["reason"]
    assert item["support_level"] == "needs_confirmation"
    for suggestion in result:
        assert "非负" not in suggestion["title"] + suggestion["reason"]
        assert "一律非法" not in suggestion["title"] + suggestion["reason"]
        if suggestion.get("definition"):
            assert suggestion["definition"]["expression"]["op"] == "is_null"

    unknown_right = _candidate(
        null_policy="zero",
        expression={"left": "qty", "op": "gt", "right_type": "field", "right": "name"},
    )
    result = _build(candidates=[unknown_right], limit=10)
    coverage = [item for item in result if item["category"] == "coverage_gap"]
    assert len(coverage) == 1
    assert "无法判断" in coverage[0]["reason"]

    non_number = _candidate(
        null_policy="zero",
        expression={"left": "name", "op": "gt", "right_type": "value", "right": 0},
    )
    result = _build(candidates=[non_number], limit=10)
    assert not [item for item in result if item["category"] == "coverage_gap"]
