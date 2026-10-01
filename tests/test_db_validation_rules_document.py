from io import BytesIO

import pytest
from openpyxl import load_workbook

from auto_check.db_validation.legacy_rules import ACTIVE_LEGACY_RULES, DISABLED_LEGACY_RULE_IDS
from auto_check.db_validation.rules_document import (
    DOCUMENT_ENABLED_RULE_IDS,
    RULE_DOCUMENT_FILENAME,
    build_rules_document,
)


def test_rules_document_is_user_readable_workbook():
    filename, payload = build_rules_document()

    assert filename == RULE_DOCUMENT_FILENAME
    assert payload.startswith(b"PK")

    workbook = load_workbook(BytesIO(payload), read_only=True, data_only=True)
    assert len(workbook.sheetnames) == 3

    overview = workbook[workbook.sheetnames[0]]
    overview_values = [cell.value for row in overview.iter_rows(values_only=False) for cell in row if cell.value]
    assert overview_values
    assert any(
        "\u516c\u5f00\u4fe1\u606f\u4ea4\u53c9\u6821\u9a8c" in str(value)
        and "\u6a21\u677f\u4ea4\u53c9\u6821\u9a8c" in str(value)
        for value in overview_values
    )

    detail = workbook[workbook.sheetnames[2]]
    rows = list(detail.iter_rows(values_only=True))
    assert rows[0][3] in {"\u89c4\u5219\u7f16\u53f7", "\u7470\u52cb\u5782\u7f16\u53f7"}
    flat_text = "\n".join(str(value) for row in rows for value in row if value)
    expected_rule_ids = {rule.rule_id for rule in ACTIVE_LEGACY_RULES}
    document_rule_ids = {row[3] for row in rows[1:]}
    assert expected_rule_ids <= document_rule_ids
    disabled_rule_ids = DISABLED_LEGACY_RULE_IDS - DOCUMENT_ENABLED_RULE_IDS
    disabled_rows = [row for row in rows[1:] if row[3] in disabled_rule_ids]
    if disabled_rows:
        assert {row[9] for row in disabled_rows} <= {"\u505c\u7528", "\u934b\u6ec5\u7528"}
    assert "SQL" not in flat_text

    workbook.close()


def test_rules_document_describes_template_cpkj_table_mapping():
    _, payload = build_rules_document()

    workbook = load_workbook(BytesIO(payload), read_only=True, data_only=True)
    rows = list(workbook[workbook.sheetnames[2]].iter_rows(values_only=True))
    detail_by_rule_id = {row[3]: row for row in rows[1:]}
    flat_text = "\n".join(str(value) for row in rows for value in row if value)

    assert detail_by_rule_id["Zg09_Rule3"][9] == "启用"
    assert detail_by_rule_id["Zg10_Rule1"][9] == "启用"
    assert "信托产品类型口径=1 对比字段映射解析出的 ZG09 口径 1 模板物理表" in flat_text
    assert "信托产品类型口径=1 对比字段映射解析出的 ZG10 口径 1 模板物理表" in flat_text
    assert "口径=2 对比口径 2 模板物理表" in flat_text

    workbook.close()


def _document_rows_by_rule():
    _, payload = build_rules_document()
    workbook = load_workbook(BytesIO(payload), read_only=True, data_only=True)
    try:
        rows = list(workbook["规则明细"].iter_rows(values_only=True))
        return {row[3]: row for row in rows[1:]}
    finally:
        workbook.close()


@pytest.mark.parametrize(
    ("empty_rule", "duplicate_rule", "encoding"),
    [
        ("Zg06_Rule17", "Zg06_Rule18", "资产收益权内部编码"),
        ("Zg07_Rule19", "Zg07_Rule20", "贷款借据编码"),
        ("Zg12_Rule19", "Zg12_Rule20", "除资产收益权外其他债权内部编码"),
    ],
)
def test_20260930_document_describes_raw_encoding_checks_inside_one_institution(
    empty_rule, duplicate_rule, encoding
):
    rows = _document_rows_by_rule()

    assert empty_rule in rows
    assert duplicate_rule in rows
    empty = rows[empty_rule]
    duplicate = rows[duplicate_rule]
    assert empty[9] == duplicate[9] == "启用"
    assert encoding in empty[5]
    assert "NULL" in empty[5] and "NaN" in empty[5] and "空串" in empty[5]
    assert "纯空格" in empty[10] and "字面字符串" in empty[10]
    assert "产品代码" in duplicate[5] and encoding in duplicate[5]
    assert "原始" in duplicate[5] and "大于等于2" in duplicate[5]
    assert "机构内" in duplicate[10]
    assert "不去除首尾空格" in duplicate[10]
    assert "NULL" in duplicate[10] and "不参与" in duplicate[10]
    assert "空串" in duplicate[10] and "同时" in duplicate[10]
    assert "金融机构编码、数据管理机构不作为必需字段" in duplicate[10]
    assert "任一分组键" in duplicate[10]
    assert "每条原始记录" in duplicate[10] and "数据值2保持为空" in duplicate[10]


def test_20260930_document_removes_retired_rules_and_corrects_zg12_form_name():
    rows = _document_rows_by_rule()

    assert "Zg13_Rule15" not in rows
    assert "Zg13_Rule16" not in rows
    assert "Zg13_Rule13" in rows
    assert {row[2] for row in rows.values() if row[1] == "ZG12"} == {
        "除资产收益权外其他债权明细信息"
    }


def test_20260930_document_explains_yield_formulas_and_previous_period_policies():
    rows = _document_rows_by_rule()
    absolute = rows["Zg04_Rule15"]
    zero = rows["Zg04_Rule17"]
    ratio = rows["Zg04_Rule19"]

    assert "abs(当期－上期)>10" in absolute[5]
    assert "差值等于10不提示" in absolute[5]
    assert "地区为空" in absolute[5]
    assert "币种为空" not in absolute[5]
    assert "上期0" in absolute[10]
    assert "未匹配上期，按0比较" in absolute[10]
    assert "产品代码、地区、客户类型、币种" in absolute[10]
    assert "上期数据源不可读" in absolute[10]
    assert absolute[7] == zero[7] == "是"
    assert "上期不等于0" in zero[5] and "NaN" in zero[5]
    assert "当期为0" in zero[5]
    assert "地区、币种为空" in zero[5]
    assert "按产品代码" in zero[10]
    assert "未匹配上期按NaN参与比较" in zero[10]
    assert "纯空格不算空" in zero[10]
    assert "多个上期总计候选逐条比较并输出" in zero[10]
    assert "不增加候选记录数" in zero[10]
    assert "float" in absolute[10] and "浮点边界" in absolute[10]
    assert "20%" in ratio[5]
    assert "上期收益率非0" in ratio[5]
    assert "绝对差" not in ratio[5]


def test_20260930_document_explains_five_filled_flags_without_treating_zero_as_empty():
    row = _document_rows_by_rule()["Zg06_Rule14"]

    assert "类型为4或5" in row[5]
    assert "至少一项已填" in row[5]
    for flag in (
        "科技相关产业标识", "绿色领域标识", "普惠领域标识",
        "养老产业标识", "数字经济核心产业标识",
    ):
        assert flag in row[5]
    assert "数值0" in row[10] and "纯空格" in row[10]
    assert "全部为空" in row[10] and "不提示" in row[10]


def test_20260930_document_overview_identifies_source_version_and_corrected_boundaries():
    _, payload = build_rules_document()
    workbook = load_workbook(BytesIO(payload), read_only=True, data_only=True)
    try:
        overview = "\n".join(
            str(value) for row in workbook["使用说明"].iter_rows(values_only=True)
            for value in row if value
        )
        assert "20260930" in overview
        assert "自己机构内" in overview
        assert "兼容口径" in overview
        assert "Rule17未匹配上期的NaN提示" in overview
        assert workbook.sheetnames == ["使用说明", "规则清单", "规则明细"]
    finally:
        workbook.close()


def test_rules_document_describes_zg05_zg07_loan_balance_mapping_dependency():
    _, payload = build_rules_document()

    workbook = load_workbook(BytesIO(payload), read_only=True, data_only=True)
    rows = list(workbook[workbook.sheetnames[2]].iter_rows(values_only=True))
    detail_by_rule_id = {row[3]: row for row in rows[1:]}

    assert "ZG07“贷款余额折人民币”字段映射" in str(detail_by_rule_id["Zg05_Rule3"][10])

    workbook.close()


def test_rules_document_describes_zg02_original_amount_mapping_dependency():
    _, payload = build_rules_document()

    workbook = load_workbook(BytesIO(payload), read_only=True, data_only=True)
    rows = list(workbook[workbook.sheetnames[2]].iter_rows(values_only=True))
    detail_by_rule_id = {row[3]: row for row in rows[1:]}

    assert "“初始募集金额”和“初始募集金额折人民币”字段映射" in str(
        detail_by_rule_id["Zg02_Rule1"][10]
    )

    workbook.close()
