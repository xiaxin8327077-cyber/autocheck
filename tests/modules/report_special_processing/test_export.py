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


def test_export_rows_follow_requested_column_order_and_include_script():
    rows = export_rows(
        [
            {
                "report_period": date(2026, 7, 31),
                "report_process_name_snapshot": "人行大集中报送、1104报送",
                "reports": ["报表A", "报表B"],
                "summary": "摘要",
                "processing_content": "说明",
                "processing_script": "select 1;",
                "special_handling_at": NOW,
                "handler_display_name_snapshot": "管理员",
                "status": "pending",
                "record_no": "RSP-should-not-export",
            }
        ]
    )
    assert EXPORT_HEADERS == (
        "所属报送期",
        "关联报送",
        "涉及报表",
        "处理摘要",
        "处理说明",
        "处理脚本",
        "处理时间",
        "处理人",
        "状态",
    )
    assert rows == [
        [
            "2026-07-31",
            "人行大集中报送、1104报送",
            "报表A、报表B",
            "摘要",
            "说明",
            "select 1;",
            "2026-08-06 11:20:00",
            "管理员",
            "待处理",
        ]
    ]
    assert "RSP-should-not-export" not in str(rows)


def test_build_export_xlsx_writes_headers_and_script_column():
    payload = build_export_xlsx(
        [
            {
                "report_period": "2026-07-31",
                "report_process_name_snapshot": "1104报送",
                "reports": [{"report_name": "F1104"}],
                "summary": "s",
                "processing_content": "c",
                "processing_script": "print(1)",
                "special_handling_at": "2026-08-06T11:20:00+08:00",
                "handler_username_snapshot": "admin",
                "status": "completed",
            }
        ]
    )
    workbook = load_workbook(BytesIO(payload))
    sheet = workbook.active
    assert [cell.value for cell in sheet[1]] == list(EXPORT_HEADERS)
    assert sheet["F2"].value == "print(1)"
    assert sheet["I2"].value == "已完成"


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
                    "reports": ["R1"],
                    "summary": "摘要",
                    "processing_content": "说明",
                    "processing_script": "script",
                    "special_handling_at": NOW,
                    "handler_display_name_snapshot": "管理员",
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
