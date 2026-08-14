from __future__ import annotations

from auto_check.db_validation.mapping_models import CrossTableMapping
from auto_check.db_validation.metadata import TableFieldCatalog
from auto_check.db_validation.rules.basic import _resolve, _row_text, _rule_context


def test_with_catalog_chinese_maps_to_current_english_and_ignores_stale_english():
    catalog = TableFieldCatalog(
        {
            "zg01_t": {
                "产品代码": "product_code_new",
                "地区代码": "area_code_new",
            }
        }
    )
    row = {
        "product_code_new": "P1",
        "productcode": "STALE",
        "area_code_new": "110101",
        "areacode": "999999",
    }
    with _rule_context(catalog, "zg01_t"):
        assert _resolve("产品代码") == "product_code_new"
        assert _row_text(row, "产品代码") == "P1"
        assert _row_text(row, "地区代码") == "110101"
        # 即使调用里混入旧英文，有中文时也不走英文兜底
        assert _row_text(row, "productcode", "产品代码") == "P1"


def test_without_catalog_chinese_returns_empty_no_english_fallback():
    row = {"productcode": "P1", "areacode": "110101", "产品代码": ""}
    # 无映射目录：中文解析为空，不回退写死英文
    assert _resolve("产品代码") == ""
    assert _row_text(row, "productcode", "产品代码") == ""
    assert _row_text(row, "areacode", "地区代码") == ""


def test_missing_chinese_mapping_returns_empty_even_if_stale_english_exists():
    catalog = TableFieldCatalog({"zg01_t": {"产品代码": "product_code_new"}})
    row = {"productcode": "STALE"}
    with _rule_context(catalog, "zg01_t"):
        assert _resolve("产品名称") == ""
        assert _row_text(row, "productcode", "产品名称") == ""


def test_resolve_field_accepts_unique_controlled_semantic_name_match():
    catalog = TableFieldCatalog({
        "public_information_rh": {
            "地区代码": "areacode",
            "实际终止日": "realdate",
        }
    })

    assert catalog.resolve_field("public_information_rh", "地区") == "areacode"
    assert catalog.resolve_field("public_information_rh", "产品实际终止日期") == "realdate"


def test_resolve_field_rejects_uncontrolled_partial_name_match():
    catalog = TableFieldCatalog({
        "public_information_rh": {
            "产品预计终止日": "predate",
        }
    })

    assert catalog.resolve_field("public_information_rh", "终止日") == ""


def test_cross_table_mapping_is_resolved_by_logical_code_and_scope():
    mapping = CrossTableMapping("ZG09:1:asset", "ZG09", "1", "asset", "template_1", "f1")
    catalog = TableFieldCatalog(
        by_table={},
        cross_table_mappings={("ZG09", "1"): (mapping,)},
    )

    assert catalog.cross_table_mappings_for("zg09", "1") == (mapping,)
