from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
COMPONENTS = ROOT / "src" / "auto_check" / "modules" / "report_special_processing" / "web" / "components"


def _run_model(tmp_path: Path, changed_fields: dict) -> dict:
    shutil.copy2(COMPONENTS / "audit_detail.js", tmp_path / "audit_detail.mjs")
    shutil.copy2(COMPONENTS / "dom.js", tmp_path / "dom.mjs")
    source = (tmp_path / "audit_detail.mjs").read_text(encoding="utf-8")
    (tmp_path / "audit_detail.mjs").write_text(
        source.replace('from "./dom.js"', 'from "./dom.mjs"'), encoding="utf-8",
    )
    script = tmp_path / "scenario.mjs"
    script.write_text(
        "import { buildSemanticAuditViewModel } from './audit_detail.mjs';\n"
        f"const changedFields = {json.dumps(changed_fields, ensure_ascii=False)};\n"
        "console.log(JSON.stringify(buildSemanticAuditViewModel({changed_fields: changedFields})));\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["node", str(script)], cwd=tmp_path, text=True, encoding="utf-8", capture_output=True, check=True,
    )
    return json.loads(result.stdout)


def _run_render(tmp_path: Path, changed_fields: dict) -> dict:
    shutil.copy2(COMPONENTS / "audit_detail.js", tmp_path / "audit_detail.mjs")
    shutil.copy2(COMPONENTS / "dom.js", tmp_path / "dom.mjs")
    source = (tmp_path / "audit_detail.mjs").read_text(encoding="utf-8")
    (tmp_path / "audit_detail.mjs").write_text(
        source.replace('from "./dom.js"', 'from "./dom.mjs"'), encoding="utf-8",
    )
    script = tmp_path / "render-scenario.mjs"
    script.write_text(
        "import { buildSemanticAuditViewModel, renderSemanticAuditDetail } from './audit_detail.mjs';\n"
        "class FakeNode {\n"
        "  constructor(tag) { this.tag = tag; this.className = ''; this.textContent = ''; this.children = []; this.attributes = {}; this.dataset = {}; }\n"
        "  setAttribute(key, value) { this.attributes[key] = String(value); }\n"
        "  addEventListener() {}\n"
        "  append(child) { this.children.push(child); }\n"
        "}\n"
        "const documentRef = { createElement: (tag) => new FakeNode(tag) };\n"
        f"const changedFields = {json.dumps(changed_fields, ensure_ascii=False)};\n"
        "const model = buildSemanticAuditViewModel({ changed_fields: changedFields });\n"
        "const root = renderSemanticAuditDetail(documentRef, model);\n"
        "function serialize(node) { return { tag: node.tag, className: node.className, text: node.textContent, attributes: node.attributes, children: node.children.map(serialize) }; }\n"
        "console.log(JSON.stringify({ model, root: serialize(root) }));\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["node", str(script)], cwd=tmp_path, text=True, encoding="utf-8", capture_output=True, check=True,
    )
    return json.loads(result.stdout)


def _rendered_text(node: dict) -> str:
    return "\n".join([
        str(node.get("text") or ""),
        *(_rendered_text(child) for child in node.get("children") or []),
    ])


def _modified_table(change_count: int = 3) -> dict:
    return {
        "change": "modified",
        "change_count": change_count,
        "before": {"datasource_name": "ass_man_reg", "table_name": "alarm_hand_count", "chinese_table_name": "报警处理"},
        "after": {"datasource_name": "ass_man_reg", "table_name": "alarm_hand_count", "chinese_table_name": "报警处理"},
        "table_info": [],
        "scope_info": [],
        "conditions": [{
            "change": "modified",
            "before": {"column_name": "jrname", "operator": "=", "values": ["江苏信托"]},
            "after": {"column_name": "jrname", "operator": "IN", "values": ["江苏信托", "33"]},
            "changes": [
                {"key": "operator", "old": "=", "new": "IN"},
                {"key": "values", "old": ["江苏信托"], "new": ["江苏信托", "33"]},
            ],
            "change_count": 2,
        }],
        "fields": [{
            "change": "modified",
            "before": {"column_name": "datejg", "chinese_column_name": "数据管理机构", "value_before": "10", "value_after": "20"},
            "after": {"column_name": "datejg", "chinese_column_name": "数据管理机构", "value_before": "10", "value_after": "t"},
            "changes": [{"key": "value_after", "old": "20", "new": "t"}],
            "change_count": 1,
        }],
    }


def test_example_a_only_basic_information(tmp_path):
    model = _run_model(tmp_path, {
        "dimension": {"old": "项目端", "new": "产品端"},
        "summary": {"old": "原因A", "new": "原因B"},
    })

    assert model["business_change_count"] == 2
    assert model["basic_change_count"] == 2
    assert model["special_change_count"] == 0
    assert model["tables"] == []
    assert model["summary_parts"] == ["基本信息2项"]


def test_example_b_groups_basic_and_one_modified_table_and_keeps_script_secondary(tmp_path):
    model = _run_model(tmp_path, {
        "dimension": {"old": "项目端", "new": "产品端"},
        "summary": {"old": "原因A", "new": "原因B"},
        "structured_content": {
            "change_count": 3, "affected_tables": 1,
            "modified_tables": 1, "added_tables": 0, "removed_tables": 0,
            "tables": [_modified_table()],
        },
        "processing_script": {"old": "UPDATE old;", "new": "UPDATE new;"},
    })

    assert model["business_change_count"] == 5
    assert model["basic_change_count"] == 2
    assert model["special_change_count"] == 3
    assert model["script_changed"] is True
    assert model["tables"][0]["default_expanded"] is True
    assert model["summary_parts"] == ["基本信息2项", "特殊处理内容3项", "涉及1张处理表", "脚本同步更新"]


def test_example_c_keeps_three_tables_isolated_and_collapses_removed_snapshot(tmp_path):
    modified = _modified_table(change_count=2)
    modified["fields"] = []
    added = {
        "change": "added", "change_count": 1,
        "after": {"datasource_name": "reg-report-analysis", "table_name": "table_a", "chinese_table_name": "报送分析结果", "conditions": [], "fields": []},
    }
    removed = {
        "change": "removed", "change_count": 1,
        "before": {"datasource_name": "xxx", "table_name": "table_b", "chinese_table_name": "历史表", "conditions": [{}, {}], "fields": [{}, {}]},
    }
    model = _run_model(tmp_path, {
        "structured_content": {
            "change_count": 4, "affected_tables": 3,
            "modified_tables": 1, "added_tables": 1, "removed_tables": 1,
            "tables": [modified, added, removed],
        },
    })

    assert [item["change"] for item in model["tables"]] == ["modified", "added", "removed"]
    assert [item["default_expanded"] for item in model["tables"]] == [True, False, False]
    assert model["summary_parts"] == [
        "特殊处理内容4项", "修改1张表", "新增1张表", "删除1张表", "涉及3张处理表",
    ]


def test_added_table_expansion_contains_complete_current_configuration(tmp_path):
    conditions = [
        {
            "column_name": f"condition_{index}",
            "chinese_column_name": "第四条件" if index == 4 else "",
            "operator": "=",
            "values": [str(index)],
        }
        for index in range(1, 5)
    ]
    fields = [
        {
            "column_name": f"field_{index}",
            "chinese_column_name": f"字段{index}",
            "value_before": f"old-{index}",
            "value_after": f"new-{index}",
        }
        for index in range(1, 5)
    ]
    rendered = _run_render(tmp_path, {
        "structured_content": {
            "change_count": 1,
            "affected_tables": 1,
            "modified_tables": 0,
            "added_tables": 1,
            "removed_tables": 0,
            "tables": [{
                "change": "added",
                "change_count": 1,
                "after": {
                    "datasource_name": "ass_man_reg",
                    "table_name": "table_added",
                    "chinese_table_name": "新增处理表",
                    "limit_report_period": True,
                    "report_period_field": "datedate",
                    "conditions": conditions,
                    "fields": fields,
                },
            }],
        },
    })

    text = _rendered_text(rendered["root"])
    assert rendered["model"]["tables"][0]["default_expanded"] is True
    assert "表信息" in text
    assert "处理范围" in text
    assert "数据日期字段" in text
    assert "datedate" in text
    assert "第四条件（condition_4）" in text
    assert "修改字段" in text
    assert "field_4" in text


def test_removed_table_expansion_contains_complete_previous_configuration(tmp_path):
    rendered = _run_render(tmp_path, {
        "structured_content": {
            "change_count": 1,
            "affected_tables": 1,
            "modified_tables": 0,
            "added_tables": 0,
            "removed_tables": 1,
            "tables": [{
                "change": "removed",
                "change_count": 1,
                "before": {
                    "datasource_name": "ass_man_reg",
                    "table_name": "table_removed",
                    "chinese_table_name": "删除处理表",
                    "limit_report_period": True,
                    "report_period_field": "report_date",
                    "conditions": [
                        {"column_name": f"removed_condition_{index}", "operator": "=", "values": [str(index)]}
                        for index in range(1, 5)
                    ],
                    "fields": [
                        {
                            "column_name": f"removed_field_{index}",
                            "chinese_column_name": f"删除字段{index}",
                            "value_before": f"old-{index}",
                            "value_after": f"new-{index}",
                        }
                        for index in range(1, 5)
                    ],
                },
            }],
        },
    })

    text = _rendered_text(rendered["root"])
    table = rendered["model"]["tables"][0]
    assert table["default_expanded"] is False
    assert "查看删除前配置" in text
    assert "report_date" in text
    assert "removed_condition_4" in text
    assert "removed_field_4" in text


def test_manual_script_change_is_secondary_evidence_instead_of_automatic_sync(tmp_path):
    changed_fields = {
        "structured_content": {
            "change_count": 1,
            "affected_tables": 1,
            "modified_tables": 1,
            "added_tables": 0,
            "removed_tables": 0,
            "tables": [_modified_table(change_count=1)],
        },
        "processing_script": {
            "mode": "MANUAL",
            "old": "UPDATE old;",
            "new": "UPDATE manually_edited;",
        },
    }

    rendered = _run_render(tmp_path, changed_fields)
    text = _rendered_text(rendered["root"])

    assert rendered["model"]["script"]["mode"] == "MANUAL"
    assert rendered["model"]["summary_parts"][-1] == "手动脚本已修改"
    assert "脚本变更 · 手动编辑 · 查看 Diff" in text
