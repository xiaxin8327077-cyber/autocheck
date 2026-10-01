"""20260930 逐笔业务同步：原始值边界、跨期保护与真实映射执行链。"""
from datetime import date
from decimal import Decimal
import re

from openpyxl import load_workbook
import pytest

from auto_check.db_validation.engine import DbValidationEngine
from auto_check.db_validation.excel import HEADERS
from auto_check.db_validation.mapping_models import TableMapping
from auto_check.db_validation.mapping_service import DbValidationMappingService
from auto_check.db_validation.metadata import TableFieldCatalog
from auto_check.db_validation.rules.basic import (
    REQUIRED_CHINESE_FIELDS_BY_SCOPE,
    OPTIONAL_CHINESE_FIELDS_BY_SCOPE,
    run_basic_rules,
)
from tests.test_db_validation_mapping_service import (
    FakeDataClient,
    FakeMetadataClient,
    FakeStorage,
)


REPORT_DATE = date(2026, 9, 30)
YIELD_FIELDS = {
    "产品代码": "physical_product",
    "地区": "physical_region",
    "地区代码": "physical_region",
    "客户类型": "physical_client",
    "币种": "physical_currency",
    "当月年化收益率": "physical_yield",
    "期末产品金额折人民币": "physical_amount",
}
CODE_RULES = (
    ("ZG06", "资产收益权内部编码", "Zg06_Rule17", "Zg06_Rule18"),
    ("ZG07", "贷款借据编码", "Zg07_Rule19", "Zg07_Rule20"),
    ("ZG12", "除资产收益权外其他债权内部编码", "Zg12_Rule19", "Zg12_Rule20"),
)
FLAGS = (
    "科技相关产业标识", "绿色领域标识", "普惠领域标识",
    "养老产业标识", "数字经济核心产业标识",
)


def _rule_id(row):
    return re.search(r"Zg\d{2}_Rule\d+", row.rule).group()


def _run(code, current, previous=(), *, fields, related=None):
    table = f"physical_{code.lower()}"
    return run_basic_rules(
        code, REPORT_DATE, current, list(previous), related,
        field_catalog=TableFieldCatalog({table: fields}), table_name=table,
    )


def _only(rows, rule):
    return [row for row in rows if _rule_id(row) == rule]


def _yield_row(value, *, product="P1", region="", client="", currency=""):
    return {
        "physical_product": product, "physical_region": region,
        "physical_client": client, "physical_currency": currency,
        "physical_yield": value,
    }


@pytest.mark.parametrize("current,previous,expected", [
    ("12", "2", False), ("12.00001", "2", True),
    ("2", "12", False), ("1.99999", "12", True),
    ("10", "0", False), ("10.00001", "0", True),
    ("-10", "0", False), ("-10.00001", "0", True),
    ("4.5", "1", False), ("100", "89", True),
])
def test_zg04_rule15_uses_strict_absolute_difference(current, previous, expected):
    rows = _run("ZG04", [_yield_row(current)], [_yield_row(previous)], fields=YIELD_FIELDS)
    hits = _only(rows, "Zg04_Rule15")
    assert bool(hits) is expected
    if expected:
        assert hits[0].value1 == f"当月年化收益率:{float(current)}"
        assert hits[0].value2 == f"当月年化收益率上期数:{float(previous)}"
        assert "200%" not in hits[0].rule + hits[0].error
        assert "波动幅度" not in hits[0].detail


@pytest.mark.parametrize("value_type", [str, Decimal, float], ids=["string", "decimal-db", "float-db"])
@pytest.mark.parametrize("current,previous,expected", [
    ("16.01", "6.01", False), ("6.01", "16.01", False),
    ("16.01001", "6.01", True), ("6.01", "16.01001", True),
])
def test_zg04_rule15_decimal_boundary_does_not_turn_exact_ten_into_float_excess(value_type, current, previous, expected):
    rows = _run(
        "ZG04", [_yield_row(value_type(current))], [_yield_row(value_type(previous))],
        fields=YIELD_FIELDS,
    )
    assert bool(_only(rows, "Zg04_Rule15")) is expected


@pytest.mark.parametrize("current,expected", [("10", False), ("10.01", True), ("-10.01", True)])
def test_zg04_rule15_missing_previous_compares_to_zero_and_identifies_it(current, expected):
    rows = _run("ZG04", [_yield_row(current)], fields=YIELD_FIELDS)
    hits = _only(rows, "Zg04_Rule15")
    assert bool(hits) is expected
    if expected:
        assert hits[0].value2.endswith(":0.0")
        assert "未匹配上期" in " ".join(hits[0].to_excel_row())


@pytest.mark.parametrize("changed_field,changed_value", [
    ("physical_product", "P2"), ("physical_client", "2"),
    ("physical_currency", "USD"), ("physical_region", "320101"),
])
def test_zg04_rule15_keeps_the_four_business_matching_dimensions(changed_field, changed_value):
    current = _yield_row("11", client="1", currency="CNY")
    previous = _yield_row("11", client="1", currency="CNY")
    previous[changed_field] = changed_value
    hits = _only(_run("ZG04", [current], [previous], fields=YIELD_FIELDS), "Zg04_Rule15")
    assert len(hits) == 1
    assert "未匹配上期" in " ".join(hits[0].to_excel_row())


@pytest.mark.parametrize("current,previous,zero_amount,expected", [
    ("1.2", "1", True, False), ("1.20001", "1", True, True),
    ("0.8", "1", True, False), ("0.79999", "1", True, True),
    ("-1.20001", "-1", True, True), ("12", "0", True, False),
    ("12", "1", False, False),
])
def test_zg04_rule19_retains_relative_twenty_percent_and_nonzero_previous(current, previous, zero_amount, expected):
    amount_row = _yield_row("", region="000000", client="1", currency="BWB")
    amount_row["physical_amount"] = "0" if zero_amount else "100"
    rows = _run("ZG04", [_yield_row(current), amount_row], [_yield_row(previous)], fields=YIELD_FIELDS)
    hits = _only(rows, "Zg04_Rule19")
    assert bool(hits) is expected
    if expected:
        assert "20%" in hits[0].rule
        assert "波动幅度" in hits[0].detail


@pytest.mark.parametrize("previous,expected", [
    ("0", False), ("0.0000", False), (None, False), ("", False),
    (float("nan"), False), (Decimal("NaN"), False), ("nan", False),
    (float("inf"), False), (float("-inf"), False),
    (Decimal("Infinity"), False), (Decimal("-Infinity"), False),
    ("invalid", False), ("5", True), ("-3", True),
])
def test_zg04_rule17_requires_a_real_valid_nonzero_previous_yield(previous, expected):
    rows = _run("ZG04", [_yield_row("0")], [_yield_row(previous)], fields=YIELD_FIELDS)
    hits = _only(rows, "Zg04_Rule17")
    assert bool(hits) is expected
    if expected:
        assert hits[0].value1 == "当月年化收益率:0.0"
        assert hits[0].value2 == f"当月年化收益率上期数:{float(previous)}"


def test_zg04_rule17_does_not_treat_missing_previous_as_nonzero():
    assert not _only(_run("ZG04", [_yield_row("0")], fields=YIELD_FIELDS), "Zg04_Rule17")


def test_zg04_rule17_matches_product_total_without_requiring_equal_client_type():
    rows = _run(
        "ZG04", [_yield_row("0", client="1")],
        [_yield_row("4.5", client="2")], fields=YIELD_FIELDS,
    )
    hits = _only(rows, "Zg04_Rule17")
    assert len(hits) == 1
    assert hits[0].value2 == "当月年化收益率上期数:4.5"


@pytest.mark.parametrize("previous", [
    _yield_row("5", product="P2"),
    _yield_row("5", region="320101"),
    _yield_row("5", currency="CNY"),
])
def test_zg04_rule17_does_not_use_another_product_or_non_total_previous_row(previous):
    rows = _run("ZG04", [_yield_row("0")], [previous], fields=YIELD_FIELDS)
    assert not _only(rows, "Zg04_Rule17")


@pytest.mark.parametrize("region,currency,current", [("320101", "", "0"), ("", "CNY", "0"), ("", "", "1")])
def test_zg04_rule17_keeps_current_total_and_zero_conditions(region, currency, current):
    rows = _run("ZG04", [_yield_row(current, region=region, currency=currency)], [_yield_row("5")], fields=YIELD_FIELDS)
    assert not _only(rows, "Zg04_Rule17")


@pytest.mark.parametrize("current", ["invalid", None, float("nan"), Decimal("NaN"), float("inf"), Decimal("Infinity")])
def test_zg04_rule17_requires_current_to_be_a_valid_finite_zero(current):
    rows = _run("ZG04", [_yield_row(current)], [_yield_row("5")], fields=YIELD_FIELDS)
    assert not _only(rows, "Zg04_Rule17")


@pytest.mark.parametrize("previous_values", [
    ("5", "0", "invalid"), ("invalid", "0", "5"),
    ("5", "7", None, "0"), ("0", None, "7", "5"),
    ("5", "5"),
])
def test_zg04_rule17_compares_each_valid_nonzero_total_candidate_without_overwriting(previous_values):
    rows = _run("ZG04", [_yield_row("0")], [_yield_row(value) for value in previous_values], fields=YIELD_FIELDS)
    hits = _only(rows, "Zg04_Rule17")
    expected_values = {f"当月年化收益率上期数:{float(value)}" for value in previous_values if value in {"5", "7"}}
    assert {row.value2 for row in hits} == expected_values
    assert len(hits) == sum(value in {"5", "7"} for value in previous_values)
    assert all(str(len(previous_values)) in row.note and "上期" in row.note and "逐条" in row.note for row in hits)


@pytest.mark.parametrize("issuer_type", ["4", "5"])
def test_zg06_rule14_does_not_report_when_all_five_flags_are_null_or_empty(issuer_type):
    fields = {"产品代码": "physical_product", "基础资产出让机构类型": "physical_type"}
    row = {"physical_product": "P1", "physical_type": issuer_type}
    for index, flag in enumerate(FLAGS):
        fields[flag] = f"physical_flag_{index}"
        row[f"physical_flag_{index}"] = None if index % 2 else ""
    assert not _only(_run("ZG06", [row], fields=fields), "Zg06_Rule14")


@pytest.mark.parametrize("flag", FLAGS)
@pytest.mark.parametrize("value", [0, "0", " ", "1"])
def test_zg06_rule14_treats_each_filled_raw_flag_including_zero_and_space_as_filled(flag, value):
    fields = {
        "产品代码": "physical_product", "基础资产出让机构类型": "physical_type",
        flag: "physical_flag",
    }
    row = {"physical_product": "P1", "physical_type": "5", "physical_flag": value}
    assert len(_only(_run("ZG06", [row], fields=fields), "Zg06_Rule14")) == 1


@pytest.mark.parametrize("issuer_type", ["1", "2", "3"])
def test_zg06_rule14_does_not_apply_to_other_issuer_types(issuer_type):
    fields = {"产品代码": "physical_product", "基础资产出让机构类型": "physical_type", FLAGS[0]: "physical_flag"}
    row = {"physical_product": "P1", "physical_type": issuer_type, "physical_flag": "1"}
    assert not _only(_run("ZG06", [row], fields=fields), "Zg06_Rule14")


@pytest.mark.parametrize("field", ["转让预计终止日期", "转让展期到期日期"])
@pytest.mark.parametrize("value,expected", [("2089-12-31", False), ("2090-01-01", True)])
def test_zg06_rule9_retains_2090_boundary_and_removes_only_error_prefix(field, value, expected):
    fields = {"产品代码": "physical_product", "资产收益权内部编码": "physical_code", field: "physical_end"}
    rows = _run("ZG06", [{"physical_product": "P1", "physical_code": "B1", "physical_end": value}], fields=fields)
    hits = _only(rows, "Zg06_Rule9")
    assert bool(hits) is expected
    if expected:
        assert hits[0].mark.endswith("Zg06_Rule9")
        assert hits[0].rule.startswith("Zg06_Rule9:")
        assert hits[0].error == "转让预计终止日期，转让展期到期日期大于、等于2090，需核实"


@pytest.mark.parametrize("scope,field,empty_rule,duplicate_rule", CODE_RULES)
@pytest.mark.parametrize("code,expected", [
    (None, True), (float("nan"), True), (Decimal("NaN"), True), ("", True),
    (" ", False), ("None", False), ("nan", False), ("VALID1", False),
])
def test_new_code_empty_rules_preserve_raw_null_empty_space_and_literal_semantics(scope, field, empty_rule, duplicate_rule, code, expected):
    fields = {"产品代码": "physical_product", field: "physical_code"}
    rows = _run(scope, [{"physical_product": "P1", "physical_code": code}], fields=fields)
    hits = _only(rows, empty_rule)
    assert bool(hits) is expected
    assert not _only(rows, duplicate_rule)
    if expected:
        assert hits[0].mark.endswith(empty_rule)
        assert field in hits[0].detail
        assert hits[0].value1.startswith(field + ":")
        assert field in hits[0].error


@pytest.mark.parametrize("scope,field,empty_rule,duplicate_rule", CODE_RULES)
@pytest.mark.parametrize("code", ["CODE1", "", " "])
def test_new_code_duplicates_execute_without_institution_or_manager_fields(scope, field, empty_rule, duplicate_rule, code):
    fields = {"产品代码": "physical_product", field: "physical_code"}
    records = [{"physical_product": "P1", "physical_code": code} for _ in range(3)]
    rows = _run(scope, records, fields=fields)
    hits = _only(rows, duplicate_rule)
    assert hits, "三条同产品同原始编码的业务明细应真正执行查重并输出"
    assert len(hits) == len(records), "相同记录也须逐条输出，不能按结果去重折叠重复明细"
    assert all(row.mark.endswith(duplicate_rule) for row in hits)
    assert all(row.value2 == "重复次数:3" for row in hits)
    assert all(field in row.detail and field in row.error for row in hits)
    assert bool(_only(rows, empty_rule)) is (code == "")
    if code == "":
        assert len(_only(rows, empty_rule)) == len(records)


@pytest.mark.parametrize("scope,field,empty_rule,duplicate_rule", CODE_RULES)
@pytest.mark.parametrize("code", [None, float("nan"), Decimal("NaN")])
def test_new_code_null_values_do_not_form_duplicate_groups(scope, field, empty_rule, duplicate_rule, code):
    fields = {"产品代码": "physical_product", field: "physical_code"}
    records = [{"physical_product": "P1", "physical_code": code} for _ in range(2)]
    rows = _run(scope, records, fields=fields)
    assert _only(rows, empty_rule)
    assert not _only(rows, duplicate_rule)


@pytest.mark.parametrize("scope,field,empty_rule,duplicate_rule", CODE_RULES)
def test_new_code_duplicate_groups_do_not_strip_original_codes(scope, field, empty_rule, duplicate_rule):
    fields = {"产品代码": "physical_product", field: "physical_code"}
    records = [{"physical_product": "P1", "physical_code": code} for code in ("CODE1", " CODE1", "CODE1 ", "CODE2")]
    rows = _run(scope, records, fields=fields)
    assert not _only(rows, empty_rule)
    assert not _only(rows, duplicate_rule)


@pytest.mark.parametrize("scope,field,empty_rule,duplicate_rule", CODE_RULES)
@pytest.mark.parametrize("product", [None, float("nan"), Decimal("NaN")])
def test_new_code_null_products_do_not_form_duplicate_groups(scope, field, empty_rule, duplicate_rule, product):
    fields = {"产品代码": "physical_product", field: "physical_code"}
    records = [{"physical_product": product, "physical_code": "CODE1"} for _ in range(2)]
    rows = _run(scope, records, fields=fields)
    assert not _only(rows, duplicate_rule)


@pytest.mark.parametrize("loan_type", ["3", "4"])
def test_zg07_rule19_does_not_reuse_loan_type_or_original_issuer_condition(loan_type):
    fields = {
        "产品代码": "physical_product", "贷款借据编码": "physical_code",
        "贷款种类": "physical_type", "贷款合同原始发放机构代码": "physical_original_issuer",
    }
    rows = _run("ZG07", [{
        "physical_product": "P1", "physical_code": "LOAN1", "physical_type": loan_type,
        "physical_original_issuer": "",
    }], fields=fields)
    if loan_type == "4":
        assert _only(rows, "Zg07_Rule18"), "应证明原机构字段规则条件实际已触发"
    assert not _only(rows, "Zg07_Rule19")


def _refreshed_catalog(scope, *, extra_fields=None):
    table = f"business_{scope.lower()}"
    fields = {name: f"column_{index:02d}" for index, name in enumerate(sorted(REQUIRED_CHINESE_FIELDS_BY_SCOPE[scope]))}
    fields.update(extra_fields or {})
    mappings = [TableMapping("detail", scope, "", table)]
    if scope == "ZG12":
        mappings.extend([TableMapping("detail", "ZG01", "", "business_zg01"), TableMapping("detail", "ZG05", "", "business_zg05")])
    storage = FakeStorage(mappings)
    service = DbValidationMappingService(database=object())
    service.storage = storage
    metadata = FakeMetadataClient(
        tables=[{"table_name_en": table}],
        fields=[{"table": table, "chinese": name, "english": column} for name, column in fields.items()],
    )
    catalog = service.refresh(
        metadata_client=metadata, data_clients={"detail": FakeDataClient({table: list(fields.values())})},
        baseinfo_table="xt_reg_table_baseinfo", field_info_table="xt_reg_table_field_info",
        sys_manage_id="", classification_id="", signature=("20260930-offline",), source="manual",
        required_chinese_fields_by_scope={scope: REQUIRED_CHINESE_FIELDS_BY_SCOPE[scope]},
        optional_chinese_fields_by_scope={scope: OPTIONAL_CHINESE_FIELDS_BY_SCOPE.get(scope, frozenset())},
    )
    return table, fields, catalog, storage


class _EngineClient:
    """只返回显式的物理表行；上期表不会因为表名前缀意外取得当期行。"""
    class config:
        db_type = "postgresql"
        schema = "dws"

    def __init__(self, rows_by_table):
        self.rows_by_table = rows_by_table
        self.calls = []

    def fetch_all(self, sql, params=()):
        self.calls.append((sql, params))
        for table, rows in self.rows_by_table.items():
            if f'"{table}"' in sql:
                return rows
        return []


@pytest.mark.parametrize("scope,field,empty_rule,duplicate_rule", CODE_RULES)
def test_code_rules_run_through_refresh_catalog_engine_and_excel_without_institution_mapping(tmp_path, scope, field, empty_rule, duplicate_rule):
    table, fields, catalog, storage = _refreshed_catalog(scope)
    assert not [item for item in storage.saved["fields"] if item.is_required and item.mapping_status == "required_missing"]
    assert all(name not in REQUIRED_CHINESE_FIELDS_BY_SCOPE[scope] for name in ("金融机构编码", "数据管理机构", "法人金融机构名称"))
    assert "金融机构编码" not in catalog.fields_for_table(table)
    assert "数据管理机构" not in catalog.fields_for_table(table)
    raw = {column: "" for column in fields.values()}
    raw[fields["产品代码"]] = "P1"
    client = _EngineClient({table: [raw, dict(raw)]})
    result = DbValidationEngine(data_client=client, field_catalog=catalog, output_dir=tmp_path).run(
        report_date=REPORT_DATE, selected_tables=[scope],
    )
    hits = _only(result.rows, empty_rule) + _only(result.rows, duplicate_rule)
    assert {_rule_id(row) for row in hits} == {empty_rule, duplicate_rule}
    assert len(_only(result.rows, empty_rule)) == 2
    assert len(_only(result.rows, duplicate_rule)) == 2
    assert all(row.value2 == "重复次数:2" for row in _only(result.rows, duplicate_rule))
    assert "Ver.20260930" in result.excel_path.name
    assert all(field in row.detail and row.value1.startswith(field + ":") for row in hits)
    assert all(row.form == {"ZG06": "资产收益权明细信息", "ZG07": "除回购和拆借外贷款明细信息", "ZG12": "除资产收益权外其他债权明细信息"}[scope] for row in hits)
    assert all(field in row.error and "规则执行" not in row.error for row in hits)
    wb = load_workbook(result.excel_path, read_only=True, data_only=True)
    try:
        exported = list(wb.active.iter_rows(values_only=True))
        assert list(exported[0]) == HEADERS
        assert all(len(row) == 12 for row in exported)
        excel_hits = [dict(zip(HEADERS, row)) for row in exported[1:] if any(rule in str(row[9]) for rule in (empty_rule, duplicate_rule))]
        assert len(excel_hits) == len(hits)
        assert {re.search(r"Zg\d{2}_Rule\d+", row["校验规则"]).group() for row in excel_hits} == {empty_rule, duplicate_rule}
        assert all(field in row["明细数据相关信息"] and row["数据值1"].startswith(field + ":") for row in excel_hits)
        assert all(row["校验标识"].endswith(re.search(r"Zg\d{2}_Rule\d+", row["校验规则"]).group()) for row in excel_hits)
        assert all(row["数据值2"] == "重复次数:2" for row in excel_hits if duplicate_rule in row["校验规则"])
    finally:
        wb.close()


def test_zg13_removed_financial_institution_code_rules_do_not_execute_and_other_rules_still_do():
    fields = {
        "产品代码": "physical_product", "标的企业代码": "physical_target",
        "标的企业名称": "physical_name", "股权出让方代码": "physical_out",
        "股权出让方名称": "physical_out_name", "地区代码": "physical_region",
        "其他股权投资内部编码": "physical_code",
    }
    records = [{
        "physical_product": "P1", "physical_target": "91310000100019382F",
        "physical_name": "光大证券股份有限公司", "physical_out": "91310000100019382F",
        "physical_out_name": "光大证券股份有限公司", "physical_region": "320100",
        "physical_code": "EQ1",
    }]
    rows = _run("ZG13", records, fields=fields)
    assert not _only(rows, "Zg13_Rule15")
    assert not _only(rows, "Zg13_Rule16")
    assert _only(rows, "Zg13_Rule1")


@pytest.mark.parametrize("zg05_balance,zg12_balance,expected", [
    ("0.1", "0", False), ("0.10001", "0", True),
    ("0", "0.1", False), ("0", "0.10001", True),
    ("100", "100.05", False), ("100", "101", True), ("101", "100", True),
])
def test_zg12_rule16_retains_both_difference_directions_and_strict_tenth_boundary(zg05_balance, zg12_balance, expected):
    rows = _run("ZG12", [{"physical_product": "P1", "physical_balance": zg12_balance}], fields={
        "产品代码": "physical_product", "除资产收益权外其他债权余额折人民币": "physical_balance",
    }, related={"ZG05": [{"产品代码": "P1", "币种": "BWB", "AD200_除资产收益权外其他债权": zg05_balance}]})
    assert bool(_only(rows, "Zg12_Rule16")) is expected


def test_empty_zg12_still_checks_zg05_ad200_in_the_formal_engine(tmp_path):
    catalog = TableFieldCatalog({
        "business_zg12": {"产品代码": "product_id", "除资产收益权外其他债权余额折人民币": "debt_balance"},
        "business_zg05": {"产品代码": "product_id", "币种": "currency_id", "AD200_除资产收益权外其他债权": "amount_ad200"},
    }, table_mappings={
        ("detail", "ZG12", ""): "business_zg12", ("detail", "ZG01", ""): "business_zg01",
        ("detail", "ZG05", ""): "business_zg05",
    })
    client = _EngineClient({"business_zg12": [], "business_zg05": [{"product_id": "P1", "currency_id": "BWB", "amount_ad200": "100"}]})
    result = DbValidationEngine(data_client=client, field_catalog=catalog, output_dir=tmp_path).run(report_date=REPORT_DATE, selected_tables=["ZG12"])
    hits = _only(result.rows, "Zg12_Rule16")
    assert len(hits) == 1
    assert hits[0].value1.endswith(":0.0")
    assert hits[0].value2.endswith(":100.0")
    assert any("ZG12 当期表无数据" in message for message in result.warnings)


def test_formal_engine_result_filename_identifies_the_20260930_rule_version(tmp_path):
    catalog = TableFieldCatalog({}, table_mappings={("detail", "ZG06", ""): "business_zg06"})
    result = DbValidationEngine(data_client=_EngineClient({}), field_catalog=catalog, output_dir=tmp_path).run(
        report_date=REPORT_DATE, selected_tables=["ZG06"],
    )
    assert "Ver.20260930" in result.excel_path.name
