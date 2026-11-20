import pytest

from auto_check.modules.data_validation.storage import RULES
from tests.modules.data_validation.support import Metadata, loan_definition, service, user
from tests.modules.data_validation.test_execution_result_details import registered
from auto_check.modules.data_validation.compiler import compile_rule


def test_results_search_and_review_use_frozen_execution_version():
    db, svc = service(metadata=Metadata())
    sql = "SELECT project_code AS 合同编号 FROM loan"
    original = loan_definition(name="旧版口径", description="本次执行说明", violation_message="本次提醒条件")
    rid = registered(svc.storage, original, sql)
    task = svc.start_task(user(), {"rule_ids": [rid], "report_period": "2026-09-30"})
    other = registered(svc.storage, loan_definition(name="无关规则"), "SELECT project_code FROM loan")
    with db.begin() as conn:
        conn.execute(RULES.update().where(RULES.c.id == rid).values(name="新版规则", status="deleted"))
    detail = svc.task_detail(user(), task["id"], {"keyword": "旧版", "page": 5})
    assert detail["rule_page"]["total"] == 1
    assert detail["rule_page"]["page"] == 1
    assert detail["rule_page"]["keyword"] == "旧版"
    review = detail["rules"][0]
    assert review["name"] == "旧版口径"
    assert review["sql_text"] == sql
    assert review["description"] == "本次执行说明"
    assert review["violation_message"] == "本次提醒条件"
    assert svc.task_detail(user(), task["id"], {"keyword": "新版"})["rules"] == []
    assert svc.task_detail(user(), task["id"], {"keyword": "旧%"})["rules"] == []
    assert svc.task_detail(user(), task["id"], {"keyword": f"DV{rid:06d}"})["rule_page"]["total"] == 1
    assert other != rid


@pytest.mark.parametrize(("keyword", "expected"), [("DV", 1), ("DV0000", 1), ("v000", 1), ("DV9999999999999999999", 0)])
def test_result_search_matches_display_code_and_accepts_long_text(keyword, expected):
    _, svc = service(metadata=Metadata())
    rid = registered(svc.storage, loan_definition(name="余额校验"), "SELECT project_code FROM loan")
    task = svc.start_task(user(), {"rule_ids": [rid], "report_period": "2026-09-30"})
    assert svc.task_detail(user(), task["id"], {"keyword": keyword})["rule_page"]["total"] == expected


def test_result_review_inlines_frozen_filters_and_batch_date_without_changing_template():
    _, svc = service(metadata=Metadata())
    definition = loan_definition(filters=[{"table": "base", "field": "project_code", "op": "in", "value": ["1", "3"]}], report_date="2000-01-01")
    sql, _ = compile_rule({"definition": definition})
    rid = registered(svc.storage, definition, sql)
    task = svc.start_task(user(), {"rule_ids": [rid], "report_period": "2026-10-31"})
    review = svc.task_detail(user(), task["id"], {})["rules"][0]
    assert review["sql_text"] == sql
    assert ":report_date" in sql and ":filter_1_0" in sql
    assert "'2026-10-31'" in review["sql_display"]
    assert "'1', '3'" in review["sql_display"]
    assert ":report_date" not in review["sql_display"] and ":filter_1_0" not in review["sql_display"]
    assert "2000-01-01" not in review["sql_display"]
