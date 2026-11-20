import pytest

from auto_check.modules.data_validation.issue_query_results import collect_row, output_projection


@pytest.mark.parametrize("alias,name", [('"数据日期"', "数据日期"), ('`数据日期`', "数据日期"), ("数据日期", "数据日期"),
                                       ('"数据 日期"', "数据 日期"), ('"数据,日期"', "数据,日期"),
                                       ('"数据""日期"', '数据"日期'), ('`数据``日期`', '数据`日期')])
def test_explicit_chinese_sql_alias_is_the_display_name(alias, name):
    spec = {"rule_type": "custom_sql", "table_name": "project"}
    columns, status = output_projection(spec, f"SELECT cldate AS {alias} FROM project", False,
                                        [name], [{"column_name": "cldate", "comment": "旧备注"}], [])
    assert status == ""
    assert columns == [{"name": name, "label": name, "source_field": "cldate"}]
    assert collect_row(columns, status, {name: "2026-10-31"})["values"] == {name: "2026-10-31"}


def test_compiled_projection_preserves_actual_english_aliases():
    spec = {"rule_type": "field_compare", "table_name": "project", "business_key": "id",
            "include_result_fields": True, "report_date_field": "cldate",
            "expression": {"left": "nav", "op": "is_null"}}
    names = ["business_key", "violation_message", "data_date", "checked_value"]
    columns, _ = output_projection(spec, "", True, names, [{"column_name": "nav", "comment": "单位净值"}], [])
    assert [item["label"] for item in columns] == names


def test_english_alias_is_not_replaced_by_document_or_database_label():
    spec = {"rule_type": "custom_sql", "table_name": "project"}
    columns, status = output_projection(spec, "SELECT nav AS checked_value, cldate AS data_date, other FROM project",
                                        False, ["checked_value", "data_date", "other"],
                                        [{"column_name": "nav", "column_name_cn": "单位净值", "comment": "数据库备注"}], [])
    assert status == ""
    assert [item["label"] for item in columns] == ["checked_value", "data_date", "other"]


@pytest.mark.parametrize("sql", ['SELECT * FROM project', 'SELECT SUM(nav) AS "净值" FROM project',
                                  'WITH a AS (SELECT nav FROM project) SELECT nav AS "净值" FROM a'])
def test_chinese_alias_support_does_not_guess_unsupported_projection(sql):
    columns, status = output_projection({"rule_type": "custom_sql", "table_name": "project"}, sql, False,
                                        ["净值"], [], [])
    assert columns == [] and status == "unsupported_projection"


def test_chinese_aliases_survive_real_sql_result_storage_and_csv():
    import csv
    import io
    import sqlite3
    from types import SimpleNamespace
    from tests.modules.data_validation.support import Metadata, loan_definition, service, user
    from tests.modules.data_validation.test_execution_result_details import registered

    sql = 'SELECT project_code AS business_key, report_date AS "数据日期", amount AS "校验金额" FROM loan'
    columns = Metadata().columns + [{"column_name": "amount", "data_type": "numeric", "comment": "不会替换别名的备注"}]
    with sqlite3.connect(":memory:") as business:
        business.execute("CREATE TABLE loan(project_code text, report_date text, amount numeric)")
        business.execute("INSERT INTO loan VALUES('0001','2026-10-31',0)")

        def execute(_source, statement, params, **_limits):
            cursor = business.execute(statement, params)
            return SimpleNamespace(columns=[item[0] for item in cursor.description], rows=cursor.fetchall(), truncated=False)

        _db, rules = service(metadata=SimpleNamespace(describe_table=lambda *_: {"columns": columns}, execute_select=execute))
        rule_id = registered(rules.storage, loan_definition(rule_type="custom_sql", sql=sql), sql)
        task = rules.start_task(user(), {"rule_ids": [rule_id], "report_period": "2026-10-31"})
    issue = rules.list_task_issues(user(), task["id"])["items"][0]
    assert issue["query_result"]["values"] == {"business_key": "0001", "数据日期": "2026-10-31", "校验金额": 0}
    assert [item["label"] for item in issue["query_result"]["columns"]] == ["business_key", "数据日期", "校验金额"]
    exported = list(csv.DictReader(io.StringIO(rules.export_issues(user(), task["id"], "csv")["content"].decode())))
    assert exported[0]["数据日期"] == "2026-10-31" and exported[0]["校验金额"] == "0"
