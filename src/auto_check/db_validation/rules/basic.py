from __future__ import annotations

import contextlib
import contextvars
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable

from auto_check.db_validation.legacy_resources import get_indicator_names, get_org_codes, get_org_info, get_zg05_zg08_mappings
from auto_check.db_validation.legacy_rules import EXECUTABLE_LEGACY_RULE_IDS
from auto_check.db_validation.models import ValidationResultRow
from auto_check.db_validation.rules.common import area_not_county_level, has_value, text, to_decimal
from auto_check.db_validation.tables import report_date_token


_ZG05_RULE_INDICATOR_CODES: frozenset[str] = frozenset({
    "A5100", "AD200", "A7310", "A7320",
    "C1110", "C1120", "C1130", "C1140", "C1150", "C1160", "C1170", "C1180",
    "C1210", "C1220", "C1230", "C1240", "C1250", "C1260", "C1270", "C1280",
})
_ZG05_RULE_INDICATOR_NAMES_BY_CODE: dict[str, str] = {
    name.split("_", 1)[0].upper(): name
    for name in get_indicator_names("ZG05")
    if name.split("_", 1)[0].upper() in _ZG05_RULE_INDICATOR_CODES
}
_ZG05_RULE_INDICATOR_FIELDS: frozenset[str] = frozenset(
    _ZG05_RULE_INDICATOR_NAMES_BY_CODE.values()
)


# ---------------------------------------------------------------------------
# 校验引擎实际使用的中文字段名
# ---------------------------------------------------------------------------
# PyInstaller 冻结环境不提供模块源码，不能在导入阶段调用 inspect.getsource。
# 本快照由 tests/test_package_smoke.py 与规则源码中的字段调用保持同步。
# 保留全局兼容；新逻辑优先使用 REQUIRED_CHINESE_FIELDS_BY_SCOPE（按表/模板/公开信息）。

REQUIRED_CHINESE_FIELDS: frozenset[str] = frozenset({
    "交易对手产品代码",
    "交易对手产品种类",
    "交易对手机构编码",
    "产品代码",
    "产品名称",
    "产品品种",
    "产品增信标识",
    "产品实际终止日期",
    "产品期末业绩表现",
    "产品起始日期",
    "产品预计终止日期",
    "企业规模",
    "信息类型名称",
    "信托产品类型口径",
    "借款人代码",
    "借款人类型",
    "债权类型",
    "兑付客户收益折人民币",
    "兑付客户收益率",
    "其他股权余额折人民币",
    "其他股权投资内部编码",
    "净值型产品期末净值",
    "净值型产品期末净值折人民币",
    "净值型产品期末累计净值",
    "出让机构出表标识",
    "出让机构回购标识",
    "分级产品标识",
    "利率水平",
    "募集起始日期",
    "发行机构代码",
    "发行机构提前终止权标识",
    "合同预计终止日期",
    "地区",
    "地区代码",
    "基础资产出让机构代码",
    "基础资产出让机构注册地区",
    "基础资产出让机构类型",
    "基础资产出让机构行业",
    "基础资产出让机构规模",
    "基础资产类型",
    "境内托管机构代码",
    "增信形式",
    "增信机构类型",
    "客户类型",
    "客户赎回权标识",
    "币种",
    "当月年化收益率",
    "当期申购份额",
    "当期申购金额",
    "托管机构名称",
    "担保方式",
    "持股比例",
    "指标代码",
    "数据值",
    "数据管理机构",
    "数据类型",
    "期末产品份额",
    "期末产品金额",
    "期末产品金额折人民币",
    "期末金额折人民币",
    "机构代码",
    "标的企业代码",
    "法人金融机构名称",
    "登记交易场所",
    "登记交易场所代码",
    "管理方式",
    "股权出让方代码",
    "行业信息",
    "表单名称",
    "贷款产品类别",
    "贷款余额折人民币",
    "贷款借据编码",
    "贷款到期日期",
    "贷款发放日期",
    "贷款合同原始发放机构代码",
    "贷款合同原始发放机构所在地代码",
    "贷款展期到期日期",
    "贷款状态",
    "贷款种类",
    "贷款转让方机构代码",
    "资产收益权内部编码",
    "资产负债项目",
    "转让展期到期日期",
    "转让起始日期",
    "转让预计终止日期",
    "运行方式",
    "金融机构编码",
    "除资产收益权外其他债权余额折人民币",
    "除资产收益权外其他债权内部编码",
    "除资产收益权外其他债权起始日期",
    "除资产收益权外其他债权预计到期日期",
})


# ---------------------------------------------------------------------------
# 按逻辑表/模板/公开信息的必需中文字段集合
# ---------------------------------------------------------------------------
# 每个逻辑范围仅包含本规则真正读取的中文字段，禁止把全局集合套到每一张表。

REQUIRED_CHINESE_FIELDS_BY_SCOPE: dict[str, frozenset[str]] = {
    "ZG01": frozenset({
        "产品代码", "产品名称", "产品预计终止日期", "发行机构提前终止权标识",
        "产品增信标识", "增信形式", "增信机构类型", "运行方式",
        "客户赎回权标识", "募集起始日期", "分级产品标识", "管理方式",
        "托管机构名称", "境内托管机构代码", "发行机构代码",
    }),
    "ZG02": frozenset({
        "产品代码", "地区代码", "客户类型", "地区", "币种",
        "初始募集金额", "初始募集金额折人民币",
    }),
    "ZG03": frozenset({
        "产品代码", "兑付客户收益折人民币", "兑付客户收益率", "币种",
    }),
    "ZG04": frozenset({
        "产品代码", "地区代码", "地区", "客户类型", "币种",
        "期末产品份额", "期末产品金额折人民币", "期末产品金额",
        "当期申购份额", "当期兑付/赎回份额", "当期申购金额", "当期兑付/赎回金额",
        "净值型产品期末净值", "净值型产品期末累计净值", "净值型产品期末净值折人民币",
        "产品期末业绩表现", "当月年化收益率",
    }),
    "ZG05": frozenset({
        "产品代码", "币种", "数据类型",
    }) | _ZG05_RULE_INDICATOR_FIELDS,
    "ZG06": frozenset({
        "产品代码", "资产收益权内部编码", "基础资产出让机构名称", "基础资产出让机构类型",
        "基础资产出让机构行业", "资产负债项目", "基础资产类型",
        "基础资产出让机构代码", "基础资产出让机构注册地区", "基础资产出让机构规模",
        "基础资产出让机构经济成分", "转让起始日期", "转让预计终止日期",
        "转让展期到期日期", "基础资产转让金额折人民币",
        "利率水平", "出让机构出表标识", "出让机构回购标识",
        "基础资产原始协议币种", "基础资产原始协议金额", "基础资产原始协议金额折人民币",
        "基础资产转让币种", "基础资产转让金额", "利率是否固定", "担保方式",
        "基础资产投向部门", "科技相关产业标识", "绿色领域标识", "普惠领域标识",
        "养老产业标识", "数字经济核心产业标识", "基础资产投向对象行业",
        "基础资产投向对象规模",
    }),
    "ZG07": frozenset({
        "产品代码", "贷款借据编码", "贷款种类", "借款人类型", "借款人代码",
        "地区代码", "行业信息", "企业规模", "利率水平", "贷款发放日期",
        "贷款状态", "贷款展期到期日期", "贷款产品类别", "贷款到期日期",
        "贷款转让方机构代码", "贷款合同原始发放机构代码", "贷款合同原始发放机构所在地代码",
        "企业出资人经济成分", "贷款实际投向", "贷款担保方式", "贷款转让折扣率",
        "原始合同币种", "原始合同金额", "原始合同金额折人民币", "贷款余额币种",
        "贷款余额折人民币", "利率是否固定",
        "科技相关产业标识", "绿色领域标识", "普惠领域标识", "养老产业标识",
        "数字经济核心产业标识",
    }),
    "ZG08": frozenset({
        "产品代码", "交易对手产品代码", "交易对手产品种类", "交易对手机构编码",
        "资产负债项目", "期末金额折人民币",
    }),
    "ZG09": frozenset({
        "信托产品类型口径", "发行机构代码",
    }),
    "ZG10": frozenset({
        "信托产品类型口径", "产品品种", "发行机构代码",
    }),
    "ZG12": frozenset({
        "产品代码", "借款人类型", "地区代码", "借款人代码", "行业信息",
        "企业规模", "除资产收益权外其他债权起始日期", "利率水平",
        "除资产收益权外其他债权预计到期日期", "债权类型", "登记交易场所",
        "登记交易场所代码", "担保方式", "除资产收益权外其他债权内部编码", "企业出资人经济成分",
        "除资产收益权外其他债权实际投向", "原始合同币种", "原始合同金额",
        "原始合同金额折人民币", "除资产收益权外其他债权余额币种",
        "除资产收益权外其他债权余额折人民币", "科技相关产业标识", "绿色领域标识",
        "普惠领域标识", "养老产业标识", "数字经济核心产业标识",
    }),
    "ZG13": frozenset({
        "产品代码", "地区代码", "标的企业代码", "股权出让方代码", "资产负债项目",
        "行业信息", "合同预计终止日期", "持股比例", "标的企业名称",
        "企业出资人经济成分", "企业规模", "股权投资方式", "股权出让方名称",
        "合同币种", "其他股权余额币种", "投资退出方式", "合同起始日期",
        "合同展期到期日期", "其他股权投资内部编码",
        "其他股权余额折人民币",
    }),
    "TEMPLATE": frozenset({
        "机构代码", "产品品种", "指标代码", "数据值", "表单名称",
    }),
    "PUBLIC_INFO": frozenset({
        "产品代码", "产品起始日期", "产品起始日", "产品预计终止日期",
        "产品实际终止日期", "发行机构代码", "信息类型名称",
    }),
}


# 规则运行可读取、但缺失时不阻断校验的中文字段。
# 这些字段仍参与自动/人工映射，无法映射时归入“未映射”。
OPTIONAL_CHINESE_FIELDS_BY_SCOPE: dict[str, frozenset[str]] = {
    "ZG04": frozenset({"金融机构编码"}),
    "ZG05": frozenset({"金融机构编码", "数据管理机构"}),
    "ZG06": frozenset({"金融机构编码", "数据管理机构"}),
    "ZG08": frozenset({"发行机构代码"}),
    "ZG09": frozenset({"数据管理机构", "法人金融机构名称"}),
    "ZG10": frozenset({"数据管理机构", "法人金融机构名称"}),
    "ZG13": frozenset({"金融机构编码", "数据管理机构"}),
}


# ---------------------------------------------------------------------------
# 字段名映射解析上下文
# ---------------------------------------------------------------------------
# 当 run_basic_rules 带 field_catalog 调用时，_row_text / _row_has_any 等
# 辅助函数会自动通过映射表解析硬编码的英文字段名，使规则引擎能适应
# 数据库列名变化而无需修改规则代码。
# ---------------------------------------------------------------------------

_FIELD_CATALOG: contextvars.ContextVar[Any] = contextvars.ContextVar("_FIELD_CATALOG", default=None)
_TABLE_NAME: contextvars.ContextVar[str] = contextvars.ContextVar("_TABLE_NAME", default="")


@contextlib.contextmanager
def _rule_context(field_catalog: Any, table_name: str):
    """设置当前规则执行的字段映射上下文。"""
    cat_token = _FIELD_CATALOG.set(field_catalog)
    tbl_token = _TABLE_NAME.set(table_name)
    try:
        yield
    finally:
        _FIELD_CATALOG.reset(cat_token)
        _TABLE_NAME.reset(tbl_token)


def _is_chinese_business_field(name: str) -> bool:
    value = str(name or "")
    return bool(value) and "_" not in value and any("\u4e00" <= ch <= "\u9fff" for ch in value)


def _resolve(field_name: str) -> str:
    """中文业务字段 → 当前英文字段。

    无映射目录或缺字段时返回空字符串，不做英文字段兜底。
    动态指标编码等非中文字段原样返回（ZG05/ZG09/ZG10 指标码）。
    """
    if not field_name:
        return ""
    if not _is_chinese_business_field(field_name):
        return field_name
    catalog = _FIELD_CATALOG.get(None)
    table_name = _TABLE_NAME.get("")
    if catalog is None or not table_name:
        return ""
    try:
        return catalog.field_for(table_name, field_name)
    except (KeyError, AttributeError):
        return ""


def _chinese_fields_only(*fields: str) -> list[str]:
    return [field for field in fields if _is_chinese_business_field(field)]


DEFAULT_ORG_CODE = "D1003632000013"
TEMPLATE_CROSS_CHECK_RULE_IDS: frozenset[str] = frozenset({"Zg09_Rule3", "Zg10_Rule1"})
IMPLEMENTED_RULE_IDS: frozenset[str] = frozenset(
    {
        "Zg01_Rule6",
        "Zg01_Rule1",
        "Zg01_Rule3",
        "Zg01_Rule4",
        "Zg01_Rule5",
        "Zg01_Rule7",
        "Zg01_Rule8",
        "Zg01_Rule9",
        "Zg02_Rule1",
        "Zg02_Rule2",
        "Zg03_Rule1",
        "Zg03_Rule2",
        "Zg04_Rule1",
        "Zg04_Rule2",
        "Zg04_Rule3",
        "Zg04_Rule4",
        "Zg04_Rule6",
        "Zg04_Rule7",
        "Zg04_Rule8",
        "Zg04_Rule9",
        "Zg04_Rule10",
        "Zg04_Rule11",
        "Zg04_Rule12",
        "Zg04_Rule13",
        "Zg04_Rule14",
        "Zg04_Rule15",
        "Zg04_Rule16",
        "Zg04_Rule17",
        "Zg04_Rule18",
        "Zg04_Rule19",
        "Zg05_Rule1",
        "Zg05_Rule2",
        "Zg05_Rule3",
        "Zg05_Rule4",
        "Zg06_Rule3",
        "Zg06_Rule1",
        "Zg06_Rule2",
        "Zg06_Rule4",
        "Zg06_Rule5",
        "Zg06_Rule6",
        "Zg06_Rule7",
        "Zg06_Rule8",
        "Zg06_Rule9",
        "Zg06_Rule10",
        "Zg06_Rule11",
        "Zg06_Rule12",
        "Zg06_Rule13",
        "Zg06_Rule14",
        "Zg06_Rule15",
        "Zg06_Rule16",
        "Zg07_Rule1",
        "Zg07_Rule2",
        "Zg07_Rule3",
        "Zg07_Rule4",
        "Zg07_Rule5",
        "Zg07_Rule6",
        "Zg07_Rule7",
        "Zg07_Rule8",
        "Zg07_Rule9",
        "Zg07_Rule11",
        "Zg07_Rule12",
        "Zg07_Rule13",
        "Zg07_Rule14",
        "Zg07_Rule15",
        "Zg07_Rule16",
        "Zg07_Rule17",
        "Zg07_Rule18",
        "Zg08_Rule2",
        "Zg08_Rule1",
        "Zg08_Rule3",
        "Zg08_Rule4",
        "Zg08_Rule5",
        "Zg08_Rule6",
        "Zg08_Rule7",
        "Zg08_Rule8",
        "Zg08_Rule9",
        "Zg08_Rule10",
        "Zg08_Rule11",
        "Zg08_Rule12",
        "Zg08_Rule13",
        "Zg09_Rule3",
        "Zg10_Rule1",
        "Zg12_Rule1",
        "Zg12_Rule2",
        "Zg12_Rule3",
        "Zg12_Rule4",
        "Zg12_Rule5",
        "Zg12_Rule6",
        "Zg12_Rule7",
        "Zg12_Rule8",
        "Zg12_Rule9",
        "Zg12_Rule10",
        "Zg12_Rule11",
        "Zg12_Rule12",
        "Zg12_Rule13",
        "Zg12_Rule14",
        "Zg12_Rule16",
        "Zg12_Rule17",
        "Zg12_Rule18",
        "Zg13_Rule1",
        "Zg13_Rule2",
        "Zg13_Rule3",
        "Zg13_Rule4",
        "Zg13_Rule5",
        "Zg13_Rule6",
        "Zg13_Rule8",
        "Zg13_Rule9",
        "Zg13_Rule10",
        "Zg13_Rule11",
        "Zg13_Rule12",
        "Zg13_Rule13",
        "Zg13_Rule15",
        "Zg13_Rule16",
    }
)
_LEGACY_RULE_ORDER = (
    "Zg04_Rule1",
    "Zg04_Rule2",
    "Zg04_Rule3",
    "Zg04_Rule4",
    "Zg04_Rule6",
    "Zg04_Rule7",
    "Zg04_Rule8",
    "Zg04_Rule9",
    "Zg04_Rule10",
    "Zg04_Rule11",
    "Zg04_Rule13",
    "Zg04_Rule12",
    "Zg04_Rule14",
    "Zg04_Rule15",
    "Zg04_Rule16",
    "Zg04_Rule17",
    "Zg04_Rule18",
    "Zg04_Rule19",
)


def make_row(
    *,
    report_date: date,
    zg_code: str,
    rule_id: str,
    rule: str,
    form: str,
    detail: str,
    value1: str = "",
    value2: str = "",
    error: str = "",
    org_code: str = DEFAULT_ORG_CODE,
    org_name: str | None = None,
    manager_org: str | None = None,
) -> ValidationResultRow:
    org_info = get_org_info(org_code)
    return ValidationResultRow(
        data_date=report_date.isoformat(),
        org_code=org_code,
        org_name=org_name if org_name is not None else org_info.org_name,
        manager_org=manager_org if manager_org is not None else org_info.manager_org,
        detail=detail,
        form=form,
        value1=value1,
        value2=value2,
        mark=f"{report_date_token(report_date)}-{org_code}-{zg_code}-{rule_id}",
        rule=rule,
        error=error,
        note="",
    )


def _sort_by_legacy_rule_order(rows: list[ValidationResultRow]) -> list[ValidationResultRow]:
    priority = {rule_id: index for index, rule_id in enumerate(_LEGACY_RULE_ORDER)}
    return sorted(
        rows,
        key=lambda row: (
            priority.get(_rule_prefix(row.rule), len(priority)),
            _reverse_text(_detail_first_value(row.detail)),
        ),
    )


def _rule_prefix(rule: str) -> str:
    return rule.split(":", 1)[0].split("：", 1)[0]


def _detail_first_value(detail: str) -> str:
    if ":" not in detail:
        return ""
    return detail.split(":", 1)[1].split("_", 1)[0]


def _reverse_text(value: str) -> str:
    return "".join(chr(0x10FFFF - ord(char)) for char in value)


def run_basic_rules(
    zg_code: str,
    report_date: date,
    current_rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
    related_rows: dict[str, list[dict[str, Any]]] | None = None,
    enable_template_check: bool = False,
    *,
    field_catalog: Any | None = None,
    table_name: str = "",
) -> list[ValidationResultRow]:
    related_rows = related_rows or {}
    with _rule_context(field_catalog, table_name):
        return _run_basic_rules_inner(
            zg_code,
            report_date,
            current_rows,
            previous_rows,
            related_rows,
            enable_template_check,
        )


def _run_basic_rules_inner(
    zg_code: str,
    report_date: date,
    current_rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
    related_rows: dict[str, list[dict[str, Any]]],
    enable_template_check: bool,
) -> list[ValidationResultRow]:
    if not _has_executable_rules_for_zg(zg_code, enable_template_check=enable_template_check):
        return []
    if zg_code == "ZG01":
        return _only_executable(list(_zg01(report_date, current_rows)), enable_template_check=enable_template_check)
    if zg_code == "ZG02":
        return _only_executable(list(_zg02(report_date, current_rows)), enable_template_check=enable_template_check)
    if zg_code == "ZG03":
        return _only_executable(list(_zg03(report_date, current_rows)), enable_template_check=enable_template_check)
    if zg_code == "ZG04":
        return _only_executable(
            _sort_by_legacy_rule_order(list(_zg04(report_date, current_rows, previous_rows, related_rows))),
            enable_template_check=enable_template_check,
        )
    if zg_code == "ZG05":
        return _only_executable(list(_zg05(report_date, current_rows, related_rows)), enable_template_check=enable_template_check)
    if zg_code == "ZG06":
        return _only_executable(
            list(_zg06(report_date, current_rows, previous_rows, related_rows)),
            enable_template_check=enable_template_check,
        )
    if zg_code == "ZG07":
        return _only_executable(
            list(_zg07(report_date, current_rows, previous_rows, related_rows)),
            enable_template_check=enable_template_check,
        )
    if zg_code == "ZG12":
        return _only_executable(
            list(_zg12(report_date, current_rows, previous_rows, related_rows)),
            enable_template_check=enable_template_check,
        )
    if zg_code == "ZG08":
        return _only_executable(
            list(_zg08(report_date, current_rows, previous_rows, related_rows)),
            enable_template_check=enable_template_check,
        )
    if zg_code == "ZG09":
        return _only_executable(
            list(_zg09(report_date, current_rows, related_rows)),
            enable_template_check=enable_template_check,
        )
    if zg_code == "ZG10":
        return _only_executable(
            list(_zg10(report_date, current_rows, related_rows)),
            enable_template_check=enable_template_check,
        )
    if zg_code == "ZG13":
        return _only_executable(
            list(_zg13(report_date, current_rows, previous_rows, related_rows)),
            enable_template_check=enable_template_check,
        )
    return []


def _has_executable_rules_for_zg(zg_code: str, *, enable_template_check: bool = False) -> bool:
    prefix = f"Zg{zg_code[-2:]}_"
    executable_rule_ids = _executable_rule_ids(enable_template_check=enable_template_check)
    return any(rule_id.startswith(prefix) for rule_id in executable_rule_ids)


def _only_executable(rows: list[ValidationResultRow], *, enable_template_check: bool = False) -> list[ValidationResultRow]:
    executable_rule_ids = _executable_rule_ids(enable_template_check=enable_template_check)
    return [row for row in rows if _rule_prefix(row.rule) in executable_rule_ids]


def _executable_rule_ids(*, enable_template_check: bool = False) -> frozenset[str]:
    if enable_template_check:
        return EXECUTABLE_LEGACY_RULE_IDS | TEMPLATE_CROSS_CHECK_RULE_IDS
    return EXECUTABLE_LEGACY_RULE_IDS


def _zg01(report_date: date, rows: list[dict[str, Any]]) -> Iterable[ValidationResultRow]:
    for row in rows:
        projcode = _row_text(row, "产品代码")
        projname = _row_text(row, "产品名称")
        product_end = _row_text(row, "产品预计终止日期")
        early_stop = _row_text(row, "发行机构提前终止权标识")
        if product_end == "" and early_stop == "1":
            yield _zg01_row_result(
                report_date,
                row,
                "Zg01_Rule1",
                "Zg01_Rule1:无固定期限产品，发行机构提前终止权标识填“1-有”，需核实",
                "发行机构提前终止权标识",
                early_stop,
                "产品预计终止日期",
                product_end,
                error="无固定期限产品，发行机构提前终止权标识一般应填“2-无”",
            )

        credit_flag = _row_text(row, "产品增信标识")
        credit_form = _row_text(row, "增信形式")
        credit_type = _row_text(row, "增信机构类型")
        credit_mismatch = (
            credit_flag == "1"
            and (
                ("1" in credit_form and "4" not in credit_type)
                or ("2" in credit_form and not any(value in credit_type for value in ("1", "2", "3", "5", "6")))
                or "1" in credit_type
            )
        )
        if credit_mismatch:
            yield _zg01_row_result(
                report_date,
                row,
                "Zg01_Rule3",
                "Zg01_Rule3:资管产品增信形式与增信机构类型不对应，需核实",
                "增信形式",
                credit_form,
                "增信机构类型",
                credit_type,
                error="资管产品增信形式与增信机构类型不对应；或增信机构类型为住户，需核实",
            )

        run_mode = _row_text(row, "运行方式")
        redeem_flag = _row_text(row, "客户赎回权标识")
        if run_mode in {"1", "2"} and redeem_flag == "1":
            yield _zg01_row_result(
                report_date,
                row,
                "Zg01_Rule4",
                "Zg01_Rule4:开放式产品客户赎回权标识填报“1-有”，需核实",
                "运行方式",
                run_mode,
                "客户赎回权标识",
                redeem_flag,
                error="开放式产品客户赎回权标识一般应填报“2-无”",
            )

        raise_begin = _row_text(row, "募集起始日期")
        if len(projcode) >= 9 and len(raise_begin) >= 4 and projcode[7:9] != raise_begin[2:4]:
            yield _zg01_row_result(
                report_date,
                row,
                "Zg01_Rule5",
                "Zg01_Rule5:产品代码第8-9位，与产品募集起始日期年份不一致，需核实",
                "产品代码",
                projcode,
                "募集起始日期",
                raise_begin,
                error="产品代码第8-9位应当与产品募集起始日期年份一致",
            )

        if len(projname) <= 5 or any(symbol in projname for symbol in ["?", "？", "！", "!", "^"]):
            yield make_row(
                report_date=report_date,
                zg_code="ZG01",
                rule_id="Zg01_Rule6",
                form="资管产品基本信息校验",
                detail=f"产品代码_产品名称:{projcode}_{projname}",
                value1=f"产品名称:{projname}",
                rule="Zg01_Rule6:产品名称长度小于等于5个字，有特殊符号，需核实",
                error="产品名称过于简单，含有特殊字符（？、！、^），需核实",
            )

        level_flag = _row_text(row, "分级产品标识")
        manage_source = _row_text(row, "管理方式")
        if level_flag == "1" and manage_source == "2":
            yield _zg01_row_result(
                report_date,
                row,
                "Zg01_Rule7",
                "Zg01_Rule7:分级产品的管理方式为单独管理，需核实",
                "分级产品标识",
                level_flag,
                "管理方式",
                manage_source,
                error="分级产品的管理方式一般应为集合管理",
            )

        custodian_name = _row_text(row, "托管机构名称")
        custodian_code = _row_text(row, "境内托管机构代码")
        if any(keyword in custodian_name and custodian_name.find(keyword) > 0 for keyword in ("分行", "支行", "营业部", "营业室")):
            yield _zg01_row_result(
                report_date,
                row,
                "Zg01_Rule8",
                "Zg01_Rule8:托管机构名称未填报法人机构名称，需核实",
                "托管机构名称",
                custodian_name,
                error="托管机构名称应填报法人机构名称",
            )
        if (custodian_name != "" and custodian_code == "") or (custodian_name == "" and custodian_code != ""):
            yield _zg01_row_result(
                report_date,
                row,
                "Zg01_Rule9",
                "Zg01_Rule9:托管机构名称与代码未同时有数，需核实",
                "托管机构名称",
                custodian_name,
                "境内托管机构代码",
                custodian_code,
                error="托管机构名称与代码应同时有数",
            )


def _zg01_row_result(
    report_date: date,
    row: dict[str, Any],
    rule_id: str,
    rule: str,
    value1_label: str,
    value1: str,
    value2_label: str = "",
    value2: str = "",
    *,
    error: str = "",
) -> ValidationResultRow:
    projcode = _row_text(row, "产品代码")
    projname = _row_text(row, "产品名称")
    return make_row(
        report_date=report_date,
        zg_code="ZG01",
        rule_id=rule_id,
        form="资管产品基本信息",
        detail=f"产品代码_产品名称:{projcode}_{projname}",
        value1=f"{value1_label}:{value1}" if value1_label else text(value1),
        value2=f"{value2_label}:{value2}" if value2_label else "",
        rule=rule,
        error=error,
    )


def _zg02(report_date: date, rows: list[dict[str, Any]]) -> Iterable[ValidationResultRow]:
    yield from _currency_total_rules(
        report_date,
        "ZG02",
        rows,
        key_fields=("产品代码", "地区代码", "客户类型"),
        exclude_fields={"币种", "产品代码", "地区代码", "地区", "客户类型"},
        rule_id="Zg02_Rule1",
        rule="Zg02_Rule1:初始募集信息指标人民币合计与人民币金额不相等，需核实",
        form="资管产品初始募集信息",
    )

    for row in rows:
        area_code = _row_text(row, "地区", "地区代码")
        client_kind = _row_text(row, "客户类型")
        if area_code == "000000" or not area_code:
            continue
        if (area_code[:3] == "000" and client_kind != "6") or (area_code[:3] != "000" and client_kind == "6"):
            yield make_row(
                report_date=report_date,
                zg_code="ZG02",
                rule_id="Zg02_Rule2",
                form="资管产品初始募集信息",
                detail=_legacy_detail(row, "产品代码_地区_客户类型_币种", ("产品代码", "地区", "地区代码", "客户类型", "币种")),
                value1=f"初始募集金额折人民币:{_legacy_df_text(_row_value(row, '初始募集金额折人民币'))}",
                rule="Zg02_Rule2:客户类型与地区代码不对应，需核实",
                error="客户类型应当与地区代码对应",
            )


def _zg03(report_date: date, rows: list[dict[str, Any]]) -> Iterable[ValidationResultRow]:
    for row in rows:
        client_income_cny = _legacy_float(_row_value(row, "兑付客户收益折人民币"))
        client_rate = _row_text(row, "兑付客户收益率")
        rate_value = _legacy_float(client_rate.replace("%", "")) if client_rate else 0.0
        if client_income_cny > 500000000 or (client_rate and ("%" in client_rate or rate_value > 10)):
            yield make_row(
                report_date=report_date,
                zg_code="ZG03",
                rule_id="Zg03_Rule1",
                form="资管产品终止信息",
                detail=_legacy_detail(row, "产品代码", ("产品代码",)),
                value1=f"兑付客户收益折人民币:{_legacy_df_text(_row_value(row, '兑付客户收益折人民币'))}",
                value2=f"兑付客户收益率:{client_rate}",
                rule="Zg03_Rule1:兑付客户收益金额较大，超过5亿元；兑付客户收益率过高，大于10%，需核实",
                error="兑付客户收益金额较大；兑付客户收益率过高；或含有“%”，需核实",
            )

    yield from _currency_total_rules(
        report_date,
        "ZG03",
        rows,
        key_fields=("产品代码",),
        exclude_fields={"币种", "产品代码", "兑付客户收益率"},
        rule_id="Zg03_Rule2",
        rule="Zg03_Rule2:终止信息指标人民币合计与人民币金额不相等，需核实",
        form="资管产品终止信息",
    )


def _zg05(
    report_date: date,
    rows: list[dict[str, Any]],
    related_rows: dict[str, list[dict[str, Any]]],
) -> Iterable[ValidationResultRow]:
    by_key = {(_row_text(row, "产品代码"), _row_text(row, "币种"), _row_text(row, "数据类型")): row for row in rows}
    metric_specs = _legacy_zg_metric_specs("ZG05", skip={"产品代码", "币种", "数据类型"})
    zg07_totals = _zg07_loan_totals(related_rows.get("ZG07", []))
    spv_totals = _zg08_spv_totals(related_rows.get("ZG08", []))

    for row in rows:
        if _row_text(row, "币种") != "BWB" or _row_text(row, "数据类型") != "3":
            continue
        projcode = _row_text(row, "产品代码")
        cny1_row = by_key.get((projcode, "CNY", "1"))
        if not cny1_row:
            yield from _zg05_related_rules_for_row(report_date, row, projcode, zg07_totals, spv_totals)
            continue
        for cny_type, rule_id, rule_text in (
            ("1", "Zg05_Rule1", "Zg05_Rule1:资产负债指标人民币合计与人民币金额不相等，需核实"),
            ("2", "Zg05_Rule2", "Zg05_Rule2:资产负债指标人民币合计与折人民币金额不相等，需核实"),
        ):
            cny_row = by_key.get((projcode, "CNY", cny_type))
            if not cny_row:
                continue
            for field, label in metric_specs:
                diff = _legacy_float(_row_value(cny_row, field, label)) - _legacy_float(_row_value(row, field, label))
                if diff == 0:
                    continue
                yield make_row(
                    report_date=report_date,
                    zg_code="ZG05",
                    rule_id=rule_id,
                    form="资产负债明细信息",
                    detail=f"产品代码_指标名称_BWB_3:{projcode}_{label}_{_legacy_df_text(_row_value(row, field, label))}",
                    value1=f"CNY_{cny_type}:{_legacy_df_text(_row_value(cny_row, field, label))}",
                    value2=f"差值:{diff}",
                    rule=rule_text,
                    error="资产负债指标人民币合计与人民币金额应相等",
                )

        loan_value = _legacy_float(_zg05_indicator_value(row, "A5100"))
        if loan_value != 0:
            zg07_total = zg07_totals.get(projcode, 0.0)
            if loan_value != zg07_total:
                yield make_row(
                    report_date=report_date,
                    zg_code="ZG05",
                    rule_id="Zg05_Rule3",
                    form="资产负债明细信息VS除回购和拆借外贷款",
                    detail=f"产品代码_A5100:{projcode}_{loan_value}",
                    value1=f"ZG07_贷款余额折人民币:{zg07_total}",
                    value2=f"差值（G05减G07）:{loan_value - zg07_total}",
                    rule="Zg05_Rule3:ZG05除回购和拆借外贷款与ZG07明细数据汇总金额不相等，需核实",
                    error="ZG05除回购和拆借外贷款与ZG07明细数据汇总金额应相等",
                )

        for mapping in get_zg05_zg08_mappings():
            field = _legacy_indicator_field(mapping.zg05_indicator)
            debt_project = f"{field[:3].upper()}00"
            zg05_value = _legacy_float(_row_value(row, field, mapping.zg05_indicator))
            if zg05_value <= 0:
                continue
            zg08_total = spv_totals.get((projcode, debt_project, mapping.zg08_counterparty_type), 0.0)
            diff = zg05_value - zg08_total
            if abs(diff) <= 0.1:
                continue
            yield make_row(
                report_date=report_date,
                zg_code="ZG05",
                rule_id="Zg05_Rule4",
                form="资产负债明细信息VS特定目的载体交易对手明细信息",
                detail=f"产品代码_指标名称:{projcode}_{mapping.zg05_indicator}",
                value1=f"ZG05指标:{zg05_value}",
                value2=f"ZG08汇总:{zg08_total}",
                rule="Zg05_Rule4:ZG05指标与ZG08明细数据汇总金额不相等，需核实",
                error="ZG05指标与ZG08明细数据汇总金额应相等",
            )


def _zg05_related_rules_for_row(
    report_date: date,
    row: dict[str, Any],
    projcode: str,
    zg07_totals: dict[str, float],
    spv_totals: dict[tuple[str, str, str], float],
) -> Iterable[ValidationResultRow]:
    loan_value = _legacy_float(_zg05_indicator_value(row, "A5100"))
    if loan_value != 0:
        zg07_total = zg07_totals.get(projcode, 0.0)
        if loan_value != zg07_total:
            yield make_row(
                report_date=report_date,
                zg_code="ZG05",
                rule_id="Zg05_Rule3",
                form="资产负债明细信息VS除回购和拆借外贷款",
                detail=f"产品代码_A5100:{projcode}_{loan_value}",
                value1=f"ZG07_贷款余额折人民币:{zg07_total}",
                value2=f"差值（G05减G07）:{loan_value - zg07_total}",
                rule="Zg05_Rule3:ZG05除回购和拆借外贷款与ZG07明细数据汇总金额不相等，需核实",
                error="ZG05除回购和拆借外贷款与ZG07明细数据汇总金额应相等",
            )

    for mapping in get_zg05_zg08_mappings():
        field = _legacy_indicator_field(mapping.zg05_indicator)
        debt_project = f"{field[:3].upper()}00"
        zg05_value = _legacy_float(_row_value(row, field, mapping.zg05_indicator))
        if zg05_value <= 0:
            continue
        zg08_total = spv_totals.get((projcode, debt_project, mapping.zg08_counterparty_type), 0.0)
        diff = zg05_value - zg08_total
        if abs(diff) <= 0.1:
            continue
        yield make_row(
            report_date=report_date,
            zg_code="ZG05",
            rule_id="Zg05_Rule4",
            form="资产负债明细信息VS特定目的载体交易对手明细信息",
            detail=f"产品代码_指标名称:{projcode}_{mapping.zg05_indicator}",
            value1=f"ZG05指标:{zg05_value}",
            value2=f"ZG08汇总:{zg08_total}",
            rule="Zg05_Rule4:ZG05指标与ZG08明细数据汇总金额不相等，需核实",
            error="ZG05指标与ZG08明细数据汇总金额应相等",
        )


def _zg04(
    report_date: date,
    rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
    related_rows: dict[str, list[dict[str, Any]]],
) -> Iterable[ValidationResultRow]:
    previous_by_key = {
        (_zg04_product_code(r), _zg04_area_code(r), _zg04_client_kind(r), _zg04_currency(r)): r
        for r in previous_rows
    }
    summary_nav_by_product_currency = _zg04_summary_nav_by_product_currency(rows)
    terminated_products = {_zg04_product_code(row) for row in related_rows.get("ZG03", []) if _zg04_product_code(row)}
    zero_share_products = {
        _zg04_product_code(row)
        for row in rows
        if _zg04_area_code(row) and _legacy_float(_row_value(row, "期末产品份额")) == 0.0
    }
    product_amounts: dict[str, float] = {}
    for row in rows:
        if _zg04_area_code(row) == "000000" and _zg04_currency(row) == "BWB":
            projcode = _zg04_product_code(row)
            product_amounts[projcode] = product_amounts.get(projcode, 0.0) + _legacy_float(
                _row_value(row, "期末产品金额折人民币")
            )
    zero_amount_products = {projcode for projcode, amount in product_amounts.items() if amount == 0.0}

    yield from _zg04_share_principal_rules(report_date, rows, related_rows.get("ZG05", []))
    yield from _currency_total_rules(
        report_date,
        "ZG04",
        rows,
        key_fields=("产品代码", "地区代码", "客户类型"),
        exclude_fields={
            "产品代码",
            "地区",
            "地区代码",
            "客户类型",
            "币种",
        },
        rule_id="Zg04_Rule8",
        rule="Zg04_Rule8:存续期募集信息指标人民币合计与人民币金额不相等，需核实",
        form="资管产品存续期募集信息",
    )

    for row in rows:
        key = (_zg04_product_code(row), _zg04_area_code(row), _zg04_client_kind(row), _zg04_currency(row))
        prev = previous_by_key.get(key)
        previous_share = to_decimal(_row_value(prev, "期末产品份额")) if prev else Decimal("0")
        expected_share = previous_share + to_decimal(_row_value(row, "当期申购份额")) - to_decimal(
            _row_value(row, "当期兑付/赎回份额")
        )
        actual_share = to_decimal(_row_value(row, "期末产品份额"))
        if abs(actual_share - expected_share) > Decimal("0.01"):
            share_diff = (
                _legacy_float(previous_share)
                + _legacy_float(_row_value(row, "当期申购份额"))
                - _legacy_float(_row_value(row, "当期兑付/赎回份额"))
                - _legacy_float(_row_value(row, "期末产品份额"))
            )
            yield make_row(
                report_date=report_date,
                zg_code="ZG04",
                rule_id="Zg04_Rule2",
                form="资管产品存续期募集信息上下期校验",
                detail="产品代码_地区_客户类型_币种_上期产品份额_当期申购份额_当期兑付/赎回份额_期末产品份额:"
                f"{key[0]}_{key[1]}_{key[2]}_{key[3]}_{_legacy_number_text(previous_share)}_{_legacy_number_text(_row_value(row, '当期申购份额'))}_{_legacy_number_text(_row_value(row, '当期兑付/赎回份额'))}_{_legacy_number_text(_row_value(row, '期末产品份额'))}",
                value1=f"期末产品份额:{_legacy_number_text(_row_value(row, '期末产品份额'))}",
                value2=f"份额跨期差值:{share_diff}",
                rule="Zg04_Rule2:产品份额比对不符合校验公式（当期期末产品份额=上期期末产品份额+当期申购份额-当期兑付份额），需核实",
                error="产品份额比对不符合校验公式，需核实",
            )

        if key[1] and key[1] != "000000" and key[3] != "BWB":
            previous_amount = _legacy_float(_row_value(prev, "期末产品金额")) / 10000.0 if prev else 0.0
            raise_amount = _legacy_float(_row_value(row, "当期申购金额")) / 10000.0
            cash_amount = _legacy_float(_row_value(row, "当期兑付/赎回金额")) / 10000.0
            actual_amount = _legacy_float(_row_value(row, "期末产品金额")) / 10000.0
            expected_amount = previous_amount + raise_amount - cash_amount
            amount_diff = expected_amount - actual_amount
            if expected_amount:
                amount_ratio = amount_diff / expected_amount
            elif actual_amount:
                amount_ratio = float("-inf")
            else:
                amount_ratio = 0.0
            if abs(amount_diff) >= 1000 and abs(amount_ratio) > 0.05:
                yield make_row(
                    report_date=report_date,
                    zg_code="ZG04",
                    rule_id="Zg04_Rule3",
                    form="资管产品存续期募集信息上下期校验",
                    detail="产品代码_地区_客户类型_币种_上期产品金额_当期申购金额_当期兑付/赎回金额_期末产品金额:"
                    f"{key[0]}_{key[1]}_{key[2]}_{key[3]}_{previous_amount}_{raise_amount}_{cash_amount}_{actual_amount}",
                    value1=f"金额跨期差值波动幅度:{amount_ratio}",
                    value2=f"金额跨期差值:{amount_diff}",
                    rule="Zg04_Rule3:产品金额比对不符合校验公式（当期期末产品金额≈上期期末产品金额+当期申购金额-当期兑付金额），需核实",
                    error="产品金额比对不符合校验公式，需核实",
                )

        if prev and _zg04_is_summary_row(row):
            current_nav = _legacy_float(_row_value(row, "净值型产品期末净值"))
            previous_nav = _legacy_float(_row_value(prev, "净值型产品期末净值"))
            if previous_nav != 0 and abs((current_nav - previous_nav) / previous_nav) > 0.2:
                nav_diff = current_nav - previous_nav
                nav_ratio = nav_diff / previous_nav
                yield make_row(
                    report_date=report_date,
                    zg_code="ZG04",
                    rule_id="Zg04_Rule4",
                    form="资管产品存续期募集信息上下期校验",
                    detail=f"产品代码_地区_客户类型_币种_净值跨期差值_净值跨期差值波动幅度:{key[0]}_{_legacy_key_part(key[1])}_{_legacy_key_part(key[2])}_{_legacy_key_part(key[3])}_{nav_diff}_{nav_ratio}",
                    value1=f"净值型产品期末净值:{_legacy_number_text(current_nav)}",
                    value2=f"净值型产品上期期末净值:{_legacy_number_text(previous_nav)}",
                    rule="Zg04_Rule4:净值型产品报送期末净值跨期变动过大（超过20%），需核实",
                    error="净值型产品报送期末净值跨期变动过大（超过20%），需核实",
                )

        if _zg04_is_summary_row(row) and _row_has_any(row, "净值型产品期末净值") and _row_has_any(row, "净值型产品期末累计净值"):
            nav = _legacy_float(_row_value(row, "净值型产品期末净值"))
            cumulative_nav = _legacy_float(_row_value(row, "净值型产品期末累计净值"))
            if cumulative_nav < nav:
                yield _zg04_row_result(
                    report_date,
                    row,
                    "Zg04_Rule6",
                    "Zg04_Rule6：净值型产品期末累计净值小于期末净值，需核实",
                    "净值型产品期末净值",
                    _legacy_number_text(nav),
                    "净值型产品期末累计净值",
                    _legacy_number_text(cumulative_nav),
                    error="净值型产品期末累计净值一般应大于等于期末净值",
                )

        if (
            prev
            and key[0] in zero_share_products
            and key[0] in terminated_products
            and key[3] == "BWB"
            and _legacy_float(_row_value(prev, "净值型产品期末净值")) > 0
        ):
            current_nav = _legacy_float(_row_value(row, "净值型产品期末净值"))
            previous_nav = _legacy_float(_row_value(prev, "净值型产品期末净值"))
            if current_nav != previous_nav and current_nav == 1:
                yield make_row(
                    report_date=report_date,
                    zg_code="ZG04",
                    rule_id="Zg04_Rule7",
                    form="资管产品存续期募集信息",
                    detail=f"产品代码:{key[0]}",
                    value1=f"净值型产品期末净值:{_legacy_number_text(current_nav)}",
                    value2=f"净值型产品上期期末净值:{_legacy_number_text(previous_nav)}",
                    rule="Zg04_Rule7：期末产品份额为0的净值型产品期末净值与上期不一致且为1，需核实",
                    error="期末产品份额为0的净值型产品期末净值为1，需核实",
                )

        if key[1] != "000000" and _row_has_any(row, "地区") and _row_has_any(row, "客户类型"):
            if (key[1].startswith("000") and key[2] != "6") or (not key[1].startswith("000") and key[2] == "6"):
                yield _zg04_row_result(
                    report_date,
                    row,
                    "Zg04_Rule9",
                    "Zg04_Rule9:客户类型与地区代码不对应，需核实",
                    "期末产品金额折人民币",
                    _legacy_df_text(_row_value(row, "期末产品金额折人民币")),
                    error="客户类型应当与地区代码对应",
                )

        summary_nav = summary_nav_by_product_currency.get((key[0], key[3]))
        if key[1] and key[3] == "BWB" and summary_nav and _amount_share_nav_delta_over(
            row,
            "当期申购金额",
            "当期申购份额",
            summary_nav,
        ):
            yield _zg04_amount_share_result(
                report_date,
                row,
                "Zg04_Rule11",
                "Zg04_Rule11:当期募集金额与份额变动过大（超过20%），需核实",
                "资管产品存续期募集信息",
                "当期申购金额",
                "当期申购份额",
                summary_nav,
                error="当期募集金额与份额变动过大（超过20%），需核实",
            )

        if key[1] and key[3] == "BWB" and summary_nav and _amount_share_nav_delta_over(
            row,
            "当期兑付/赎回金额",
            "当期兑付/赎回份额",
            summary_nav,
        ):
            yield _zg04_amount_share_result(
                report_date,
                row,
                "Zg04_Rule13",
                "Zg04_Rule13:当期兑付/赎回金额与份额变动过大（超过20%），需核实",
                "资管产品存续期兑付/赎回信息",
                "当期兑付/赎回金额",
                "当期兑付/赎回份额",
                summary_nav,
                error="当期兑付/赎回金额与份额变动过大（超过20%），需核实",
            )

        if key[1] and key[3] != "CNY" and summary_nav:
            current_amount = _legacy_float(_row_value(row, "期末产品金额折人民币"))
            current_share = _legacy_float(_row_value(row, "期末产品份额"))
            nav_amount = current_share * summary_nav
            diff = current_amount - nav_amount
            if summary_nav > 0 and abs(diff) > 5000:
                yield make_row(
                    report_date=report_date,
                    zg_code="ZG04",
                    rule_id="Zg04_Rule14",
                    form="资管产品存续期募集信息校验",
                    detail=f"产品代码_地区_客户类型_币种_净值跨期差值_净值型产品期末净值折人民币:{key[0]}_{key[1]}_{key[2]}_{key[3]}_{diff}_{summary_nav}",
                    value1=f"期末产品金额折人民币:{_legacy_number_text(current_amount)}",
                    value2=f"期末产品份额:{_legacy_number_text(current_share)}",
                    rule="Zg04_Rule14：存续期募集信息净值型产品期末净值和期末产品份额之积与期末产品金额的差值较大，需核实",
                    error="产品金额与份额乘以净值差异较大（超过5000元），需核实",
                )

        if key[1] and _row_has_any(row, "期末产品金额折人民币") and _row_has_any(row, "期末产品份额"):
            if _legacy_float(_row_value(row, "期末产品份额")) == 0 and _legacy_float(
                _row_value(row, "期末产品金额折人民币")
            ) > 0:
                yield _zg04_row_result(
                    report_date,
                    row,
                    "Zg04_Rule16",
                    "Zg04_Rule16:净值型产品期末产品金额有数，期末产品份额为0，需核实",
                    "期末产品金额折人民币",
                    _legacy_number_text(_row_value(row, "期末产品金额折人民币")),
                    "期末产品份额",
                    _legacy_number_text(_row_value(row, "期末产品份额")),
                    error="净值型产品期末产品金额有数，期末产品份额为0",
                )

        if _zg04_is_summary_row(row) and key[3] == "BWB" and _row_has_any(row, "净值型产品期末净值") and _row_has_any(row, "净值型产品期末累计净值"):
            nav = _legacy_float(_row_value(row, "净值型产品期末净值"))
            cumulative_nav = _legacy_float(_row_value(row, "净值型产品期末累计净值"))
            if nav == 0 or cumulative_nav == 0:
                yield _zg04_row_result(
                    report_date,
                    row,
                    "Zg04_Rule18",
                    "Zg04_Rule18：净值型产品期末净值或累计净值为0，需核实",
                    "净值型产品期末净值",
                    _legacy_number_text(nav),
                    "净值型产品期末累计净值",
                    _legacy_number_text(cumulative_nav),
                    error="净值型产品期末净值或累计净值为0，需核实",
                )

        if prev and key[1] == "":
            current_yield = _legacy_float(_row_value(row, "当月年化收益率"))
            previous_yield = _legacy_float(_row_value(prev, "当月年化收益率"))
            if previous_yield != 0:
                yield_diff = current_yield - previous_yield
                yield_ratio = yield_diff / previous_yield
                key_text = "_".join(_legacy_key_part(part) for part in key)
                if abs(yield_ratio) > 2 and abs(previous_yield) > 0:
                    rule = "Zg04_Rule15：当月年化收益率跨期变动过大（超过200%），需核实"
                    yield make_row(
                        report_date=report_date,
                        zg_code="ZG04",
                        rule_id=rule,
                        form="资管产品存续期募集信息上下期校验",
                        detail=f"产品代码_地区_客户类型_币种_当月年化收益率跨期差值_当月年化收益率跨期差值波动幅度:{key_text}_{yield_diff}_{yield_ratio}",
                        value1=f"当月年化收益率:{_legacy_number_text(_row_value(row, '当月年化收益率'))}",
                        value2=f"当月年化收益率上期数:{_legacy_number_text(_row_value(prev, '当月年化收益率'))}",
                        rule=rule,
                        error="当月年化收益率跨期变动过大（超过200%），需核实",
                    )
                if _row_text(row, "产品代码") in zero_amount_products and abs(yield_ratio) > 0.2 and abs(previous_yield) > 0:
                    rule = "Zg04_Rule19：期末产品金额折人民币为0时，当月年化收益率比上期波动超过20%，需核实"
                    yield make_row(
                        report_date=report_date,
                        zg_code="ZG04",
                        rule_id=rule,
                        form="资管产品存续期募集信息上下期校验",
                        detail=f"产品代码_地区_客户类型_币种_当月年化收益率跨期差值_当月年化收益率跨期差值波动幅度:{key_text}_{yield_diff}_{yield_ratio}",
                        value1=f"当月年化收益率:{_legacy_number_text(_row_value(row, '当月年化收益率'))}",
                        value2=f"当月年化收益率上期数:{_legacy_number_text(_row_value(prev, '当月年化收益率'))}",
                        rule=rule,
                        error="期末产品金额折人民币为0时，当月年化收益率比上期波动超过20%，需核实",
                    )

        if key[1] == "" and key[3] == "" and _legacy_has_text(_row_value(row, "当月年化收益率")) and _legacy_float(_row_value(row, "当月年化收益率")) == 0:
            rule = "Zg04_Rule17：当月年化收益率为0，需核实"
            yield make_row(
                report_date=report_date,
                zg_code="ZG04",
                rule_id=rule,
                form="资管产品存续期募集信息",
                detail=f"产品代码:{key[0]}",
                value1=f"当月年化收益率:{_legacy_number_text(_row_value(row, '当月年化收益率'))}",
                rule=rule,
                error="当月年化收益率为0，需核实",
            )

        if _row_has_any(row, "当期申购金额") and _row_has_any(row, "当期申购份额") and (
            has_value(_row_value(row, "当期申购金额")) != has_value(_row_value(row, "当期申购份额"))
        ):
            yield make_row(
                report_date=report_date,
                zg_code="ZG04",
                rule_id="Zg04_Rule10",
                form="资管产品存续期募集信息校验",
                detail=f"产品代码_地区_客户类型_币种:{key[0]}_{key[1]}_{key[2]}_{key[3]}",
                value1=f"当期申购金额:{_row_value(row, '当期申购金额')}",
                value2=f"当期申购份额:{_row_value(row, '当期申购份额')}",
                rule="Zg04_Rule10:当期申购金额与份额未同时有数，需核实",
            )

        if (
            _zg04_area_code(row)
            and _row_has_any(row, "当期兑付/赎回金额")
            and _row_has_any(row, "当期兑付/赎回份额")
            and _legacy_float(_row_value(row, "当期兑付/赎回金额")) <= 0
            and _legacy_float(_row_value(row, "当期兑付/赎回份额")) > 0
        ):
            yield make_row(
                report_date=report_date,
                zg_code="ZG04",
                rule_id="Zg04_Rule12",
                form="资管产品存续期募集信息",
                detail=f"产品代码_地区_客户类型_币种:{key[0]}_{key[1]}_{key[2]}_{key[3]}",
                value1=f"当期兑付/赎回金额:{_row_value(row, '当期兑付/赎回金额')}",
                value2=f"当期兑付/赎回份额:{_row_value(row, '当期兑付/赎回份额')}",
                rule="Zg04_Rule12:当期兑付/赎回金额与份额未同时有数，需核实",
                error="当期兑付/赎回金额与份额应同时有数",
            )


def _zg04_share_principal_rules(
    report_date: date,
    rows: list[dict[str, Any]],
    zg05_rows: list[dict[str, Any]],
) -> Iterable[ValidationResultRow]:
    principal_index = _zg05_client_principal_index(zg05_rows)
    for row in rows:
        client_kind = _zg04_client_kind(row)
        if client_kind not in {"1", "2", "3", "4", "5", "6"}:
            continue
        if _zg04_currency(row) != "BWB" or _zg04_area_code(row) not in {"000000", "0"}:
            continue
        product_code = _zg04_product_code(row)
        share = _legacy_float(_row_value(row, "期末产品份额"))
        if share <= 0:
            continue
        principal = principal_index.get((product_code, client_kind, _row_financial_org_code(row)), 0.0)
        diff = share - principal
        if abs(diff) <= 0.1:
            continue
        yield make_row(
            report_date=report_date,
            zg_code="ZG04-ZG05",
            rule_id="Zg04_Rule1",
            form="资管产品存续期募集信息VS资产负债信息",
            detail=f"产品代码_地区_客户类型_币种_期末份额减实收本金:{product_code}_{_zg04_area_code(row)}_{client_kind}_{_zg04_currency(row)}_{diff}",
            value1=f"期末产品份额:{_legacy_number_text(share)}",
            value2=f"期末产品金额折人民币:{_legacy_number_text(_row_value(row, '期末产品金额折人民币'))}",
            rule="Zg04_Rule1:分产品分客户类型存续募集信息（ZG04）份额与资产负债信息（ZG05）实收本金不一致，需核实",
            error="存续募集信息（ZG04）分客户类型份额与资产负债信息（ZG05）实收本金不一致，需核实",
        )


def _zg05_client_principal_index(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], float]:
    totals: dict[tuple[str, str, str], float] = {}
    for row in rows:
        product_code = _row_text(row, "产品代码")
        if not product_code:
            continue
        if _row_text(row, "币种") != "BWB" or _row_text(row, "数据类型") != "3":
            continue
        org_code = _row_financial_org_code(row)
        for client_kind in ("1", "2", "3", "4", "5", "6"):
            totals[(product_code, client_kind, org_code)] = totals.get((product_code, client_kind, org_code), 0.0) + _zg05_client_principal_for_row(row, client_kind)
    return totals


def _zg05_client_principal(rows: list[dict[str, Any]], product_code: str, client_kind: str, org_code: str) -> float:
    total = 0.0
    for row in rows:
        if _row_text(row, "产品代码") != product_code:
            continue
        if _row_text(row, "币种") != "BWB" or _row_text(row, "数据类型") != "3":
            continue
        if _row_financial_org_code(row) != org_code:
            continue
        total += _zg05_client_principal_for_row(row, client_kind)
    return total


def _zg05_client_principal_for_row(row: dict[str, Any], client_kind: str) -> float:
    component_codes = {
        "1": ("C1110", "C1210"),
        "2": ("C1120", "C1220"),
        "3": ("C1130", "C1230"),
        "4": ("C1140", "C1240", "C1150", "C1250", "C1160", "C1260"),
        "5": ("C1170", "C1270"),
        "6": ("C1180", "C1280"),
    }[client_kind]
    return sum(
        _legacy_float(_zg05_indicator_value(row, code))
        for code in component_codes
    )


def _zg04_summary_nav_by_product_currency(rows: list[dict[str, Any]]) -> dict[tuple[str, str], float]:
    result: dict[tuple[str, str], float] = {}
    for row in rows:
        if not _zg04_is_summary_row(row):
            continue
        if _legacy_has_text(_row_value(row, "产品期末业绩表现")):
            continue
        product_code = _zg04_product_code(row)
        currency = _zg04_currency(row)
        nav = _row_value(row, "净值型产品期末净值折人民币")
        if not _legacy_has_text(nav):
            nav = _row_value(row, "净值型产品期末净值")
        if product_code and currency and _legacy_has_text(nav):
            result[(product_code, currency)] = _legacy_float(nav)
    return result


def _amount_share_nav_delta_over(
    row: dict[str, Any],
    amount_label: str,
    share_label: str,
    nav: float,
) -> bool:
    if not _row_has_any(row, amount_label) or not _row_has_any(row, share_label):
        return False
    amount = _legacy_float(_row_value(row, amount_label))
    share = _legacy_float(_row_value(row, share_label))
    if share == 0 or nav == 0:
        return False
    diff = amount - nav * share
    ratio = diff / share
    return abs(ratio) > 0.2 and nav > 0


def _zg04_amount_share_result(
    report_date: date,
    row: dict[str, Any],
    rule_id: str,
    rule: str,
    form: str,
    amount_label: str,
    share_label: str,
    nav: float,
    *,
    error: str,
) -> ValidationResultRow:
    amount = _legacy_float(_row_value(row, amount_label))
    share = _legacy_float(_row_value(row, share_label))
    diff = amount - nav * share
    ratio = diff / share if share else 0.0
    return make_row(
        report_date=report_date,
        zg_code="ZG04",
        rule_id=rule_id,
        form=form,
        detail=f"产品代码_地区_客户类型_币种_净值跨期差值_净值跨期差值波动幅度_净值型产品期末净值:{_zg04_product_code(row)}_{_zg04_area_code(row)}_{_zg04_client_kind(row)}_{_zg04_currency(row)}_{diff}_{ratio}_{nav}",
        value1=f"{amount_label}:{_legacy_number_text(amount)}",
        value2=f"{share_label}:{_legacy_number_text(share)}",
        rule=rule,
        error=error,
    )


def _zg04_row_result(
    report_date: date,
    row: dict[str, Any],
    rule_id: str,
    rule: str,
    value1_label: str,
    value1: str,
    value2_label: str = "",
    value2: str = "",
    *,
    error: str = "",
) -> ValidationResultRow:
    return make_row(
        report_date=report_date,
        zg_code="ZG04",
        rule_id=rule_id,
        form="资管产品存续期募集信息",
        detail=f"产品代码_地区_客户类型_币种:{_zg04_product_code(row)}_{_zg04_area_code(row)}_{_zg04_client_kind(row)}_{_zg04_currency(row)}",
        value1=f"{value1_label}:{value1}",
        value2=f"{value2_label}:{value2}" if value2_label else "",
        rule=rule,
        error=error,
    )


def _zg04_is_summary_row(row: dict[str, Any]) -> bool:
    return _zg04_area_code(row) == ""


def _zg04_product_code(row: dict[str, Any]) -> str:
    return _row_text(row, "产品代码")


def _zg04_area_code(row: dict[str, Any]) -> str:
    return _row_text(row, "地区", "地区代码")


def _zg04_client_kind(row: dict[str, Any]) -> str:
    return _row_text(row, "客户类型")


def _zg04_currency(row: dict[str, Any]) -> str:
    return _row_text(row, "币种")


def _legacy_has_text(value: Any) -> bool:
    raw = text(value)
    return raw != "" and raw.lower() != "none"


def _currency_total_rules(
    report_date: date,
    zg_code: str,
    rows: list[dict[str, Any]],
    *,
    key_fields: tuple[str, ...],
    exclude_fields: set[str],
    rule_id: str,
    rule: str,
    form: str,
) -> Iterable[ValidationResultRow]:
    by_key: dict[tuple[str, ...], dict[str, dict[str, Any]]] = {}
    for row in rows:
        key = tuple(_row_text(row, field) for field in key_fields)
        by_key.setdefault(key, {})[_row_text(row, "币种")] = row
    fields = _numeric_metric_fields(rows, exclude_fields)

    for key, by_currency in by_key.items():
        cny = by_currency.get("CNY")
        bwb = by_currency.get("BWB")
        if not cny or not bwb:
            continue
        for field in fields:
            diff = _legacy_float(_row_value(cny, field)) - _legacy_float(_row_value(bwb, field))
            if diff == 0:
                continue
            yield make_row(
                report_date=report_date,
                zg_code=zg_code,
                rule_id=rule_id,
                form=form,
                detail=f"{'_'.join(key_fields)}_指标名称:{'_'.join(key)}_{field}",
                value1=f"CNY:{_legacy_df_text(cny.get(field))}",
                value2=f"差值:{diff}",
                rule=rule,
                error="人民币合计与人民币金额应相等",
            )
            break


def _numeric_metric_fields(rows: list[dict[str, Any]], exclude_fields: set[str]) -> list[str]:
    fields: list[str] = []
    for row in rows:
        for field, value in row.items():
            # 只统计中文业务字段；英文物理列与中文镜像同值，避免重复计入。
            if not _is_chinese_business_field(field):
                continue
            if field in exclude_fields or field in fields:
                continue
            if _legacy_has_text(value):
                fields.append(field)
    return fields


def _legacy_zg_metric_specs(zg_code: str, *, skip: set[str] | None = None) -> tuple[tuple[str, str], ...]:
    skipped = skip or set()
    specs: list[tuple[str, str]] = []
    for label in get_indicator_names(zg_code):
        if label in skipped:
            continue
        field = _legacy_indicator_field(label)
        if not field:
            continue
        specs.append((field, label))
    return tuple(specs)


def _legacy_indicator_field(label: str) -> str:
    prefix = str(label or "").split("_", 1)[0].strip()
    if not prefix:
        return ""
    if prefix.upper() == "A0000":
        return "a0001"
    return prefix.lower()


def _zg05_indicator_value(row: dict[str, Any], indicator_code: str) -> Any:
    code = str(indicator_code or "").strip().upper()
    official_name = _ZG05_RULE_INDICATOR_NAMES_BY_CODE.get(code, "")
    # 生产读取时字段目录会先注入正式指标名称；旧指标码仅用于兼容旧数据和历史测试夹具。
    return _row_value(row, official_name, code.lower())


def _zg07_loan_totals(rows: list[dict[str, Any]]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for row in rows:
        projcode = _row_text(row, "产品代码")
        if not projcode:
            continue
        totals[projcode] = totals.get(projcode, 0.0) + _legacy_float(
            _row_value(row, "贷款余额折人民币")
        )
    return totals


def _zg08_spv_totals(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], float]:
    totals: dict[tuple[str, str, str], float] = {}
    for row in rows:
        product_code = _zg08_product_code(row)
        debt_project = _zg08_debt_project(row)
        counterparty_type = _row_text(row, "交易对手产品种类")
        if not product_code or not debt_project or not counterparty_type:
            continue
        amount = _legacy_float(_row_value(row, "期末金额折人民币"))
        key = (product_code, debt_project, counterparty_type)
        totals[key] = totals.get(key, 0.0) + amount
    return totals


def _legacy_float(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    raw = text(value)
    if raw == "" or raw.lower() == "none":
        return 0.0
    try:
        result = float(raw.replace(",", ""))
    except ValueError:
        return 0.0
    if result != result:
        return 0.0
    return result


def _legacy_number_text(value: Any) -> str:
    return str(_legacy_float(value))


def _legacy_key_part(value: str) -> str:
    return value if value else "0"


def _zg06(
    report_date: date,
    rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
    related_rows: dict[str, list[dict[str, Any]]],
) -> Iterable[ValidationResultRow]:
    seen: set[tuple[str, str, str, str]] = set()

    for row in rows:
        issuer_type = _row_text(row, "基础资产出让机构类型")
        issuer_industry = _row_text(row, "基础资产出让机构行业")
        debt_project = _row_text(row, "资产负债项目")
        asset_type = _row_text(row, "基础资产类型")
        issuer_code = _row_text(row, "基础资产出让机构代码")
        issuer_area = _row_text(row, "基础资产出让机构注册地区")
        issuer_scale = _row_text(row, "基础资产出让机构规模")

        if len(debt_project) >= 3 and asset_type and debt_project[2:3] != asset_type:
            result = _zg06_row_result(
                report_date,
                row,
                "Zg06_Rule1",
                "Zg06_Rule1:资产负债项目与基础资产类型不对应，需核实",
                "资产负债项目",
                debt_project,
                "基础资产类型",
                asset_type,
                error="资产负债项目应当与基础资产类型相对应",
            )
            if _unique_result(seen, result):
                yield result

        if issuer_type in {"2", "3"} and issuer_code and not _valid_social_credit_code(issuer_code):
            result = _zg06_row_result(
                report_date,
                row,
                "Zg06_Rule2",
                "Zg06_Rule2:基础资产出让机构代码不符合编码规则，需核实",
                "基础资产出让机构代码",
                issuer_code,
                error="基础资产出让机构代码不符合编码规则，需核实",
            )
            if _unique_result(seen, result):
                yield result

        if issuer_area and area_not_county_level(issuer_area):
            result = _zg06_row_result(
                report_date,
                row,
                "Zg06_Rule4",
                "Zg06_Rule4:基础资产出让机构注册地区未填报到区县一级，需核实",
                "基础资产出让机构注册地区",
                issuer_area,
                error="基础资产出让机构注册地区应填报到区县一级",
            )
            if _unique_result(seen, result):
                yield result

        scale_mismatch = (
            _row_has_any(row, "基础资产出让机构规模")
            and ((issuer_type in {"1", "5", "6"} and issuer_scale != "") or (issuer_type not in {"1", "5", "6"} and issuer_scale == ""))
        )
        if scale_mismatch:
            result = _zg06_row_result(
                report_date,
                row,
                "Zg06_Rule5",
                "Zg06_Rule5:基础资产出让机构类型与规模不对应，需核实",
                "基础资产出让机构类型",
                issuer_type,
                "基础资产出让机构规模",
                issuer_scale,
                error="基础资产出让机构类型应当与规模相对应",
            )
            if _unique_result(seen, result):
                yield result

        if issuer_type == "4" and issuer_code and len(issuer_code) != 14:
            result = _zg06_row_result(
                report_date,
                row,
                "Zg06_Rule7",
                "Zg06_Rule7:金融机构实体基础资产出让机构代码不等于14位，需核实",
                "基础资产出让机构代码",
                issuer_code,
                error="金融机构实体基础资产出让机构代码一般应为14位金融机构编码",
            )
            if _unique_result(seen, result):
                yield result

        industry_mismatch = (
            (issuer_type == "1" and issuer_industry != "1")
            or (issuer_type != "1" and issuer_industry == "1")
            or (issuer_type == "4" and issuer_industry != "J")
            or (issuer_type != "4" and issuer_industry == "J")
            or (issuer_type == "6" and issuer_industry != "2")
            or (issuer_type != "6" and issuer_industry == "2")
            or (issuer_type == "5" and len(issuer_industry) != 0)
            or (issuer_type != "5" and len(issuer_industry) == 0)
        )
        if _row_has_any(row, "基础资产出让机构类型") and _row_has_any(row, "基础资产出让机构行业") and industry_mismatch:
            result = make_row(
                report_date=report_date,
                zg_code="ZG06",
                rule_id="Zg06_Rule3",
                form="资产收益权明细信息",
                detail=_legacy_detail(
                    row,
                    "产品代码_资产收益权内部编码_基础资产出让机构名称",
                    ("产品代码", "资产收益权内部编码", "基础资产出让机构名称"),
                ),
                value1=f"基础资产出让机构类型:{_legacy_df_text(_row_value(row, '基础资产出让机构类型'))}",
                value2=f"基础资产出让机构行业:{_legacy_df_text(_row_value(row, '基础资产出让机构行业'))}",
                rule="Zg06_Rule3:基础资产出让机构类型与行业不对应，需核实",
                error="基础资产出让机构类型应当与行业相对应",
            )
            if _unique_result(seen, result):
                yield result

        five_article_fields = (
            "科技相关产业标识",
            "绿色领域标识",
            "普惠领域标识",
            "养老产业标识",
            "数字经济核心产业标识",
        )
        if issuer_type in {"1", "2", "3", "6"} and any(_row_has_any(row, field) and not _row_text(row, field) for field in five_article_fields):
            result = _zg06_row_result(
                report_date,
                row,
                "Zg06_Rule13",
                "Zg06_Rule13:“五篇大文章”相关字段标识未填报，需核实",
                "基础资产出让机构类型",
                issuer_type,
                error="“五篇大文章”相关字段标识未填报，需核实",
            )
            if _unique_result(seen, result):
                yield result

        if _row_text(row, "出让机构出表标识") == "1":
            result = _zg06_row_result(
                report_date,
                row,
                "Zg06_Rule15",
                "Zg06_Rule15:出让机构出表标识为1-是，需核实",
                "出让机构出表标识",
                "1",
                error="出让机构出表标识为1-是，需核实",
            )
            if _unique_result(seen, result):
                yield result

        if _row_text(row, "出让机构回购标识") == "1":
            result = _zg06_row_result(
                report_date,
                row,
                "Zg06_Rule16",
                "Zg06_Rule16:出让机构回购标识为1-是，需核实",
                "出让机构回购标识",
                "1",
                error="出让机构回购标识为1-是，需核实",
            )
            if _unique_result(seen, result):
                yield result

    for result in _zg06_cross_period_rules(report_date, rows, previous_rows):
        if _unique_result(seen, result):
            yield result

    for result in _zg06_same_issuer_rules(report_date, rows):
        if _unique_result(seen, result):
            yield result

    for row in rows:
        if (_legacy_float(_row_value(row, "利率水平")) >= 10 or _legacy_float(_row_value(row, "利率水平")) <= 1) and _in_report_month(
            _row_text(row, "转让起始日期"), report_date
        ):
            result = make_row(
                report_date=report_date,
                zg_code="ZG06",
                rule_id="Zg06_Rule6",
                form="资产收益权明细信息",
                detail=_legacy_detail(
                    row,
                    "产品代码_资产收益权内部编码_基础资产出让机构名称",
                    ("产品代码", "资产收益权内部编码", "基础资产出让机构名称"),
                ),
                value1=f"利率水平:{_legacy_decimal_text(_row_value(row, '利率水平'), 5)}",
                rule="Zg06_Rule6:利率水平大于等于10或小于等于1，需核实",
                error="利率水平一般应小于10%，大于1",
            )
            if _unique_result(seen, result):
                yield result

    for row in rows:
        if _row_text(row, "转让预计终止日期")[:4] >= "2090" or _row_text(row, "转让展期到期日期")[:4] >= "2090":
            rule = "Zg06_Rule9:转让预计终止日期，转让展期到期日期大于、等于2090，需核实"
            result = make_row(
                report_date=report_date,
                zg_code="ZG06",
                rule_id="Zg06_Rule9",
                form="资产收益权明细信息",
                detail=_legacy_detail(
                    row,
                    "产品代码_资产收益权内部编码_基础资产出让机构名称",
                    ("产品代码", "资产收益权内部编码", "基础资产出让机构名称"),
                ),
                value1=f"转让预计终止日期:{_legacy_df_text(_row_text(row, '转让预计终止日期'))}",
                value2=f"转让展期到期日期:{_legacy_df_text(_row_value(row, '转让展期到期日期'))}",
                rule=rule,
                error=rule,
            )
            if _unique_result(seen, result):
                yield result

    for row in rows:
        if _row_text(row, "基础资产出让机构类型") in {"4", "5"}:
            result = make_row(
                report_date=report_date,
                zg_code="ZG06",
                rule_id="Zg06_Rule14",
                form="资产收益权明细信息",
                detail=_legacy_detail(
                    row,
                    "产品代码_资产收益权内部编码_基础资产出让机构名称_基础资产出让机构类型_科技相关产业标识_绿色领域标识_普惠领域标识",
                    (
                        "产品代码",
                        "资产收益权内部编码",
                        "基础资产出让机构名称",
                        "基础资产出让机构类型",
                        "科技相关产业标识",
                        "绿色领域标识",
                        "普惠领域标识",
                    ),
                ),
                value1=f"养老产业标识:{_legacy_df_text(_row_value(row, '养老产业标识'))}",
                value2=f"数字经济核心产业标识:{_legacy_df_text(_row_value(row, '数字经济核心产业标识'))}",
                rule="Zg06_Rule14:“五篇大文章”相关字段标识不应填报",
                error="金融机构实体与特定目的载体，“五篇大文章”相关字段标识不应填报",
            )
            if _unique_result(seen, result):
                yield result

    for result in _zg06_public_date_rules(report_date, rows, related_rows):
        if _unique_result(seen, result):
            yield result


_ZG06_RULE8_LEGACY_FIELDS: tuple[str, ...] = (
    "资产负债项目",
    "基础资产出让机构名称",
    "基础资产出让机构代码",
    "基础资产出让机构类型",
    "基础资产出让机构行业",
    "基础资产出让机构注册地区",
    "基础资产出让机构经济成分",
    "基础资产出让机构规模",
    "转让起始日期",
    "转让预计终止日期",
    "基础资产类型",
    "基础资产原始协议币种",
    "基础资产原始协议金额",
    "基础资产原始协议金额折人民币",
    "基础资产转让币种",
    "基础资产转让金额",
    "基础资产转让金额折人民币",
    "出让机构出表标识",
    "出让机构回购标识",
    "利率是否固定",
    "利率水平",
    "担保方式",
    "基础资产投向部门",
    "科技相关产业标识",
    "绿色领域标识",
    "普惠领域标识",
    "养老产业标识",
    "数字经济核心产业标识",
    "基础资产投向对象行业",
    "基础资产投向对象规模",
)


def _zg06_cross_period_rules(
    report_date: date,
    rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
) -> Iterable[ValidationResultRow]:
    previous_by_key = {
        (_row_manager_key(row), _row_financial_org_code(row), _row_text(row, "产品代码"), _row_text(row, "资产收益权内部编码")): row
        for row in previous_rows
    }
    for row in rows:
        key = (_row_manager_key(row), _row_financial_org_code(row), _row_text(row, "产品代码"), _row_text(row, "资产收益权内部编码"))
        previous = previous_by_key.get(key)
        if not previous:
            continue
        for label in _ZG06_RULE8_LEGACY_FIELDS:
            current_value = _legacy_compare_text(_row_value(row, label), label)
            previous_value = _legacy_compare_text(_row_value(previous, label), label)
            if current_value == previous_value:
                continue
            yield make_row(
                report_date=report_date,
                zg_code="ZG06",
                rule_id=f"{label}-Zg06_Rule8",
                form="资产收益权明细信息上下期校验",
                detail=_legacy_detail(row, "产品代码_资产收益权内部编码", ("产品代码", "资产收益权内部编码")),
                value1=f"{label}:{current_value}",
                value2=f"{label}上期数:{previous_value}",
                rule="Zg06_Rule8:资产收益权明细数据跨期校验",
                error=f"{label}跨期不一致，需核实",
            )


def _zg06_same_issuer_rules(report_date: date, rows: list[dict[str, Any]]) -> Iterable[ValidationResultRow]:
    fields = (
        "基础资产出让机构名称",
        "基础资产出让机构类型",
        "基础资产出让机构行业",
        "基础资产出让机构注册地区",
        "基础资产出让机构经济成分",
        "基础资产出让机构规模",
    )
    values_by_issuer: dict[str, dict[str, set[str]]] = {}
    sample_by_issuer: dict[str, dict[str, Any]] = {}
    for row in rows:
        issuer_code = _row_text(row, "基础资产出让机构代码")
        if not issuer_code:
            continue
        sample_by_issuer.setdefault(issuer_code, row)
        by_field = values_by_issuer.setdefault(issuer_code, {})
        for label in fields:
            by_field.setdefault(label, set()).add(_row_text(row, label))

    for issuer_code, by_field in values_by_issuer.items():
        row = sample_by_issuer[issuer_code]
        for label, values in by_field.items():
            if len(values) <= 1:
                continue
            yield make_row(
                report_date=report_date,
                zg_code="ZG06",
                rule_id=f"{label}-Zg06_Rule10",
                form="资产收益权明细信息",
                detail=_legacy_detail(row, "产品代码_资产收益权内部编码_基础资产出让机构代码", ("产品代码", "资产收益权内部编码", "基础资产出让机构代码")),
                value1=f"{label}:{'/'.join(sorted(values))}",
                rule="Zg06_Rule10:同一基础资产出让机构相关信息不一致，需核实",
                error=f"同一基础资产出让机构代码，{label}应相同",
            )


def _zg06_row_result(
    report_date: date,
    row: dict[str, Any],
    rule_id: str,
    rule: str,
    value1_label: str,
    value1: str,
    value2_label: str = "",
    value2: str = "",
    *,
    error: str = "",
) -> ValidationResultRow:
    return make_row(
        report_date=report_date,
        zg_code="ZG06",
        rule_id=rule_id,
        form="资产收益权明细信息",
        detail=_legacy_detail(row, "产品代码_资产收益权内部编码_基础资产出让机构名称", ("产品代码", "资产收益权内部编码", "基础资产出让机构名称")),
        value1=f"{value1_label}:{value1}" if value1_label else text(value1),
        value2=f"{value2_label}:{value2}" if value2_label else "",
        rule=rule,
        error=error,
    )


def _zg07(
    report_date: date,
    rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
    related_rows: dict[str, list[dict[str, Any]]],
) -> Iterable[ValidationResultRow]:
    previous_by_key = {
        (_row_text(row, "产品代码"), _row_text(row, "贷款借据编码")): row
        for row in previous_rows
        if _row_text(row, "贷款种类") != "4"
    }
    seen: set[tuple[str, str, str, str]] = set()
    for result in _zg07_field_rules(report_date, rows):
        if _unique_result(seen, result):
            yield result
    for label in _ZG07_CROSS_PERIOD_FIELDS:
        for row in rows:
            if _row_text(row, "贷款种类") == "4":
                continue
            key = (_row_text(row, "产品代码"), _row_text(row, "贷款借据编码"))
            previous = previous_by_key.get(key)
            if not previous:
                continue
            current_value = _legacy_compare_text(_row_value(row, label), label)
            previous_value = _legacy_compare_text(_row_value(previous, label), label)
            if current_value == previous_value:
                continue
            result = make_row(
                report_date=report_date,
                zg_code="ZG07",
                rule_id=f"{label}-Zg07_Rule9",
                form="除回购和拆借外贷款明细信息上下期校验",
                detail=_legacy_detail(row, "产品代码_贷款借据编码", ("产品代码", "贷款借据编码")),
                value1=f"{label}:{current_value}",
                value2=f"{label}_上期:{previous_value}",
                rule="Zg07_Rule9:除回购和拆借外贷款明细信息跨期校验",
                error=f"{label}跨期数据不一致",
            )
            if _unique_result(seen, result):
                yield result
    for result in _zg07_same_borrower_rules(report_date, rows):
        if _unique_result(seen, result):
            yield result
    for result in _zg07_public_end_date_rule(report_date, rows, related_rows):
        if _unique_result(seen, result):
            yield result


def _zg07_field_rules(report_date: date, rows: list[dict[str, Any]]) -> Iterable[ValidationResultRow]:
    for row in rows:
        borrower_type = _row_text(row, "借款人类型")
        borrower_code = _row_text(row, "借款人代码")
        area_code = _row_text(row, "地区代码")
        industry = _row_text(row, "行业信息")
        scale = _row_text(row, "企业规模")
        rate = _legacy_float(_row_value(row, "利率水平"))
        grant_date = _row_text(row, "贷款发放日期")
        loan_state = _first_text(row, "贷款状态")
        extension_date = _row_text(row, "贷款展期到期日期")
        product_type = _row_text(row, "贷款产品类别")
        end_date = _row_text(row, "贷款到期日期")
        loan_type = _row_text(row, "贷款种类")
        transferor_code = _row_text(row, "贷款转让方机构代码")
        original_issuer_code = _row_text(row, "贷款合同原始发放机构代码")

        if _row_has_any(row, "贷款合同原始发放机构所在地代码") and area_not_county_level(_row_text(row, "贷款合同原始发放机构所在地代码")):
            yield _zg07_row_result(
                report_date,
                row,
                "Zg07_Rule1",
                "Zg07_Rule1:贷款合同原始发放机构所在地代码未填报到区县一级，需核实",
                "贷款合同原始发放机构所在地代码",
                _row_text(row, "贷款合同原始发放机构所在地代码"),
                error="贷款合同原始发放机构所在地代码应填报到区县一级",
            )

        if _row_has_any(row, "借款人类型") and _row_has_any(row, "地区代码") and (
            (borrower_type == "1" and area_code != "")
            or (borrower_type != "1" and area_code == "")
            or borrower_type in {"4", "5"}
            or (borrower_type == "6" and not area_code.startswith("000"))
            or (borrower_type != "6" and area_code.startswith("000"))
        ):
            yield _zg07_row_result(
                report_date,
                row,
                "Zg07_Rule2",
                "Zg07_Rule2:借款人类型与地区代码不对应，需核实",
                "借款人类型",
                borrower_type,
                "地区代码",
                area_code,
                error="借款人类型应当与地区代码相对应",
            )

        if _row_has_any(row, "地区代码") and area_not_county_level(area_code):
            yield _zg07_row_result(
                report_date,
                row,
                "Zg07_Rule3",
                "Zg07_Rule3:地区代码未填报到区县一级，需核实",
                "地区代码",
                area_code,
                error="地区代码应填报到区县一级",
            )

        if _row_has_any(row, "借款人类型") and _row_has_any(row, "借款人代码") and _zg12_borrower_type_code_mismatch(borrower_type, borrower_code):
            yield _zg07_row_result(
                report_date,
                row,
                "Zg07_Rule4",
                "Zg07_Rule4:借款人类型与借款人代码不对应，需核实",
                "借款人类型",
                borrower_type,
                "借款人代码",
                borrower_code,
                error="借款人类型应当与借款人代码相对应",
            )

        if _row_has_any(row, "借款人类型") and _row_has_any(row, "借款人代码") and borrower_type in {"2", "3"} and borrower_code and not _valid_social_credit_code(borrower_code):
            yield _zg07_row_result(
                report_date,
                row,
                "Zg07_Rule5",
                "Zg07_Rule5:借款人代码不符合编码规则，需核实",
                "借款人代码",
                borrower_code,
                error="借款人代码不符合编码规则",
            )

        if _row_has_any(row, "借款人类型") and _row_has_any(row, "行业信息") and (
            (borrower_type == "1" and industry != "1")
            or (borrower_type != "1" and industry == "1")
            or (borrower_type == "6" and industry != "2")
            or (borrower_type != "6" and industry == "2")
        ):
            yield _zg07_row_result(
                report_date,
                row,
                "Zg07_Rule6",
                "Zg07_Rule6:借款人类型与行业不对应，需核实",
                "借款人类型",
                borrower_type,
                "行业信息",
                industry,
                error="借款人类型应当与行业相对应",
            )

        if _row_has_any(row, "借款人类型") and _row_has_any(row, "企业规模") and (
            (borrower_type in {"1", "5", "6"} and scale != "")
            or (borrower_type not in {"1", "5", "6"} and scale == "")
        ):
            yield _zg07_row_result(
                report_date,
                row,
                "Zg07_Rule7",
                "Zg07_Rule7:借款人类型与企业规模不对应，需核实",
                "借款人类型",
                borrower_type,
                "企业规模",
                scale,
                error="借款人类型应当与企业规模相对应",
            )

        if _row_has_any(row, "利率水平") and _row_has_any(row, "贷款发放日期") and (rate >= 10 or rate <= 1) and _in_report_month(grant_date, report_date):
            yield _zg07_row_result(
                report_date,
                row,
                "Zg07_Rule8",
                "Zg07_Rule8:利率水平大于等于10或小于等于1，需核实",
                "利率水平",
                _legacy_decimal_text(rate, 5),
                error="利率水平一般应小于10%，大于1%",
            )

        if (
            _row_text(row, "贷款种类") != "4"
            and (_row_has_any(row, "贷款状态") or _row_has_any(row, "贷款展期到期日期"))
            and ((loan_state == "FS02" and not extension_date) or (loan_state != "FS02" and extension_date))
        ):
            yield _zg07_row_result(
                report_date,
                row,
                "Zg07_Rule11",
                "Zg07_Rule11:展期贷款（贷款状态FS03）与贷款展期到期日期不对应，需核实",
                "贷款状态",
                loan_state,
                "贷款展期到期日期",
                extension_date,
                error="贷款状态与贷款展期到期日期需对应",
            )

        if _row_has_any(row, "借款人代码") and borrower_code == "":
            yield _zg07_row_result(
                report_date,
                row,
                "Zg07_Rule14",
                "Zg07_Rule14:借款人代码为空，需核实。",
                "借款人类型",
                borrower_type,
                "借款人代码",
                borrower_code,
                error="借款人代码不应为空",
            )

        loan_product_prefix = product_type[:4]
        if _row_has_any(row, "借款人类型") and _row_has_any(row, "贷款产品类别") and (
            (loan_product_prefix == "F021" and borrower_type != "1")
            or (loan_product_prefix == "F023" and borrower_type != "3")
        ):
            yield _zg07_row_result(
                report_date,
                row,
                "Zg07_Rule15",
                "Zg07_Rule15:借款人类型与贷款产品类别不对应，需核实",
                "借款人类型",
                borrower_type,
                "贷款产品类别",
                product_type,
                error="借款人类型应当与贷款产品类别相对应",
            )

        if _row_has_any(row, "贷款产品类别") and product_type and not product_type.startswith("F02"):
            yield _zg07_row_result(
                report_date,
                row,
                "Zg07_Rule16",
                "Zg07_Rule16:贷款产品类别不为F02，需核实",
                "贷款产品类别",
                product_type,
                error="贷款产品类别一般应为F02",
            )

        if (_row_has_any(row, "贷款到期日期") or _row_has_any(row, "贷款展期到期日期")) and (end_date[:4] >= "2090" or extension_date[:4] >= "2090"):
            yield _zg07_row_result(
                report_date,
                row,
                "Zg07_Rule17",
                "Zg07_Rule17:贷款到期日期或贷款展期到期日期大于、等于2090，需核实",
                "贷款到期日期",
                end_date,
                "贷款展期到期日期",
                extension_date,
                error="贷款到期日期或贷款展期到期日期大于、等于2090，需核实",
            )

        if loan_type == "4" and _row_has_any(row, "贷款转让方机构代码", "贷款合同原始发放机构代码", "贷款合同原始发放机构所在地代码") and (not transferor_code or not original_issuer_code or not _row_text(row, "贷款合同原始发放机构所在地代码")):
            yield _zg07_row_result(
                report_date,
                row,
                "Zg07_Rule18",
                "Zg07_Rule18:转让贷款的贷款转让机构代码、贷款合同原始发放机构代码为空，需核实。",
                "贷款转让机构代码",
                transferor_code,
                "贷款合同原始发放机构代码",
                original_issuer_code,
                error="转让贷款的贷款转让机构代码、贷款合同原始发放机构代码、所在地代码不应为空",
            )


def _zg07_same_borrower_rules(report_date: date, rows: list[dict[str, Any]]) -> Iterable[ValidationResultRow]:
    fields = (
        "借款人类型",
        "地区代码",
        "行业信息",
        "企业出资人经济成分",
        "企业规模",
    )
    values_by_borrower: dict[str, dict[str, set[str]]] = {}
    sample_by_borrower: dict[str, dict[str, Any]] = {}
    for row in rows:
        borrower_code = _row_text(row, "借款人代码")
        if not borrower_code:
            continue
        sample_by_borrower.setdefault(borrower_code, row)
        by_field = values_by_borrower.setdefault(borrower_code, {})
        for label in fields:
            by_field.setdefault(label, set()).add(_row_text(row, label))

    for borrower_code, by_field in values_by_borrower.items():
        row = sample_by_borrower[borrower_code]
        for label, values in by_field.items():
            if len(values) <= 1:
                continue
            yield make_row(
                report_date=report_date,
                zg_code="ZG07",
                rule_id=f"{label}-Zg07_Rule12",
                form="除回购和拆借外贷款明细信息",
                detail=_legacy_detail(row, "产品代码_贷款借据编码", ("产品代码", "贷款借据编码")),
                value1=f"{label}:{'/'.join(sorted(values))}",
                rule="Zg07_Rule12:同一借款人字段信息不一致，需核实",
                error=f"同一借款人代码，{label}应相同",
            )


def _zg07_row_result(
    report_date: date,
    row: dict[str, Any],
    rule_id: str,
    rule: str,
    value1_label: str,
    value1: str,
    value2_label: str = "",
    value2: str = "",
    *,
    error: str = "",
) -> ValidationResultRow:
    return make_row(
        report_date=report_date,
        zg_code="ZG07",
        rule_id=rule_id,
        form="除回购和拆借外贷款明细信息",
        detail=_legacy_detail(row, "产品代码_贷款借据编码", ("产品代码", "贷款借据编码")),
        value1=f"{value1_label}:{value1}",
        value2=f"{value2_label}:{value2}" if value2_label else "",
        rule=rule,
        error=error,
    )


def _zg12(
    report_date: date,
    rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
    related_rows: dict[str, list[dict[str, Any]]],
) -> Iterable[ValidationResultRow]:
    seen: set[tuple[str, str, str, str]] = set()
    for row in rows:
        borrower_type = _row_text(row, "借款人类型")
        area_code = _row_text(row, "地区代码")
        borrower_code = _row_text(row, "借款人代码")
        industry = _row_text(row, "行业信息")
        scale = _row_text(row, "企业规模")
        start_date = _row_text(row, "除资产收益权外其他债权起始日期")
        rate = _legacy_float(_row_value(row, "利率水平"))
        due_date = _row_text(row, "除资产收益权外其他债权预计到期日期")
        debt_type = _row_text(row, "债权类型")
        venue = _row_text(row, "登记交易场所")
        venue_code = _row_text(row, "登记交易场所代码")
        guarantee = _row_text(row, "担保方式")

        if area_not_county_level(area_code):
            result = _zg12_row_result(
                report_date,
                row,
                "Zg12_Rule1",
                "Zg12_Rule1:地区代码未填报到区县一级，需核实",
                "地区代码",
                area_code,
                error="地区代码应填报到区县一级",
            )
            if _unique_result(seen, result):
                yield result

        if (
            (borrower_type == "1" and area_code != "")
            or (borrower_type != "1" and area_code == "")
            or borrower_type in {"4", "5"}
            or (borrower_type == "6" and not area_code.startswith("000"))
            or (borrower_type != "6" and area_code.startswith("000"))
        ):
            result = _zg12_row_result(
                report_date,
                row,
                "Zg12_Rule2",
                "Zg12_Rule2:借款人类型与地区代码不对应，需核实",
                "借款人类型",
                borrower_type,
                "地区代码",
                area_code,
                error="借款人类型应当与地区代码相对应；一般不能为金融机构和特定目的载体",
            )
            if _unique_result(seen, result):
                yield result

        if borrower_code == "":
            result = _zg12_row_result(
                report_date,
                row,
                "Zg12_Rule3",
                "Zg12_Rule3:借款人代码为空，需核实。",
                "借款人类型",
                borrower_type,
                "借款人代码",
                borrower_code,
                error="借款人代码不应为空",
            )
            if _unique_result(seen, result):
                yield result

        if _zg12_borrower_type_code_mismatch(borrower_type, borrower_code):
            result = _zg12_row_result(
                report_date,
                row,
                "Zg12_Rule4",
                "Zg12_Rule4:借款人类型与借款人代码不对应，需核实",
                "借款人类型",
                borrower_type,
                "借款人代码",
                borrower_code,
                error="个人证件代码应按规则脱敏；单位社会信用代码一般应为18位",
            )
            if _unique_result(seen, result):
                yield result

        if borrower_type in {"2", "3"} and not _valid_social_credit_code(borrower_code):
            result = _zg12_row_result(
                report_date,
                row,
                "Zg12_Rule5",
                "Zg12_Rule5:借款人代码不符合编码规则，需核实",
                "借款人类型",
                borrower_type,
                "借款人代码",
                borrower_code,
                error="借款人代码不符合编码规则，需核实",
            )
            if _unique_result(seen, result):
                yield result

        if (
            (borrower_type == "1" and industry != "1")
            or (borrower_type != "1" and industry == "1")
            or (borrower_type == "6" and industry != "2")
            or (borrower_type != "6" and industry == "2")
        ):
            result = _zg12_row_result(
                report_date,
                row,
                "Zg12_Rule6",
                "Zg12_Rule6:借款人类型与行业不对应，需核实",
                "借款人类型",
                borrower_type,
                "行业信息",
                industry,
                error="借款人类型应当与行业相对应",
            )
            if _unique_result(seen, result):
                yield result

        if (
            (borrower_type in {"1", "5", "6"} and scale != "")
            or (borrower_type not in {"1", "5", "6"} and scale == "")
        ):
            result = _zg12_row_result(
                report_date,
                row,
                "Zg12_Rule7",
                "Zg12_Rule7:借款人类型与企业规模不对应，需核实",
                "借款人类型",
                borrower_type,
                "企业规模",
                scale,
                error="借款人类型应当与企业规模相对应",
            )
            if _unique_result(seen, result):
                yield result

        if (rate >= 10 or rate <= 1) and _in_report_month(start_date, report_date):
            result = _zg12_row_result(
                report_date,
                row,
                "Zg12_Rule8",
                "Zg12_Rule8:利率水平大于等于10或小于等于1，需核实",
                "利率水平",
                _legacy_decimal_text(rate, 5),
                "行业信息",
                industry,
                include_start_date=True,
                error="利率水平一般应小于10%，大于1%",
            )
            if _unique_result(seen, result):
                yield result

        if due_date[:4] >= "2090":
            result = _zg12_row_result(
                report_date,
                row,
                "Zg12_Rule11",
                "Zg12_Rule11:除资产收益权外其他债权预计到期日期大于、等于2090，需核实",
                "除资产收益权外其他债权预计到期日期",
                due_date,
                error="除资产收益权外其他债权预计到期日期大于、等于2090，需核实",
            )
            if _unique_result(seen, result):
                yield result

        if (debt_type != "2" and venue == "2") or (debt_type == "2" and venue != "2"):
            result = _zg12_row_result(
                report_date,
                row,
                "Zg12_Rule14",
                "Zg12_Rule14:债权类型与登记交易场所不对应，需核实",
                "债权类型",
                debt_type,
                "登记交易场所",
                venue,
                error="债权类型应当与登记交易场所相对应",
            )
            if _unique_result(seen, result):
                yield result

        if (venue == "4" and venue_code != "000000000000000000") or (
            venue != "4" and venue_code == "000000000000000000"
        ):
            result = _zg12_row_result(
                report_date,
                row,
                "Zg12_Rule17",
                "Zg12_Rule17:登记交易场所为其他，代码未填报18个0；或者填18个0，类型未填其他，需核实",
                "登记交易场所",
                venue,
                "登记交易场所代码",
                venue_code,
                error="登记交易场所为其他时，代码应填报18个0；填18个0时，类型应填其他",
            )
            if _unique_result(seen, result):
                yield result

        if guarantee == "Z":
            result = _zg12_row_result(
                report_date,
                row,
                "Zg12_Rule18",
                "Zg12_Rule18:担保方式为其他，需核实",
                "担保方式",
                guarantee,
                error="担保方式一般不应填报Z-其他",
            )
            if _unique_result(seen, result):
                yield result

    for result in _zg12_cross_period_rules(report_date, rows, previous_rows):
        if _unique_result(seen, result):
            yield result
    for result in _zg12_same_borrower_rules(report_date, rows):
        if _unique_result(seen, result):
            yield result
    for result in _zg12_balance_rule(report_date, rows, related_rows.get("ZG05", [])):
        if _unique_result(seen, result):
            yield result
    for result in _zg12_public_end_date_rule(report_date, rows, related_rows):
        if _unique_result(seen, result):
            yield result
    for row in rows:
        venue_code = _row_text(row, "登记交易场所代码")
        if venue_code and not (_valid_social_credit_code(venue_code) or venue_code == "000000000000000000"):
            result = _zg12_row_result(
                report_date,
                row,
                "Zg12_Rule10",
                "Zg12_Rule10:登记交易场所代码不符合编码规则，需核实",
                "登记交易场所代码",
                venue_code,
                error="登记交易场所代码不符合编码规则，需核实",
            )
            if _unique_result(seen, result):
                yield result


def _zg12_public_end_date_rule(
    report_date: date,
    rows: list[dict[str, Any]],
    related_rows: dict[str, list[dict[str, Any]]],
) -> Iterable[ValidationResultRow]:
    product_dates = _public_product_dates(related_rows)

    for row in rows:
        product_code = _zg12_product_code(row)
        product_end = product_dates.get(product_code, {}).get("end", "")
        if not product_end:
            continue
        due_date = _row_text(row, "除资产收益权外其他债权预计到期日期")
        if not due_date:
            continue
        if not _after_product_end(due_date, product_end):
            continue
        yield make_row(
            report_date=report_date,
            zg_code="ZG12",
            rule_id="Zg12_Rule13",
            form="除资产收益权外其他债权明细信息",
            detail=f"{_zg12_detail(row)}_债权类型:{_row_text(row, '债权类型')}",
            value1=f"除资产收益权外其他债权预计到期日期:{due_date[:10]}",
            value2=f"产品预计终止日期:{product_end[:10]}",
            rule="Zg12_Rule13:公开信息交叉校验-除资产收益权外其他债权预计到期日期大于产品预计终止日期，需核实",
            error="除资产收益权外其他债权预计到期日期应小于等于产品预计终止日期",
        )


def _zg06_public_date_rules(
    report_date: date,
    rows: list[dict[str, Any]],
    related_rows: dict[str, list[dict[str, Any]]],
) -> Iterable[ValidationResultRow]:
    product_dates = _public_product_dates(related_rows)
    for row in rows:
        product_code = _row_text(row, "产品代码")
        product_date = product_dates.get(product_code, {})
        transfer_start = _row_text(row, "转让起始日期")
        product_start = product_date.get("start", "")
        if transfer_start and product_start:
            parsed_transfer_start = _parse_date(transfer_start)
            parsed_product_start = _parse_date(product_start)
            if parsed_transfer_start is not None and parsed_product_start is not None and parsed_transfer_start < parsed_product_start:
                yield make_row(
                    report_date=report_date,
                    zg_code="ZG06",
                    rule_id="Zg06_Rule11",
                    form="资产收益权明细信息",
                    detail=_legacy_detail(
                        row,
                        "产品代码_资产收益权内部编码_基础资产出让机构名称",
                        ("产品代码", "资产收益权内部编码", "基础资产出让机构名称"),
                    ),
                    value1=f"转让起始日期:{transfer_start[:10]}",
                    value2=f"产品起始日期:{product_start[:10]}",
                    rule="Zg06_Rule11:公开信息交叉校验-资产转让起始日期早于产品起始日期，需核实",
                    error="资产转让起始日期一般应晚于等于产品起始日期",
                )

        transfer_end = _row_text(row, "转让预计终止日期")
        product_end = product_date.get("end", "")
        if transfer_end and product_end and _after_product_end(transfer_end, product_end):
            yield make_row(
                report_date=report_date,
                zg_code="ZG06",
                rule_id="Zg06_Rule12",
                form="资产收益权明细信息",
                detail=_legacy_detail(
                    row,
                    "产品代码_资产收益权内部编码_基础资产出让机构名称",
                    ("产品代码", "资产收益权内部编码", "基础资产出让机构名称"),
                ),
                value1=f"转让预计终止日期:{transfer_end[:10]}",
                value2=f"产品预计终止日期:{product_end[:10]}",
                rule="Zg06_Rule12:公开信息交叉校验-转让预计终止日期晚于产品预计终止日期，需核实",
                error="转让预计终止日期一般应早于等于产品预计终止日期",
            )


def _zg07_public_end_date_rule(
    report_date: date,
    rows: list[dict[str, Any]],
    related_rows: dict[str, list[dict[str, Any]]],
) -> Iterable[ValidationResultRow]:
    product_dates = _public_product_dates(related_rows)
    for row in rows:
        product_code = _row_text(row, "产品代码")
        product_end = product_dates.get(product_code, {}).get("end", "")
        if not product_end:
            continue
        end_date = _row_text(row, "贷款到期日期")
        extension_date = _row_text(row, "贷款展期到期日期")
        if not (_after_product_end(end_date, product_end) or _after_product_end(extension_date, product_end)):
            continue
        yield make_row(
            report_date=report_date,
            zg_code="ZG07",
            rule_id="Zg07_Rule13",
            form="除回购和拆借外贷款明细信息",
            detail=(
                "产品代码_借款人代码_贷款借据编码_贷款种类_贷款展期到期日期:"
                f"{_legacy_df_text(_row_value(row, '产品代码'))}_"
                f"{_legacy_df_text(_row_value(row, '借款人代码'))}_"
                f"{_legacy_df_text(_row_value(row, '贷款借据编码'))}_"
                f"{_legacy_df_text(_row_value(row, '贷款种类'))}_"
                f"{_legacy_nat_text(_row_value(row, '贷款展期到期日期'))}"
            ),
            value1=f"贷款到期日期:{end_date[:10]}",
            value2=f"产品预计终止日期:{product_end[:10]}",
            rule="Zg07_Rule13:公开信息交叉校验-贷款到期日期或展期到期日期大于产品预计终止日期，需核实",
            error="贷款到期日期或展期到期日期应小于等于产品预计终止日期",
        )


def _zg13_public_end_date_rule(
    report_date: date,
    rows: list[dict[str, Any]],
    related_rows: dict[str, list[dict[str, Any]]],
) -> Iterable[ValidationResultRow]:
    product_dates = _legacy_public_product_dates(related_rows)
    for row in rows:
        if _legacy_float(_row_value(row, "持股比例")) <= 0:
            continue
        product_code = _first_text(row, "产品代码")
        product_end = product_dates.get(product_code, {}).get("end", "")
        contract_end = _row_text(row, "合同预计终止日期")
        if not product_end or not contract_end or not _after_product_end(contract_end, product_end):
            continue
        yield make_row(
            report_date=report_date,
            zg_code="ZG13",
            rule_id="Zg13_Rule9",
            form="其他股权投资明细信息",
            detail=_legacy_zg13_detail(row),
            value1=f"合同预计终止日期:{contract_end[:10]}",
            value2=f"产品预计终止日期:{product_end[:10]}",
            rule="Zg13_Rule9:公开信息交叉校验-合同预计终止日期大于产品预计终止日期，需核实",
            error="合同预计终止日期应小于等于产品预计终止日期",
        )


def _public_product_dates(related_rows: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, str]]:
    product_rows = _public_info_rows(related_rows)
    product_dates: dict[str, dict[str, str]] = {}
    for row in product_rows:
        product_code = _row_text(row, "产品代码")
        if not product_code:
            continue
        dates = product_dates.setdefault(product_code, {})
        start_date = _row_text(row, "产品起始日期", "产品起始日")
        end_date = _row_text(row, "产品预计终止日期")
        if start_date:
            dates["start"] = start_date
        if end_date:
            dates["end"] = end_date
    return product_dates


def _legacy_public_product_dates(related_rows: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, str]]:
    org_codes = get_org_codes()
    changed_rows: list[dict[str, Any]] = []
    new_rows: list[dict[str, Any]] = []
    for row in _public_info_rows(related_rows):
        issuer_code = _row_text(row, "发行机构代码")
        if issuer_code and issuer_code not in org_codes:
            continue
        info_type = _row_text(row, "信息类型名称")
        if info_type == "变更资管产品基本信息":
            changed_rows.append(row)
        elif info_type == "新增资管产品基本信息":
            new_rows.append(row)

    changed_codes = {_row_text(row, "产品代码") for row in changed_rows}
    rows = changed_rows + [row for row in new_rows if _row_text(row, "产品代码") not in changed_codes]
    product_dates: dict[str, dict[str, str]] = {}
    for row in rows:
        product_code = _row_text(row, "产品代码")
        end_date = _row_text(row, "产品预计终止日期")
        if product_code and end_date:
            product_dates.setdefault(product_code, {})["end"] = end_date
    return product_dates


def _public_info_rows(related_rows: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return related_rows.get("PUBLIC_INFO", []) + related_rows.get("公开信息", [])


def _after_product_end(value: Any, product_end: Any) -> bool:
    raw = text(value)
    if not raw:
        return False
    if raw[:4] == "9999":
        return True
    parsed_value = _parse_date(raw)
    product_end_text = text(product_end)
    parsed_product_end = _parse_date("2049-12-31" if product_end_text[:4] == "9999" else product_end_text)
    return parsed_value is not None and parsed_product_end is not None and parsed_value > parsed_product_end


_ZG12_CROSS_PERIOD_FIELDS: tuple[str, ...] = (
    "借款人类型",
    "地区代码",
    "借款人代码",
    "行业信息",
    "企业出资人经济成分",
    "企业规模",
    "除资产收益权外其他债权实际投向",
    "除资产收益权外其他债权起始日期",
    "除资产收益权外其他债权预计到期日期",
    "利率水平",
    "担保方式",
    "原始合同币种",
    "原始合同金额",
    "原始合同金额折人民币",
    "除资产收益权外其他债权余额币种",
    "科技相关产业标识",
    "绿色领域标识",
    "普惠领域标识",
    "养老产业标识",
    "数字经济核心产业标识",
)


def _zg12_cross_period_rules(
    report_date: date,
    rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
) -> Iterable[ValidationResultRow]:
    previous_by_key = {(_zg12_product_code(row), _zg12_inner_code(row)): row for row in previous_rows}
    for label in _ZG12_CROSS_PERIOD_FIELDS:
        for row in rows:
            previous = previous_by_key.get((_zg12_product_code(row), _zg12_inner_code(row)))
            if not previous:
                continue
            current_value = _zg12_compare_text(_row_value(row, label), label)
            previous_value = _zg12_compare_text(_row_value(previous, label), label)
            if current_value == previous_value:
                continue
            yield make_row(
                report_date=report_date,
                zg_code="ZG12",
                rule_id=f"{label}-Zg12_Rule9",
                form="除资产收益权外其他债权明细信息上下期校验",
                detail=_zg12_detail(row),
                value1=f"{label}:{current_value}",
                value2=f"{label}_上期:{previous_value}",
                rule="Zg12_Rule9:除资产收益权外其他债权明细信息跨期校验",
                error=f"{label}跨期数据不一致",
            )


def _zg12_same_borrower_rules(report_date: date, rows: list[dict[str, Any]]) -> Iterable[ValidationResultRow]:
    fields = (
        "借款人类型",
        "地区代码",
        "行业信息",
        "企业出资人经济成分",
        "企业规模",
    )
    values_by_borrower: dict[str, dict[str, set[str]]] = {}
    sample_by_borrower: dict[str, dict[str, Any]] = {}
    for row in rows:
        borrower_code = _zg12_borrower_code(row)
        if not borrower_code:
            continue
        sample_by_borrower.setdefault(borrower_code, row)
        by_field = values_by_borrower.setdefault(borrower_code, {})
        for label in fields:
            by_field.setdefault(label, set()).add(_row_text(row, label))

    for borrower_code, by_field in values_by_borrower.items():
        row = sample_by_borrower[borrower_code]
        for label, values in by_field.items():
            if len(values) <= 1:
                continue
            yield make_row(
                report_date=report_date,
                zg_code="ZG12",
                rule_id=f"{label}-Zg12_Rule12",
                form="除资产收益权外其他债权明细信息",
                detail=_zg12_detail(row),
                value1=f"{label}:{'/'.join(sorted(values))}",
                rule="Zg12_Rule12:同一借款人字段信息不一致，需核实",
                error=f"同一借款人代码，{label}应该相同",
            )


def _zg12_balance_rule(
    report_date: date,
    rows: list[dict[str, Any]],
    zg05_rows: list[dict[str, Any]],
) -> Iterable[ValidationResultRow]:
    zg05_by_product: dict[str, float] = {}
    for row in zg05_rows:
        if _row_text(row, "币种") != "BWB":
            continue
        product_code = _row_text(row, "产品代码")
        zg05_by_product[product_code] = zg05_by_product.get(product_code, 0.0) + _legacy_float(
            _zg05_indicator_value(row, "AD200")
        )

    zg12_by_product: dict[str, float] = {}
    for row in rows:
        product_code = _zg12_product_code(row)
        zg12_by_product[product_code] = zg12_by_product.get(product_code, 0.0) + _legacy_float(
            _row_value(row, "除资产收益权外其他债权余额折人民币")
        )

    for product_code in sorted(set(zg05_by_product) | set(zg12_by_product)):
        diff = zg05_by_product.get(product_code, 0.0) - zg12_by_product.get(product_code, 0.0)
        if abs(diff) <= 0.1:
            continue
        yield make_row(
            report_date=report_date,
            zg_code="ZG05-ZG12",
            rule_id="Zg12_Rule16",
            form="资产负债明细信息VS除资产收益权外其他债权",
            detail=f"产品代码_AD200_除资产收益权外其他债权:{product_code}_{zg05_by_product.get(product_code, 0.0)}",
            value1=f"zg12_除资产收益权外其他债权余额折人民币:{zg12_by_product.get(product_code, 0.0)}",
            value2=f"差值（G05减G12）:{diff}",
            rule="Zg12_Rule16:ZG05除资产收益权外其他债权与ZG12明细数据汇总金额不相等，需核实",
            error="ZG05除资产收益权外其他债权与ZG12明细数据汇总金额应相等",
        )


def _zg12_row_result(
    report_date: date,
    row: dict[str, Any],
    rule_id: str,
    rule: str,
    value1_label: str,
    value1: str,
    value2_label: str = "",
    value2: str = "",
    *,
    error: str = "",
    include_start_date: bool = False,
) -> ValidationResultRow:
    detail = _zg12_detail(row)
    if include_start_date:
        detail = f"{detail}_{_row_text(row, '除资产收益权外其他债权起始日期')}"
    return make_row(
        report_date=report_date,
        zg_code="ZG12",
        rule_id=rule_id,
        form="除资产收益权外其他债权明细信息",
        detail=detail,
        value1=f"{value1_label}:{value1}",
        value2=f"{value2_label}:{value2}" if value2_label else "",
        rule=rule,
        error=error,
    )


def _zg12_borrower_type_code_mismatch(borrower_type: str, borrower_code: str) -> bool:
    if borrower_code == "":
        return False
    if borrower_type == "1":
        return len(borrower_code) != 46 or borrower_code.upper() == borrower_code
    if borrower_type in {"2", "3"}:
        return len(borrower_code) != 18
    return False


def _valid_social_credit_code(value: str) -> bool:
    if len(value) != 18:
        return False
    return value.isalnum()


def _legacy_social_credit_code_invalid(value: str) -> bool:
    code = text(value).upper()
    if len(code) > 18:
        return True
    if len(code) != 18:
        return False
    alphabet = "0123456789ABCDEFGHJKLMNPQRTUWXY"
    weights = (1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28)
    values = {char: index for index, char in enumerate(alphabet)}
    try:
        total = sum(values[char] * weight for char, weight in zip(code[:17], weights))
    except KeyError:
        return True
    check_value = 31 - total % 31
    expected = "0" if check_value == 31 else alphabet[check_value]
    return code[17] != expected


def _zg12_compare_text(value: Any, field: str) -> str:
    if field == "利率水平":
        return _legacy_decimal_text(value, 5)
    if field in {"原始合同金额", "原始合同金额折人民币"}:
        return _legacy_decimal_text(value, 2)
    return _legacy_df_text(value)


def _zg12_detail(row: dict[str, Any]) -> str:
    return (
        "产品代码_借款人代码_除资产收益权外其他债权内部编码:"
        f"{_legacy_df_text(_zg12_product_code(row))}_{_legacy_df_text(_zg12_borrower_code(row))}_{_legacy_df_text(_zg12_inner_code(row))}"
    )


def _zg12_product_code(row: dict[str, Any]) -> str:
    return _row_text(row, "产品代码")


def _zg12_borrower_code(row: dict[str, Any]) -> str:
    return _row_text(row, "借款人代码")


def _zg12_inner_code(row: dict[str, Any]) -> str:
    return _row_text(row, "除资产收益权外其他债权内部编码")


def _row_text(row: dict[str, Any], *fields: str) -> str:
    return text(_row_value(row, *fields))


def _row_financial_org_code(row: dict[str, Any]) -> str:
    return _first_text(row, "金融机构编码", "金融机构代码", "机构编码", "机构代码") or DEFAULT_ORG_CODE


def _row_manager_key(row: dict[str, Any]) -> str:
    return _first_text(row, "数据管理机构")


def _is_metric_code(name: str) -> bool:
    """ZG05/ZG09/ZG10 等指标编码（含数字），不是业务英文字段名。"""
    value = str(name or "")
    if not value or _is_chinese_business_field(value):
        return False
    return any(ch.isdigit() for ch in value)


def _row_value(row: dict[str, Any], *fields: str) -> Any:
    chinese_fields = _chinese_fields_only(*fields)
    if chinese_fields:
        # 有中文业务字段时只走映射；无映射/缺字段返回空，由启动预检拦截
        for field in chinese_fields:
            if field in row:
                return row.get(field)
        for field in chinese_fields:
            english = _resolve(field)
            if english and english in row:
                return row.get(english)
        return None
    # 仅允许指标编码直接取值；禁止业务英文字段名兜底
    for field in fields:
        if field and _is_metric_code(field) and field in row:
            return row.get(field)
    return None


def _row_has_any(row: dict[str, Any], *fields: str) -> bool:
    chinese_fields = _chinese_fields_only(*fields)
    if chinese_fields:
        for field in chinese_fields:
            if field in row:
                return True
            english = _resolve(field)
            if english and english in row:
                return True
        return False
    return any(bool(field) and _is_metric_code(field) and field in row for field in fields)


def _zg13_field_rules(report_date: date, rows: list[dict[str, Any]]) -> Iterable[ValidationResultRow]:
    for row in rows:
        area_code = _row_text(row, "地区代码")
        target_code = _row_text(row, "标的企业代码")
        transferor_code = _row_text(row, "股权出让方代码")
        debt_project = _row_text(row, "资产负债项目")
        industry = _row_text(row, "行业信息")
        contract_end = _row_text(row, "合同预计终止日期")
        hold_rate = _row_text(row, "持股比例")

        if area_not_county_level(area_code):
            yield _zg13_row_result(
                report_date,
                row,
                "Zg13_Rule1",
                "Zg13_Rule1:地区代码未填报到区县一级，需核实",
                "地区代码",
                area_code,
                error="地区代码应填报到区县一级",
            )

        if target_code == "":
            yield _zg13_row_result(
                report_date,
                row,
                "Zg13_Rule3",
                "Zg13_Rule3:标的企业代码为空，需核实。",
                "标的企业代码",
                target_code,
                error="标的企业代码不应为空",
            )
        elif _legacy_social_credit_code_invalid(target_code):
            yield _zg13_row_result(
                report_date,
                row,
                "Zg13_Rule2",
                "Zg13_Rule2:标的企业代码不符合编码规则，需核实",
                "标的企业代码",
                target_code,
                error="标的企业代码不符合编码规则",
            )

        if transferor_code == "":
            yield _zg13_row_result(
                report_date,
                row,
                "Zg13_Rule6",
                "Zg13_Rule6:股权出让方代码为空，需核实。",
                "股权出让方代码",
                transferor_code,
                error="股权出让方代码不应为空",
            )
        elif _legacy_social_credit_code_invalid(transferor_code):
            yield _zg13_row_result(
                report_date,
                row,
                "Zg13_Rule5",
                "Zg13_Rule5:股权出让方代码不符合编码规则，需核实",
                "股权出让方代码",
                transferor_code,
                error="股权出让方代码不符合编码规则",
            )

        debt_project = _zg13_debt_project(row)
        if debt_project == "A7320" and (contract_end[:4] != "9999" or _legacy_float(hold_rate) != 0.0):
            yield _zg13_row_result(
                report_date,
                row,
                "Zg13_Rule12",
                "Zg13_Rule12:股性永续债合同预计终止日期与持股比例填报不符合要求，需核实",
                "合同预计终止日期",
                contract_end,
                "持股比例",
                hold_rate,
                error="合同预计终止日期应填报9999-12-31、持股比例填报0，需核实",
            )

        if debt_project == "A7320" and industry != "J":
            yield _zg13_row_result(
                report_date,
                row,
                "Zg13_Rule13",
                "Zg13_Rule13:资产负债项目与行业信息不对应，需核实",
                "资产负债项目",
                debt_project,
                "行业信息",
                industry,
                error="资产负债项目应与行业信息相对应",
            )


_ZG13_CROSS_PERIOD_FIELDS: tuple[str, ...] = (
    "标的企业名称",
    "地区代码",
    "标的企业代码",
    "行业信息",
    "企业出资人经济成分",
    "企业规模",
    "股权投资方式",
    "股权出让方代码",
    "股权出让方名称",
    "合同币种",
    "其他股权余额币种",
    "持股比例",
    "投资退出方式",
    "合同起始日期",
    "合同预计终止日期",
    "合同展期到期日期",
)


def _zg13_cross_period_rules(
    report_date: date,
    rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
) -> Iterable[ValidationResultRow]:
    previous_by_key = {(_zg13_product_code(row), _zg13_inner_code(row)): row for row in previous_rows}
    for label in _ZG13_CROSS_PERIOD_FIELDS:
        for row in rows:
            previous = previous_by_key.get((_zg13_product_code(row), _zg13_inner_code(row)))
            if not previous:
                continue
            current_value = _legacy_compare_text(_row_value(row, label), label)
            previous_value = _legacy_compare_text(_row_value(previous, label), label)
            if current_value == previous_value:
                continue
            yield make_row(
                report_date=report_date,
                zg_code="ZG13",
                rule_id=f"{label}-Zg13_Rule4",
                form="其他股权投资明细信息上下期校验",
                detail=_legacy_zg13_detail(row),
                value1=f"{label}:{current_value}",
                value2=f"{label}_上期:{previous_value}",
                rule="Zg13_Rule4:其他股权投资明细信息跨期校验",
                error=f"{label}跨期数据不一致",
            )


def _zg13_same_target_rules(report_date: date, rows: list[dict[str, Any]]) -> Iterable[ValidationResultRow]:
    legacy_fields = (
        "地区代码",
        "行业信息",
        "企业出资人经济成分",
        "企业规模",
    )
    values_by_target: dict[tuple[str, str, str], dict[str, set[str]]] = {}
    sample_by_target: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        target_code = _row_text(row, "标的企业代码")
        if not target_code:
            continue
        target_key = (_row_manager_key(row), _row_financial_org_code(row), target_code)
        sample_by_target.setdefault(target_key, row)
        by_field = values_by_target.setdefault(target_key, {})
        for label in legacy_fields:
            by_field.setdefault(label, set()).add(_row_text(row, label))

    for target_key, by_field in values_by_target.items():
        row = sample_by_target[target_key]
        for label, values in by_field.items():
            if len(values) <= 1:
                continue
            yield make_row(
                report_date=report_date,
                zg_code="ZG13",
                rule_id=f"{label}-Zg13_Rule8",
                form="其他股权投资明细信息",
                detail=_legacy_zg13_detail(row),
                value1=f"{label}:{'/'.join(sorted(values))}",
                rule="Zg13_Rule8:同一标的企业字段信息不一致，需核实",
                error=f"同一标的企业代码，{label}应相同",
            )


def _zg13_balance_rules(
    report_date: date,
    rows: list[dict[str, Any]],
    zg05_rows: list[dict[str, Any]],
) -> Iterable[ValidationResultRow]:
    for debt_project, zg05_field, rule_id in (("A7310", "A7310", "Zg13_Rule10"), ("A7320", "A7320", "Zg13_Rule11")):
        zg05_by_key: dict[tuple[str, str, str], float] = {}
        for row in zg05_rows:
            if _row_text(row, "币种") != "BWB":
                continue
            key = (_row_manager_key(row), _row_financial_org_code(row), _row_text(row, "产品代码"))
            zg05_by_key[key] = zg05_by_key.get(key, 0.0) + _legacy_float(
                _zg05_indicator_value(row, zg05_field)
            )

        zg13_by_key: dict[tuple[str, str, str], float] = {}
        for row in rows:
            if _zg13_debt_project(row) != debt_project:
                continue
            key = (_row_manager_key(row), _row_financial_org_code(row), _zg13_product_code(row))
            zg13_by_key[key] = zg13_by_key.get(key, 0.0) + _legacy_float(_zg13_amount_cny(row))

        for key in sorted(set(zg05_by_key) | set(zg13_by_key)):
            product_code = key[2]
            diff = zg05_by_key.get(key, 0.0) - zg13_by_key.get(key, 0.0)
            if abs(diff) <= 0.1:
                continue
            yield make_row(
                report_date=report_date,
                zg_code="ZG05-ZG13",
                rule_id=rule_id,
                form=f"资产负债明细信息VS{debt_project}其他股权投资明细信息",
                detail=f"产品代码_{zg05_field.upper()}:{product_code}_{zg05_by_key.get(key, 0.0)}",
                value1=f"zg13_其他股权余额折人民币:{zg13_by_key.get(key, 0.0)}",
                value2=f"差值（G05减G13）:{diff}",
                rule=f"{rule_id}:ZG05-{zg05_field.upper()}与ZG13-{debt_project}明细数据汇总金额不相等，需核实",
                error=f"ZG05-{zg05_field.upper()}与ZG13-{debt_project}明细数据汇总金额应相等",
            )


def _zg13_row_result(
    report_date: date,
    row: dict[str, Any],
    rule_id: str,
    rule: str,
    value1_label: str,
    value1: str,
    value2_label: str = "",
    value2: str = "",
    *,
    error: str = "",
) -> ValidationResultRow:
    return make_row(
        report_date=report_date,
        zg_code="ZG13",
        rule_id=rule_id,
        form="其他股权投资明细信息",
        detail=_legacy_zg13_detail(row),
        value1=f"{value1_label}:{value1}",
        value2=f"{value2_label}:{value2}" if value2_label else "",
        rule=rule,
        error=error,
    )


def _zg13_product_code(row: dict[str, Any]) -> str:
    return _first_text(row, "产品代码")


def _zg13_debt_project(row: dict[str, Any]) -> str:
    return _first_text(row, "资产负债项目")


def _zg13_amount_cny(row: dict[str, Any]) -> Any:
    return _row_value(row, "其他股权余额折人民币")


def _zg13_inner_code(row: dict[str, Any]) -> str:
    return _first_text(row, "其他股权投资内部编码")


def _zg13(
    report_date: date,
    rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
    related_rows: dict[str, list[dict[str, Any]]],
) -> Iterable[ValidationResultRow]:
    seen: set[tuple[str, str, str, str]] = set()
    for result in _zg13_field_rules(report_date, rows):
        if _unique_result(seen, result):
            yield result
    for result in _zg13_cross_period_rules(report_date, rows, previous_rows):
        if _unique_result(seen, result):
            yield result
    for result in _zg13_same_target_rules(report_date, rows):
        if _unique_result(seen, result):
            yield result
    for result in _zg13_public_end_date_rule(report_date, rows, related_rows):
        if _unique_result(seen, result):
            yield result
    for result in _zg13_balance_rules(report_date, rows, related_rows.get("ZG05", [])):
        if _unique_result(seen, result):
            yield result

    for row in rows:
        if _zg13_financial_code_mismatch(row, "标的企业代码", "标的企业名称"):
            result = make_row(
                report_date=report_date,
                zg_code="ZG13",
                rule_id="Zg13_Rule15",
                form="其他股权投资明细信息",
                detail=_legacy_zg13_detail(row),
                value1=f"标的企业代码:{_legacy_df_text(_row_value(row, '标的企业代码'))}",
                value2=f"标的企业名称:{_legacy_df_text(_row_value(row, '标的企业名称'))}",
                rule="Zg13_Rule15:境内金融机构标的企业代码未填报金融机构编码，需核实。",
                error="境内金融机构标的企业代码应填报金融机构编码",
            )
            if _unique_result(seen, result):
                yield result

    for row in rows:
        if _zg13_financial_code_mismatch(row, "股权出让方代码", "股权出让方名称"):
            result = make_row(
                report_date=report_date,
                zg_code="ZG13",
                rule_id="Zg13_Rule16",
                form="其他股权投资明细信息",
                detail=_legacy_zg13_detail(row),
                value1=f"股权出让方代码:{_legacy_df_text(_row_value(row, '股权出让方代码'))}",
                value2=f"股权出让方名称:{_legacy_df_text(_row_value(row, '股权出让方名称'))}",
                rule="Zg13_Rule16:境内金融机构标的股权出让方代码未填报金融机构编码，需核实。",
                error="境内金融机构标的股权出让方代码未填报金融机构编码，需核实",
            )
            if _unique_result(seen, result):
                yield result


_ZG07_CROSS_PERIOD_FIELDS: tuple[str, ...] = (
    "贷款种类",
    "贷款转让方机构代码",
    "贷款合同原始发放机构代码",
    "贷款合同原始发放机构所在地代码",
    "借款人类型",
    "地区代码",
    "借款人代码",
    "行业信息",
    "企业出资人经济成分",
    "企业规模",
    "贷款产品类别",
    "贷款实际投向",
    "贷款发放日期",
    "贷款到期日期",
    "利率是否固定",
    "利率水平",
    "贷款担保方式",
    "贷款转让折扣率",
    "原始合同币种",
    "原始合同金额",
    "原始合同金额折人民币",
    "贷款余额币种",
    "科技相关产业标识",
    "绿色领域标识",
    "普惠领域标识",
    "养老产业标识",
    "数字经济核心产业标识",
)

_ZG08_COUNTERPARTY_ISSUER_CODE_FIELDS = (
    "交易对手机构编码",
)
_ZG08_COUNTERPARTY_PRODUCT_CODE_FIELDS = (
    "交易对手产品代码",
)


def _legacy_detail(row: dict[str, Any], label: str, fields: tuple[str, ...]) -> str:
    return f"{label}:{'_'.join(_legacy_df_text(_row_value(row, field)) for field in fields)}"


def _legacy_df_text(value: Any) -> str:
    raw = text(value)
    if raw == "" or raw.lower() == "none":
        return "nan"
    return raw


def _legacy_nat_text(value: Any) -> str:
    raw = text(value)
    if raw == "" or raw.lower() in {"none", "nan"}:
        return "NaT"
    return raw


def _legacy_decimal_text(value: Any, digits: int) -> str:
    raw = text(value)
    if raw == "" or raw.lower() == "none":
        return "nan"
    try:
        return f"{float(raw.replace(',', '')):.{digits}f}"
    except ValueError:
        return "nan" if raw.lower() == "nan" else raw


def _legacy_compare_text(value: Any, field: str) -> str:
    if field in {"利率水平", "贷款转让折扣率"}:
        return _legacy_decimal_text(value, 5)
    if field in {"原始合同金额", "原始合同金额折人民币"}:
        return _legacy_decimal_text(value, 2)
    return _legacy_df_text(value)


def _in_report_month(value: Any, report_date: date) -> bool:
    parsed = _parse_date(value)
    return parsed is not None and parsed.year == report_date.year and parsed.month == report_date.month


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = text(value)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        parts = raw[:10].split("-")
        if len(parts) == 3:
            try:
                return date(int(parts[0]), int(parts[1]), int(parts[2]))
            except ValueError:
                return None
        return None


def _zg13_financial_code_mismatch(row: dict[str, Any], code_chinese: str, name_chinese: str) -> bool:
    code = _row_text(row, code_chinese)
    name = _row_text(row, name_chinese)
    excluded = ("融资租赁", "国际租赁", "担保", "典当", "小额贷款")
    return len(code) != 14 and _row_text(row, "行业信息") == "J" and not any(keyword in name for keyword in excluded)


def _legacy_zg13_detail(row: dict[str, Any]) -> str:
    product_code = _first_text(row, "产品代码")
    inner_code = _first_text(row, "其他股权投资内部编码")
    return (
        "产品代码_标的企业代码_其他股权投资内部编码:"
        f"{_legacy_df_text(product_code)}_{_legacy_df_text(_row_text(row, '标的企业代码'))}_{_legacy_df_text(inner_code)}"
    )


def _first_text(row: dict[str, Any], *fields: str) -> str:
    """Return the first non-empty mapped value. No English business-field fallback."""
    chinese_fields = _chinese_fields_only(*fields)
    if chinese_fields:
        for field in chinese_fields:
            if field in row and text(row.get(field)):
                return text(row.get(field))
            english = _resolve(field)
            if english and english in row and text(row.get(english)):
                return text(row.get(english))
        return ""
    for field in fields:
        if field and _is_metric_code(field) and field in row and text(row.get(field)):
            return text(row.get(field))
    return ""


def _unique_result(seen: set[tuple[str, str, str, str]], row: ValidationResultRow) -> bool:
    key = (row.detail, row.value1, row.value2, row.mark)
    if key in seen:
        return False
    seen.add(key)
    return True


def _common_detail_rules(zg_code: str, report_date: date, rows: list[dict[str, Any]]) -> Iterable[ValidationResultRow]:
    area_field_groups = {
        "ZG06": (("基础资产出让机构注册地区",),),
        "ZG07": (("贷款合同原始发放机构所在地代码",), ("地区代码",)),
        "ZG12": (("地区代码",),),
        "ZG13": (("地区代码",),),
    }.get(zg_code, ())
    for row in rows:
        for group in area_field_groups:
            value = _row_text(row, *group)
            display = _resolve(group[0]) or group[0]
            if area_not_county_level(value):
                yield make_row(
                    report_date=report_date,
                    zg_code=zg_code,
                    rule_id=f"Zg{zg_code[-2:]}_Rule1",
                    form=f"{zg_code}明细信息校验",
                    detail=f"{display}:{value}",
                    value1=f"{display}:{value}",
                    rule=f"Zg{zg_code[-2:]}_Rule1:地区代码未填报到区县一级，需核实",
                )


def _zg08(
    report_date: date,
    rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
    related_rows: dict[str, list[dict[str, Any]]],
) -> Iterable[ValidationResultRow]:
    seen: set[tuple[str, str, str, str]] = set()
    public_product_codes = _public_product_codes(related_rows)
    if public_product_codes:
        actual_end_dates = _public_product_actual_end_dates(related_rows)
        for row in rows:
            counterparty_product = _zg08_counterparty_product_code(row)
            actual_end_date = actual_end_dates.get(counterparty_product, "")
            parsed_actual_end_date = _parse_date(actual_end_date)
            if not actual_end_date or parsed_actual_end_date is None or parsed_actual_end_date > report_date:
                continue
            result = _zg08_result(
                report_date,
                row,
                "Zg08_Rule1",
                "Zg08_Rule1:公开信息交叉校验-所投资资管产品已终止，需核实",
                "交易对手产品代码",
                counterparty_product,
                "产品实际终止日期",
                actual_end_date,
                error="所投资资管产品当月应当处于存续期",
            )
            if _unique_result(seen, result):
                yield result

        previous_missing = {
            _zg08_counterparty_product_code(row)
            for row in previous_rows
            if _zg08_counterparty_product_code(row) and _zg08_counterparty_product_code(row) not in public_product_codes
        }
        for row in rows:
            counterparty_product = _zg08_counterparty_product_code(row)
            if not counterparty_product or counterparty_product in public_product_codes or counterparty_product not in previous_missing:
                continue
            result = _zg08_result(
                report_date,
                row,
                "Zg08_Rule2",
                "Zg08_Rule2:公开信息交叉校验-当期及上期所投资资管产品均不在平台名录库中，需核实",
                "产品代码",
                _zg08_product_code(row),
                "交易对手产品代码",
                counterparty_product,
                error="所投资资管产品在当月不存在时，一般应在上月中存在",
            )
            if _unique_result(seen, result):
                yield result

    for row in rows:
        product_code = _zg08_product_code(row)
        debt_project = _zg08_debt_project(row)
        if _row_text(row, "交易对手产品种类") == "1" and debt_project in {"A7200", "C1100", "C1200"} and product_code[:1] in {"C", "Z"}:
            result = _zg08_result(
                report_date,
                row,
                "Zg08_Rule3",
                "Zg08_Rule3:银行非保本理财产品的交易对手为理财产品，需核实",
                "资产负债项目",
                debt_project,
                "交易对手产品代码",
                _zg08_counterparty_product_code(row),
                error="银行非保本理财产品的交易对手一般不应为理财产品，需核实",
            )
            if _unique_result(seen, result):
                yield result

    if public_product_codes:
        counterparty_amounts = _zg08_counterparty_amounts(rows)
        local_product_codes = _zg08_product_codes(rows)
        public_product_issuer_codes = _public_product_issuer_codes(related_rows)
        zg01_product_issuer_codes = _zg01_product_issuer_codes(related_rows)
        own_issuer_code = _zg01_default_issuer_code(related_rows)
        for result in _zg08_pair_rules(
            report_date,
            rows,
            counterparty_amounts,
            local_product_codes,
            public_product_issuer_codes,
            zg01_product_issuer_codes,
            own_issuer_code,
            left_projects={"A5200"},
            right_projects={"B1200"},
            missing_rule_id="Zg08_Rule4",
            missing_rule_text="Zg08_Rule4:公开信息交叉校验-回购业务交易对手方未填报相关数据，需核实",
            missing_error="回购业务交易对手方未填报相关数据，需核实",
            reverse_rule_id="Zg08_Rule8",
            reverse_rule_text="Zg08_Rule8:公开信息交叉校验-回购业务交易对手方填报相关数据，本机构未填写，需核实",
            reverse_error="回购业务交易对手方填报相关数据，本机构未填写，需核实",
        ):
            if _unique_result(seen, result):
                yield result
        for result in _zg08_pair_rules(
            report_date,
            rows,
            counterparty_amounts,
            local_product_codes,
            public_product_issuer_codes,
            zg01_product_issuer_codes,
            own_issuer_code,
            left_projects={"A7200"},
            right_projects={"C1100", "C1200"},
            missing_rule_id="Zg08_Rule5",
            missing_rule_text="Zg08_Rule5:公开信息交叉校验-特定目的载体投资交易对手实收本金方未填报相关数据，需核实",
            missing_error="特定目的载体投资，交易对手实收本金方未填报相关数据，需核实",
            reverse_rule_id="Zg08_Rule9",
            reverse_rule_text="Zg08_Rule9:公开信息交叉校验-特定目的载体投资交易实收本金方填报相关数据，本机构未填写，需核实",
            reverse_error="特定目的载体投资交易实收本金方填报相关数据，本机构未填写，需核实",
        ):
            if _unique_result(seen, result):
                yield result
        for result in _zg08_pair_rules(
            report_date,
            rows,
            counterparty_amounts,
            local_product_codes,
            public_product_issuer_codes,
            zg01_product_issuer_codes,
            own_issuer_code,
            left_projects={"C1100", "C1200"},
            right_projects={"A7200"},
            missing_rule_id="Zg08_Rule6",
            missing_rule_text="Zg08_Rule6:公开信息交叉校验-实收本金方交易对手特定目的载体投资未填报相关数据，需核实",
            missing_error="实收本金方交易对手特定目的载体投资未填报相关数据，需核实",
            reverse_rule_id="Zg08_Rule10",
            reverse_rule_text="Zg08_Rule10:公开信息交叉校验-实收本金方交易对手特定目的载体投资填报相关数据，本机构未填写，需核实",
            reverse_error="实收本金方交易对手特定目的载体投资填报相关数据，本机构未填写，需核实",
        ):
            if _unique_result(seen, result):
                yield result
        for result in _zg08_pair_rules(
            report_date,
            rows,
            counterparty_amounts,
            local_product_codes,
            public_product_issuer_codes,
            zg01_product_issuer_codes,
            own_issuer_code,
            left_projects={"B1200"},
            right_projects={"A5200"},
            missing_rule_id="Zg08_Rule7",
            missing_rule_text="Zg08_Rule7:公开信息交叉校验-拆借业务交易对手方未填报相关数据，需核实",
            missing_error="拆借业务交易对手方未填报相关数据，需核实",
            reverse_rule_id="Zg08_Rule11",
            reverse_rule_text="Zg08_Rule11:公开信息交叉校验-拆借业务交易对手方填报相关数据，本机构未填写，需核实",
            reverse_error="拆借业务交易对手方填报相关数据，本机构未填写，需核实",
        ):
            if _unique_result(seen, result):
                yield result

    for row in rows:
        projcode = _zg08_product_code(row)
        riverprojcode = _zg08_counterparty_product_code(row)
        riverissuercode = _row_text(row, "交易对手机构编码")
        if projcode and riverprojcode and projcode == riverprojcode:
            result = make_row(
                report_date=report_date,
                zg_code="ZG08",
                rule_id="Zg08_Rule12",
                form="特定目的载体交易对手明细信息校验",
                detail=_zg08_detail(row),
                value1=f"交易对手产品代码:{riverprojcode}",
                rule="Zg08_Rule12:交易对手代码为自身产品代码，需核实",
                error="交易对手产品代码一般不应与本产品代码相同",
            )
            if _unique_result(seen, result):
                yield result
        if (
            _row_has_any(row, *_ZG08_COUNTERPARTY_ISSUER_CODE_FIELDS)
            and _row_has_any(row, *_ZG08_COUNTERPARTY_PRODUCT_CODE_FIELDS)
            and (not riverissuercode or not riverprojcode or not riverprojcode.startswith(riverissuercode[:6]))
        ):
            result = make_row(
                report_date=report_date,
                zg_code="ZG08",
                rule_id="Zg08_Rule13",
                form="特定目的载体交易对手明细信息校验",
                detail=_zg08_detail(row),
                value1=f"交易对手机构编码:{riverissuercode}",
                value2=f"交易对手产品代码:{riverprojcode}",
                rule="Zg08_Rule13:交易对手机构编码与交易对手产品代码前6位不一致，需核实",
                error="交易对手机构编码一般应与交易对手产品代码前6位一致",
            )
            if _unique_result(seen, result):
                yield result


def _public_product_codes(related_rows: dict[str, list[dict[str, Any]]]) -> set[str]:
    result: set[str] = set()
    for row in _public_info_rows(related_rows):
        product_code = _row_text(row, "产品代码")
        if product_code:
            result.add(product_code)
    return result


def _public_product_actual_end_dates(related_rows: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in _public_info_rows(related_rows):
        product_code = _row_text(row, "产品代码")
        actual_end_date = _row_text(row, "产品实际终止日期")
        if product_code and actual_end_date:
            result[product_code] = actual_end_date
    return result


_ZG08_EXCLUDED_ORG_CODES: frozenset[str] = frozenset({"Z7003132000018", "D2003832000012", "C1086832000010"})


def _public_product_issuer_codes(related_rows: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in _public_info_rows(related_rows):
        product_code = _row_text(row, "产品代码")
        issuer_code = _row_text(row, "发行机构代码")
        if product_code and issuer_code:
            result[product_code] = issuer_code
    return result


def _zg01_product_issuer_codes(related_rows: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in related_rows.get("ZG01", []):
        product_code = _row_text(row, "产品代码")
        issuer_code = _row_text(row, "发行机构代码")
        if product_code and issuer_code:
            result[product_code] = issuer_code
    return result


def _zg01_default_issuer_code(related_rows: dict[str, list[dict[str, Any]]]) -> str:
    for row in related_rows.get("ZG01", []):
        issuer_code = _row_text(row, "发行机构代码")
        if issuer_code:
            return issuer_code
    return ""


def _zg08_pair_rules(
    report_date: date,
    rows: list[dict[str, Any]],
    counterparty_amounts: dict[tuple[str, str, str], float],
    local_product_codes: set[str],
    public_product_issuer_codes: dict[str, str],
    zg01_product_issuer_codes: dict[str, str],
    own_issuer_code: str,
    *,
    left_projects: set[str],
    right_projects: set[str],
    missing_rule_id: str,
    missing_rule_text: str,
    missing_error: str,
    reverse_rule_id: str,
    reverse_rule_text: str,
    reverse_error: str,
    require_counterparty_local: bool = False,
) -> Iterable[ValidationResultRow]:
    for row, debt_project, amount in _zg08_left_pair_rows(rows, left_projects):
        if not _zg08_legacy_public_pair_scope(row, public_product_issuer_codes, zg01_product_issuer_codes, own_issuer_code):
            continue
        if require_counterparty_local and _zg08_counterparty_product_code(row) not in local_product_codes:
            continue
        reverse_amount = _zg08_counterparty_amount(row, counterparty_amounts, right_projects)
        if not _zg08_legacy_pair_change_is_full(amount, reverse_amount):
            continue
        issuer_code = _zg08_pair_issuer_code(row, zg01_product_issuer_codes, own_issuer_code)
        counterparty_issuer_code = public_product_issuer_codes.get(_zg08_counterparty_product_code(row), "")
        yield _zg08_pair_result(
            report_date,
            row,
            missing_rule_id,
            missing_rule_text,
            "交易对手",
            _zg08_product_code(row),
            debt_project,
            _zg08_counterparty_org_name(row, public_product_issuer_codes),
            "交易对手产品代码",
            _zg08_counterparty_product_code(row),
            amount,
            org_code=issuer_code,
            error=missing_error,
        )
        yield _zg08_pair_result(
            report_date,
            row,
            reverse_rule_id,
            reverse_rule_text,
            "交易对手方",
            _zg08_counterparty_product_code(row),
            debt_project,
            _zg08_own_org_name(own_issuer_code),
            "交易对手方产品代码",
            _zg08_product_code(row),
            amount,
            org_code=counterparty_issuer_code,
            error=reverse_error,
        )


def _zg08_left_pair_rows(
    rows: list[dict[str, Any]],
    left_projects: set[str],
) -> Iterable[tuple[dict[str, Any], str, float]]:
    if left_projects != {"C1100", "C1200"}:
        for row in rows:
            if _zg08_debt_project(row) in left_projects:
                yield row, _zg08_debt_project(row), _zg08_amount(row)
        return

    grouped: dict[tuple[str, str], tuple[dict[str, Any], float]] = {}
    for row in rows:
        if _zg08_debt_project(row) not in left_projects:
            continue
        key = (_zg08_product_code(row), _zg08_counterparty_product_code(row))
        if not all(key):
            continue
        first_row, amount = grouped.get(key, (row, 0.0))
        grouped[key] = (first_row, amount + _zg08_amount(row))
    for row, amount in grouped.values():
        yield row, "C1100-VS-C1200", amount


def _zg08_product_codes(rows: list[dict[str, Any]]) -> set[str]:
    result: set[str] = set()
    for row in rows:
        if _zg08_amount(row) == 0:
            continue
        product_code = _zg08_product_code(row)
        if product_code:
            result.add(product_code)
    return result


def _zg08_pair_result(
    report_date: date,
    row: dict[str, Any],
    rule_id: str,
    rule: str,
    detail_suffix: str,
    detail_product_code: str,
    debt_project: str,
    detail_org_name: str,
    value1_label: str,
    value1: str,
    amount: float,
    *,
    org_code: str = "",
    error: str = "",
) -> ValidationResultRow:
    return make_row(
        report_date=report_date,
        zg_code="ZG08",
        org_code=org_code or DEFAULT_ORG_CODE,
        rule_id=rule_id,
        form="特定目的载体交易对手明细信息",
        detail=(
            f"产品代码_资产负债项目_法人金融机构名称-{detail_suffix}:"
            f"{_legacy_df_text(detail_product_code)}_{_legacy_df_text(debt_project)}_{_legacy_df_text(detail_org_name)}"
        ),
        value1=f"{value1_label}:{value1}",
        value2=f"期末金额折人民币:{_legacy_number_text(amount)}",
        rule=rule,
        error=error,
    )


def _zg08_legacy_public_pair_scope(
    row: dict[str, Any],
    public_product_issuer_codes: dict[str, str],
    zg01_product_issuer_codes: dict[str, str],
    own_issuer_code: str,
) -> bool:
    if _zg08_amount(row) == 0:
        return False
    org_codes = get_org_codes() - _ZG08_EXCLUDED_ORG_CODES
    issuer_code = zg01_product_issuer_codes.get(_zg08_product_code(row), "") or own_issuer_code or _issuer_code(row)
    counterparty_issuer_code = public_product_issuer_codes.get(_zg08_counterparty_product_code(row), "")
    return issuer_code in org_codes and counterparty_issuer_code in org_codes


def _zg08_pair_issuer_code(
    row: dict[str, Any],
    zg01_product_issuer_codes: dict[str, str],
    own_issuer_code: str,
) -> str:
    return zg01_product_issuer_codes.get(_zg08_product_code(row), "") or own_issuer_code or _issuer_code(row)


def _zg08_counterparty_org_name(row: dict[str, Any], public_product_issuer_codes: dict[str, str]) -> str:
    issuer_code = public_product_issuer_codes.get(_zg08_counterparty_product_code(row), "")
    return get_org_info(issuer_code).org_name if issuer_code else ""


def _zg08_own_org_name(own_issuer_code: str) -> str:
    return get_org_info(own_issuer_code).org_name if own_issuer_code else get_org_info(DEFAULT_ORG_CODE).org_name


def _zg08_counterparty_amounts(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], float]:
    result: dict[tuple[str, str, str], float] = {}
    for row in rows:
        if _zg08_amount(row) == 0:
            continue
        product_code = _zg08_product_code(row)
        counterparty_product = _zg08_counterparty_product_code(row)
        debt_project = _zg08_debt_project(row)
        if product_code and counterparty_product and debt_project:
            key = (product_code, counterparty_product, debt_project)
            result[key] = result.get(key, 0.0) + _zg08_amount(row)
    return result


def _zg08_counterparty_amount(
    row: dict[str, Any],
    counterparty_amounts: dict[tuple[str, str, str], float],
    expected_projects: set[str],
) -> float:
    product_code = _zg08_product_code(row)
    counterparty_product = _zg08_counterparty_product_code(row)
    if not product_code or not counterparty_product:
        return 0.0
    return sum(counterparty_amounts.get((counterparty_product, product_code, debt_project), 0.0) for debt_project in expected_projects)


def _zg08_legacy_pair_change_is_full(left_amount: float, right_amount: float) -> bool:
    diff = left_amount - right_amount
    if left_amount != 0:
        change = 100 * diff / left_amount
    elif right_amount != 0:
        change = 100 * diff / right_amount
    else:
        change = 0
    return abs(change) == 100


def _zg08_result(
    report_date: date,
    row: dict[str, Any],
    rule_id: str,
    rule: str,
    value1_label: str,
    value1: str,
    value2_label: str = "",
    value2: str = "",
    *,
    error: str = "",
) -> ValidationResultRow:
    return make_row(
        report_date=report_date,
        zg_code="ZG08",
        rule_id=rule_id,
        form="特定目的载体交易对手明细信息",
        detail=_zg08_detail(row),
        value1=f"{value1_label}:{value1}",
        value2=f"{value2_label}:{value2}" if value2_label else "",
        rule=rule,
        error=error,
    )


def _zg08_detail(row: dict[str, Any]) -> str:
    return (
        "产品代码_资产负债项目_交易对手产品种类_交易对手机构编码:"
        f"{_legacy_df_text(_zg08_product_code(row))}_{_legacy_df_text(_zg08_debt_project(row))}_"
        f"{_legacy_df_text(_row_text(row, '交易对手产品种类'))}_"
        f"{_legacy_df_text(_row_text(row, '交易对手机构编码'))}"
    )


def _zg08_product_code(row: dict[str, Any]) -> str:
    return _row_text(row, "产品代码")


def _zg08_counterparty_product_code(row: dict[str, Any]) -> str:
    return _row_text(row, "交易对手产品代码")


def _zg08_debt_project(row: dict[str, Any]) -> str:
    return _row_text(row, "资产负债项目")


def _zg09(
    report_date: date,
    rows: list[dict[str, Any]],
    related_rows: dict[str, list[dict[str, Any]]],
) -> Iterable[ValidationResultRow]:
    template_rows = _template_rows_for("ZG09", related_rows)
    template_values = _template_vertical_values_by_table(template_rows)
    if not template_values:
        return

    for row in rows:
        scope_code = _row_text(row, "信托产品类型口径")
        if scope_code not in {"1", "2"}:
            continue
        org_code = _issuer_code(row)
        for mapping in _cross_table_mappings("ZG09", scope_code):
            field = mapping.effective_detail_field_name
            template_table = mapping.effective_template_table_name.lower()
            template_field = mapping.effective_template_field_name.lower()
            if not _legacy_has_text(row.get(field)):
                continue
            template_value = template_values.get((template_table, template_field))
            if template_value is None:
                continue
            platform_value = _legacy_float(row.get(field)) / 10000.0
            diff = template_value - platform_value
            if abs(diff) < 0.01:
                continue
            yield _template_result(
                report_date,
                "ZG09",
                row,
                "Zg09_Rule3",
                "Zg09_Rule3:模板交叉校验-表内（金融）资产与模板数据不一致，需核实",
                "资产负债剩余期限信息",
                f"金融机构编码_指标名称:{_legacy_df_text(org_code)}_{field}",
                template_value,
                platform_value,
                diff,
                "表内（金融）资产应当与模板数一致",
            )


def _zg10(
    report_date: date,
    rows: list[dict[str, Any]],
    related_rows: dict[str, list[dict[str, Any]]],
) -> Iterable[ValidationResultRow]:
    template_rows = [
        row for row in _template_rows_for("ZG10", related_rows) if _template_form_matches_zg10(row)
    ]
    template_values = _template_vertical_values_by_table(template_rows)
    if not template_values:
        return

    for row in rows:
        scope_code = _row_text(row, "信托产品类型口径")
        if scope_code not in {"1", "2"}:
            continue
        org_code = _issuer_code(row)
        product_type = _row_text(row, "产品品种")
        for mapping in _cross_table_mappings("ZG10", scope_code):
            field = mapping.effective_detail_field_name
            if not _legacy_has_text(row.get(field)):
                continue
            template_value = template_values.get((
                mapping.effective_template_table_name.lower(),
                mapping.effective_template_field_name.lower(),
            ))
            if template_value is None:
                continue
            platform_value = _legacy_float(row.get(field)) / 10000.0
            diff = template_value - platform_value
            if abs(diff) < 0.01:
                continue
            yield _template_result(
                report_date,
                "ZG10",
                row,
                "Zg10_Rule1",
                "Zg10_Rule1:模板交叉校验-数据平台指标与模板数据不一致，需核实",
                "债券等资产配置情况信息",
                f"金融机构编码_产品品种_指标名称:{_legacy_df_text(org_code)}_{_legacy_df_text(product_type)}_{field}",
                template_value,
                platform_value,
                diff,
                "数据平台数据应当与模板数一致",
            )


def _mapped_template_table(zg_code: str, scope_code: str) -> str:
    """模板物理表只从字段映射目录解析，规则不再拼接或引用生产物理表名。"""
    catalog = _FIELD_CATALOG.get(None)
    if catalog is None or not scope_code:
        return ""
    try:
        return str(catalog.table_for("template", zg_code, scope_code))
    except (KeyError, AttributeError, TypeError):
        return ""


def _cross_table_mappings(zg_code: str, scope_code: str) -> tuple[Any, ...]:
    catalog = _FIELD_CATALOG.get(None)
    if catalog is None:
        return ()
    try:
        return tuple(catalog.cross_table_mappings_for(zg_code, scope_code))
    except (AttributeError, TypeError):
        return ()


def _zg09_template_metrics(row: dict[str, Any]) -> Iterable[tuple[str, str, str]]:
    column_map = {"a": "A", "b": "B", "c": "C", "d": "D", "e": "E"}
    for field in row:
        field_code = text(field).strip().lower()
        if len(field_code) != 5 or not field_code.startswith("g"):
            continue
        row_code = field_code[1:4]
        column_code = field_code[4]
        if not row_code.isdigit() or column_code not in column_map:
            continue
        template_field = f"{column_map[column_code]}_g{row_code}00"
        yield field, template_field, field_code.upper()


def _template_vertical_values_by_table(rows: list[dict[str, Any]]) -> dict[tuple[str, str], float]:
    values: dict[tuple[str, str], float] = {}
    for row in rows:
        # 模板物理表名由引擎注入；纵表结构字段使用元数据生成的中文别名。
        table_name = text(row.get("template_table") or row.get("table_name_en") or row.get("table_name")).lower()
        field_name = text(row.get("指标代码") or row.get("指标名称") or row.get("字段名")).lower()
        if not table_name or not field_name:
            continue
        values[(table_name, field_name)] = _legacy_float(row.get("数据值", row.get("指标值", row.get("字段值"))))
    return values


def _template_indicator_values_for_table(
    values: dict[tuple[str, str], float],
    table_name: str,
) -> dict[str, float]:
    indicators: dict[str, float] = {}
    target_table = table_name.lower()
    for (current_table, field_name), value in values.items():
        if current_table != target_table:
            continue
        indicator = _template_indicator_from_vertical_field(field_name)
        if indicator:
            indicators[indicator] = value
    return indicators


def _template_indicator_from_vertical_field(field_name: str) -> str:
    for part in reversed(field_name.lower().split("_")):
        if len(part) == 6 and part[0].isalpha() and part[1:].isdigit():
            return part
    return ""


def _template_rows_for(zg_code: str, related_rows: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in (f"TEMPLATE_{zg_code}", f"{zg_code}_TEMPLATE", "TEMPLATE", "模板"):
        rows.extend(related_rows.get(key, []))
    return rows


def _template_value_lookup(
    rows: list[dict[str, Any]],
    *,
    include_product_type: bool,
) -> dict[tuple[str, str, str], float]:
    values: dict[tuple[str, str, str], float] = {}
    for row in rows:
        org_code = _row_text(row, "机构代码", "金融机构编码")
        product_type = _row_text(row, "产品品种") if include_product_type else ""
        indicator_code = _template_metric_code(_row_text(row, "指标代码"))
        if not org_code or not indicator_code:
            continue
        values[(org_code, product_type, indicator_code)] = _legacy_float(
            _row_value(row, "数据值")
        )
    return values


def _template_form_matches_zg10(row: dict[str, Any]) -> bool:
    form_name = _row_text(row, "表单名称")
    return form_name == "" or "1-1" in form_name


def _template_metric_code(value: str) -> str:
    code = text(value).strip().upper()
    if not code:
        return ""
    code = code.split("_", 1)[0].split("-", 1)[0]
    if code.startswith("FB") and len(code) >= 7:
        return code[2:7]
    if code.startswith("00000") and len(code) >= 6:
        return code[1:6]
    if len(code) >= 6 and code[0].isalpha() and code[1:6].isdigit():
        return code[:6]
    if len(code) >= 5 and code[:5].isdigit():
        return code[:5]
    return code[:6]


def _zg10_metric_fields(rows: list[dict[str, Any]]) -> list[str]:
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field in fields:
                continue
            if _template_metric_code(field).startswith("H"):
                fields.append(field)
    return fields


def _template_result(
    report_date: date,
    zg_code: str,
    row: dict[str, Any],
    rule_id: str,
    rule: str,
    form: str,
    detail: str,
    template_value: float,
    platform_value: float,
    diff: float,
    error: str,
) -> ValidationResultRow:
    return make_row(
        report_date=report_date,
        zg_code=zg_code,
        rule_id=rule_id,
        form=form,
        detail=detail,
        value1=f"数据值_模板数据:{_legacy_number_text(template_value)}",
        value2=f"差值（万元、模板减数据平台）:{_legacy_number_text(diff)}",
        rule=rule,
        error=error,
        org_code=_issuer_code(row),
        org_name=_row_text(row, "法人金融机构名称") or None,
        manager_org=_row_text(row, "数据管理机构") or None,
    )


def _issuer_code(row: dict[str, Any]) -> str:
    return _row_text(row, "发行机构代码")


def _zg08_amount(row: dict[str, Any]) -> float:
    return _legacy_float(_row_value(row, "期末金额折人民币"))
