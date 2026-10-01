from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from auto_check.db_validation.legacy_rules import ACTIVE_LEGACY_RULES, LegacyRule


RULE_DOCUMENT_FILENAME = "数据库校验规则说明.xlsx"


FORM_NAMES: dict[str, str] = {
    "ZG01": "资管产品基本信息",
    "ZG02": "资管产品初始募集信息",
    "ZG03": "资管产品终止信息",
    "ZG04": "资管产品存续募集信息",
    "ZG05": "资管产品资产负债信息",
    "ZG06": "资产收益权明细信息",
    "ZG07": "除回购和拆借外贷款明细信息",
    "ZG08": "特定目的载体交易对手明细信息",
    "ZG09": "资产负债剩余期限信息",
    "ZG10": "债券等资产配置情况信息",
    "ZG11": "行业投向信息",
    "ZG12": "除资产收益权外其他债权明细信息",
    "ZG13": "其他股权投资明细信息",
}

DOCUMENT_ENABLED_RULE_IDS: frozenset[str] = frozenset({"Zg09_Rule3", "Zg10_Rule1"})
_RAW_ENCODING_EMPTY_NOTE = (
    "按映射后的原始编码判空，不去除首尾空格。纯空格以及字面字符串“None”“nan”不为空；"
    "只检查本表编码，不混入转让贷款机构条件。按每条原始记录输出编码为空提示。"
)
_RAW_ENCODING_DUPLICATE_NOTE = (
    "仅在自己机构内校验，金融机构编码、数据管理机构不作为必需字段。"
    "产品代码和编码均使用原始值，不去除首尾空格；任一分组键为NULL或实际NaN均不参与查重。"
    "空串参与查重，同产品重复空串可同时触发编码为空和不唯一提示。"
    "按每条原始记录输出重复结果，数据值2展示重复次数。"
)
RULE_NOTES: dict[str, str] = {
    "Zg02_Rule1": "依赖“初始募集金额”和“初始募集金额折人民币”字段映射进行人民币合计校验。",
    "Zg04_Rule15": (
        "地区为空的汇总行按产品代码、地区、客户类型、币种四个业务维度匹配上期，不增加机构名称或机构编码匹配要求。"
        "上期0也参与绝对差比较；未匹配上期，按0比较，并在结果说明中标明此策略。"
        "上期数据源不可读时保留已有警告。阈值10为两期原始收益率的绝对差，不是10%。"
    ),
    "Zg04_Rule17": (
        "当期及上期均取地区、币种为空的总计行，按产品代码取得上期总计候选。"
        "缺失或无效上期不提示上期非零；仅有限、有效的非零收益率参与比较。"
        "多个上期总计候选逐条比较并输出，结果说明注明候选记录数，不覆盖为最后一条。"
    ),
    "Zg04_Rule19": "保持原有20%相对变化口径及上期收益率非0的分母保护，不随Rule15改为绝对差阈值。",
    "Zg05_Rule3": "依赖 ZG07“贷款余额折人民币”字段映射，按产品代码汇总后与 ZG05 对比。",
    "Zg06_Rule14": (
        "五项标识按原始值判断填写，NULL、实际NaN和原始空串为空；数值0、纯空格及字面字符串均算已填。"
        "五项全部为空不提示；其他机构类型不触发本条。"
    ),
    "Zg06_Rule17": _RAW_ENCODING_EMPTY_NOTE,
    "Zg06_Rule18": _RAW_ENCODING_DUPLICATE_NOTE,
    "Zg07_Rule19": _RAW_ENCODING_EMPTY_NOTE,
    "Zg07_Rule20": _RAW_ENCODING_DUPLICATE_NOTE,
    "Zg12_Rule16": "保留空ZG12与ZG05余额核对，以及abs(差值)>0.1的双向金额差检查；差值等于正负0.1不提示。",
    "Zg12_Rule19": _RAW_ENCODING_EMPTY_NOTE,
    "Zg12_Rule20": _RAW_ENCODING_DUPLICATE_NOTE,
}
RULE_TRIGGER_CONDITIONS: dict[str, str] = {
    "Zg04_Rule15": (
        "地区为空的汇总行，两期原始当月年化收益率满足abs(当期－上期)>10时提示；差值等于10不提示。"
    ),
    "Zg04_Rule17": (
        "地区、币种为空的总计行，当月年化收益率当期为0，且存在有效上期收益率不等于0时提示。"
    ),
    "Zg04_Rule19": "期末产品金额折人民币为0且上期收益率非0，abs((当期收益率－上期收益率)/上期收益率)>20%时提示。",
    "Zg06_Rule14": (
        "基础资产出让机构类型为4或5，且科技相关产业标识、绿色领域标识、普惠领域标识、"
        "养老产业标识、数字经济核心产业标识中至少一项已填时提示。"
    ),
    "Zg06_Rule17": "资产收益权内部编码为NULL、实际NaN或原始空串时提示。",
    "Zg06_Rule18": "按产品代码＋原始资产收益权内部编码分组，记录数大于等于2时提示。",
    "Zg07_Rule19": "贷款借据编码为NULL、实际NaN或原始空串时提示。",
    "Zg07_Rule20": "按产品代码＋原始贷款借据编码分组，记录数大于等于2时提示。",
    "Zg12_Rule19": "除资产收益权外其他债权内部编码为NULL、实际NaN或原始空串时提示。",
    "Zg12_Rule20": "按产品代码＋原始除资产收益权外其他债权内部编码分组，记录数大于等于2时提示。",
}
TEMPLATE_RULE_NOTES: dict[str, str] = {
    "Zg09_Rule3": (
        "\u53d7\u6267\u884c\u754c\u9762\u7684\u201c\u6a21\u677f\u6821\u9a8c\u201d\u52fe\u9009\u9879\u63a7\u5236\uff1b"
        "\u4fe1\u6258\u4ea7\u54c1\u7c7b\u578b\u53e3\u5f84=1 \u5bf9\u6bd4\u5b57\u6bb5\u6620\u5c04\u89e3\u6790\u51fa\u7684 ZG09 \u53e3\u5f84 1 \u6a21\u677f\u7269\u7406\u8868\uff1b"
        "\u53e3\u5f84=2 \u5bf9\u6bd4\u53e3\u5f84 2 \u6a21\u677f\u7269\u7406\u8868\uff082a\uff09\u3002"
    ),
    "Zg10_Rule1": (
        "\u53d7\u6267\u884c\u754c\u9762\u7684\u201c\u6a21\u677f\u6821\u9a8c\u201d\u52fe\u9009\u9879\u63a7\u5236\uff1b"
        "\u4fe1\u6258\u4ea7\u54c1\u7c7b\u578b\u53e3\u5f84=1 \u5bf9\u6bd4\u5b57\u6bb5\u6620\u5c04\u89e3\u6790\u51fa\u7684 ZG10 \u53e3\u5f84 1 \u6a21\u677f\u7269\u7406\u8868\uff1b"
        "\u53e3\u5f84=2 \u5bf9\u6bd4\u53e3\u5f84 2 \u6a21\u677f\u7269\u7406\u8868\uff082a\uff09\u3002"
    ),
}


@dataclass(frozen=True)
class UserRule:
    form_code: str
    form_name: str
    rule_id: str
    category: str
    status: str
    check_item: str
    trigger_condition: str
    result_message: str
    cross_period: str
    note: str = ""


def build_rules_document() -> tuple[str, bytes]:
    workbook = Workbook()
    overview = workbook.active
    overview.title = "使用说明"
    summary = workbook.create_sheet("规则清单")
    detail = workbook.create_sheet("规则明细")

    rules = tuple(_user_rule(rule) for rule in ACTIVE_LEGACY_RULES)
    _write_overview(overview, rules)
    _write_summary(summary, rules)
    _write_detail(detail, rules)

    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return RULE_DOCUMENT_FILENAME, buffer.getvalue()


def _rule_document_enabled(rule: LegacyRule) -> bool:
    return rule.enabled or rule.rule_id in DOCUMENT_ENABLED_RULE_IDS


def _user_rule(rule: LegacyRule) -> UserRule:
    message = _message(rule)
    note = _note(rule)
    return UserRule(
        form_code=rule.zg_code,
        form_name=FORM_NAMES.get(rule.zg_code, rule.zg_code),
        rule_id=rule.rule_id,
        category=rule.category,
        status="启用" if _rule_document_enabled(rule) else "停用",
        check_item=_check_item(rule, message),
        trigger_condition=_trigger_condition(rule, message),
        result_message=message,
        cross_period="是" if _is_cross_period(message) else "否",
        note=note,
    )


def _message(rule: LegacyRule) -> str:
    return rule.rule_text.split(":", 1)[-1].split("：", 1)[-1].strip()


def _check_item(rule: LegacyRule, message: str) -> str:
    if rule.is_template_rule:
        return "将数据平台填报值与模板数据进行一致性比对。"
    if rule.is_public_info_rule:
        return "将逐笔数据与公开信息表或交易对手填报信息进行交叉比对。"
    if _is_cross_period(message):
        return "检查本期数据与上期数据之间是否保持旧程序要求的一致性或衔接关系。"
    if "人民币合计" in message:
        return "检查人民币合计、人民币金额或折人民币金额之间是否一致。"
    if "地区代码" in message:
        return "检查地区代码是否按旧程序地区字典填报到区县一级。"
    if "代码" in message and "编码规则" in message:
        return "检查机构、客户、借款人或交易场所代码是否符合旧程序编码规则。"
    if "同一" in message and "不一致" in message:
        return "检查同一主体或同一业务编号下的关键字段是否一致。"
    return f"检查{_strip_suffix(message)}。"


def _trigger_condition(rule: LegacyRule, message: str) -> str:
    if rule.rule_id in RULE_TRIGGER_CONDITIONS:
        return RULE_TRIGGER_CONDITIONS[rule.rule_id]
    body = _strip_suffix(message)
    if rule.is_template_rule:
        return f"启用模板校验并取得模板数据后，旧程序发现{body}时提示。"
    if rule.is_public_info_rule:
        return f"勾选公开信息校验后，旧程序发现{body}时提示。"
    if _is_cross_period(message):
        return f"按旧程序匹配键对本期和上期数据进行比对，发现{body}时提示。"
    return f"旧程序发现{body}时提示。"


def _note(rule: LegacyRule) -> str:
    notes: list[str] = []
    if rule.rule_id in RULE_NOTES:
        notes.append(RULE_NOTES[rule.rule_id])
    if rule.is_public_info_rule:
        notes.append("受执行界面的“公开信息校验”勾选项控制。")
    if rule.rule_id in TEMPLATE_RULE_NOTES:
        notes.append(TEMPLATE_RULE_NOTES[rule.rule_id])
    elif rule.is_template_rule:
        notes.append("模板数据源已在配置中预留，启用模板校验后执行。")
    if not _rule_document_enabled(rule) and rule.disabled_reason:
        notes.append(rule.disabled_reason)
    return "".join(notes)


def _rule_label(rule: UserRule) -> str:
    labels = [rule.rule_id, f"[{rule.category}]"]
    if rule.status == "停用":
        labels.append("[停用]")
    return "".join(labels)


def _is_cross_period(message: str) -> bool:
    return "跨期" in message or "上期" in message or "本期" in message and "上期" in message


def _strip_suffix(message: str) -> str:
    cleaned = message
    for suffix in ("，需核实。", "，需核实", "需核实。", "需核实"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
            break
    return cleaned.rstrip("，。")


def _write_overview(sheet, rules: tuple[UserRule, ...]) -> None:
    public_count = sum(1 for rule in rules if "公开信息" in rule.result_message)
    template_count = sum(1 for rule in rules if "模板" in rule.result_message)
    rows = [
        ["数据库校验规则说明"],
        ["用途", "用于说明数据库校验引擎当前接入的业务校验规则，便于业务人员理解校验结果。"],
        ["规则来源", "已同步最终20260930更新版的有效业务变化；历史迁移规则继续保留。"],
        ["适用范围", "本说明覆盖数据库校验引擎的当前活动规则；新增编码校验仅用于自己机构内数据，查重按产品代码和本表原始编码执行。"],
        ["纠错差异", "保留AutoCheck空ZG12及双向余额核对；空编码正常输出，缺失或无效上期不报上期非零。具体触发和边界以本说明为准。"],
        ["规则数量", f"共 {len(rules)} 条；其中公开信息交叉校验 {public_count} 条，模板交叉校验 {template_count} 条。"],
        ["读取方法", "先看“规则清单”了解每张表包含哪些规则，再看“规则明细”理解每条规则的触发含义。"],
        ["说明", "文档使用业务名称描述规则，不展示数据库字段名、技术实现细节或查询语句。"],
    ]
    for row in rows:
        sheet.append(row)
    sheet.merge_cells("A1:B1")
    sheet["A1"].font = Font(size=16, bold=True, color="1F2937")
    sheet["A1"].fill = PatternFill("solid", fgColor="EAF2FF")
    sheet.column_dimensions["A"].width = 18
    sheet.column_dimensions["B"].width = 96
    _style_sheet(sheet, header_row=1)


def _write_summary(sheet, rules: Iterable[UserRule]) -> None:
    sheet.append(["表单编号", "表单名称", "规则数量", "包含规则"])
    grouped: dict[tuple[str, str], list[UserRule]] = {}
    for rule in rules:
        grouped.setdefault((rule.form_code, rule.form_name), []).append(rule)
    for (form_code, form_name), form_rules in grouped.items():
        sheet.append([form_code, form_name, len(form_rules), "、".join(_rule_label(rule) for rule in form_rules)])
    _style_sheet(sheet)
    _set_widths(sheet, [12, 34, 12, 110])


def _write_detail(sheet, rules: Iterable[UserRule]) -> None:
    headers = ["序号", "表单编号", "表单名称", "规则编号", "检查内容", "什么情况下提示", "结果中的提示", "是否跨期", "规则类型", "执行状态", "备注"]
    sheet.append(headers)
    for index, rule in enumerate(rules, start=1):
        sheet.append([
            index,
            rule.form_code,
            rule.form_name,
            rule.rule_id,
            rule.check_item,
            rule.trigger_condition,
            rule.result_message,
            rule.cross_period,
            rule.category,
            rule.status,
            rule.note,
        ])
    _style_sheet(sheet)
    _set_widths(sheet, [8, 10, 28, 16, 42, 68, 48, 10, 16, 12, 56])


def _style_sheet(sheet, *, header_row: int = 1) -> None:
    header_fill = PatternFill("solid", fgColor="DCEBFF")
    header_font = Font(bold=True, color="111827")
    for cell in sheet[header_row]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in sheet.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    sheet.freeze_panes = f"A{header_row + 1}"


def _set_widths(sheet, widths: list[int]) -> None:
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
