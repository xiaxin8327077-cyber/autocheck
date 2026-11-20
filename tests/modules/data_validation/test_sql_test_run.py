import sqlite3
from datetime import date
from types import SimpleNamespace

import pytest

from auto_check.modules.data_validation.contracts import AppError
from tests.modules.data_validation.support import Metadata, user
from tests.modules.data_validation.test_ai_service import _rules_with_doc


def setup_query(*, count=15, error=None):
    fields = [("row_id", "编号", "varchar", "Y"), ("maturity_date", "到期日期", "date", ""),
              ("issue_date", "发放日期", "date", ""), ("report_date", "报送日期", "date", "")]
    rules, model = _rules_with_doc([], fields=fields)
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE test_table (row_id, maturity_date, issue_date, report_date)")
    db.executemany("INSERT INTO test_table VALUES (?, ?, ?, ?)",
                   [(str(i), "2026-10-01", "2026-10-02", "2026-10-31") for i in range(count)])

    class BusinessSource(Metadata):
        def execute_select(self, source_id, sql, params, *, timeout_seconds, max_rows):
            self.calls.append((sql, params, timeout_seconds, max_rows))
            if error:
                raise error
            cursor = db.execute(sql, params)
            records = cursor.fetchmany(max_rows + 1)
            return SimpleNamespace(columns=tuple(c[0] for c in cursor.description),
                                   rows=tuple(records[:max_rows]), truncated=len(records) > max_rows)

    rules.metadata = BusinessSource(columns=[{"column_name": n, "comment": cn, "data_type": kind}
                                             for n, cn, kind, _ in fields],
                                   sources=[SimpleNamespace(id="src", name="监管报送集市", dialect="postgresql")])
    definition = {"name": "日期校验", "source_id": "src", "table_name": "test_table", "business_key": "row_id",
                  "rule_type": "field_compare", "report_date_field": "report_date", "null_policy": "skip",
                  "equality_policy": "allow_equal", "violation_message": "到期早于发放",
                  "expression": {"left": "maturity_date", "op": "lt", "right": "issue_date"}}
    preview = rules.preview_candidate(user(), definition)
    return rules, model, db, preview


def run(rules, preview, **overrides):
    from auto_check.modules.data_validation.sql_test_run import run_candidate_sql
    return run_candidate_sql(rules, {**user(), "capabilities": ["dv.test", "dv.run", "dv.view_results"]}, {"definition": preview["definition"],
        "expected_hash": preview["content_sha256"], "report_date": "2026-10-31", **overrides})


def test_sql_run_queries_only_ten_rows_with_server_constants_and_no_persistence():
    rules, model, db, preview = setup_query()
    try:
        result = run(rules, preview, sql="DELETE FROM test_table", max_rows=99999, timeout_seconds=99999,
                     params={"report_date": "2026-09-30"})
        assert result["row_count"] == len(result["rows"]) == 10
        assert result["truncated"] and result["max_rows"] == 10 and result["persisted"] is False
        assert result["report_date"] == "2026-10-31"
        assert "到期日期" in [c["name"] for c in result["columns"]]
        assert result["rows"][0]["values"]["到期日期"] == "2026-10-01"
        sql, params, timeout, limit = rules.metadata.calls[0]
        assert sql.endswith("LIMIT 11") and params["report_date"] == date(2026, 10, 31)
        assert timeout == 30 and limit == 10 and "DELETE" not in sql
        assert db.execute("SELECT COUNT(*) FROM test_table").fetchone()[0] == 15
        assert not model.calls and not rules.storage.visible_rules("1")
    finally:
        db.close()


@pytest.mark.parametrize("day", ["2026-02-30", "20261031", "", None, "2026-10-31' OR 1=1"])
def test_sql_run_rejects_invalid_dates_before_business_query(day):
    rules, _, db, preview = setup_query()
    try:
        with pytest.raises(AppError, match="VALIDATION_ERROR"):
            run(rules, preview, report_date=day)
        assert not rules.metadata.calls
    finally:
        db.close()


def test_sql_run_rejects_stale_preview_before_business_query():
    rules, _, db, preview = setup_query()
    try:
        with pytest.raises(AppError, match="CONFLICT_VERSION"):
            run(rules, preview, expected_hash="stale")
        assert not rules.metadata.calls
    finally:
        db.close()


@pytest.mark.parametrize("count,day,expected", [(0, "2026-10-31", 0), (10, "2026-10-31", 10), (15, "2026-09-30", 0)])
def test_sql_run_handles_empty_results_and_exact_limit(count, day, expected):
    rules, _, db, preview = setup_query(count=count)
    try:
        result = run(rules, preview, report_date=day)
        assert result["row_count"] == expected and not result["truncated"]
        assert result["columns"], "空结果仍保留真实 SQL 表头"
    finally:
        db.close()


@pytest.mark.parametrize("error,code", [(TimeoutError("secret"), "TIMEOUT"), (RuntimeError("password=secret"), "SOURCE_UNAVAILABLE")])
def test_sql_run_masks_query_failures(error, code):
    rules, _, db, preview = setup_query(error=error)
    try:
        with pytest.raises(AppError, match=code):
            run(rules, preview)
    finally:
        db.close()


def test_sql_run_route_requires_login_and_existing_test_permission():
    from auto_check.app.module_system.contracts import ModuleRequest
    from auto_check.app.module_system.permissions import default_permission_evaluator
    from auto_check.app.module_system.routing import ModuleRouter
    from auto_check.modules.data_validation.api import register_routes
    from auto_check.modules.data_validation.module import MANIFEST

    rules, _, db, preview = setup_query()
    router = ModuleRouter(MANIFEST, default_permission_evaluator)
    register_routes(router, lambda: rules)
    payload = {"definition": preview["definition"], "expected_hash": preview["content_sha256"], "report_date": "2026-10-31"}
    try:
        for owner in (None, *({**user(), "capabilities": caps} for caps in (
                [], ["dv.test"], ["dv.test", "dv.run"], ["dv.test", "dv.view_results"], ["dv.run", "dv.view_results"]))):
            response = router.dispatch(ModuleRequest(method="POST", path=f"{MANIFEST.api_prefix}/ai/sql-test",
                path_params={}, query={}, body=payload, current_user=owner))
            assert response.status in {401, 403}
        assert not rules.metadata.calls
        response = router.dispatch(ModuleRequest(method="POST", path=f"{MANIFEST.api_prefix}/ai/sql-test",
            path_params={}, query={}, body=payload, current_user={**user(), "capabilities": ["dv.test", "dv.run", "dv.view_results"]}))
        assert response.status == 200 and response.body["data"]["row_count"] == 10
    finally:
        db.close()


@pytest.mark.parametrize("kind", ["postgresql", "mysql"])
def test_sql_run_maps_database_statement_timeout(kind):
    class QueryCanceled(Exception):
        sqlstate = "57014"
    error = QueryCanceled("secret") if kind == "postgresql" else RuntimeError(3024, "secret timeout")
    rules, _, db, preview = setup_query(error=error)
    try:
        with pytest.raises(AppError, match="TIMEOUT"):
            run(rules, preview)
    finally:
        db.close()


def test_sql_run_concurrency_limit_rejects_before_query_and_releases_after_error():
    from auto_check.modules.data_validation import sql_test_run
    rules, _, db, preview = setup_query()
    try:
        assert sql_test_run._SLOTS.acquire(blocking=False)
        assert sql_test_run._SLOTS.acquire(blocking=False)
        try:
            with pytest.raises(AppError, match="SQL_TEST_LIMIT_REACHED"):
                run(rules, preview)
            assert not rules.metadata.calls
        finally:
            sql_test_run._SLOTS.release()
            sql_test_run._SLOTS.release()
        with pytest.raises(AppError, match="CONFLICT_VERSION"):
            run(rules, preview, expected_hash="stale")
        assert run(rules, preview)["row_count"] == 10
    finally:
        db.close()
