from copy import deepcopy

import pytest
from sqlalchemy import update

from auto_check.modules.data_validation.parallel_checks import project_parallel_checks
from auto_check.modules.data_validation.storage import DOC_FIELDS
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request, _select_payload
from tests.modules.data_validation.test_followup_service_bridge import _rules

TABLE = "reg_pub_project_info"
FIELDS = [
    ("c_projcode", "项目编号", "varchar", "Y"), ("c_projname", "项目名全称", "varchar", ""),
    ("f_endp_amt", "实收信托", "numeric", ""), ("f_balan_fatotal", "资产大类科目余额", "numeric", ""),
    ("c_projstatus", "项目状态", "varchar", ""), ("pro_status", "项目状态", "varchar", ""),
    ("d_cldate", "数据日期", "date", ""),
]


def fixture(with_asset=True, dictionary=True):
    model = _select_payload(target={}, result_type="clarification",
                            unsupported_requirements=["项目、费用与科目余额必须三表关联"])
    rules, provider = _rules([model], table=TABLE, table_cn="项目信息表", dimension="项目",
        fields=FIELDS if with_asset else [row for row in FIELDS if row[0] != "f_balan_fatotal"],
        extra_tables=[{"name": "reg_pub_fa_fee", "cn": "FA费用表", "dimension": "项目、费用类型",
                       "fields": [("f_fee", "本期实收金额", "numeric", "")]},
                      {"name": "reg_pub_accountbalance_sum", "cn": "科目余额表", "dimension": "项目",
                       "fields": [("f_balan_fatotal", "资产大类科目余额", "numeric", "")]}])
    if dictionary:
        with rules.storage.database.begin() as conn:
            conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "c_projstatus").values(dictionary="1-存续"))
            conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "pro_status").values(dictionary="2-存续"))
    return rules, provider


@pytest.mark.parametrize("asset", ["资产", "资产大类科目余额"])
def test_project_exact_screenshot_previews_each_check_with_one_scope(asset):
    rules, provider = fixture()
    result = rules.parse_rule_request(user(), _request(request_text=f"存续项目的{asset}和实收不得小于0"))
    items = [entry["candidate"] for entry in result["candidate_options"]]
    assert len(items) == 2 and not provider.calls  # model's spurious three-table conclusion is never needed
    first, second = items
    assert [q["id"] for q in first["questions"]] == (["filters.0", "expression.left"] if asset == "资产" else ["filters.0"])
    assert [q["id"] for q in second["questions"]] == ["filters.0"]
    assert second["expression"]["left"] == "f_endp_amt"
    assert first["questions"][0] == second["questions"][0]
    selected = second["questions"][0]["options"][0]["selection"]
    assert selected["field"] == "c_projstatus" and selected["value"] == "1"
    for item, expected_field in zip(items, ["f_balan_fatotal", "f_endp_amt"]):
        definition = deepcopy(item)
        definition["expression"]["left"] = expected_field  # explicit asset choice if ambiguous
        definition["filters"] = [selected]
        definition["uncertainty_resolutions"] = ["已确认存续筛选"]
        preview = rules.preview_candidate(user(), {"definition": definition})
        sql = preview["sql_preview"]
        assert '"c_projstatus" = :filter_1' in sql and preview["sql_params"]["filter_1"] == "1"
        assert f'"{expected_field}" < :right_value' in sql and preview["sql_params"]["right_value"] == 0
        assert '"reg_pub_project_info"' in sql and '"c_projname" AS' in sql
        assert "reg_pub_fa_fee" not in sql and "reg_pub_accountbalance_sum" not in sql
        tests = rules.test_candidate(user(), {"definition": definition, "expected_hash": preview["content_sha256"]})
        assert tests["passed_count"] > 0 and tests["failed_count"] == tests["not_run_count"] == 0
        assert not preview["persisted"] and not tests["persisted"]
    assert rules.storage.visible_rules("1") == []


def test_missing_one_field_retains_the_known_check_and_missing_scope_blocks_both():
    rules, _ = fixture(with_asset=False, dictionary=False)
    result = rules.parse_rule_request(user(), _request(request_text="存续项目的资产和实收不得小于0"))
    asset, received = [entry["candidate"] for entry in result["candidate_options"]]
    assert "资产" in asset["parallel_blocked"] and asset["expression"]["left"] == ""
    assert "存续" in received["parallel_blocked"] and received["expression"]["left"] == "f_endp_amt"
    assert not received["preview"] and not asset["preview"]


@pytest.mark.parametrize("text", ["项目资产与实收比较不得小于0", "项目资产和实收不得小于0，零余额除外",
                                  "项目资产和合同汇总不得小于0", "项目资产或实收不得小于0",
                                  "项目资产和实收不得小于0或大于10", "项目资产和实收不得小于0万元"])
def test_does_not_reduce_different_rule_shapes_to_simple_parallel_checks(text):
    assert project_parallel_checks(text, [{"field_name": name, "field_cn": cn, "data_type": kind}
                                          for name, cn, kind, _ in FIELDS]) is None
