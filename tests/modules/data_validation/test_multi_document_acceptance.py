"""Acceptance of the user's actual cross-table measure ambiguity, not same-name mocks."""
from sqlalchemy import insert, update

from auto_check.modules.data_validation.storage import DOC_FIELDS, DOC_TABLES
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _generate_payload, _request, _rules_with_doc, _select_payload

AMBIGUITY = "无法确定‘实收’是指实收信托规模还是实收信托余额，因为 reg_pub_ta_pact_info 和 reg_pub_accountbalance_sum 均包含相关字段"


def _finance_rules(extra_uncertainties=(), *, clarification=False):
    selection = _select_payload(target={"table": "reg_pub_ta_pact_info"}, uncertainties=[AMBIGUITY])
    if clarification:
        selection["result_type"] = "clarification"
    draft = _generate_payload(expression={"left": "f_actual_trust_scale", "op": "eq", "right_type": "value", "right": 0},
                              uncertainties=[AMBIGUITY, *extra_uncertainties])
    fields = [("c_pactid", "合同编号", "varchar", "Y"), ("c_projcode", "项目代码", "varchar", ""),
              ("c_projname", "项目名称", "varchar", ""),
              ("f_actual_trust_scale", "实收信托规模（委托资产，合同份额余额+待结转收益）", "numeric", ""),
              ("d_cldate", "数据日期", "date", "")]
    rules, model = _rules_with_doc([selection, draft], fields=fields)
    table = rules.storage.doc_tables(rules.storage.active_document()["id"])[0]
    template = rules.storage.doc_fields(table["id"])[0]
    with rules.storage.database.begin() as connection:
        connection.execute(update(DOC_TABLES).where(DOC_TABLES.c.id == table["id"]).values(
            table_name="reg_pub_ta_pact_info", table_name_cn="资金端合同明细表", dimension="合同"))
        for name, label, field, field_label, period in (
            ("reg_pub_project_info", "项目信息表", "f_endp_amt", "实收信托", "d_cldate"),
            ("reg_pub_accountbalance_sum", "项目余额汇总表", "f_balan_endp_amt", "实收信托余额", "d_balancedate"),
        ):
            values = {key: value for key, value in table.items() if key != "id"}
            values.update(table_name=name, table_name_cn=label, dimension="项目")
            table_id = connection.execute(insert(DOC_TABLES).values(**values)).inserted_primary_key[0]
            for column_name, comment, data_type, is_pk in (
                ("c_projcode", "项目代码", "varchar", "Y"), ("c_projname", "项目名称", "varchar", ""),
                (field, field_label, "numeric", ""),
                (period, "数据日期" if period == "d_cldate" else "余额日期", "date", ""),
            ):
                column = {key: value for key, value in template.items() if key != "id"}
                column.update(table_id=table_id, field_name=column_name, field_cn=comment,
                              data_type=data_type, is_pk=is_pk)
                connection.execute(insert(DOC_FIELDS).values(**column))
    return rules, model


def test_actual_trust_measures_offer_independent_schemes_instead_of_rewriting_request():
    rules, model = _finance_rules()
    result = rules.parse_rule_request(user(), _request(request_text="项目得实收不得为0"))
    options = result.get("candidate_options", [])
    assert len(options) == 3
    assert result["table_name"] == "reg_pub_project_info"
    assert options[0]["recommended"] and options[0]["candidate"]["table_name"] == result["table_name"]
    actual = {item["candidate"]["table_name"]: item["candidate"] for item in options}
    assert len({item["candidate"]["rule_name"] for item in options}) == 3
    for table, field, key, date in (
        ("reg_pub_project_info", "f_endp_amt", "c_projcode", "d_cldate"),
        ("reg_pub_ta_pact_info", "f_actual_trust_scale", "c_pactid", "d_cldate"),
        ("reg_pub_accountbalance_sum", "f_balan_endp_amt", "c_projcode", "d_balancedate"),
    ):
        candidate = actual[table]
        assert candidate["expression"] == {"left": field, "op": "eq", "right_type": "value", "right": 0}
        assert candidate["business_key"] == key and candidate["report_date_field"] == date
        assert candidate["uncertainties"] == []
        assert candidate["preview"]["definition"].get("uncertainties", []) == []
        assert not candidate.get("questions")
        assert table in candidate["preview"]["sql_preview"] and field in candidate["preview"]["sql_preview"]
    assert len(model.calls) == 2
    assert rules.storage.visible_rules("1") == []
    assert result["comparison_suggestions"] == [], "没有模型提案时不补程序模板建议"


def test_target_choice_never_erases_unit_or_relation_uncertainty():
    unresolved = "目标表币种不明确，不能比较金额"
    rules, _model = _finance_rules([unresolved])
    result = rules.parse_rule_request(user(), _request(request_text="项目得实收不得为0"))
    assert len(result.get("candidate_options", [])) == 3
    for option in result["candidate_options"]:
        assert unresolved in option["candidate"]["uncertainties"]
        assert option["candidate"].get("can_enable") is not True


def test_selector_ambiguity_with_real_document_options_continues_without_rewriting():
    rules, model = _finance_rules(clarification=True)
    result = rules.parse_rule_request(user(), _request(request_text="项目得实收不得为0"))
    assert len(result.get("candidate_options", [])) == 3
    assert result["table_name"] == "reg_pub_project_info"
    assert len(model.calls) == 2
    assert all(not option["candidate"]["uncertainties"] for option in result["candidate_options"])


def test_counterpart_discovery_never_discards_existing_scope_filters():
    rules, _model = _finance_rules()
    candidate = rules.parse_rule_request(user(), _request(request_text="项目得实收不得为0"))
    candidate.pop("candidate_options", None)
    candidate.pop("comparison_suggestions", None)
    candidate["filters"] = [{"table": "base", "field": "c_projcode", "op": "eq",
                             "value": "ONLY_PROJECT_A", "confirmed": True}]
    tables = rules.storage.doc_tables(rules.storage.active_document()["id"])
    table = next(item for item in tables if item["table_name"] == candidate["table_name"])
    result = rules._attach_candidate_options(
        user=user(), source=rules.list_selectable_sources()[0], tables=tables,
        fields_by_table={item["id"]: rules.storage.doc_fields(item["id"]) for item in tables},
        table=table, refined=candidate, request_text="仅检查项目 ONLY_PROJECT_A 的实收不得为0",
    )
    assert result is candidate and result["filters"][0]["value"] == "ONLY_PROJECT_A"
    assert not result.get("candidate_options")
