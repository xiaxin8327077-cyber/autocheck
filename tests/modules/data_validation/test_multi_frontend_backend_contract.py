"""Consume the workbench's actual JSON payload with the real Python batch service."""
from __future__ import annotations

import io
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from auto_check.modules.data_validation.contracts import AppError
from tests.modules.data_validation.support import Metadata, doc_xlsx_bytes, service, user
from tests.modules.data_validation.test_frontend_multi_behavior import copy_web_modules


def _document() -> bytes:
    books = []
    for table, label, dimension, field in (
        ("synthetic_project_info", "项目信息表", "项目", "f_endp_amt"),
        ("reg_pub_contract", "项目合同表", "项目合同", "f_contract_amt"),
    ):
        books.append(load_workbook(io.BytesIO(doc_xlsx_bytes(
            table=table, table_cn=label, dimension=dimension, sheet=f"集市层_{dimension}",
            fields=[("project_code", "项目编号", "varchar", "Y"),
                    ("project_name", "项目名称", "varchar", ""),
                    ("f_endp_amt", "实收信托", "numeric", ""),
                    ("f_balan_endp_amt", "余额金额", "numeric", ""),
                    ("f_contract_amt", "合同金额", "numeric", ""),
                    ("report_date", "报送日期", "date", ""),
                    ("d_cldate", "数据日期", "date", "")],
        ))))
    first, second = books
    sheet = first.create_sheet(second.active.title)
    for row in second.active.iter_rows(values_only=True):
        sheet.append(row)
    output = io.BytesIO()
    first.save(output)
    for book in books:
        book.close()
    return output.getvalue()


def _backend_context(definition: dict) -> dict:
    """把前端 ctx 规范为后端稳定 DTO：base 不含 lookup 专属 key；lookup 的 key 为 {left,right}。"""
    context = definition.get("project_context") or {}
    if context.get("mode") == "lookup":
        key = context.get("key") or {}
        if isinstance(key, str):
            key = {"left": context.get("code_field") or key, "right": key}
        return {
            "mode": "lookup",
            "code_field": context.get("code_field"),
            "name_field": context.get("name_field"),
            "table_name": context.get("table_name"),
            "key": key,
            "date_field": context.get("date_field"),
            "unique_evidence": context.get("unique_evidence"),
            "confirmed": bool(context.get("confirmed")),
        }
    return {
        "mode": "base",
        "code_field": context.get("code_field"),
        "name_field": context.get("name_field"),
        "confirmed": True,
    }


def _backend_definition(definition: dict) -> dict:
    item = {
        **definition,
        "project_context": _backend_context(definition),
    } if definition.get("project_context") else {**definition}
    expression = item.get("expression") or {}
    if expression.get("right_type") == "field":
        item["equality_policy"] = "reject_equal" if expression.get("op") in ("eq", "lte", "gte") else "allow_equal"
    return item


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js unavailable")
def test_actual_multi_workbench_payload_is_accepted_and_idempotent(tmp_path: Path):
    metadata = Metadata(sources=[SimpleNamespace(id="src", name="监管报送集市", dialect="mysql")])
    _database, rules = service(metadata=metadata)
    rules.import_document(user(), "multi-contract.xlsx", _document())
    active = rules.storage.active_document()
    mapping = f"doc-v{active['version_no']}-{active['content_sha256'][:12]}"
    copy_web_modules(tmp_path)
    scenario_source = Path(__file__).with_name("frontend_multi_behavior.mjs").read_text(encoding="utf-8")
    # Supply a real server document version before the UI fixture mounts, not by repairing its emitted payload.
    scenario_source = scenario_source.replace('"map-multi"', json.dumps(mapping))
    # This scenario exercises generic lookup, not the real project's fixed name binding.
    scenario_source = scenario_source.replace("reg_pub_project_info", "synthetic_project_info")
    scenario = tmp_path / "frontend_multi_behavior.mjs"
    scenario.write_text(scenario_source, encoding="utf-8")
    completed = subprocess.run(["node", str(scenario)], cwd=tmp_path, capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=60, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    observation = json.loads(completed.stdout.strip())
    payload = observation["batch_payload"]
    assert len(payload["definitions"]) == 2
    payload = {
        **payload,
        "definitions": [_backend_definition(item) for item in payload["definitions"]],
    }
    expected = [rules.preview_candidate(user(), {"definition": item}) for item in payload["definitions"]]
    saved = rules.batch_save_candidates(user(), payload)
    assert saved["count"] == 2
    ids = [item["id"] for item in saved["rules"]]
    assert len(set(ids)) == 2
    assert len({item["rule_code"] for item in saved["rules"]}) == 2
    for rule_id, preview in zip(ids, expected):
        version = rules.storage.latest_version(int(rule_id))
        assert version["definition"] == preview["definition"]
        assert version["content_sha256"] == preview["content_sha256"]
        assert rules.storage.get_rule(int(rule_id))["status"] == "draft"
    repeated = rules.batch_save_candidates(user(), payload)
    assert [item["id"] for item in repeated["rules"]] == ids
    assert rules.storage.stats(str(user()["id"]))["total"] == 2
    assert metadata.calls == [], "No business source query or metadata execution is needed to save candidates"

    # lookup 透传：真实 selection 形状 + project_columns 第二表列，后端重核 Doc。
    lookup_definition = {
        **payload["definitions"][0],
        "project_context": {
            "mode": "lookup", "code_field": "project_code", "name_field": "project_name",
            "table_name": "reg_pub_contract", "key": {"left": "project_code", "right": "project_code"},
            "date_field": "report_date", "unique_evidence": "项目编号主键", "confirmed": False,
        },
    }
    review = rules.preview_candidate(user(), {"definition": lookup_definition}, return_questions=True)
    assert review["questions"] and not review.get("sql_preview")
    with pytest.raises(AppError) as pending:
        rules.preview_candidate(user(), {"definition": lookup_definition})
    assert pending.value.code == "PROJECT_CONTEXT_REQUIRED"
    lookup_definition["project_context"]["confirmed"] = True
    lookup_preview = rules.preview_candidate(user(), {"definition": lookup_definition})
    assert lookup_preview["definition"]["project_context"]["mode"] == "lookup"
    assert lookup_preview["definition"]["project_context"]["table_name"] == "reg_pub_contract"
