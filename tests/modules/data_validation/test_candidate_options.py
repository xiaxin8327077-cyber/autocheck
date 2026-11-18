"""多候选合同：同源真实语义字段发现、项目优先、独立预览与分句消解。"""

from __future__ import annotations

from sqlalchemy import insert, update

from auto_check.modules.data_validation.candidate_choices import (
    counterpart_fields, grain_label, resolve_uncertainty_clauses, semantic_core,
    target_ambiguity_indices,
)
from auto_check.modules.data_validation.storage import DOC_FIELDS, DOC_TABLES
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import (
    _generate_payload, _request, _rules_with_doc, _select_payload,
)


MAIN_FIELDS = [
    ("row_id", "编号", "varchar", "Y"),
    ("f_main_amt", "实收信托", "decimal", ""),
    ("maturity_date", "到期日期", "date", ""),
]

SCREENSHOT_AMBIGUITY = (
    "需求中的“实收”可能对应多个字段，如 reg_pub_ta_pact_info.f_actual_scale "
    "或 reg_pub_accountbalance_sum.f_balan_endp_amt，需确认哪个字段代表项目实收；"
    "未指定业务日期口径，是否需过滤特定日期数据"
)


def _add_table(rules, *, name: str, cn: str, dimension: str,
               fields: list[tuple[str, str, str, str]], source_desc: str = "") -> None:
    document = rules.storage.active_document()
    base = rules.storage.doc_tables(int(document["id"]))[0]
    row = {key: value for key, value in base.items() if key != "id"}
    row.update(table_name=name, table_name_cn=cn, dimension=dimension, source_desc=source_desc)
    template = rules.storage.doc_fields(int(base["id"]))[0]
    with rules.storage.database.begin() as connection:
        table_id = connection.execute(insert(DOC_TABLES).values(**row)).inserted_primary_key[0]
        for order, (field_name, field_cn, data_type, is_pk) in enumerate(fields):
            field_row = {key: value for key, value in template.items() if key != "id"}
            field_row.update(
                table_id=int(table_id), field_name=field_name, field_cn=field_cn,
                data_type=data_type, is_pk=is_pk, sort_order=order,
            )
            connection.execute(insert(DOC_FIELDS).values(**field_row))


def _project_table(rules) -> None:
    _add_table(rules, name="reg_pub_project_info", cn="项目信息表", dimension="项目", fields=[
        ("c_projcode", "项目编号", "varchar", "Y"),
        ("c_projname", "项目名称", "varchar", ""),
        ("f_endp_amt", "实收信托", "decimal", ""),
        ("d_cldate", "数据日期", "date", ""),
    ])


def _contract_table(rules) -> None:
    _add_table(rules, name="reg_pub_ta_pact_info", cn="资金端合同明细表", dimension="合同",
               source_desc="项目相关来源", fields=[
        ("c_pactid", "合同编号", "varchar", "Y"),
        ("c_projcode", "项目编号", "varchar", ""),
        ("c_projname", "项目名称", "varchar", ""),
        ("f_actual_scale", "实收信托规模（委托资产，合同份额余额+待结转收益）", "decimal", ""),
        ("d_cldate", "数据日期", "date", ""),
    ])


def _balance_table(rules) -> None:
    _add_table(rules, name="reg_pub_accountbalance_sum", cn="项目余额汇总表", dimension="余额", fields=[
        ("c_projcode", "项目编号", "varchar", "Y"),
        ("c_projname", "项目名称", "varchar", ""),
        ("f_balan_endp_amt", "实收信托余额", "decimal", ""),
        ("d_balancedate", "余额日期", "date", ""),
    ])


def _parse_with_candidates(selection=None, *, include_balance=False):
    rules, _model = _rules_with_doc([
        selection or _select_payload(),
        _generate_payload(expression={"left": "实收信托", "op": "eq", "right_type": "value", "right": 0}),
    ], fields=MAIN_FIELDS)
    with rules.storage.database.begin() as connection:
        connection.execute(
            DOC_TABLES.update().where(DOC_TABLES.c.table_name == "test_table").values(dimension="测试")
        )
    _project_table(rules)
    _contract_table(rules)
    if include_balance:
        _balance_table(rules)
    return rules.parse_rule_request(user(), _request(request_text="项目得实收不得为0"))


def test_real_semantic_counterparts_match_without_same_english_or_chinese_names() -> None:
    base = {"field_name": "f_endp_amt", "field_cn": "实收信托"}
    fields = [
        {"field_name": "f_actual_scale", "field_cn": "实收信托规模（委托资产，合同份额余额+待结转收益）"},
        {"field_name": "f_balan_endp_amt", "field_cn": "实收信托余额"},
        {"field_name": "f_loan_amt", "field_cn": "贷款余额"},
    ]
    assert semantic_core("实收信托", "实收信托规模") == "实收信托"
    matched = {field["field_name"] for field in counterpart_fields(fields, base)}
    assert matched == {"f_actual_scale", "f_balan_endp_amt"}
    assert counterpart_fields(
        [{"field_name": "f_amt", "field_cn": "罚款金额"}],
        {"field_name": "f_amt", "field_cn": "实收信托"},
    ) == []


def test_grain_uses_dimension_and_does_not_flip_on_source_description() -> None:
    assert grain_label({"dimension": "项目合同"}) == ""
    assert grain_label({"table_name_cn": "项目合同信息表", "scope": ""}) == ""
    assert grain_label({
        "dimension": "合同", "table_name_cn": "资金端合同明细表", "source_desc": "项目相关来源",
    }) == "合同级"
    assert grain_label({
        "dimension": "项目", "table_name_cn": "项目信息表", "source_desc": "",
    }) == "项目级"


def test_target_ambiguity_filter_protects_units_and_matches_screenshot() -> None:
    indices = target_ambiguity_indices([
        SCREENSHOT_AMBIGUITY,
        "目标表币种不明确，不能比较金额",
        "需要按例外范围筛选",
    ])
    assert indices == [0]


def test_cross_grain_real_indicators_become_project_first_options() -> None:
    candidate = _parse_with_candidates()

    assert candidate["table_name"] == "reg_pub_project_info"
    assert candidate["candidate_options"], "应给出含主推荐在内的真实可选项"
    labels = {item["table_label"] for item in candidate["candidate_options"]}
    assert labels == {"项目信息表", "测试表（test_table.ktr）", "资金端合同明细表"}
    grains = {item["grain"] for item in candidate["candidate_options"]}
    assert grains == {"项目级", "", "合同级"}
    assert next(item for item in candidate["candidate_options"]
                if item["table_label"] == "项目信息表")["recommended"] is True

    contract = next(item for item in candidate["candidate_options"] if item["table_label"] == "资金端合同明细表")
    inner = contract["candidate"]
    assert inner["expression"]["left"] == "f_actual_scale"
    assert inner["business_key"] == "c_pactid"
    assert inner["report_date_field"] == "d_cldate"
    assert "candidate_options" not in inner and "comparison_suggestions" not in inner
    assert inner["preview"]["sql_preview"]
    assert inner["preview"]["definition"]["uncertainties"] == []
    assert not any("单位/币种/粒度" in value for value in inner["uncertainties"])
    assert any("口径差异" in line for line in contract["differences"])

    names = {item["candidate"]["rule_name"] for item in candidate["candidate_options"]}
    assert len(names) == 3
    assert all(f"（{item['candidate']['table_name']}）" in item["candidate"]["violation_message"]
               for item in candidate["candidate_options"])

    suggestions = candidate["comparison_suggestions"]
    assert suggestions and suggestions[0]["supported"] is False
    assert suggestions[0]["limitations"]


def test_exact_screenshot_sentence_is_resolved_into_three_fact_bound_schemes() -> None:
    selection = _select_payload(
        target={}, result_type="clarification", uncertainties=[SCREENSHOT_AMBIGUITY],
        target_ambiguities=[
            {"table": "reg_pub_project_info", "field": "f_endp_amt"},
            {"table": "reg_pub_ta_pact_info", "field": "f_actual_scale"},
            {"table": "reg_pub_accountbalance_sum", "field": "f_balan_endp_amt"},
        ],
    )
    candidate = _parse_with_candidates(selection, include_balance=True)

    assert candidate["table_name"] == "reg_pub_project_info"
    assert len(candidate.get("candidate_options") or []) == 3
    for option in candidate["candidate_options"]:
        inner = option["candidate"]
        assert inner["report_date_field"] in {"d_cldate", "d_balancedate"}
        assert inner["uncertainties"] == []
        assert inner["preview"]["definition"]["uncertainties"] == []
        assert "未指定业务日期" not in "\n".join(inner["uncertainties"])
        assert "对应多个字段" not in "\n".join(inner["uncertainties"])
    # 用户已明确选择期间日期后，单候选也不再出现伪日期追问。
    assert candidate["preview"]["definition"]["uncertainties"] == []


def test_clause_level_resolution_keeps_real_unit_range_and_drops_date_only() -> None:
    resolved = resolve_uncertainty_clauses(
        ["目标表币种不明确，不能比较金额；未指定业务日期口径"],
        has_candidates=False, has_period=True,
    )
    assert resolved == ["目标表币种不明确，不能比较金额"]
    assert resolve_uncertainty_clauses(
        ["需要截止报告日期的余额范围；未指定业务日期口径"],
        has_candidates=False, has_period=True,
    ) == ["需要截止报告日期的余额范围"]


def test_no_evidence_means_no_invented_options() -> None:
    rules, _model = _rules_with_doc([
        _select_payload(),
        _generate_payload(expression={"left": "实收信托", "op": "eq", "right_type": "value", "right": 0}),
    ], fields=MAIN_FIELDS)
    candidate = rules.parse_rule_request(user(), _request(request_text="实收不得为0"))
    assert "candidate_options" not in candidate
    assert "comparison_suggestions" not in candidate


def _clarification_fixture(selection):
    rules, model = _rules_with_doc([
        selection,
        _generate_payload(expression={"left": "实收信托", "op": "eq", "right_type": "value", "right": 0}),
    ], fields=MAIN_FIELDS)
    with rules.storage.database.begin() as connection:
        connection.execute(
            DOC_TABLES.update().where(DOC_TABLES.c.table_name == "test_table").values(dimension="测试")
        )
    _project_table(rules)
    _contract_table(rules)
    _balance_table(rules)
    return rules, model


def test_typed_clarification_continues_once_with_two_real_targets() -> None:
    selection = _select_payload(
        target={}, result_type="clarification", uncertainties=[SCREENSHOT_AMBIGUITY],
        target_ambiguities=[
            {"table": "reg_pub_project_info", "field": "f_endp_amt"},
            {"table": "reg_pub_accountbalance_sum", "field": "f_balan_endp_amt"},
        ],
    )
    rules, model = _clarification_fixture(selection)
    candidate = rules.parse_rule_request(user(), _request(request_text="项目得实收不得为0"))

    assert len(model.calls) == 2
    assert candidate["rule_type"] == "field_compare"
    assert candidate["table_name"] == "reg_pub_project_info"
    assert len(candidate.get("candidate_options") or []) >= 1
    joined = "\n".join(candidate.get("uncertainties") or [])
    assert "实收信托规模还是实收信托余额" not in joined
    assert "对应多个字段" not in joined


def test_legacy_sentence_with_two_real_table_names_continues() -> None:
    selection = _select_payload(target={}, uncertainties=[SCREENSHOT_AMBIGUITY])
    rules, model = _clarification_fixture(selection)
    candidate = rules.parse_rule_request(user(), _request(request_text="项目得实收不得为0"))
    assert len(model.calls) == 2
    assert candidate["rule_type"] == "field_compare"
    assert candidate["table_name"] in {"reg_pub_ta_pact_info", "reg_pub_accountbalance_sum"}
    assert "未指定业务日期" not in "\n".join(candidate.get("uncertainties") or [])


def test_single_or_untargeted_clarification_keeps_single_call_protection() -> None:
    selection = _select_payload(target={}, uncertainties=["无法确定目标对象，请补充业务描述"])
    rules, model = _clarification_fixture(selection)
    candidate = rules.parse_rule_request(user(), _request(request_text="项目得实收不得为0"))
    assert len(model.calls) == 1
    assert candidate["status"] == "needs_clarification"
    assert "candidate_options" not in candidate
