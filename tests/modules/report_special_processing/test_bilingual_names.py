"""bilingual_names 规范串解析/序列化/摘要测试。"""

from __future__ import annotations

import pytest

from auto_check.modules.report_special_processing.bilingual_names import (
    BilingualNameError,
    bilingual_summary,
    flatten_bilingual_groups,
    is_canonical_bilingual,
    normalize_bilingual_value,
    parse_bilingual_groups,
    parse_bilingual_items,
    serialize_bilingual_groups,
    serialize_bilingual_items,
    shortest_bilingual_summary,
)


def test_parse_single_and_multiple_items():
    assert parse_bilingual_items("资产表｜fa_balance") == (("资产表", "fa_balance"),)
    assert parse_bilingual_items("资产表｜fa_balance；估值表｜valuation") == (
        ("资产表", "fa_balance"),
        ("估值表", "valuation"),
    )


def test_parse_strips_whitespace_and_empty_returns_empty():
    assert parse_bilingual_items("  中文｜en ； 甲｜乙 ") == (("中文", "en"), ("甲", "乙"))
    assert parse_bilingual_items("") == ()
    assert parse_bilingual_items(None) == ()


@pytest.mark.parametrize(
    "value",
    [
        "只有中文",  # 缺英文名与分隔符
        "｜en",  # 缺中文
        "zh｜",  # 缺英文
        "zh｜a｜b",  # 多余部分分隔符
        "zh｜en；",  # 空尾项
        "zh｜en；；zh2｜en2",  # 连续分隔符
        "；",
        "zh｜en；zh｜en2｜x",  # 项内含额外｜
        "甲" * 101 + "｜en",  # 中文名超长
        "zh｜" + "e" * 101,  # 英文名超长
        "zh｜en" + "；zh｜en" * 5,  # 超过 5 项
        "x" * 4097,  # 总长超限
    ],
)
def test_parse_rejects_invalid(value):
    with pytest.raises(BilingualNameError):
        parse_bilingual_items(value)


def test_parse_accepts_at_most_five_items():
    value = "；".join(f"字段{i}｜field_{i}" for i in range(5))
    assert len(parse_bilingual_items(value)) == 5


def test_is_canonical():
    assert is_canonical_bilingual("资产表｜fa_balance")
    assert not is_canonical_bilingual("t_asset")
    assert not is_canonical_bilingual("")


def test_serialize_roundtrip():
    items = [("资产表", "fa_balance"), ("估值表", "valuation")]
    assert serialize_bilingual_items(items) == "资产表｜fa_balance；估值表｜valuation"
    assert parse_bilingual_items(serialize_bilingual_items(items)) == tuple(items)
    assert serialize_bilingual_items([("甲", "a"), ("  ", "  "), ("乙", "b")]) == "甲｜a；乙｜b"


def test_normalize_only_affects_canonical_values():
    assert normalize_bilingual_value(" 资产表｜ fa_balance ") == "资产表｜fa_balance"
    assert normalize_bilingual_value("legacy_value") == "legacy_value"


def test_bilingual_summary():
    assert bilingual_summary("资产表｜fa_balance") == "资产表"
    assert bilingual_summary("资产表｜fa_balance；估值表｜valuation", which="字段") == "资产表 等 2 字段"
    assert bilingual_summary("legacy") == "legacy"
    assert bilingual_summary("") == ""
    assert bilingual_summary(None) == ""


def test_shortest_bilingual_summary_keeps_total_field_count():
    assert shortest_bilingual_summary(
        "法人金融机构名称｜jrname；短字段｜short_col；；数据管理机构｜datejg"
    ) == "短字段 等 3 字段"
    assert shortest_bilingual_summary("余额字段｜balance") == "余额字段"
    assert shortest_bilingual_summary("long_legacy_field、short") == "short 等 2 字段"


# ===== 分组格式（表→字段关联，组间“；；”） =====


def test_parse_groups_flat_value_as_single_group():
    assert parse_bilingual_groups("金额｜amt；数量｜qty") == ((("金额", "amt"), ("数量", "qty")),)
    assert parse_bilingual_groups("") == ()
    assert parse_bilingual_groups(None) == ()


def test_parse_groups_grouped_value_with_empty_group():
    groups = parse_bilingual_groups("金额｜amt；数量｜qty；；汇率｜rate")
    assert groups == (
        (("金额", "amt"), ("数量", "qty")),
        (("汇率", "rate"),),
    )
    assert serialize_bilingual_groups(groups) == "金额｜amt；数量｜qty；；汇率｜rate"
    # 空组（该表暂无关联字段）保留占位
    with_empty = parse_bilingual_groups("金额｜amt；；；；汇率｜rate")
    assert with_empty == ((("金额", "amt"),), (), (("汇率", "rate"),))
    assert serialize_bilingual_groups(with_empty) == "金额｜amt；；；；汇率｜rate"


@pytest.mark.parametrize(
    "value",
    [
        "金额｜amt；；只有中文",  # 组内非法
        "；；",  # 所有组均为空
    ],
)
def test_parse_groups_rejects_invalid(value):
    with pytest.raises(BilingualNameError):
        parse_bilingual_groups(value)


def test_parse_groups_rejects_too_many_groups():
    value = "；；".join(f"字段{i}｜f{i}" for i in range(6))
    with pytest.raises(BilingualNameError):
        parse_bilingual_groups(value)


def test_parse_groups_rejects_overlong_total():
    value = "；；".join(["甲" * 2100 + "｜en", "乙" * 2100 + "｜en"])
    with pytest.raises(BilingualNameError):
        parse_bilingual_groups(value)


def test_flatten_and_summary_for_groups():
    groups = parse_bilingual_groups("金额｜amt；；汇率｜rate；利率｜ir")
    assert flatten_bilingual_groups(groups) == (("金额", "amt"), ("汇率", "rate"), ("利率", "ir"))
    assert bilingual_summary("金额｜amt；；汇率｜rate；利率｜ir", which="字段") == "金额 等 3 字段"
    assert bilingual_summary("金额｜amt；；legacy坏值") == "金额｜amt；；legacy坏值"


def test_normalize_grouped_value():
    assert normalize_bilingual_value(" 金额｜ amt ；； ") == "金额｜amt；；"
    assert normalize_bilingual_value("legacy；；x") == "legacy；；x"
