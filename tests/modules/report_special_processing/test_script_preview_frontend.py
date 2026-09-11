from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PREVIEW = (
    ROOT
    / "src"
    / "auto_check"
    / "modules"
    / "report_special_processing"
    / "web"
    / "components"
    / "script_preview.js"
)


def run_preview(tmp_path: Path, content: dict, field_types: dict | None = None, report_period: str = "") -> str:
    workdir = tmp_path / "script_preview"
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "package.json").write_text('{"type":"module"}', encoding="utf-8")
    scenario = f"""
import {{ buildScriptPreview }} from {json.dumps(SCRIPT_PREVIEW.as_uri())};
const content = {json.dumps(content, ensure_ascii=False)};
const fieldTypes = {json.dumps(field_types or {}, ensure_ascii=False)};
process.stdout.write(buildScriptPreview(content, fieldTypes, {json.dumps(report_period)}));
"""
    (workdir / "scenario.js").write_text(scenario, encoding="utf-8")
    result = subprocess.run(
        ["node", "scenario.js"],
        cwd=workdir,
        text=True,
        capture_output=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def table(**overrides) -> dict:
    value = {
        "datasource_id": "ds1",
        "datasource_name": "TCMP生产库",
        "table_name": "t_customer",
        "chinese_table_name": "客户信息表",
        "limit_report_period": False,
        "report_period_field": "",
        "conditions": [],
        "fields": [],
    }
    value.update(overrides)
    return value


def content(*tables: dict) -> dict:
    return {"datasource_id": "ds1", "datasource_type": "postgresql", "tables": list(tables)}


def test_table_selection_immediately_generates_update(tmp_path: Path) -> None:
    script = run_preview(tmp_path, content(table()))

    assert "-- 数据源：TCMP生产库" in script
    assert "-- 表：t_customer（客户信息表）" in script
    assert script.rstrip().endswith("UPDATE t_customer")
    assert "\nSET " not in script
    assert "\nWHERE " not in script


def test_selected_fields_immediately_generate_set_and_where_with_empty_values(tmp_path: Path) -> None:
    script = run_preview(
        tmp_path,
        content(table(
            fields=[{"column_name": "customer_status", "value_after": ""}],
            conditions=[{"column_name": "project_no", "operator": "=", "values": []}],
        )),
    )

    assert "SET customer_status = ''" in script
    assert "WHERE project_no = '';" in script


def test_without_selected_condition_field_does_not_generate_where(tmp_path: Path) -> None:
    script = run_preview(
        tmp_path,
        content(table(fields=[{"column_name": "customer_status", "value_after": "冻结"}])),
    )

    assert "SET customer_status = '冻结';" in script
    assert "WHERE" not in script


def test_report_period_always_uses_hyphenated_date(tmp_path: Path) -> None:
    script = run_preview(
        tmp_path,
        content(table(
            limit_report_period=True,
            report_period_field="jrcode",
            fields=[{"column_name": "customer_status", "value_after": "冻结"}],
        )),
        {"ds1": {"t_customer": {"jrcode": "varchar"}}},
        "2026-08-31",
    )

    assert "WHERE jrcode = '2026-08-31';" in script
    assert "20260831" not in script


def test_tables_generate_independently_and_literals_follow_current_rules(tmp_path: Path) -> None:
    script = run_preview(
        tmp_path,
        content(
            table(table_name="table_only", chinese_table_name="仅选表"),
            table(
                table_name="t_contract",
                chinese_table_name="合同表",
                fields=[
                    {"column_name": "remark", "value_after": "Bob's"},
                    {"column_name": "amount", "value_after": "120"},
                ],
                conditions=[
                    {"column_name": "contract_no", "operator": "IN", "values": ["C1", "C2"]},
                    {"column_name": "closed_at", "operator": "IS NULL", "values": []},
                ],
            ),
        ),
        {"ds1": {"t_contract": {"amount": "decimal", "contract_no": "varchar"}}},
    )

    assert "UPDATE table_only" in script
    assert "UPDATE t_contract" in script
    assert "remark = 'Bob''s'" in script
    assert "amount = '120'" in script
    assert "contract_no IN ('C1', 'C2')" in script
    assert "closed_at IS NULL" in script
