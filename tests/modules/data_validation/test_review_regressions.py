"""复核回归：关联证据、消息转义、执行期类型漂移、数据源白名单。

只覆盖审查中确认的四类风险，不连接真实模型或业务库。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from auto_check.modules.data_validation.compiler import compile_rule
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.executor import execute_version
from auto_check.app.data_source_platform import ensure_readonly_sql
from auto_check.modules.data_validation.storage import DOC_TABLES
from tests.modules.data_validation.support import (
    Metadata, SequenceModel, doc_xlsx_bytes, service, user,
)
from tests.modules.data_validation.test_ai_service import (
    _Processes, _generate_payload, _request, _rules_with_doc, _select_payload,
)
from tests.modules.data_validation.test_query_generation import (
    FIELDS, make_rules, resolved_definition,
)


class _RecordingMetadata(Metadata):
    """记录 describe/execute 调用，确保被拒绝的路径没有触达业务库。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.describe_calls: list[tuple[str, str]] = []
        self.select_calls: list[dict] = []

    def describe_table(self, source_id, table_name):
        self.describe_calls.append((str(source_id), str(table_name)))
        return super().describe_table(source_id, table_name)

    def execute_select(self, source_id, sql, params, timeout_seconds, max_rows):
        self.select_calls.append({"sql": sql, "params": dict(params)})
        return super().execute_select(source_id, sql, params, timeout_seconds, max_rows)


# ---------------------------------------------------------------------------
# 1) 已保存的两表规则：get_rule 补充 related_columns，但不改 definition/hash
# ---------------------------------------------------------------------------


def test_saved_related_rule_returns_related_columns_without_touching_version() -> None:
    rules, _model = make_rules(related=True)
    candidate = rules.parse_rule_request(user(), _request(request_text="存续项目实收信托一般不为0"))
    definition = resolved_definition(candidate)
    definition["null_policy"] = "skip"
    preview = rules.preview_candidate(user(), definition)
    rule = rules.save_draft(user(), definition)

    version = rules.storage.latest_version(rule["id"])
    detail = rules.get_rule(user(), rule["id"])
    assert detail["definition"] == version["definition"]
    assert detail["content_sha256"] == version["content_sha256"]
    assert "related_columns" not in detail["definition"]
    assert detail["related_columns"] == preview["related_columns"]
    assert [item["column_name"] for item in detail["related_columns"]] == [name for name, *_ in FIELDS]

    # 原样重载后仍可保存新版本，且关联列仍由当前文档可信补充。
    second = rules.save_draft(user(), detail["definition"], int(rule["id"]))
    assert int(second["version_no"]) == 2
    reloaded = rules.get_rule(user(), rule["id"])
    assert int(reloaded["version_no"]) == 2
    assert reloaded["content_sha256"] == version["content_sha256"]
    assert [item["column_name"] for item in reloaded["related_columns"]] == [name for name, *_ in FIELDS]


# ---------------------------------------------------------------------------
# 2) violation_message：反斜线必须绑定；旧的字面量缓存必须拒绝执行
# ---------------------------------------------------------------------------


def _message_definition(message: str) -> dict:
    return {
        "rule_type": "field_compare",
        "dialect": "mysql",
        "table_name": "loan",
        "business_key": "project_code",
        "report_date_field": "report_date",
        "violation_message": message,
        "null_policy": "skip",
        "equality_policy": "allow_equal",
        "expression": {"left": "maturity_date", "op": "lt", "right": "issue_date"},
        "project_context": {
            "mode": "base", "code_field": "project_code", "name_field": "project_name",
            "confirmed": True,
        },
    }


_MESSAGE_COLUMNS = [
    {"column_name": "project_code", "data_type": "varchar", "comment": "项目编号"},
    {"column_name": "project_name", "data_type": "varchar", "comment": "项目名称"},
    {"column_name": "maturity_date", "data_type": "date", "comment": "到期日"},
    {"column_name": "issue_date", "data_type": "date", "comment": "发放日"},
    {"column_name": "report_date", "data_type": "date", "comment": "报送日期"},
]


def _legacy_message_definition(message: str) -> dict:
    """非项目口径旧规则：用于验证与项目身份无关的 SQL 绑定/缓存拒绝路径。"""
    definition = {**_message_definition(message), "business_key": "contract_no"}
    definition.pop("project_context", None)
    return definition


_LEGACY_MESSAGE_COLUMNS = [
    {"column_name": "contract_no", "data_type": "varchar", "comment": "合同编号"},
    {"column_name": "maturity_date", "data_type": "date", "comment": "到期日"},
    {"column_name": "issue_date", "data_type": "date", "comment": "发放日"},
    {"column_name": "report_date", "data_type": "date", "comment": "报送日期"},
]


def test_backslash_message_is_bound_and_external_params_cannot_override_it() -> None:
    message = "期限\\'异常"
    sql, params = compile_rule({"definition": _message_definition(message)})
    assert ":violation_message" in sql
    assert message not in sql
    assert params["violation_message"] == message
    ensure_readonly_sql(sql)

    metadata = _RecordingMetadata(columns=_MESSAGE_COLUMNS)
    run = execute_version(
        {"definition": _message_definition(message)},
        {"report_date": "2026-01-01", "violation_message": "外部覆盖"},
        metadata,
    )
    assert run.status in {"PASS", "VIOLATION"}
    assert metadata.select_calls, "合法绑定消息应真正执行"
    assert ":violation_message" in metadata.select_calls[0]["sql"]
    assert metadata.select_calls[0]["params"]["violation_message"] == message


def test_single_quote_message_stays_doubled_and_readonly_safe() -> None:
    sql, params = compile_rule({"definition": _message_definition("期限'异常")})
    assert "期限''异常" in sql
    assert "violation_message" not in params
    ensure_readonly_sql(sql)


def test_stale_literal_cache_with_backslash_message_is_denied_before_execute() -> None:
    message = "期限\\'异常"
    metadata = _RecordingMetadata(columns=_LEGACY_MESSAGE_COLUMNS)
    run = execute_version(
        {"definition": _legacy_message_definition(message), "sql_text": "SELECT 'stale literal'"},
        {"report_date": "2026-01-01"},
        metadata,
    )
    assert run.status == "ERROR"
    assert run.error_code == "SQL_POLICY_DENIED"
    assert metadata.select_calls == []


# ---------------------------------------------------------------------------
# 3) 实际元数据数值列漂移成 varchar：新规格执行前拒绝，且不查询业务库
# ---------------------------------------------------------------------------


def test_execution_rejects_actual_type_drift_without_query() -> None:
    definition = {
        "rule_type": "field_compare",
        "dialect": "mysql",
        "table_name": "loan",
        "business_key": "project_code",
        "report_date_field": "report_date",
        "violation_message": "金额异常",
        "null_policy": "violate",
        "equality_policy": "allow_equal",
        "expression": {"left": "amount", "op": "is_null"},
        "filters": [{"table": "base", "field": "amount", "op": "eq", "value": 100, "confirmed": True}],
    }
    metadata = _RecordingMetadata(columns=[
        {"column_name": "project_code", "data_type": "varchar"},
        {"column_name": "report_date", "data_type": "date"},
        {"column_name": "amount", "data_type": "varchar"},  # 文档假设 numeric，真实结构已漂移
    ])
    run = execute_version({"definition": definition}, {"report_date": "2026-01-01"}, metadata)
    assert run.status == "ERROR"
    assert run.error_code == "MAPPING_DRIFT"
    assert metadata.select_calls == []


# ---------------------------------------------------------------------------
# 4) 非白名单数据源：describe / parse / preview 均拒绝，且不读取表结构
# ---------------------------------------------------------------------------


class _MultiSourceMetadata(_RecordingMetadata):
    def list_sources(self):
        return [
            SimpleNamespace(id="ok", name="监管报表", dialect="mysql"),
            SimpleNamespace(id="bad", name="其他业务库", dialect="mysql"),
        ]


def _whitelist_service() -> tuple:
    metadata = _MultiSourceMetadata()
    model = SequenceModel([_select_payload(), _generate_payload()])
    _database, rules = service(metadata=metadata, model=model, report_navigation=_Processes())
    rules.import_document(user(), "doc.xlsx", doc_xlsx_bytes(fields=FIELDS))
    return metadata, model, rules


def test_non_allowlisted_source_is_rejected_for_describe_parse_and_preview() -> None:
    metadata, model, rules = _whitelist_service()
    # 让文档中确实存在“其他业务库”的表，排除“只是没匹配到文档”的假阳性。
    with rules.storage.database.begin() as connection:
        connection.execute(
            DOC_TABLES.update().where(DOC_TABLES.c.table_name == "test_table")
            .values(data_source_name="其他业务库")
        )

    with pytest.raises(AppError) as describe_error:
        rules.describe_source_table("bad", "test_table")
    assert describe_error.value.code == "SOURCE_UNAVAILABLE"
    assert metadata.describe_calls == []

    with pytest.raises(AppError) as parse_error:
        rules.parse_rule_request(user(), _request(source_id="bad"))
    assert parse_error.value.code == "SOURCE_UNAVAILABLE"
    assert model.calls == []
    assert metadata.describe_calls == []

    definition = {
        "rule_type": "field_compare",
        "dialect": "mysql",
        "source_id": "bad",
        "table_name": "test_table",
        "business_key": "row_id",
        "report_date_field": "business_day",
        "violation_message": "金额异常",
        "null_policy": "skip",
        "equality_policy": "allow_equal",
        "expression": {"left": "amount", "op": "gt", "right_type": "value", "right": 0},
    }
    with pytest.raises(AppError) as preview_error:
        rules.preview_candidate(user(), {"definition": definition})
    assert preview_error.value.code == "SOURCE_UNAVAILABLE"
    assert metadata.describe_calls == []
