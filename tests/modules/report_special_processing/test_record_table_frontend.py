from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
COMPONENTS = ROOT / "src" / "auto_check" / "modules" / "report_special_processing" / "web" / "components"


def _render_table(tmp_path: Path, records: list[dict]) -> dict:
    for name in ("record_table.js", "dom.js", "bilingual_name_list.js"):
        shutil.copy2(COMPONENTS / name, tmp_path / name)
    (tmp_path / "package.json").write_text('{"type":"module"}', encoding="utf-8")
    script = tmp_path / "scenario.js"
    script.write_text(
        'import { createRecordTable } from "./record_table.js";\n'
        "class FakeNode {\n"
        "  constructor(tag) { this.tag = tag; this.className = ''; this.textContent = ''; this.children = []; this.attributes = {}; this.dataset = {}; }\n"
        "  setAttribute(key, value) { this.attributes[key] = String(value); }\n"
        "  addEventListener() {}\n"
        "  append(...items) { this.children.push(...items.filter(Boolean)); }\n"
        "}\n"
        "const documentRef = { createElement: (tag) => new FakeNode(tag) };\n"
        f"const records = {json.dumps(records, ensure_ascii=False)};\n"
        "const root = createRecordTable(documentRef, records, { selectedId: null, highlightId: null, onOpen() {}, onAction() {} });\n"
        "function serialize(node) { return { tag: node.tag, className: node.className, text: node.textContent, attributes: node.attributes, children: node.children.map(serialize) }; }\n"
        "console.log(JSON.stringify(serialize(root)));\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["node", str(script)], cwd=tmp_path, text=True, encoding="utf-8", capture_output=True, check=True,
    )
    return json.loads(result.stdout)


def _nodes(root: dict, class_name: str) -> list[dict]:
    found = []
    if class_name in str(root.get("className") or "").split():
        found.append(root)
    for child in root.get("children") or []:
        found.extend(_nodes(child, class_name))
    return found


def _tags(root: dict, tag_name: str) -> list[dict]:
    found = []
    if root.get("tag") == tag_name:
        found.append(root)
    for child in root.get("children") or []:
        found.extend(_tags(child, tag_name))
    return found


def _text(root: dict) -> str:
    return "\n".join([
        str(root.get("text") or ""),
        *(_text(child) for child in root.get("children") or []),
    ])


def _base_record(**changes) -> dict:
    record = {
        "id": 1,
        "record_no": "RSP-1",
        "status": "pending",
        "can_edit": True,
        "can_confirm": False,
        "can_void": False,
        "can_reopen": False,
        "can_delete": False,
        "business_system_name_snapshot": "衡泰",
        "report_process_name_snapshot": "1104报送",
        "handler_display_name_snapshot": "管理员",
        "special_handling_at": "2026-09-10T17:48:37+08:00",
    }
    record.update(changes)
    return record


def test_main_list_uses_three_plain_change_columns_and_deduplicates_fields(tmp_path: Path) -> None:
    record = _base_record(structured_content={"tables": [
        {"table_name": "table_a", "chinese_table_name": "表A", "fields": [
            {"column_name": "jrname", "chinese_column_name": "法人金融机构名称", "value_before": "1", "value_after": "2"},
            {"column_name": "status_a", "chinese_column_name": "客户状态", "value_before": "正常", "value_after": "冻结"},
        ]},
        {"table_name": "table_b", "chinese_table_name": "表B", "fields": [
            {"column_name": "jrname_copy", "chinese_column_name": "法人金融机构名称", "value_before": "1", "value_after": "2"},
            {"column_name": "rival_kind", "chinese_column_name": "借款人类型", "value_before": "1", "value_after": "2"},
            {"column_name": "status_b", "chinese_column_name": "客户状态", "value_before": "正常", "value_after": "终止"},
        ]},
    ]})

    rendered = _render_table(tmp_path, [record])
    assert [node["text"] for node in _tags(rendered, "th")[:3]] == ["修改字段", "修改前", "修改后"]
    visible = _text(rendered)
    for hidden in ("变更摘要", "表A", "表B", "table_a", "table_b", "jrname", "jrname_copy"):
        assert hidden not in visible

    rows = _nodes(rendered, "rsp-record-row")
    assert len(rows) == 1
    group_rows = _nodes(rows[0], "rsp-change-grid-row")
    assert len(group_rows) == 3
    assert "客户状态" in _text(group_rows[0]) and "冻结" in _text(group_rows[0])
    assert "客户状态" in _text(group_rows[1]) and "终止" in _text(group_rows[1])
    assert _text(group_rows[2].get("children")[0]).count("法人金融机构名称") == 1
    assert "借款人类型" in _text(group_rows[2].get("children")[0])
    assert group_rows[2]["children"][1]["text"] == "1"
    assert group_rows[2]["children"][2]["text"] == "2"


def test_multiple_value_pairs_stay_in_one_business_row_without_rowspan_gap(tmp_path: Path) -> None:
    record = _base_record(structured_content={"tables": [{"fields": [
        {"column_name": "a", "chinese_column_name": "字段A", "value_before": "1", "value_after": "2"},
        {"column_name": "b", "chinese_column_name": "字段B", "value_before": "3", "value_after": "4"},
    ]}]})

    rendered = _render_table(tmp_path, [record])
    rows = _nodes(rendered, "rsp-record-row")
    assert len(rows) == 1
    assert len(_nodes(rows[0], "rsp-change-grid-row")) == 2
    outer = _nodes(rows[0], "rsp-change-grid-cell")[0]
    assert outer["attributes"].get("colspan") == "3"
    assert all("rowspan" not in cell["attributes"] for cell in _tags(rows[0], "td"))


def test_null_missing_and_empty_values_share_one_group(tmp_path: Path) -> None:
    record = _base_record(structured_content={"tables": [{"fields": [
        {"column_name": "a", "chinese_column_name": "字段甲", "value_before": None, "value_after": ""},
        {"column_name": "b", "chinese_column_name": "字段乙", "value_after": None},
        {"column_name": "c", "chinese_column_name": "字段丙", "value_before": "", "value_after": ""},
    ]}]})

    rendered = _render_table(tmp_path, [record])
    rows = _nodes(rendered, "rsp-record-row")
    assert len(rows) == 1
    group = _nodes(rows[0], "rsp-change-grid-row")[0]
    assert all(name in _text(group["children"][0]) for name in ("字段甲", "字段乙", "字段丙"))
    assert group["children"][1]["text"] == "—"
    assert group["children"][2]["text"] == "—"


def test_single_value_pair_stacks_deduplicated_field_names(tmp_path: Path) -> None:
    record = _base_record(structured_content={"tables": [
        {"fields": [
            {"column_name": "a1", "chinese_column_name": "字段A", "value_before": "1", "value_after": "2"},
            {"column_name": "b", "chinese_column_name": "字段B", "value_before": "1", "value_after": "2"},
        ]},
        {"fields": [
            {"column_name": "a2", "chinese_column_name": "字段A", "value_before": "1", "value_after": "2"},
            {"column_name": "c", "chinese_column_name": "字段C", "value_before": "1", "value_after": "2"},
        ]},
    ]})

    rendered = _render_table(tmp_path, [record])
    rows = _nodes(rendered, "rsp-record-row")
    assert len(rows) == 1
    field_list = _nodes(rows[0], "rsp-change-field-list")[0]
    assert "is-stacked" in field_list["className"].split()
    assert [node["text"] for node in _nodes(field_list, "rsp-change-field-name")] == ["字段A", "字段B", "字段C"]
    assert _nodes(field_list, "rsp-change-field-sep") == []


def test_multiple_value_groups_sort_combined_field_lines_from_short_to_long(tmp_path: Path) -> None:
    record = _base_record(structured_content={"tables": [{"fields": [
        {"column_name": "long", "chinese_column_name": "超长字段名称", "value_before": "1", "value_after": "2"},
        {"column_name": "short", "chinese_column_name": "短", "value_before": "1", "value_after": "2"},
        {"column_name": "medium", "chinese_column_name": "中等字段", "value_before": "1", "value_after": "2"},
        {"column_name": "other_long", "chinese_column_name": "另一个较长字段", "value_before": "3", "value_after": "4"},
        {"column_name": "other_short", "chinese_column_name": "小项", "value_before": "3", "value_after": "4"},
    ]}]})

    rendered = _render_table(tmp_path, [record])
    groups = _nodes(rendered, "rsp-change-grid-row")
    assert len(groups) == 2
    assert [node["text"] for node in _nodes(groups[0], "rsp-change-field-name")] == ["另一个较长字段", "小项"]
    assert [node["text"] for node in _nodes(groups[1], "rsp-change-field-name")] == ["超长字段名称", "短", "中等字段"]
    assert all("is-stacked" not in _nodes(group, "rsp-change-field-list")[0]["className"].split() for group in groups)
    assert len(_nodes(groups[0], "rsp-change-field-sep")) == 1
    assert len(_nodes(groups[1], "rsp-change-field-sep")) == 2


def test_short_single_field_group_precedes_long_group_with_separators(tmp_path: Path) -> None:
    record = _base_record(structured_content={"tables": [{"fields": [
        {"column_name": "cool", "chinese_column_name": "酷酷酷", "value_before": "哇哇哇", "value_after": "外网"},
        {"column_name": "3333", "value_before": "哇哇哇", "value_after": "外网"},
        {"column_name": "444", "value_before": "哇哇哇", "value_after": "外网"},
        {"column_name": "jrcode", "chinese_column_name": "金融机构编码", "value_before": "1", "value_after": "2"},
    ]}]})

    groups = _nodes(_render_table(tmp_path, [record]), "rsp-change-grid-row")
    assert len(groups) == 2
    assert [node["text"] for node in _nodes(groups[0], "rsp-change-field-name")] == ["金融机构编码"]
    assert (groups[0]["children"][1]["text"], groups[0]["children"][2]["text"]) == ("1", "2")
    assert [node["text"] for node in _nodes(groups[1], "rsp-change-field-name")] == ["酷酷酷", "3333", "444"]
    assert len(_nodes(groups[1], "rsp-change-field-sep")) == 2
    assert (groups[1]["children"][1]["text"], groups[1]["children"][2]["text"]) == ("哇哇哇", "外网")


def test_group_order_and_exact_value_pair_are_preserved(tmp_path: Path) -> None:
    record = _base_record(structured_content={"tables": [{"fields": [
        {"column_name": "a", "chinese_column_name": "字段A", "value_before": "ab", "value_after": "c"},
        {"column_name": "b", "chinese_column_name": "字段B", "value_before": "a", "value_after": "bc"},
        {"column_name": "c", "chinese_column_name": "字段C", "value_before": "ab", "value_after": "c"},
    ]}]})

    rows = _nodes(_render_table(tmp_path, [record]), "rsp-change-grid-row")
    assert len(rows) == 2
    assert "字段B" in _text(rows[0]["children"][0])
    assert (rows[0]["children"][1]["text"], rows[0]["children"][2]["text"]) == ("a", "bc")
    assert "字段A" in _text(rows[1]["children"][0]) and "字段C" in _text(rows[1]["children"][0])
    assert (rows[1]["children"][1]["text"], rows[1]["children"][2]["text"]) == ("ab", "c")


def test_same_field_name_with_different_values_is_not_merged(tmp_path: Path) -> None:
    record = _base_record(structured_content={"tables": [
        {"fields": [{"column_name": "status_a", "chinese_column_name": "客户状态", "value_before": "正常", "value_after": "冻结"}]},
        {"fields": [{"column_name": "status_b", "chinese_column_name": "客户状态", "value_before": "正常", "value_after": "终止"}]},
    ]})

    rows = _nodes(_render_table(tmp_path, [record]), "rsp-change-grid-row")
    assert len(rows) == 2
    assert all("客户状态" in _text(row) for row in rows)
    assert [(row["children"][1]["text"], row["children"][2]["text"]) for row in rows] == [
        ("正常", "冻结"), ("正常", "终止"),
    ]


def test_field_name_prefers_chinese_then_falls_back_to_english(tmp_path: Path) -> None:
    record = _base_record(structured_content={"tables": [{"fields": [
        {"column_name": "customer_code", "chinese_column_name": "客户编码", "value_before": "1", "value_after": "2"},
        {"column_name": "fallback_column", "value_before": "1", "value_after": "2"},
        {"value_before": "1", "value_after": "2"},
    ]}]})

    rendered = _render_table(tmp_path, [record])
    field_names = _nodes(rendered, "rsp-change-field-name")
    assert [node["text"] for node in field_names] == ["客户编码", "fallback_column", "未设置字段"]
    assert all("title" not in node["attributes"] for node in field_names)
    assert "customer_code" not in _text(rendered)


def test_legacy_record_keeps_chinese_fields_and_value_alignment(tmp_path: Path) -> None:
    aligned = _base_record(
        id=2,
        structured_content=None,
        field_name="字段甲｜a；字段乙｜b",
        value_before="1\nr",
        value_after="2\nt",
    )
    mismatch = _base_record(
        id=3,
        structured_content=None,
        field_name="字段丙｜c；字段丁｜d",
        value_before="旧值1\n旧值2\n旧值3",
        value_after="新值",
    )

    rendered = _render_table(tmp_path, [aligned, mismatch])
    rows = _nodes(rendered, "rsp-record-row")
    assert len(rows) == 2
    aligned_groups = _nodes(rows[0], "rsp-change-grid-row")
    assert len(aligned_groups) == 2
    assert "字段甲" in _text(aligned_groups[0]) and "a" not in _text(aligned_groups[0]["children"][0])
    assert (aligned_groups[0]["children"][1]["text"], aligned_groups[0]["children"][2]["text"]) == ("1", "2")
    assert "字段乙" in _text(aligned_groups[1])
    mismatch_text = _text(rows[1])
    for value in ("字段丙", "字段丁", "旧值1", "旧值2", "旧值3", "新值"):
        assert value in mismatch_text


def test_whitespace_values_remain_distinct(tmp_path: Path) -> None:
    record = _base_record(structured_content={"tables": [{"fields": [
        {"column_name": "a", "value_before": "1", "value_after": "2"},
        {"column_name": "b", "value_before": " 1", "value_after": "2"},
        {"column_name": "c", "value_before": "1", "value_after": "2 "},
    ]}]})

    rows = _nodes(_render_table(tmp_path, [record]), "rsp-change-grid-row")
    assert [(row["children"][1]["text"], row["children"][2]["text"]) for row in rows] == [
        ("1", "2"), (" 1", "2"), ("1", "2 "),
    ]


def test_text_is_rendered_as_dom_text_without_technical_table_metadata(tmp_path: Path) -> None:
    record = _base_record(structured_content={"tables": [{
        "datasource_name": "dangerous_source",
        "table_name": "<script>alert(1)</script>",
        "chinese_table_name": "<i>中文表</i>",
        "fields": [{
            "column_name": "<img src=x onerror=alert(1)>",
            "chinese_column_name": "<b>粗体</b>",
            "value_before": "1",
            "value_after": "2",
        }],
    }]})

    rendered = _render_table(tmp_path, [record])
    assert not _tags(rendered, "script")
    assert not _tags(rendered, "b")
    assert _nodes(rendered, "rsp-change-field-name")[0]["text"] == "<b>粗体</b>"
    visible = _text(rendered)
    assert "dangerous_source" not in visible
    assert "<i>中文表</i>" not in visible
    assert "<script>alert(1)</script>" not in visible
    assert "innerHTML" not in (COMPONENTS / "record_table.js").read_text(encoding="utf-8")


def test_empty_structured_record_has_nonblank_fallback_row(tmp_path: Path) -> None:
    rendered = _render_table(tmp_path, [_base_record(structured_content={"tables": []})])
    row = _nodes(rendered, "rsp-record-row")[0]
    group = _nodes(row, "rsp-change-grid-row")[0]
    assert "暂无修改字段" in _text(group["children"][0])
    assert group["children"][1]["text"] == "—" and group["children"][2]["text"] == "—"


def test_no_nested_change_table(tmp_path: Path) -> None:
    record = _base_record(structured_content={"tables": [{"fields": [
        {"column_name": "f1", "chinese_column_name": "字段1", "value_before": "1", "value_after": "2"},
    ]}]})
    rendered = _render_table(tmp_path, [record])
    field_cell = _nodes(rendered, "rsp-change-grid-cell")[0]
    assert not _tags(field_cell, "table")
