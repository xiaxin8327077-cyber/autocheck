"""导出异常明细和规则包。"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from openpyxl import Workbook


_ISSUE_HEADERS = (
    "task_id", "rule_code", "business_key", "project_code", "project_name",
    "project_name_status", "issue_kind", "message", "truncated",
)


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


def issues_csv(task: dict[str, Any], issues: list[dict[str, Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_ISSUE_HEADERS)
    for issue in issues:
        writer.writerow([_csv_literal(value) for value in _issue_values(task, issue, spreadsheet=False)])
    return buffer.getvalue().encode("utf-8")


def issues_xlsx(task: dict[str, Any], issues: list[dict[str, Any]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "issues"
    sheet.append(_ISSUE_HEADERS)
    for issue in issues:
        sheet.append(_issue_values(task, issue, spreadsheet=True))
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = "s"
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


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
