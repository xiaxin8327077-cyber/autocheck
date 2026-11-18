from types import SimpleNamespace

from auto_check.modules.data_validation.executor import RuleRun, execute_version


BASE_COLUMNS = [
    {"column_name": "contract_no", "data_type": "varchar"},
    {"column_name": "project_code", "data_type": "varchar"},
    {"column_name": "project_name", "data_type": "varchar"},
    {"column_name": "amount", "data_type": "decimal"},
    {"column_name": "report_date", "data_type": "date"},
]
DIM_COLUMNS = [
    {"column_name": "project_code", "data_type": "varchar"},
    {"column_name": "project_name", "data_type": "varchar"},
    {"column_name": "report_date", "data_type": "date"},
]


def _definition(mode="base", **overrides):
    context = {"mode": mode, "code_field": "project_code", "name_field": "project_name", "confirmed": True}
    if mode == "lookup":
        context.update({
            "table_name": "dim_project",
            "key": {"left": "project_code", "right": "project_code"},
            "date_field": "report_date",
            "unique_evidence": {"kind": "pk", "fields": ["project_code", "report_date"], "confirmed": True},
        })
    definition = {
        "rule_type": "field_compare", "dialect": "mysql", "source_id": "src",
        "table_name": "contract", "business_key": "contract_no", "report_date_field": "report_date",
        "violation_message": "金额异常", "null_policy": "skip", "equality_policy": "allow_equal",
        "expression": {"left": "amount", "op": "gt", "right_type": "value", "right": 0},
        "project_context": context,
    }
    definition.update(overrides)
    return definition


class Metadata:
    def __init__(self, rows=(), columns=None, base=None, other=None):
        self.rows = rows
        self.base = BASE_COLUMNS if base is None else base
        self.other = DIM_COLUMNS if other is None else other
        self.columns = columns or ("business_key", "violation_message", "issue_kind", "project_code", "project_name")
        self.calls = []
        self.describe_calls = []

    def describe_table(self, _source, table):
        self.describe_calls.append(table)
        if table == "contract":
            return {"columns": self.base, "mapping_version": "map"}
        if table == "dim_project":
            return {"columns": self.other, "mapping_version": "map"}
        raise ValueError("SOURCE_UNAVAILABLE")

    def execute_select(self, _source, sql, params, timeout_seconds, max_rows):
        self.calls.append(sql)
        return SimpleNamespace(columns=self.columns, rows=tuple(self.rows), truncated=False)


def test_rule_run_original_four_positional_args_still_construct():
    run = RuleRun("PASS", 0, False, "")
    assert run.columns == () and run.rows == ()


def test_base_context_rows_are_dicts_and_count_is_unchanged():
    metadata = Metadata(rows=[
        ("C1", "金额异常", "comparison", "P1", "项目一"),
        ("C2", "金额异常", "missing_value", None, None),
    ])
    run = execute_version({"definition": _definition()}, {"report_date": "2026-09-30"}, metadata)
    assert run.status == "VIOLATION" and run.violation_count == 2
    assert run.columns == ("business_key", "violation_message", "issue_kind", "project_code", "project_name", "project_name_status")
    assert run.rows[0] == {
        "business_key": "C1", "violation_message": "金额异常", "issue_kind": "comparison",
        "project_code": "P1", "project_name": "项目一", "project_name_status": "ok",
    }
    assert run.rows[1]["project_name_status"] == "missing_code"


def test_lookup_context_duplicate_and_missing_reference_are_visible():
    metadata = Metadata(
        rows=[("C1", "金额异常", "missing_reference", "P1", None, 0),
              ("C2", "金额异常", "duplicate", "P2", None, 2)],
        columns=("business_key", "violation_message", "issue_kind", "project_code", "project_name", "project_match_count"),
    )
    run = execute_version({"definition": _definition(mode="lookup")}, {"report_date": "2026-09-30"}, metadata)
    assert run.violation_count == 2
    assert [row["project_name_status"] for row in run.rows] == ["missing_reference", "duplicate"]
    assert all(row["project_name"] is None for row in run.rows)
    # lookup 复用已描述元数据，不重复 describe 第二张业务表。
    assert len(metadata.describe_calls) == 2  # base + 唯一 lookup 维度表


def test_execute_requires_context_from_real_base_column_roles_not_physical_names():
    columns = [
        {"column_name": "contract_no", "data_type": "varchar", "comment": "合同编号"},
        {"column_name": "project_code", "data_type": "varchar", "comment": "项目编号"},
        {"column_name": "amount", "data_type": "decimal", "comment": "金额"},
        {"column_name": "report_date", "data_type": "date", "comment": "报送日期"},
    ]
    metadata = Metadata(base=columns, rows=())
    definition = _definition()
    del definition["project_context"]
    run = execute_version({"definition": definition}, {"report_date": "2026-09-30"}, metadata)
    assert run.status == "ERROR" and run.error_code == "PROJECT_CONTEXT_REQUIRED"
    assert metadata.calls == []

    # 只有 logic 引用“项目编号”，本列中文角色不是项目字段时不得强制。
    non_role = [
        {"column_name": "amount", "data_type": "decimal", "comment": "金额", "logic": "取项目编号为分母"},
        {"column_name": "contract_no", "data_type": "varchar", "comment": "合同编号"},
        {"column_name": "report_date", "data_type": "date", "comment": "报送日期"},
    ]
    ok_metadata = Metadata(base=non_role, rows=())
    definition = _definition()
    del definition["project_context"]
    run = execute_version({"definition": definition}, {"report_date": "2026-09-30"}, ok_metadata)
    assert run.status == "PASS"


def test_execute_explicit_flag_blocks_non_project_rule_too():
    columns = [
        {"column_name": "contract_no", "data_type": "varchar", "comment": "合同编号"},
        {"column_name": "amount", "data_type": "decimal", "comment": "金额"},
        {"column_name": "report_date", "data_type": "date", "comment": "报送日期"},
    ]
    definition = _definition()
    del definition["project_context"]
    metadata = Metadata(base=columns)
    run = execute_version({"definition": definition}, {}, metadata, require_project_context=True)
    assert run.status == "ERROR" and run.error_code == "PROJECT_CONTEXT_REQUIRED"
    assert metadata.calls == []


def test_require_project_context_blocks_old_hash_execution():
    old_definition = _definition()
    del old_definition["project_context"]
    # 非项目语义时兼容执行；这里人为要求上下文，必须显式拒绝。
    metadata = Metadata()
    run = execute_version({"definition": old_definition}, {}, metadata, require_project_context=True)
    assert run.status == "ERROR" and run.error_code == "PROJECT_CONTEXT_REQUIRED"
    assert metadata.calls == []


def test_context_mapping_drift_and_cached_sql_mismatch_are_rejected():
    drifted = [dict(column) for column in DIM_COLUMNS]
    next(column for column in drifted if column["column_name"] == "report_date")["data_type"] = "datetime"
    metadata = Metadata(other=drifted)
    run = execute_version({"definition": _definition(mode="lookup")}, {}, metadata)
    assert run.status == "ERROR" and run.error_code == "MAPPING_DRIFT"

    from auto_check.modules.data_validation.compiler import compile_rule
    definition = _definition(mode="lookup")
    sql, _params = compile_rule({"definition": definition})
    stale = sql.replace("dim_project", "old_dim")
    run = execute_version({"definition": definition, "sql_text": stale}, {}, Metadata())
    assert run.status == "ERROR" and run.error_code == "MAPPING_DRIFT"
