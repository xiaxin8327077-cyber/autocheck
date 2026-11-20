"""导出异常明细和规则包。"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE


_ISSUE_HEADERS = (
    "task_id", "rule_code", "business_key", "project_code", "project_name",
    "project_name_status", "issue_kind", "message", "truncated",
)
MAX_EXPORT_BYTES = 8 * 1024 * 1024
MAX_EXPORT_CELLS = 120_000


def _issue_values(task: dict[str, Any], issue: dict[str, Any], *, spreadsheet: bool) -> list[Any]:
    return [
        task["id"], issue.get("rule_code", ""), issue.get("business_key", ""),
        issue.get("project_code"), issue.get("project_name"),
        issue.get("project_name_status") or "legacy_unavailable",
        issue.get("issue_kind") or "legacy", issue.get("message", ""),
        bool(task.get("truncated")) if spreadsheet else ("true" if task.get("truncated") else "false"),
    ]


def _csv_literal(value: Any) -> Any:
    # Business identifiers/names are text, never executable spreadsheet formulas.
    if isinstance(value, str):
        prefix = value.lstrip()
        while prefix.startswith(chr(0xfeff)):
            prefix = prefix[1:].lstrip()
        if prefix.startswith(("=", "+", "-", "@")):
            return "'" + value
    return value


_SOURCE_HEADERS = {"checked_value": "校验字段", "comparison_value": "比较字段"}


def _query_headers(issues: list[dict]) -> dict[str, tuple[str, str]]:
    entries = {}
    for issue in issues:
        for column in (issue.get("query_result") or {}).get("columns", ()):
            name = column["name"]
            role = column.get("role", name)
            if role in _SOURCE_HEADERS and column.get("source_field"):
                entries["source", role] = _SOURCE_HEADERS[role]
            entries["value", name] = name
    reserved = set(_ISSUE_HEADERS) | {label for (kind, _), label in entries.items() if kind == "source"}
    headers = {}
    for (kind, key), label in entries.items():
        if kind == "value":
            while label in reserved or label in headers:
                label = "sql." + label
        headers[label] = (kind, key)
    return headers


def _query_values(issue: dict, headers: dict) -> list:
    result = issue.get("query_result") or {}
    values = result.get("values", {})
    unavailable = result.get("unavailable", {})
    sources = {c.get("role", c["name"]): c for c in result.get("columns", ()) if c.get("source_field")}
    output = []
    for kind, name in headers.values():
        if kind == "source":
            col = sources.get(name, {})
            field = col.get("source_field", "")
            label = col.get("label")
            output.append(f"{label}（{field}）" if field and label and label != field else field)
        elif name in unavailable:
            output.append("值超出保存上限" if unavailable[name] == "oversized" else "不支持的值类型")
        elif name not in values:
            output.append("未采集" if not result else "未返回")
        else:
            output.append("NULL" if values[name] is None else values[name])
    return output


def _csv_line(values) -> bytes:
    buffer = io.StringIO()
    csv.writer(buffer).writerow([_csv_literal(value) for value in values])
    return buffer.getvalue().encode("utf-8")


def _csv_prefix(task: dict, issues: list[dict], byte_limit: int | None) -> tuple[bytes, int]:
    headers = _query_headers(issues)
    output = io.BytesIO()
    output.write(_csv_line([*_ISSUE_HEADERS, *headers]))
    for count, issue in enumerate(issues):
        values = _issue_values(task, issue, spreadsheet=False) + _query_values(issue, headers)
        line = _csv_line(values)
        if byte_limit is not None and output.tell() + len(line) > byte_limit:
            return output.getvalue(), count
        output.write(line)
    return output.getvalue(), len(issues)


def issues_csv(task: dict[str, Any], issues: list[dict[str, Any]]) -> bytes:
    return _csv_prefix(task, issues, None)[0]


def issues_xlsx(task: dict[str, Any], issues: list[dict[str, Any]]) -> bytes:
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("issues")
    headers = _query_headers(issues)
    sheet.append([*_ISSUE_HEADERS, *headers])
    for issue in issues:
        cells = []
        for value in _issue_values(task, issue, spreadsheet=True) + _query_values(issue, headers):
            if isinstance(value, str):
                value = ILLEGAL_CHARACTERS_RE.sub(lambda m: f"\\u{ord(m[0]):04x}", value)
                cell = WriteOnlyCell(sheet, value=value)
                cell.data_type = "s"
                cells.append(cell)
            else:
                cells.append(value)
        sheet.append(cells)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class IssueExport:
    """对累计明细、列并集展开后的总单元格、最终输出字节分别设限。"""

    def __init__(self):
        self.rows: list[dict] = []
        self._bytes = 0
        self._headers = set(_ISSUE_HEADERS)

    def extend(self, batch: list[dict]) -> bool:
        for row in batch:
            extra = set(_query_headers([row]).values()) - self._headers
            cells = (len(self.rows) + 2) * (len(self._headers) + len(extra))
            size = len(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            if cells > MAX_EXPORT_CELLS or self._bytes + size > MAX_EXPORT_BYTES:
                return False
            self._headers.update(extra)
            self._bytes += size
            self.rows.append(row)
        return True

    def render(self, task: dict, file_type: str) -> dict:
        if file_type == "xlsx":
            content = issues_xlsx(task, self.rows)
            while self.rows and len(content) > MAX_EXPORT_BYTES:
                del self.rows[len(self.rows) // 2:]
                task["truncated"] = True
                content = issues_xlsx(task, self.rows)
        else:
            content, count = _csv_prefix(task, self.rows, MAX_EXPORT_BYTES)
            if count != len(self.rows):
                del self.rows[count:]
                task["truncated"] = True
                # 截断标识属于每一行。新表头是先前的子集，true 也短于 false。
                content, _ = _csv_prefix(task, self.rows, MAX_EXPORT_BYTES)
        return {"content": content, "issues": self.rows, "truncated": task["truncated"]}


def rule_pack(rules: list[dict[str, Any]]) -> bytes:
    payload = {
        "rules": [
            {
                "name": rule["name"],
                "definition": rule["definition"],
                "sql": rule.get("sql_text") or "",
            }
            for rule in rules
        ]
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")
