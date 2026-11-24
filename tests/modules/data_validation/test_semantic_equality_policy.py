import sqlite3

import pytest

from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request, _rules_with_doc


@pytest.mark.parametrize("op,word,implied,hits", [
    ("neq", "不相等", "allow_equal", {"before", "after"}),
    ("eq", "相等", "reject_equal", {"equal"}),
    ("lt", "早于", "allow_equal", {"before"}),
    ("lte", "早于或等于", "reject_equal", {"before", "equal"}),
    ("gt", "晚于", "allow_equal", {"after"}),
    ("gte", "晚于或等于", "reject_equal", {"after", "equal"}),
])
def test_comparison_operator_determines_equality_without_a_model_metadata_question(op, word, implied, hits):
    fields = [("row_id", "业务编号", "varchar", "Y"), ("business_day", "数据日期", "date", ""),
              ("planned", "计划日期", "date", ""), ("original", "原始日期", "date", "")]
    proposal = {
        "rule_name": "日期对比", "rule_type": "field_compare", "business_key": "row_id",
        "expression": {"left": "planned", "op": op, "right_type": "field", "right": "original"},
        "null_policy": "skip", "equality_policy": "reject_equal" if implied == "allow_equal" else "allow_equal",
        "violation_message": f"计划日期{word}原始日期",
        "semantic_intent": {"metrics": [
            {"side": "left", "term": "计划日期", "fields": ["planned"]},
            {"side": "right", "term": "原始日期", "fields": ["original"]},
        ], "scopes": [], "open_questions": []},
    }
    rules, model = _rules_with_doc([{"target": {"table": "test_table"}, "draft": proposal}], fields=fields)
    result = rules.parse_rule_request(user(), _request(request_text=f"计划日期{word}原始日期时提醒", analysis_protocol=2))
    assert result["preview"] and not result["questions"] and not result["uncertainties"]
    definition = result["preview"]["definition"]
    assert definition["expression"] == proposal["expression"] and definition["equality_policy"] == implied
    assert len(model.calls) == 1
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE test_table(row_id text,business_day date,planned date,original date)")
        db.executemany("INSERT INTO test_table VALUES(?,?,?,?)", [
            ("before", "2026-11-23", "2026-11-22", "2026-11-23"),
            ("equal", "2026-11-23", "2026-11-23", "2026-11-23"),
            ("after", "2026-11-23", "2026-11-24", "2026-11-23"),
            ("missing", "2026-11-23", None, "2026-11-23"),
        ])
        preview = result["preview"]
        rows = db.execute(preview["sql_preview"], {**preview["sql_params"], "report_date": "2026-11-23"}).fetchall()
    assert {row[0] for row in rows} == hits
