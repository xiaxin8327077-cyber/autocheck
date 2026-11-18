from types import SimpleNamespace

import pytest

from auto_check.modules.data_validation.executor import execute_version
from auto_check.modules.data_validation.sql_guard import guard_generated_sql, guard_sql
from auto_check.modules.data_validation.contracts import AppError


BASE_COLUMNS = [
    {"column_name": "row_id", "data_type": "varchar"},
    {"column_name": "project_code", "data_type": "varchar"},
    {"column_name": "amount", "data_type": "decimal"},
    {"column_name": "status", "data_type": "varchar"},
    {"column_name": "report_date", "data_type": "date"},
]
RELATED_COLUMNS = [
    {"column_name": "id", "data_type": "varchar"},
    {"column_name": "project_code", "data_type": "varchar"},
    {"column_name": "limit_amount", "data_type": "decimal"},
    {"column_name": "is_valid", "data_type": "varchar"},
    {"column_name": "report_date", "data_type": "date"},
]


def _definition(**overrides):
    definition = {
        "rule_type": "field_compare",
        "dialect": "mysql",
        "source_id": "src",
        "table_name": "loan",
        "business_key": "row_id",
        "report_date_field": "report_date",
        "violation_message": "额度异常",
        "null_policy": "skip",
        "equality_policy": "reject_equal",
        "expression": {
            "left": "amount", "op": "gt", "right_type": "field",
            "right": "limit_amount", "right_table": "related",
        },
        "filters": [
            {"table": "base", "field": "status", "op": "eq", "value": "1", "confirmed": True},
            {"table": "related", "field": "is_valid", "op": "eq", "value": "Y", "confirmed": True},
        ],
        "join": {
            "table_name": "loan_detail",
            "on": [{"left": "project_code", "right": "project_code"}],
            "report_date_field": "report_date",
            "unmatched_policy": "exclude",
            "relationship_confirmed": True,
        },
    }
    definition.update(overrides)
    return definition


class Metadata:
    def __init__(self, base=None, related=None, rows=(), truncated=False, table_name="loan"):
        self.base = [
            {"column_name": "row_id", "data_type": "varchar"},
            {"column_name": "project_code", "data_type": "varchar"},
            {"column_name": "amount", "data_type": "decimal"},
            {"column_name": "status", "data_type": "varchar"},
            {"column_name": "report_date", "data_type": "date"},
        ] if base is None else base
        self.related = related
        self.rows = rows
        self.truncated = truncated
        self.calls = []
        self.table_name = table_name

    def describe_table(self, _source, table):
        if table == self.table_name:
            return {"columns": self.base, "mapping_version": "map"}
        if table == "loan_detail" and self.related is not None:
            return {"columns": self.related, "mapping_version": "map"}
        raise ValueError("SOURCE_UNAVAILABLE")

    def execute_select(self, _source, sql, params, timeout_seconds, max_rows):
        self.calls.append((sql, dict(params)))
        return SimpleNamespace(columns=("business_key",), rows=tuple(self.rows), truncated=self.truncated)


def _version(definition, sql=""):
    return {"definition": definition, "sql_text": sql}


def test_execute_new_spec_uses_exists_and_protects_bound_filters():
    metadata = Metadata(related=RELATED_COLUMNS, rows=(("R1",),))
    run = execute_version(
        _version(_definition()),
        {"report_date": "2026-09-30", "filter_1": "9", "filter_2": "N"},
        metadata,
    )
    assert run.status == "VIOLATION" and run.violation_count == 1
    sql, bound = metadata.calls[0]
    assert "EXISTS (SELECT 1 FROM `loan_detail` AS o" in sql
    assert bound["filter_1"] == "1" and bound["filter_2"] == "Y"
    assert bound["report_date"] == "2026-09-30"


def test_query_ready_gate_blocks_unconfirmed_execution():
    definition = _definition()
    definition["filters"][0]["confirmed"] = False
    metadata = Metadata(related=RELATED_COLUMNS)
    run = execute_version(_version(definition), {}, metadata)
    assert run.status == "ERROR" and run.error_code == "VALIDATION_ERROR"
    assert metadata.calls == []


def test_related_missing_column_and_date_drift_are_mapping_errors():
    metadata = Metadata(related=[column for column in RELATED_COLUMNS if column["column_name"] != "limit_amount"])
    run = execute_version(_version(_definition()), {}, metadata)
    assert run.status == "ERROR" and run.error_code == "MAPPING_DRIFT"
    assert metadata.calls == []

    drifted = [dict(column) for column in RELATED_COLUMNS]
    next(column for column in drifted if column["column_name"] == "report_date")["data_type"] = "datetime"
    metadata = Metadata(related=drifted)
    run = execute_version(_version(_definition()), {}, metadata)
    assert run.status == "ERROR" and run.error_code == "MAPPING_DRIFT"


def test_custom_sql_still_allowed_with_join_and_without_report_date_column():
    metadata = Metadata(base=[
        {"column_name": "id", "data_type": "varchar"},
        {"column_name": "maturity_date", "data_type": "date"},
    ], table_name="t")
    sql = "SELECT id FROM t JOIN u ON u.id = t.id WHERE t.dt = :report_date"
    run = execute_version(
        {"definition": {
            "rule_type": "custom_sql", "dialect": "mysql", "source_id": "src",
            "table_name": "t", "business_key": "id", "sql": sql,
        }, "sql_text": sql},
        {"report_date": "2026-09-30"},
        metadata,
    )
    assert run.status == "PASS" and metadata.calls[0][0] == sql


def test_generated_guard_rejects_explicit_join_but_custom_guard_keeps_it():
    with pytest.raises(AppError) as error:
        guard_generated_sql("mysql", "SELECT 1 FROM a JOIN b ON b.id = a.id", {"id"}, {"a", "b"})
    assert error.value.code == "SQL_POLICY_DENIED"
    guard_sql("mysql", "SELECT 1 FROM a JOIN b ON b.id = a.id", {"id"})
