"""The workbench starts a fresh job with no client history, including after a service restart."""
from copy import deepcopy
from io import BytesIO

from openpyxl import load_workbook
import pytest
from sqlalchemy import create_engine

from auto_check.modules.data_validation.service import DataValidationService
from auto_check.modules.data_validation.storage import METADATA, RuleStorage
from tests.modules.data_validation.support import SequenceModel, doc_xlsx_bytes, user
from tests.modules.data_validation.test_ai_service import SourceOnlyMetadata, _Processes
from tests.modules.data_validation.test_shared_analysis_reuse import FIRST, PROPOSAL, REVISED, SELECT, analyze


def open_service(path, model):
    engine = create_engine("sqlite:///" + path.as_posix())
    return DataValidationService(RuleStorage(engine), SourceOnlyMetadata(), model, _Processes()), engine


def install_document(rules, dictionary):
    fields = [
        ("project_id", "项目编号", "varchar", "Y"), ("project_name", "项目名称", "varchar", ""),
        ("report_day", "报送日期", "date", ""), ("f_netvalue", "单位净值", "numeric", ""),
        ("c_oper_mode_orig", "运行方式_原始", "varchar", ""),
    ]
    workbook = load_workbook(BytesIO(doc_xlsx_bytes(table=SELECT["target"]["table"], table_cn="项目信息",
                                                   dimension="项目", fields=fields)))
    workbook.active.cell(row=11, column=11, value=dictionary)
    content = BytesIO()
    workbook.save(content)
    workbook.close()
    rules.import_document(user("setup", "admin"), "合成项目文档.xlsx", content.getvalue())


@pytest.mark.parametrize("change", ["adapt", "fresh", "document", "new_codes", "business_scope"])
def test_shared_memory_survives_fresh_engine_but_requires_the_same_evidence(tmp_path, change):
    path = tmp_path / "shared-analysis.sqlite"
    selection = {**SELECT, "report_category": "group:pbc"}
    old, old_engine = open_service(path, SequenceModel([selection, PROPOSAL]))
    try:
        METADATA.create_all(old_engine)
        install_document(old, "1-开放式净值型\n2-非净值型\n3-封闭式净值型")
        first = analyze(old, user("first"), FIRST)["result"]
        assert first["report_category"] == "group:pbc" and first["preview"] and len(old.model.calls) == 2
        preview = first["preview"]
        tested = old.test_candidate(user("first"), {"definition": preview["definition"],
                                                     "expected_hash": preview["content_sha256"]})
        assert tested["passed_count"] and not tested["failed_count"]
    finally:
        old.join()
        old_engine.dispose()

    note = "还需核对业务发生日期与月末截止日期的关系"
    draft = deepcopy(PROPOSAL)
    draft["expression"]["conditions"][1]["right"] = 10
    draft.update(rule_name="当期单位净值复核", violation_message="单位净值缺失或超出当前阈值。", null_policy="review",
                 equality_policy="allow_equal", filters=[{"table": "base", "field": "c_oper_mode_orig", "op": "in",
                                                        "value": ["1", "3"], "confirmed": False}])
    payloads = [{"reuse_decision": "adapt", "memory_index": 0, **selection, "draft": draft}] if change == "adapt" else [
        {**selection, **({"reuse_decision": "fresh"} if change == "fresh" else {})},
        {**draft, "uncertainties": [] if change == "new_codes" else [note]},
    ]
    model = SequenceModel(payloads)
    new, new_engine = open_service(path, model)
    try:
        if change == "document":
            install_document(new, "2-非净值型\n9-其他")
        elif change == "new_codes":
            install_document(new, "6-封闭式净值型\n7-其他\n8-开放式净值型")
        elif change == "business_scope":
            new.save_prompt(user("setup", "admin"), "business_scope", "按月末业务日期对齐。")
        result = analyze(new, user("second"), REVISED)["result"]
        if change == "adapt":
            assert len(model.calls) == 1 and result["analysis_reused"] and result["memory_decision"] == "adapt"
            assert result["verification_status"] == "not_run"
            assert result["preview"]["content_sha256"] != preview["content_sha256"]
            definition = result["preview"]["definition"]
            assert definition["filters"][0]["value"] == ["1", "3"]
            assert {p["right"] for p in definition["expression"]["conditions"] if "right" in p} == {10}
            assert not new.storage.visible_rules("second")
        else:
            assert not result.get("analysis_reused") and len(model.calls) == 2
            if change == "new_codes":
                preview = result["preview"]
                assert preview["definition"]["filters"][0]["value"] == ["6", "8"]
                assert {v for k, v in preview["sql_params"].items() if k.startswith("filter_")} == {"6", "8"}
                assert not result["questions"] and not result["uncertainties"]
            else:
                assert result.get("preview") is None
                assert note in result["uncertainties"]
            if change == "fresh":
                assert result["memory_decision"] == "fresh"
            else:
                assert all(FIRST not in message["content"] and "reuse_decision" not in message["content"]
                           for call in model.calls for message in call["messages"])
    finally:
        new.join()
        new_engine.dispose()
