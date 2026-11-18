import base64
import io

import pytest

from auto_check.app.module_system.contracts import ModuleRequest
from auto_check.app.module_system.permissions import default_permission_evaluator
from auto_check.app.module_system.routing import ModuleRouter
from auto_check.modules.data_validation.api import register_routes
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.doc_parser import parse_workbook
from auto_check.modules.data_validation.module import MANIFEST
from auto_check.modules.data_validation.service import DataValidationService
from auto_check.modules.data_validation.storage import RuleStorage
from tests.modules.data_validation.support import (
    MemoryDatabase, TransactionOnlyDatabase, doc_xlsx_bytes, service, user,
)


class _Processes:
    def list_report_processes(self):
        from types import SimpleNamespace
        return [SimpleNamespace(code="pbc_central", name="人行大集中报送", order=1, active=True)]


def _workbook_with_families() -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "人行明细表_项目明细表"
    sheet.cell(row=1, column=1, value="proj_info_dtl_pboc")
    meta = [("表名", "项目信息（proj_info_dtl_pboc.ktr）"), ("数据来源", "项目信息表"), ("维度", "项目"), ("数据范围", "全部"), ("采集周期", "每日")]
    for index, (label, value) in enumerate(meta, start=2):
        sheet.cell(row=index, column=1, value=label)
        sheet.cell(row=index, column=3, value=value)
    header = ["序号", "字段名", "字段名（中文）", "字段类型", "主键", "能否为空", "默认值", "字典", "逻辑", "公共层表名（英文）", "公共层表名（中文）", "公共层字段（英文）"]
    for column, label in enumerate(header, start=1):
        sheet.cell(row=7, column=column, value=label)
    rows = [
        ("d_cldate", "数据日期", "date", "Y", ""),
        ("c_projcode", "项目编号", "varhcar", "", "proj_detail.c_projcode"),
        ("c_amount", "金额", "", "", ""),
        ("c_geo", "空间范围", "geometry", "", ""),
    ]
    for offset, (name, cn, data_type, pk, logic) in enumerate(rows, start=8):
        sheet.cell(row=offset, column=1, value=offset - 7)
        sheet.cell(row=offset, column=2, value=name)
        sheet.cell(row=offset, column=3, value=cn)
        sheet.cell(row=offset, column=4, value=data_type)
        sheet.cell(row=offset, column=5, value=pk)
        sheet.cell(row=offset, column=9, value=logic)
        sheet.cell(row=offset, column=10, value="reg_data_market.reg_pub_project_info")
        sheet.cell(row=offset, column=11, value="项目信息表")
        sheet.cell(row=offset, column=12, value="c_projcode")
    template = workbook.create_sheet("人行结果表_表1-1 募集余额")
    template.cell(row=1, column=1, value="表1-1")
    appendix = workbook.create_sheet("附录1 地区代码")
    appendix.cell(row=2, column=1, value="代码")
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def test_parse_workbook_maps_data_source_rules_and_skips_templates() -> None:
    content = doc_xlsx_bytes()
    parsed = parse_workbook(content)
    assert parsed["table_count"] == 1
    table = parsed["tables"][0]
    assert table["data_source_name"] == "监管报送集市"
    assert table["table_name"] == "test_table"
    assert table["table_name_cn"].startswith("测试表")
    assert [field["field_name"] for field in table["fields"]] == ["row_id", "maturity_date", "issue_date"]

    mixed = parse_workbook(_workbook_with_families())
    assert mixed["table_count"] == 1
    mixed_table = mixed["tables"][0]
    assert mixed_table["data_source_name"] == "监管报表"
    types = {field["field_name"]: field["data_type"] for field in mixed_table["fields"]}
    assert types["d_cldate"] == "date"
    assert types["c_projcode"] == "varchar"  # varhcar 拼写自动纠正
    assert types["c_amount"] == "varchar"  # 类型为空默认字符串
    assert types["c_geo"] == "geometry"  # 未识别类型保留原文
    assert any("c_geo" in item and "字段类型" in item for item in mixed["warnings"])
    assert not any("c_amount" in item for item in mixed["warnings"])
    assert not any(name.startswith(("人行结果表_表", "附录")) for name in [item["sheet_name"] for item in mixed["tables"]])


@pytest.mark.parametrize(("name", "code"), [
    ("1104报送", "jr_1104"), ("21、23版全要素报送", "full_elements"),
    ("中信登定期报送", "citic_registration"), ("East5报送", "east5"),
    ("测试待出表", "test_pending_output"), ("五篇大文章报送", "five_articles"),
    ("人行大集中报送", "pbc_central"), ("资管产品模板、逐笔", "pbc_template"),
])
def test_active_category_name_matches_sheet_prefix(name, code):
    categories = [{"code": code, "name": name}]
    assert DataValidationService._doc_category_scope({"sheet_name": f"{name}_测试表"}, categories) == {code}
    assert DataValidationService._doc_category_scope({"sheet_name": f"其它{name}_测试表"}, categories) is None
    assert DataValidationService._doc_category_scope({"sheet_name": "人行_测试表"}, categories) == {"pbc_central", "pbc_template"}


@pytest.mark.parametrize("sheet", ["人行_募集明细", "人行明细表_募集明细", "人行底稿_募集明细", "1104报送_贷款报表"])
@pytest.mark.parametrize("proposed", ["pbc_template", "jr_1104"])
def test_pbc_sheet_recognized_in_import_and_restricts_ai_category(sheet, proposed):
    from types import SimpleNamespace
    from tests.modules.data_validation.support import Metadata, SequenceModel
    from tests.modules.data_validation.test_ai_service import _generate_payload, _request, _select_payload

    nav = SimpleNamespace(list_report_processes=lambda: [
        SimpleNamespace(code=code, name=name, active=True) for code, name in (
            ("pbc_central", "人行大集中报送"), ("pbc_template", "资管产品模板、逐笔"), ("jr_1104", "1104报送"),
        )
    ])
    model = SequenceModel([_select_payload(report_category=proposed), _generate_payload()])
    metadata = Metadata(sources=[SimpleNamespace(id="src", name="监管报表", dialect="postgresql")])
    _, rules = service(metadata=metadata, model=model, report_navigation=nav)
    imported = rules.import_document(user(), "人行.xlsx", doc_xlsx_bytes(sheet=sheet))
    actual = rules.storage.doc_tables(imported["document"]["id"])[0]
    assert actual["sheet_name"] == sheet and actual["data_source_name"] == "监管报表"
    result = rules.parse_rule_request(user(), _request())
    if sheet.startswith("1104报送_"):
        assert result["report_category"] == "jr_1104"
    elif proposed == "pbc_template":
        assert result["report_category"] == proposed
    else:
        assert result["report_category"] == ""
        question = next(q for q in result["questions"] if q["id"] == "report_category")
        assert [option["value"] for option in question["options"]] == ["pbc_central", "pbc_template"]


def test_document_versions_can_be_imported_listed_and_activated() -> None:
    _database, rules = service(report_navigation=_Processes())
    first = rules.import_document(user(), "doc-v1.xlsx", doc_xlsx_bytes())
    second = rules.import_document(user(), "doc-v2.xlsx", doc_xlsx_bytes(table_cn="测试表二"))
    assert first["document"]["version_no"] == 1
    assert second["document"]["version_no"] == 2
    documents = rules.list_documents()
    assert [item["version_no"] for item in documents] == [2, 1]
    assert documents[0]["status"] == "active"

    activated = rules.activate_document(user(), first["document"]["id"])
    assert activated["status"] == "active"
    active = rules.active_document()
    assert active["version_no"] == 1


def test_prompts_have_three_stages_and_support_custom_and_reset() -> None:
    _database, rules = service()
    prompts = rules.list_prompts()
    assert [item["stage"] for item in prompts] == ["select_table", "generate_rule", "generate_sql"]
    assert all(item["is_default"] for item in prompts)

    custom = "需求：{request_text} 数据源：{source_name} 表：{tables} 分类：{categories} 自定义"
    saved = rules.save_prompt(user(), "select_table", custom)
    assert saved["version_no"] == 1
    assert rules.list_prompts()[0]["content"] == custom
    reset = rules.reset_prompt(user(), "select_table")
    assert reset["version_no"] == 2
    assert rules.list_prompts()[0]["is_default"] is False

    with pytest.raises(AppError):
        rules.save_prompt(user(), "select_table", "缺少变量")
    with pytest.raises(AppError):
        rules.save_prompt(user(), "unknown_stage", "x")


def test_source_rules_save_requires_fallback_and_persists() -> None:
    _database, rules = service()
    defaults = rules.list_source_rules()
    assert defaults[0]["sheet_prefix"] == "集市层_"
    assert defaults[-1]["sheet_prefix"] == ""

    saved = rules.save_source_rules(user(), [
        {"sheet_prefix": "集市层_", "data_source_name": "监管报送集市"},
        {"sheet_prefix": "", "data_source_name": "监管报表"},
    ])
    assert [item["data_source_name"] for item in saved] == ["监管报送集市", "监管报表"]
    with pytest.raises(AppError):
        rules.save_source_rules(user(), [{"sheet_prefix": "集市层_", "data_source_name": "监管报送集市"}])


def test_settings_routes_import_document_and_manage_prompts() -> None:
    _database, rules = service()
    router = ModuleRouter(MANIFEST, default_permission_evaluator)
    register_routes(router, lambda: rules)
    admin = {
        "id": "9", "role": "user", "username": "admin", "display_name": "管理员",
        "capabilities": ["dv.admin"],
    }
    content = base64.b64encode(doc_xlsx_bytes()).decode("ascii")
    response = router.dispatch(ModuleRequest(
        method="POST", path=f"{MANIFEST.api_prefix}/settings/documents", path_params={}, query={},
        body={"file_name": "doc.xlsx", "content_base64": content}, current_user=admin,
    ))
    assert response.status == 200
    assert response.body["data"]["table_count"] == 1

    listed = router.dispatch(ModuleRequest(
        method="GET", path=f"{MANIFEST.api_prefix}/settings/documents", path_params={}, query={},
        body=None, current_user=admin,
    ))
    assert listed.body["data"][0]["version_no"] == 1

    prompts = router.dispatch(ModuleRequest(
        method="GET", path=f"{MANIFEST.api_prefix}/settings/prompts", path_params={}, query={},
        body=None, current_user=admin,
    ))
    assert len(prompts.body["data"]) == 3

    def knowledge_request(method, suffix="", body=None, actor=admin):
        return router.dispatch(ModuleRequest(
            method=method, path=f"{MANIFEST.api_prefix}/settings/knowledge{suffix}",
            path_params={}, query={}, body=body, current_user=actor,
        ))

    initial = knowledge_request("GET").body["data"]
    draft = initial["draft"]
    assert initial["active"] == []
    assert knowledge_request("GET", actor=user()).status == 403
    assert knowledge_request("POST", "/preview", {"entries": draft}, actor=user()).status == 403
    assert knowledge_request("POST", "/preview", {"entries": draft}).body["data"]["entries"] == draft
    assert rules.storage.knowledge_record() is None
    assert knowledge_request("PUT", body={"expected_revision": 0, "entries": draft}, actor=user()).status == 403
    assert knowledge_request("PUT", body={"expected_revision": 0, "entries": draft}).body["data"]["revision"] == 1
    assert knowledge_request("POST", "/activation", {"expected_revision": 1, "enabled": True}, actor=user()).status == 403
    assert knowledge_request("POST", "/activation", {"expected_revision": 0, "enabled": True}).status == 409
    assert knowledge_request("POST", "/activation", {"expected_revision": 1, "enabled": True}).body["data"]["active"] == draft

    forbidden = router.dispatch(ModuleRequest(
        method="GET", path=f"{MANIFEST.api_prefix}/settings/documents", path_params={}, query={},
        body=None, current_user=user(),
    ))
    assert forbidden.status == 403

def test_import_works_with_production_transaction_interface_and_long_meta() -> None:
    """生产应用库只有 transaction()；超长维度/采集周期说明也必须完整入库。"""
    database = MemoryDatabase()
    rules = DataValidationService(RuleStorage(TransactionOnlyDatabase(database)))
    long_dimension = "范围说明" * 100
    long_period = "按报送日期生成；" * 30
    result = rules.import_document(user(), "doc.xlsx", doc_xlsx_bytes(
        dimension=long_dimension, period=long_period,
    ))
    assert result["table_count"] == 1
    document = rules.active_document()
    tables = rules.storage.doc_tables(document["id"])
    assert tables[0]["dimension"] == long_dimension
    assert tables[0]["period"] == long_period
