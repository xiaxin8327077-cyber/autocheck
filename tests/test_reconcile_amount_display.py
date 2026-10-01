from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
import json
from pathlib import Path
import re
import subprocess

import pytest

from auto_check.app.server import build_display_details
from auto_check.engine.reconcile import ReconcileEngine
from test_reconcile import _equity_profit_loss_repo


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "src/auto_check/web/app.js"
EXPORT_JS = ROOT / "src/auto_check/web/export_detail.js"
RAW_ADJUSTMENT = "-2253936.210000000000000"
RAW_EXPLAINED = "2253936.210000000000000"
ASSET_NAME = "2023年度1511号股权1.234567"
FUNCTIONS = (
    "formatAmount", "escapeHtml", "displayDetailLabel", "isAmountDisplayLabel",
    "formatResultDetailValue", "renderDetails", "specificReasonText",
)


def _render_actual_frontend(item: dict) -> dict:
    source = APP_JS.read_text(encoding="utf-8")
    declarations = []
    for name in FUNCTIONS:
        match = re.search(rf"^function {re.escape(name)}\([^)]*\) \{{.*?^\}}", source, re.M | re.S)
        assert match is not None, f"Missing existing frontend function: {name}"
        declarations.append(match.group())
    script = "\n".join([
        'const vm = require("vm");',
        f"const api = require({json.dumps(str(EXPORT_JS))});",
        "const context = {window: api};",
        "vm.createContext(context);",
        f"vm.runInContext({json.dumps(chr(10).join(declarations), ensure_ascii=False)}, context);",
        f"const item = {json.dumps(item, ensure_ascii=False)};",
        "const before = JSON.stringify(item);",
        "const html = context.renderDetails(item.display_details || []);",
        "const reason = context.specificReasonText(item);",
        "const text = api.buildExportDetailText(item);",
        "process.stdout.write(JSON.stringify({html, reason, text, unchanged: before === JSON.stringify(item)}));",
    ])
    completed = subprocess.run(["node", "-e", script], check=True, capture_output=True, encoding="utf-8")
    return json.loads(completed.stdout)


def _historical_equity_item(*, negative: bool = True) -> dict:
    raw = RAW_ADJUSTMENT if negative else RAW_EXPLAINED
    explained = RAW_EXPLAINED if negative else RAW_ADJUSTMENT
    reason = (
        f"①股权投资损益调整差异：{ASSET_NAME}；FA损益调整金额{raw}，解释资产差额{explained}；"
        "业务代码GQ523002，科目1511.01.03.GQ523002，项目2023SJG0206\n"
        "②资产端解释后剩余差额0E-12"
    )
    return {
        "project_code": "2023SJG0206", "difference_reason": "资产差异", "match_status": "已解释",
        "display_details": [
            {"title": "最终判断结果", "rows": [
                {"label": "具体原因", "value": reason},
                {"label": "匹配说明", "value": f"股权损益调整原始合计={raw}，解释资产差额={explained}；剩余差额=0E-12"},
                {"label": "资负报表资产合计", "value": "25766472.290000000000000"},
                {"label": "估值表资产合计", "value": "23512536.080000000000000"},
                {"label": "资产差异金额", "value": RAW_EXPLAINED},
                {"label": "股权损益调整合计", "value": raw},
                {"label": "损益调整解释资产差额", "value": explained},
                {"label": "资产端解释后剩余差额", "value": "0E-12"},
            ]},
            {"title": "股权损益调整核对", "table": {
                "headers": ["序号", "科目代码", "科目名称", "业务代码", "FA损益调整金额", "解释资产差额"],
                "rows": [
                    ["①", "1511.01.03.GQ523002", ASSET_NAME, "GQ523002", raw, explained],
                    ["②", "1511.01.03.GQ523003", "第2026期股权2.345678", "GQ523003", "0E-12", "0E-12"],
                ],
            }},
        ],
    }


@pytest.mark.parametrize("negative", [True, False])
def test_reconcile_amount_display_formats_new_summary_and_table_columns(negative):
    # Existing history JSON is passed through the same production render path.
    item = json.loads(json.dumps(_historical_equity_item(negative=negative), ensure_ascii=False))
    before = deepcopy(item)

    output = _render_actual_frontend(item)

    raw = "-2,253,936.21" if negative else "2,253,936.21"
    explained = "2,253,936.21" if negative else "-2,253,936.21"
    assert f"<span>股权损益调整合计</span><strong>{raw}</strong>" in output["html"]
    assert f"<span>损益调整解释资产差额</span><strong>{explained}</strong>" in output["html"]
    assert "<span>资产端解释后剩余差额</span><strong>0.00</strong>" in output["html"]
    assert f'<td class="money-cell">{raw}</td><td class="money-cell">{explained}</td>' in output["html"]
    assert '<td class="money-cell">0.00</td><td class="money-cell">0.00</td>' in output["html"]
    assert item == before
    assert output["unchanged"] is True


@pytest.mark.parametrize("negative", [True, False])
def test_reconcile_amount_display_formats_reason_and_match_text_without_changing_identifiers(negative):
    output = _render_actual_frontend(_historical_equity_item(negative=negative))

    raw = "-2,253,936.21" if negative else "2,253,936.21"
    explained = "2,253,936.21" if negative else "-2,253,936.21"
    for rendered in [output["html"], output["reason"], output["text"]]:
        assert f"FA损益调整金额{raw}" in rendered
        assert f"解释资产差额{explained}" in rendered
        assert "0E-12" not in rendered
        assert RAW_ADJUSTMENT not in rendered
        assert RAW_EXPLAINED not in rendered
        assert ASSET_NAME in rendered
        assert "1511.01.03.GQ523002" in rendered
        assert "GQ523002" in rendered
        assert "2023SJG0206" in rendered
        assert "①" in rendered
        assert "②" in rendered
    assert f"原始合计={raw}" in output["html"]
    assert "剩余差额=0.00" in output["html"]
    assert "剩余差额=0.00" in output["text"]


@pytest.mark.parametrize("negative", [True, False])
def test_reconcile_amount_display_export_uses_fixed_two_decimals_for_signed_totals(negative):
    output = _render_actual_frontend(_historical_equity_item(negative=negative))

    raw = "-2,253,936.21" if negative else "2,253,936.21"
    explained = "2,253,936.21" if negative else "-2,253,936.21"
    assert f"股权损益调整合计={raw}" in output["text"]
    assert f"损益调整解释资产差额={explained}" in output["text"]
    assert "剩余差额=0.00" in output["text"]
    assert f"FA损益调整金额：{raw}；解释资产差额：{explained}" in output["text"]
    assert "FA损益调整金额：0.00；解释资产差额：0.00" in output["text"]


def test_reconcile_amount_display_existing_integer_and_fractional_amounts_keep_two_decimals():
    item = {
        "difference_reason": "资产缺失", "match_status": "已解释",
        "display_details": [
            {"title": "最终判断结果", "rows": [
                {"label": "资负报表资产合计", "value": "1000"},
                {"label": "估值表资产合计", "value": "1100.125"},
                {"label": "资产差异金额", "value": "100"},
            ]},
            {"title": "具体差异明细", "table": {
                "headers": ["科目代码", "科目名称", "科目尾段代码", "金额"],
                "rows": [["1101.02.15.01.100", "第2026期债券1.234567", "100", "100"]],
            }},
        ],
    }

    output = _render_actual_frontend(item)

    assert "<strong>1,000.00</strong>" in output["html"]
    assert "<strong>1,100.13</strong>" in output["html"]
    assert "<strong>100.00</strong>" in output["html"]
    assert "资负报表资产=1,000.00，估值表资产=1,100.13，差异=100.00" in output["text"]
    assert "金额：100.00" in output["text"]
    assert "科目尾段：100；" in output["text"]
    assert "第2026期债券1.234567" in output["text"]


def test_reconcile_amount_display_engine_to_frontend_keeps_decimal_and_raw_payload_precision():
    repo = _equity_profit_loss_repo([
        ("1511.01.03.GQ523002", "股权A", "-353558.620000000000000"),
        ("1511.01.03.GQ523003", "股权B", "-1237455.170000000000000"),
        ("1511.01.03.GQ523004", "股权C", "-662922.420000000000000"),
    ], report="25766472.290000000000000", valuation="23512536.080000000000000", liability="23512536.080000000000000")
    result = ReconcileEngine(repo).run("2026-09-30")[0]
    detail = next(detail.data for detail in result.details if detail.kind == "equity_profit_loss")
    before_result = deepcopy(result)
    item = {"difference_reason": result.difference_reason, "match_status": result.match_status,
            "details": [asdict(detail) for detail in result.details], "display_details": build_display_details(result)}
    before_item = deepcopy(item)

    output = _render_actual_frontend(item)

    assert detail["adjustment_total"] == RAW_ADJUSTMENT
    assert detail["explained_asset_gap"] == RAW_EXPLAINED
    assert result.difference == Decimal(RAW_EXPLAINED)
    assert str(result.difference) == RAW_EXPLAINED
    assert result == before_result
    assert item == before_item
    assert output["unchanged"] is True
    assert "-2,253,936.21" in output["html"]
    assert "0E-15" not in output["html"]
    assert "FA损益调整金额：-353,558.62；解释资产差额：353,558.62" in output["text"]
    assert "剩余差额=0.00" in output["text"]


@pytest.mark.parametrize("value,expected", [
    ("-0", "0.00"),
    ("-0E-12", "0.00"),
    ("-0.004", "0.00"),
    ("-1E-12", "0.00"),
    ("1.234567E+6", "1,234,567.00"),
    ("-1.234567E+6", "-1,234,567.00"),
    ("1.234567E-2", "0.01"),
    ("2,253,936.210000000000000", "2,253,936.21"),
    ("-2,253,936.210000000000000", "-2,253,936.21"),
])
def test_reconcile_amount_display_numeric_boundaries_have_consistent_page_reason_and_export(value, expected):
    item = _historical_equity_item()
    final_rows = item["display_details"][0]["rows"]
    for row in final_rows:
        if row["label"] == "具体原因":
            row["value"] = f"①股权投资损益调整差异：股权；FA损益调整金额{value}，解释资产差额{value}"
        elif row["label"] == "匹配说明":
            row["value"] = f"股权损益调整原始合计={value}，解释资产差额={value}"
        elif row["label"] in {"股权损益调整合计", "损益调整解释资产差额"}:
            row["value"] = value
    table_row = item["display_details"][1]["table"]["rows"][0]
    table_row[4:] = [value, value]

    output = _render_actual_frontend(item)

    assert f"<span>股权损益调整合计</span><strong>{expected}</strong>" in output["html"]
    assert f'<td class="money-cell">{expected}</td><td class="money-cell">{expected}</td>' in output["html"]
    for rendered in [output["html"], output["reason"], output["text"]]:
        assert f"FA损益调整金额{expected}，解释资产差额{expected}" in rendered
        assert "-0.00" not in rendered
    assert f"股权损益调整合计={expected}" in output["text"]
    assert f"FA损益调整金额：{expected}；解释资产差额：{expected}" in output["text"]
    assert output["unchanged"] is True


@pytest.mark.parametrize("name", ["股权金额1234", "股权合计2023", "金额1234/合计2023"])
def test_reconcile_amount_display_preserves_numeric_account_names_in_fields_and_reasons(name):
    item = _historical_equity_item()
    item["display_details"][1]["table"]["rows"][0][2] = name
    reason = f"①股权投资损益调整差异：{name}；FA损益调整金额100，解释资产差额-100"
    item["display_details"][0]["rows"][0]["value"] = reason
    item["display_details"].append({"title": "资产名称核对", "rows": [{"label": "科目名称", "value": name}]})

    output = _render_actual_frontend(item)

    for rendered in [output["html"], output["reason"], output["text"]]:
        assert name in rendered
        assert f"股权投资损益调整差异：{name}；" in rendered
        assert "FA损益调整金额100.00，解释资产差额-100.00" in rendered
    assert f"<span>科目名称</span><strong>{name}</strong>" in output["html"]
    assert output["unchanged"] is True


@pytest.mark.parametrize("invalid", ["1,23", "1.2.3", "1234GQ523002", "1.23.GQ523002", "1E2CODE", "1,234.56CODE"])
def test_reconcile_amount_display_does_not_partially_format_invalid_numbers_or_code_suffixes(invalid):
    item = _historical_equity_item()
    reason = f"①需人工核查：FA损益调整金额{invalid}；解释资产差额{invalid}；业务代码GQ523002"
    item["display_details"][0]["rows"][0]["value"] = reason
    item["display_details"][0]["rows"][1]["value"] = f"股权损益调整原始合计={invalid}；解释资产差额={invalid}"

    output = _render_actual_frontend(item)

    assert output["reason"] == reason
    for rendered in [output["html"], output["text"]]:
        assert f"FA损益调整金额{invalid}；解释资产差额{invalid}；业务代码GQ523002" in rendered
        assert f"原始合计={invalid}；解释资产差额={invalid}" in rendered
    assert output["unchanged"] is True
