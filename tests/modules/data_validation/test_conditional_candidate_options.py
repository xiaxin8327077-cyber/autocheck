"""条件非空规则的跨表候选必须重新核实本表字段、字典与可执行定义。"""

from uuid import uuid4

import pytest
from sqlalchemy import delete, update

from auto_check.modules.data_validation.storage import DOC_FIELDS
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import (
    _generate_payload, _request, _rules_with_doc, _select_payload,
)
from tests.modules.data_validation.test_candidate_options import _add_table


PROJECT = "proj_info_dtl_pboc"
DETAIL = "raise_info_dtl_pboc"
SUMMARY = "raise_info_mid_pboc"
REQUEST = "项目原始运行方式为净值型时，累计净值不得为空"
PHYSICAL_REQUEST = "c_oper_mode_orig为净值型时，累计净值不得为空"
DICTIONARY = "【RHZD0008】\n1-开放式净值型\n2-开放式非净值型\n3-封闭式净值型\n4-封闭式非净值型"


def _conditional_rules(*, different_codes=False, extra_tables=(), unsupported=(), proposed_filters=()):
    rules, model = _rules_with_doc([
        _select_payload(target={"table": PROJECT}),
        _generate_payload(expression={"left": "f_totalnetvalue", "op": "is_null"},
                          unsupported_requirements=list(unsupported), filters=list(proposed_filters)),
    ])
    _add_table(rules, name=PROJECT, cn="项目信息", dimension="项目", fields=[
        ("d_cldate", "数据日期", "date", ""),
        ("c_projinnercode", "TCMP编号", "varchar", "Y"),
        ("c_projname", "产品名称", "varchar", ""),
        ("c_oper_mode", "运行方式", "varchar", ""),
        ("c_oper_mode_orig", "运行方式_原始", "varchar", ""),
        ("f_start_totalnetvalue", "期初累计净值", "numeric", ""),
        ("f_totalnetvalue", "累计净值", "numeric", ""),
    ])
    common = [
        ("d_cldate", "数据日期", "date", ""),
        ("c_projname", "项目名称", "varchar", ""),
        ("c_oper_mode_orig", "项目运行方式（原始）", "varchar", ""),
        ("c_oper_mode", "项目运行方式", "varchar", ""),
    ]
    for name, extra_fields in extra_tables:
        _add_table(rules, name=name, cn=name, dimension="项目", fields=[
            *common, ("c_projinnercode", "项目编号", "varchar", "Y"), *extra_fields,
        ])
    _add_table(rules, name=DETAIL, cn="募集明细表", dimension="项目内部编号＋合同ID", fields=[
        *common, ("c_projinnercode", "项目编号", "varchar", "Y"),
        ("c_pactid", "合同id", "varchar", "Y"), ("f_end_acc_nav", "期末累计净值", "numeric", ""),
    ])
    _add_table(rules, name=SUMMARY, cn="募集信息汇总中间表", dimension="项目内部编号＋省级地区＋客户类型", fields=[
        *common, ("c_projinnercode", "项目编号", "varchar", ""),
        ("c_rowid", "项目、地区、客户类型组合标识", "varchar", "Y"), ("f_end_acc_nav", "期末累计净值", "numeric", ""),
    ])
    document = rules.storage.active_document()
    tables = {t["table_name"]: t["id"] for t in rules.storage.doc_tables(document["id"])}
    with rules.storage.database.begin() as conn:
        for field, source_field, caption in [("c_projinnercode", "c_projcode", "项目编号"),
                                            ("c_projname", "c_projname", "项目名全称")]:
            conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.table_id == tables[PROJECT],
                DOC_FIELDS.c.field_name == field).values(source_table="reg_data_market.reg_pub_project_info",
                    source_field=source_field, logic=f"直接取项目信息表的{caption}[{source_field}]。"))
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name.in_(["c_oper_mode", "c_oper_mode_orig"]))
                     .values(dictionary=DICTIONARY))
        if different_codes:
            conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.table_id == tables[SUMMARY],
                DOC_FIELDS.c.field_name == "c_oper_mode_orig").values(dictionary="7-开放式净值型\n8-封闭式净值型"))
    return rules, model


@pytest.mark.parametrize("request_text,different_codes", [(REQUEST, False), (PHYSICAL_REQUEST, True)])
def test_three_table_local_conditional_previews_tests_and_saved_drafts(request_text, different_codes):
    rules, model = _conditional_rules(different_codes=different_codes)
    result = rules.parse_rule_request(user(), _request(request_text=request_text))
    options = {v["candidate"]["table_name"]: v["candidate"] for v in result.get("candidate_options", [])}
    assert len(model.calls) == 2
    assert set(options) == {PROJECT, DETAIL, SUMMARY}
    definitions = []
    for name, metric, key in [(PROJECT, "f_totalnetvalue", "c_projinnercode"), (DETAIL, "f_end_acc_nav", "c_pactid"),
                              (SUMMARY, "f_end_acc_nav", "c_rowid")]:
        candidate = options[name]
        preview = candidate["preview"]
        definition = preview["definition"]
        assert definition["expression"] == {"left": metric, "op": "is_null"}
        assert definition["business_key"] == key and definition["report_date_field"] == "d_cldate"
        values = ["7", "8"] if name == SUMMARY and different_codes else ["1", "3"]
        assert definition["filters"] == [{"table": "base", "field": "c_oper_mode_orig", "op": "in",
                                         "value": values, "confirmed": True}]
        assert name in preview["sql_preview"] and "IS NULL" in preview["sql_preview"] and " IN " in preview["sql_preview"]
        result = rules.test_candidate(user(), {"definition": definition, "expected_hash": preview["content_sha256"]})
        assert result["passed_count"] > 0 and result["failed_count"] == result["not_run_count"] == 0
        definitions.append(definition)
    saved = rules.batch_save_candidates(user(), {"request_key": str(uuid4()), "definitions": definitions})
    assert saved["count"] == 3 and all(rule["status"] == "draft" for rule in saved["rules"])
    assert len({rule["id"] for rule in saved["rules"]}) == 3


def test_ineligible_objects_do_not_displace_grounded_options():
    rules, _ = _conditional_rules(extra_tables=[
        ("aa_similar", [("wrong", "累计净值日期", "date", "")]),
        ("ab_historic", [("prior", "上期累计净值", "numeric", "")]),
        ("ac_opening", [("initial", "期初累计净值", "numeric", "")]),
        ("ad_ambiguous", [("metric_a", "期末累计净值", "numeric", ""), ("metric_b", "期末累计净值", "numeric", "")]),
    ])
    result = rules.parse_rule_request(user(), _request(request_text=PHYSICAL_REQUEST))
    assert {o["candidate"]["table_name"] for o in result.get("candidate_options", [])} == {PROJECT, DETAIL, SUMMARY}


def test_peer_missing_dictionary_cannot_use_the_primary_tables_codes():
    rules, _ = _conditional_rules()
    tables = rules.storage.doc_tables(rules.storage.active_document()["id"])
    summary_id = next(item["id"] for item in tables if item["table_name"] == SUMMARY)
    with rules.storage.database.begin() as connection:
        connection.execute(update(DOC_FIELDS).where(
            DOC_FIELDS.c.table_id == summary_id, DOC_FIELDS.c.field_name == "c_oper_mode_orig",
        ).values(dictionary="【RHZD0008】"))
    result = rules.parse_rule_request(user(), _request(request_text=PHYSICAL_REQUEST))
    assert {o["candidate"]["table_name"] for o in result.get("candidate_options", [])} == {PROJECT, DETAIL}


def test_period_in_composite_key_is_already_bound_by_the_report_date():
    rules, _ = _conditional_rules()
    with rules.storage.database.begin() as connection:
        connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "d_cldate").values(is_pk="Y"))
    result = rules.parse_rule_request(user(), _request(request_text=REQUEST))
    keys = {o["candidate"]["table_name"]: o["candidate"]["business_key"] for o in result["candidate_options"]}
    assert keys == {PROJECT: "c_projinnercode", DETAIL: "c_pactid", SUMMARY: "c_rowid"}


def test_base_measure_ambiguity_keeps_its_question_and_blocks_compilation(monkeypatch):
    rules, _ = _conditional_rules()
    with rules.storage.database.begin() as connection:
        connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "f_start_totalnetvalue")
                           .values(field_cn="累计净值"))
    monkeypatch.setattr(rules, "preview_candidate", lambda *_: pytest.fail("同表字段未确认前不应编译预览"))
    result = rules.parse_rule_request(user(), _request(request_text=PHYSICAL_REQUEST))
    question = next(item for item in result["questions"] if item["id"] == "expression.left")
    assert {o["value"] for o in question["options"]} == {"f_totalnetvalue", "f_start_totalnetvalue"}
    assert result["preview"] is None and not result["can_enable"]


def test_documented_options_with_an_independent_blocker_do_not_compile(monkeypatch):
    rules, _ = _conditional_rules(unsupported=["还需系统支持另一项汇总"])
    monkeypatch.setattr(rules, "preview_candidate", lambda *_: pytest.fail("未决事项处理前不应编译预览"))
    result = rules.parse_rule_request(user(), _request(request_text=PHYSICAL_REQUEST))
    options = result.get("candidate_options", [])
    assert len(options) == 3
    for item in options:
        candidate = item["candidate"]
        assert candidate["unsupported_requirements"] and candidate["preview"] is None and not candidate["can_enable"]


def test_shorthand_rebuilds_three_independent_scope_questions_without_sql(monkeypatch):
    rules, _ = _conditional_rules(different_codes=True, proposed_filters=[
        {"table": "base", "field": "c_oper_mode_orig", "op": "in", "value": ["1", "3"]},
    ])
    tables = rules.storage.doc_tables(rules.storage.active_document()["id"])
    detail_id = next(t["id"] for t in tables if t["table_name"] == DETAIL)
    with rules.storage.database.begin() as connection:
        connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.table_id == detail_id,
            DOC_FIELDS.c.field_name == "c_oper_mode").values(field_name="local_mode", dictionary="A-净值型\nB-非净值型"))
    with monkeypatch.context() as guard:
        guard.setattr(rules, "preview_candidate", lambda *_a, **_k: pytest.fail("每张表的筛选范围均待确认"))
        result = rules.parse_rule_request(user(), _request(request_text="净值型项目的累计净值不得为空"))
    options = {item["candidate"]["table_name"]: item["candidate"] for item in result.get("candidate_options", [])}
    assert set(options) == {PROJECT, DETAIL, SUMMARY}
    for table, candidate in options.items():
        assert candidate["preview"] is None and not candidate["can_enable"] and not candidate["filters"][0]["confirmed"]
        assert [q["id"] for q in candidate["questions"]] == ["filters.0"]
        question = candidate["questions"][0]
        assert candidate["uncertainties"] == [question["uncertainty"]]
        recommended = [o["selection"]["field"] for o in question["options"] if o.get("tag") == "模型建议"]
        assert recommended == (["c_oper_mode_orig"] if table == PROJECT else [])
        selections = {option["selection"]["field"]: option["selection"] for option in question["options"]}
        current_field = "local_mode" if table == DETAIL else "c_oper_mode"
        assert set(selections) == {current_field, "c_oper_mode_orig"}
        assert selections[current_field]["value"] == ("A" if table == DETAIL else ["1", "3"])
        assert selections["c_oper_mode_orig"]["value"] == (["7", "8"] if table == SUMMARY else ["1", "3"])
        for selected in selections.values():
            decision = {**candidate, "questions": [], "uncertainty_resolutions": [selected["field"]], "filters": [selected]}
            preview = rules.preview_candidate(user(), decision)
            assert preview["definition"]["filters"] == [selected]
            assert table in preview["sql_preview"] and selected["field"] in preview["sql_preview"]


def test_shorthand_unique_peer_can_preview_while_other_tables_wait():
    rules, _ = _conditional_rules()
    tables = rules.storage.doc_tables(rules.storage.active_document()["id"])
    summary_id = next(t["id"] for t in tables if t["table_name"] == SUMMARY)
    with rules.storage.database.begin() as connection:
        connection.execute(delete(DOC_FIELDS).where(DOC_FIELDS.c.table_id == summary_id,
                                                     DOC_FIELDS.c.field_name == "c_oper_mode"))
    result = rules.parse_rule_request(user(), _request(request_text="净值型项目的累计净值不得为空"))
    options = {item["candidate"]["table_name"]: item["candidate"] for item in result.get("candidate_options", [])}
    assert set(options) == {PROJECT, DETAIL, SUMMARY}
    assert options[SUMMARY]["preview"]["definition"]["filters"][0]["field"] == "c_oper_mode_orig"
    assert not options[SUMMARY]["questions"] and not options[SUMMARY]["uncertainties"]
    assert options[PROJECT]["preview"] is None and options[DETAIL]["preview"] is None
