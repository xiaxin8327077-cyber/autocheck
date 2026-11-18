from types import SimpleNamespace

from auto_check.app.module_system.permissions import default_permission_evaluator
from auto_check.app.module_system.contracts import ModuleRequest
from auto_check.app.module_system.routing import ModuleRouter
from auto_check.modules.data_validation.api import register_routes
from auto_check.modules.data_validation.module import MANIFEST
from tests.modules.data_validation.support import loan_definition, service


class FlowMetadata:
    def list_sources(self):
        return [SimpleNamespace(id="src", name="监管报表", dialect="mysql")]

    def describe_table(self, _source_id, _table_name):
        return {
            "mapping_version": "map-1",
            "columns": [
                {"column_name": "id", "data_type": "bigint"},
                {"column_name": "project_code", "data_type": "varchar", "comment": "贷款业务编号"},
                {"column_name": "maturity_date", "data_type": "date", "comment": "贷款到期日期"},
                {"column_name": "issue_date", "data_type": "date", "comment": "贷款发放日期"},
                {"column_name": "report_date", "data_type": "date"},
            ],
        }

    def execute_select(self, _source_id, _sql, _params, timeout_seconds, max_rows):
        return SimpleNamespace(columns=("business_key",), rows=(("P001",),), truncated=False)


def test_manual_rule_can_be_confirmed_executed_and_viewed() -> None:
    _database, rules = service(metadata=FlowMetadata())
    router = ModuleRouter(MANIFEST, default_permission_evaluator)
    register_routes(router, lambda: rules)
    owner = {
        "id": "1",
        "role": "user",
        "username": "checker",
        "display_name": "校验员",
        "capabilities": [
            "dv.view", "dv.manage", "dv.ai_use", "dv.test", "dv.confirm",
            "dv.run", "dv.view_results", "dv.export",
        ],
    }

    created = call(router, "POST", "/rules", owner, body=loan_definition())
    rule_id = created["data"]["id"]
    detail = call(router, "GET", f"/rules/{rule_id}", owner)
    tested = call(router, "POST", f"/rules/{rule_id}/tests", owner, body={"version_no": detail["data"]["version_no"]})
    assert tested["data"]["failed_count"] == 0
    # 默认用例按真实表结构字段类型动态生成，不得是内置固定演示样本。
    assert [case["name"] for case in tested["data"]["cases"]] == ["正常", "明显异常", "边界", "空值"]
    assert all(case["row"]["maturity_date"] != "2026-12-31" for case in tested["data"]["cases"])
    enabled = call(
        router, "POST", f"/rules/{rule_id}/confirm", owner,
        body={"version_no": detail["data"]["version_no"], "expected_hash": detail["data"]["content_sha256"]},
    )
    assert enabled["data"]["status"] == "enabled"
    task = call(router, "POST", "/tasks", owner, body={"rule_ids": [rule_id], "source_id": "src", "report_period": "2026-09-30"})
    issues = call(router, "GET", f"/tasks/{task['data']['id']}/issues", owner)
    assert issues["data"]["items"]
    assert issues["data"]["items"][0]["message"] == "贷款期限异常"
    listed = call(router, "GET", "/tasks", owner)
    assert listed["data"][0]["id"] == task["data"]["id"]


def call(router, method, path, user, body=None):
    response = router.dispatch(ModuleRequest(
        method=method,
        path=f"{MANIFEST.api_prefix}{path}",
        path_params={},
        query={},
        body=body,
        current_user=user,
    ))
    assert response is not None
    assert response.status == 200, response.body
    return response.body
