import pytest

from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.executor import execute_version
from auto_check.modules.data_validation.sql_guard import guard_sql
from tests.modules.data_validation.support import Metadata


def test_guard_rejects_injected_identifier_and_write() -> None:
    metadata = Metadata(columns=[{"column_name": "id"}, {"column_name": "maturity_date"}])
    statements = (
        "SELECT maturity_date; delete from t",
        "SELECT 1; DELETE FROM t",
        "SELECT pg_sleep(1)",
    )
    for statement in statements:
        with pytest.raises(AppError) as error:
            guard_sql("mysql", statement, {"maturity_date"})
        assert error.value.code == "SQL_POLICY_DENIED"
        with pytest.raises(AppError):
            execute_version(
                {
                    "definition": {
                        "dialect": "mysql", "source_id": "src", "table_name": "loan",
                        "business_key": "id", "rule_type": "custom_sql",
                    },
                    "sql_text": statement,
                },
                {},
                metadata,
            )
    assert metadata.calls == []


def test_missing_column_is_mapping_drift() -> None:
    metadata = Metadata(columns=[{"column_name": "project_code"}, {"column_name": "issue_date"}])
    result = execute_version(
        {"definition": {
            "dialect": "mysql", "source_id": "src", "table_name": "loan",
            "business_key": "project_code", "rule_type": "field_compare",
            "expression": {"left": "maturity_date", "op": "lt", "right": "issue_date"},
            "violation_message": "贷款期限异常", "null_policy": "skip",
        }, "sql_text": ""},
        {},
        metadata,
    )
    assert result.status == "ERROR"
    assert result.error_code == "MAPPING_DRIFT"
    assert metadata.calls == []
