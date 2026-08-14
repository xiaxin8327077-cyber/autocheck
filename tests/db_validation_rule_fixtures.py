# -*- coding: utf-8 -*-
"""Test helpers: inject Chinese field mapping so rule unit tests match production strict mode."""
from __future__ import annotations

from typing import Any

from auto_check.db_validation.metadata import TableFieldCatalog
from auto_check.db_validation.mapping_models import CrossTableMapping
from auto_check.db_validation.rules.basic import run_basic_rules as _run_basic_rules

EN_TO_CN: dict[str, str] = {
    "projcode": "产品代码",
    "productcode": "产品代码",
    "projname": "产品名称",
    "projpredate": "产品预计终止日期",
    "earlystopflg": "发行机构提前终止权标识",
    "creditflg": "产品增信标识",
    "creditform": "增信形式",
    "credittype": "增信机构类型",
    "runmode": "运行方式",
    "redeemflg": "客户赎回权标识",
    "raisebegdate": "募集起始日期",
    "levelflg": "分级产品标识",
    "source": "管理方式",
    "depoutorgcode": "托管机构名称",
    "depinorgcode": "境内托管机构代码",
    "areacode": "地区代码",
    "clientkind": "客户类型",
    "raiseamt": "初始募集金额",
    "raiseamtcny": "初始募集金额折人民币",
    "clientincomecny": "兑付客户收益折人民币",
    "clientrate": "兑付客户收益率",
    "moneytype": "币种",
    "datetype": "数据类型",
    "projshare": "期末产品份额",
    "projamtcny": "期末产品金额折人民币",
    "curraiseshare": "当期申购份额",
    "curcashshare": "当期兑付/赎回份额",
    "projamt": "期末产品金额",
    "currraiseamt": "当期申购金额",
    "curcashamt": "当期兑付/赎回金额",
    "navamt": "净值型产品期末净值",
    "navallamt": "净值型产品期末累计净值",
    "dyshouyi": "当月年化收益率",
    "beneficialcode": "资产收益权内部编码",
    "debtproj": "资产负债项目",
    "issuername": "基础资产出让机构名称",
    "issuercode": "基础资产出让机构代码",
    "issuertype": "基础资产出让机构类型",
    "issuerindustry": "基础资产出让机构行业",
    "issuerareacode": "基础资产出让机构注册地区",
    "issuereconomytype": "基础资产出让机构经济成分",
    "issuerentscale": "基础资产出让机构规模",
    "begdate": "转让起始日期",
    "predate": "转让预计终止日期",
    "perioddate": "转让展期到期日期",
    "asstetype": "基础资产类型",
    "transferamtcny": "基础资产转让金额折人民币",
    "assteamtcny": "基础资产期末余额折人民币",
    "asstepactccy": "基础资产原始协议币种",
    "asstepactamt": "基础资产原始协议金额",
    "asstepactamtcny": "基础资产原始协议金额折人民币",
    "rateinfo": "利率水平",
    "taboutflg": "出让机构出表标识",
    "buybackflg": "出让机构回购标识",
    "loantype": "贷款种类",
    "loanissuercode": "贷款转让方机构代码",
    "loanissuerareacode": "贷款合同原始发放机构所在地代码",
    "debtortype": "借款人类型",
    "jkrtype": "借款人类型",
    "debtorcode": "借款人代码",
    "jkrid": "借款人代码",
    "indutry": "行业信息",
    "industry": "行业信息",
    "economytype": "企业出资人经济成分",
    "jjcf": "企业出资人经济成分",
    "enscale": "企业规模",
    "qygm": "企业规模",
    "iouprojtype": "贷款产品类别",
    "iouindustty": "贷款实际投向",
    "grantdate": "贷款发放日期",
    "enddate": "贷款到期日期",
    "isratelock": "利率是否固定",
    "lsp": "利率水平",
    "loanstate": "贷款状态",
    "dkzt": "贷款状态",
    "ioustatus": "贷款状态",
    "ioucode": "贷款借据编码",
    "riverissuercode": "交易对手机构编码",
    "riverprojcode": "交易对手产品代码",
    "riverprojtype": "交易对手产品种类",
    "jgcode": "金融机构编码",
    "org_code": "金融机构编码",
    "sjgljg": "数据管理机构",
    "manager_org": "数据管理机构",
    "qycode": "标的企业代码",
    "targetcode": "标的企业代码",
    "qyname": "标的企业名称",
    "outcode": "股权出让方代码",
    "outname": "股权出让方名称",
    "holdrate": "持股比例",
    "incode": "内部编码",
    "innercode": "内部编码",
    "pin_mpactid": "其他股权投资内部编码",
    "investtype": "股权投资方式",
    "pactccy": "合同币种",
    "qyccy": "其他股权余额币种",
    "outtype": "投资退出方式",
    "zqtype": "债权类型",
    "djplace": "登记交易场所",
    "dengjics": "登记交易场所",
    "djcode": "登记交易场所代码",
    "dengjicscode": "登记交易场所代码",
    "danbaotype": "担保方式",
    "guarantee": "担保方式",
    "zqmoneycny": "除资产收益权外其他债权余额折人民币",
    "zqamtcny": "除资产收益权外其他债权余额折人民币",
    "sjtx": "除资产收益权外其他债权实际投向",
    "startdate": "除资产收益权外其他债权起始日期",
    "htbz": "原始合同币种",
    "htmoney": "原始合同金额",
    "htmoneycny": "原始合同金额折人民币",
    "zqbz": "除资产收益权外其他债权余额币种",
    "issuer_code": "发行机构代码",
    "infotypename": "信息类型名称",
    "projstartdate": "产品起始日期",
    "actualenddate": "产品实际终止日期",
    "sharamtcny": "期末金额折人民币",
    "debtorproj": "资产负债项目",
    "iouamtcny_tz": "贷款余额折人民币",
    "cpkj": "信托产品类型口径",
    "org_name": "机构名称",
    "qymoneycny": "其他股权余额折人民币",
    "issuerorgcode": "发行机构代码",
    "issuer_code": "发行机构代码",
    "yecny": "余额折人民币",
    "projtype": "产品类型",
    "fb00001": "表内资产余额",
    "fb00002": "表内金融资产余额",
    "field_name": "指标代码",
    "field_value": "数据值",
}


def _rows_have(rows: list[dict[str, Any]] | None, key: str) -> bool:
    return any(key in row for row in (rows or ()))


def _mapping_from_rows(*row_groups: list[dict[str, Any]] | None) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for rows in row_groups:
        for row in rows or ():
            for english in row:
                chinese = EN_TO_CN.get(str(english))
                if chinese:
                    mapping.setdefault(chinese, str(english))
    return mapping


def _specialize_mapping(zg_code: str, rows: list[dict[str, Any]] | None, mapping: dict[str, str]) -> dict[str, str]:
    specialized = dict(mapping)
    if zg_code == "ZG12":
        if _rows_have(rows, "startdate"):
            specialized["除资产收益权外其他债权起始日期"] = "startdate"
            specialized.pop("转让起始日期", None)
        if _rows_have(rows, "predate"):
            specialized["除资产收益权外其他债权预计到期日期"] = "predate"
            specialized.pop("转让预计终止日期", None)
    elif zg_code == "ZG07":
        if _rows_have(rows, "issuercode"):
            specialized["贷款合同原始发放机构代码"] = "issuercode"
            if specialized.get("基础资产出让机构代码") == "issuercode":
                specialized.pop("基础资产出让机构代码", None)
        if _rows_have(rows, "grantdate"):
            specialized["贷款发放日期"] = "grantdate"
            specialized.pop("转让起始日期", None)
        elif _rows_have(rows, "begdate"):
            specialized["贷款发放日期"] = "begdate"
            specialized.pop("转让起始日期", None)
        if _rows_have(rows, "enddate"):
            specialized["贷款到期日期"] = "enddate"
        if _rows_have(rows, "perioddate"):
            specialized["贷款展期到期日期"] = "perioddate"
            specialized.pop("转让展期到期日期", None)
        if _rows_have(rows, "ioustatus") and not _rows_have(rows, "loanstate"):
            specialized["贷款状态"] = "ioustatus"
        elif _rows_have(rows, "loanstate"):
            specialized["贷款状态"] = "loanstate"
    elif zg_code in {"ZG09", "ZG10"}:
        if _rows_have(rows, "issuercode"):
            specialized["发行机构代码"] = "issuercode"
            if specialized.get("基础资产出让机构代码") == "issuercode":
                specialized.pop("基础资产出让机构代码", None)
        if _rows_have(rows, "cpkj"):
            specialized["信托产品类型口径"] = "cpkj"
    elif zg_code == "ZG13":
        if _rows_have(rows, "begdate"):
            specialized["合同起始日期"] = "begdate"
            specialized.pop("转让起始日期", None)
        if _rows_have(rows, "predate"):
            specialized["合同预计终止日期"] = "predate"
            specialized.pop("转让预计终止日期", None)
        if _rows_have(rows, "perioddate"):
            specialized["合同展期到期日期"] = "perioddate"
            specialized.pop("转让展期到期日期", None)
        if _rows_have(rows, "pin_mpactid"):
            specialized["其他股权投资内部编码"] = "pin_mpactid"
        elif _rows_have(rows, "innercode"):
            specialized["其他股权投资内部编码"] = "innercode"
        elif _rows_have(rows, "incode"):
            specialized["其他股权投资内部编码"] = "incode"
        if _rows_have(rows, "yecny"):
            specialized["其他股权余额折人民币"] = "yecny"
            if specialized.get("余额折人民币") == "yecny":
                specialized.pop("余额折人民币", None)
    return specialized


def _alias_rows(rows: list[dict[str, Any]] | None, mapping: dict[str, str]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in rows or ():
        item = dict(row)
        for chinese, english in mapping.items():
            if english not in row:
                continue
            value = row[english]
            if chinese not in item:
                item[chinese] = value
            elif not str(item.get(chinese) or "").strip() and str(value or "").strip():
                item[chinese] = value
        # Prefer non-empty alternate English sources for the same Chinese field.
        for english, chinese in (
            ("ioustatus", "贷款状态"),
            ("dkzt", "贷款状态"),
            ("loanstate", "贷款状态"),
        ):
            if english in row and str(row.get(english) or "").strip():
                if chinese not in item or not str(item.get(chinese) or "").strip():
                    item[chinese] = row[english]
        if "地区代码" in mapping:
            english = mapping["地区代码"]
            if english in row and "地区" not in item:
                item["地区"] = row[english]
        enriched.append(item)
    return enriched


def _alias_related(
    related_rows: dict[str, list[dict[str, Any]]] | None,
) -> dict[str, list[dict[str, Any]]]:
    if not related_rows:
        return {}
    result: dict[str, list[dict[str, Any]]] = {}
    for key, rows in related_rows.items():
        mapping = _mapping_from_rows(rows)
        if key in {"PUBLIC_INFO", "公开信息"}:
            mapping.setdefault("产品代码", "projcode")
            mapping.setdefault("产品预计终止日期", "projpredate")
            mapping.setdefault("产品起始日期", "projstartdate")
        if key in {"PUBLIC_INFO", "公开信息"}:
            mapping.setdefault("产品代码", "projcode")
            mapping.setdefault("产品预计终止日期", "projpredate")
            mapping.setdefault("产品起始日期", "projstartdate")
            mapping.setdefault("发行机构代码", "issuer_code")
            mapping.setdefault("信息类型名称", "infotypename")
            mapping.setdefault("产品实际终止日期", "actualenddate")
            if any("productcode" in row for row in rows):
                mapping["产品代码"] = "productcode"
            if any("issuerorgcode" in row for row in rows):
                mapping["发行机构代码"] = "issuerorgcode"
            elif any("issuer_code" in row for row in rows):
                mapping["发行机构代码"] = "issuer_code"
        if key == "ZG01":
            mapping.setdefault("产品代码", "projcode")
            mapping.setdefault("发行机构代码", "issuercode")
            mapping.setdefault("金融机构编码", "issuercode")
        result[key] = _alias_rows(rows, mapping)
    return result


def _template_table_mappings(
    zg_code: str,
    related_rows: dict[str, list[dict[str, Any]]] | None,
) -> dict[tuple[str, str, str], str]:
    """从测试模板行推导表映射：以 _zcglxt 结尾视为口径 2，其余为口径 1（仅测试用）。"""
    mappings: dict[tuple[str, str, str], str] = {}
    for key, rows in (related_rows or {}).items():
        if "TEMPLATE" not in str(key).upper() and "模板" not in str(key):
            continue
        for row in rows or ():
            table = str(row.get("template_table") or "")
            if not table:
                continue
            scope_code = "2" if table.endswith("_zcglxt") else "1"
            mappings[("template", zg_code, scope_code)] = table
    return mappings


def _cross_table_mappings(
    zg_code: str,
    current_rows: list[dict[str, Any]],
    table_mappings: dict[tuple[str, str, str], str],
) -> dict[tuple[str, str], tuple[CrossTableMapping, ...]]:
    result: dict[tuple[str, str], tuple[CrossTableMapping, ...]] = {}
    fields = {str(field) for row in current_rows for field in row}
    for scope in ("1", "2"):
        template_table = table_mappings.get(("template", zg_code, scope))
        if not template_table:
            continue
        items: list[CrossTableMapping] = []
        for field in sorted(fields):
            lowered = field.lower()
            template_field = ""
            if zg_code == "ZG09" and lowered in {"fb00001", "fb00002"}:
                template_field = "f1" if lowered.endswith("1") else "f2"
            elif zg_code == "ZG09" and len(lowered) == 5 and lowered.startswith("g"):
                column = {"a": "A", "b": "B", "c": "C", "d": "D", "e": "E"}.get(lowered[-1], "")
                if lowered[1:4].isdigit() and column:
                    template_field = f"{column}_g{lowered[1:4]}00"
            elif zg_code == "ZG10" and lowered.startswith("h") and lowered[1:].isdigit():
                template_field = f"A_{lowered}"
            if not template_field:
                continue
            items.append(CrossTableMapping(
                mapping_code=f"{zg_code}:{scope}:{field}",
                logical_code=zg_code,
                scope_code=scope,
                automatic_detail_field_name=field,
                automatic_template_table_name=template_table,
                automatic_template_field_name=template_field,
            ))
        result[(zg_code, scope)] = tuple(items)
    return result


def run_basic_rules(
    zg_code: str,
    report_date: Any,
    current_rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]] | None = None,
    related_rows: dict[str, list[dict[str, Any]]] | None = None,
    **kwargs: Any,
):
    if kwargs.get("field_catalog") is not None:
        return _run_basic_rules(
            zg_code,
            report_date,
            current_rows,
            previous_rows or [],
            related_rows,
            **kwargs,
        )

    table_name = f"test_{zg_code.lower()}"
    mapping = _specialize_mapping(
        zg_code,
        current_rows,
        _mapping_from_rows(current_rows, previous_rows),
    )
    catalog_mapping = dict(mapping)
    if "地区代码" in catalog_mapping and "地区" not in catalog_mapping:
        catalog_mapping["地区"] = catalog_mapping["地区代码"]
    table_mappings = _template_table_mappings(zg_code, related_rows)
    catalog = TableFieldCatalog(
        {table_name: catalog_mapping},
        table_mappings=table_mappings or None,
        cross_table_mappings=_cross_table_mappings(zg_code, current_rows, table_mappings),
    )
    return _run_basic_rules(
        zg_code,
        report_date,
        _alias_rows(current_rows, catalog_mapping),
        _alias_rows(previous_rows, catalog_mapping),
        _alias_related(related_rows),
        field_catalog=catalog,
        table_name=table_name,
        **kwargs,
    )
