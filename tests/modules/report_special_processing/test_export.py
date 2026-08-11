from datetime import date, datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from openpyxl import load_workbook

from auto_check.app.module_system.contracts import ModuleManifest, ModuleRequest
from auto_check.app.module_system.permissions import default_permission_evaluator
from auto_check.app.module_system.routing import ModuleRouter
from auto_check.modules.report_special_processing.contracts import ValidationError
from auto_check.modules.report_special_processing.export_workbook import (
    EXPORT_HEADERS,
    build_export_xlsx,
    export_rows,
)


NOW = datetime(2026, 8, 6, 11, 20, tzinfo=ZoneInfo("Asia/Shanghai"))


def test_export_rows_follow_requested_column_order_with_dimension_fields():
    rows = export_rows(
        [
            {
                "report_period": date(2026, 7, 31),
                "report_process_name_snapshot": "人行大集中报送、1104报送",
                "dimension": "project",
                "summary": "摘要",
                "table_name": "t_demo",
                "field_name": "amt",
                "value_before": "1",
                "value_after": "2",
                "special_handling_at": NOW,
                "handler_display_name_snapshot": "管理员",
                "governance_owner_display_name_snapshot": "治理负责人",
                "status": "pending",
                "record_no": "RSP-should-not-export",
                "reports": ["报表A"],
                "processing_content": "说明",
                "processing_script": "select 1;",
            }
        ]
    )
    assert EXPORT_HEADERS == (
        "所属报送期",
        "关联报送",
        "所属维度",
        "处理摘要",
        "处理表名",
        "处理字段名",
        "修改前",
        "修改后",
        "处理人",
        "数据治理负责人",
        "处理时间",
        "状态",
    )
    assert rows == [
        [
            "2026-07-31",
            "人行大集中报送、1104报送",
            "项目端",
            "摘要",
            "t_demo",
            "amt",
            "1",
            "2",
            "管理员",
            "治理负责人",
            "2026-08-06 11:20:00",
            "待确认",
        ]
    ]
    assert "RSP-should-not-export" not in str(rows)
    assert "报表A" not in str(rows)
    assert "说明" not in str(rows)
    assert "select 1;" not in str(rows)


def test_build_export_xlsx_writes_headers_and_dimension_columns():
    payload = build_export_xlsx(
        [
            {
                "report_period": "2026-07-31",
                "report_process_name_snapshot": "1104报送",
                "dimension": "fund",
                "summary": "s",
                "table_name": "t_fund",
                "field_name": "bal",
                "value_before": "a",
                "value_after": "b",
                "special_handling_at": "2026-08-06T11:20:00+08:00",
                "handler_username_snapshot": "admin",
                "governance_owner_display_name_snapshot": "治理资金",
                "status": "completed",
            }
        ]
    )
    workbook = load_workbook(BytesIO(payload))
    sheet = workbook.active
    assert [cell.value for cell in sheet[1]] == list(EXPORT_HEADERS)
    assert sheet["C2"].value == "资金端"
    assert sheet["E2"].value == "t_fund"
    assert sheet["J2"].value == "治理资金"
    assert sheet["L2"].value == "已完成"


class _ExportService:
    def catalog(self):
        return {}

    def list_records(self, query, user):
        return {"items": []}

    def export_records(self, query):
        if query.get("empty") == "1":
            raise ValidationError(message="无数据可导出")
        return "报表特殊处理_2026-07-31_20260806_112000.xlsx", build_export_xlsx(
            [
                {
                    "report_period": query.get("report_period"),
                    "report_process_name_snapshot": "1104报送",
                    "dimension": "asset",
                    "summary": "摘要",
                    "table_name": "t_asset",
                    "field_name": "qty",
                    "value_before": "3",
                    "value_after": "4",
                    "special_handling_at": NOW,
                    "handler_display_name_snapshot": "管理员",
                    "governance_owner_display_name_snapshot": "治理资产",
                    "status": "pending",
                }
            ]
        )

    def create(self, body, user, request_id):
        return {"id": 1}

    def get(self, record_id, user):
        return {"id": record_id}

    def update(self, record_id, body, user, request_id):
        return {"id": record_id}

    def change_status(self, record_id, body, user, request_id):
        return {"id": record_id}

    def void(self, record_id, body, user, request_id):
        return {"id": record_id}

    def reopen(self, record_id, body, user, request_id):
        return {"id": record_id}

    def audit(self, record_id, query):
        return {"items": []}

    def summary(self, query):
        return {"total": 0}


def _manifest():
    import json
    from importlib import resources

    return ModuleManifest.from_mapping(
        json.loads(
            resources.files("auto_check.modules.report_special_processing")
            .joinpath("manifest.json")
            .read_text(encoding="utf-8")
        )
    )


def _dispatch(suffix, *, query=None, user=None):
    from auto_check.modules.report_special_processing.api import register_routes

    router = ModuleRouter(_manifest(), default_permission_evaluator)
    register_routes(router, lambda: _ExportService())
    user = dict(user or {"role": "user"})
    if str(user.get("role")) != "admin" and "capabilities" not in user:
        user["capabilities"] = ["rsp.view", "rsp.detail"]
    return router.dispatch(
        request=ModuleRequest(
            "GET",
            _manifest().api_prefix + suffix,
            {},
            query or {},
            None,
            user,
        ),
        body_size=0,
    )


def test_api_export_returns_xlsx_attachment_before_record_id_route():
    response = _dispatch(
        "/records/export",
        query={"report_period": "2026-07-31", "status": "pending"},
    )
    assert response.status == 200
    assert response.content_type.startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert any(name.lower() == "content-disposition" for name, _ in response.headers)
    assert response.body[:2] == b"PK"


def test_api_export_empty_result_returns_domain_message():
    response = _dispatch("/records/export", query={"empty": "1"})
    assert response.status == 400
    assert response.body["error"]["message"] == "无数据可导出"
