import pytest

from auto_check.db_validation.legacy_rules import (
    ACTIVE_LEGACY_RULES,
    EXECUTABLE_LEGACY_RULE_IDS,
    LEGACY_RULE_IDS,
)
from auto_check.db_validation.rules.basic import IMPLEMENTED_RULE_IDS


def test_database_engine_covers_every_active_legacy_rule():
    expected = {rule.rule_id for rule in ACTIVE_LEGACY_RULES}
    missing = sorted(expected - IMPLEMENTED_RULE_IDS)

    assert missing == []


@pytest.mark.parametrize(
    ("rule_id", "encoding", "condition"),
    [
        ("Zg06_Rule17", "资产收益权内部编码", "为空"),
        ("Zg06_Rule18", "资产收益权内部编码", "不唯一"),
        ("Zg07_Rule19", "贷款借据编码", "为空"),
        ("Zg07_Rule20", "贷款借据编码", "不唯一"),
        ("Zg12_Rule19", "除资产收益权外其他债权内部编码", "为空"),
        ("Zg12_Rule20", "除资产收益权外其他债权内部编码", "不唯一"),
    ],
)
def test_20260930_encoding_rules_are_registered_for_execution(rule_id, encoding, condition):
    rules = {rule.rule_id: rule for rule in ACTIVE_LEGACY_RULES}

    assert rule_id in EXECUTABLE_LEGACY_RULE_IDS
    assert encoding + condition in rules[rule_id].rule_text
    assert rules[rule_id].category == "逐笔数据校验"


@pytest.mark.parametrize("rule_id", ["Zg13_Rule15", "Zg13_Rule16"])
def test_20260930_retired_zg13_rules_are_absent_from_current_catalog(rule_id):
    assert rule_id not in LEGACY_RULE_IDS
    assert rule_id not in EXECUTABLE_LEGACY_RULE_IDS


def test_20260930_catalog_describes_absolute_yield_change_and_valid_previous_yield():
    rules = {rule.rule_id: rule for rule in ACTIVE_LEGACY_RULES}

    assert "绝对值超过10" in rules["Zg04_Rule15"].rule_text
    assert "200%" not in rules["Zg04_Rule15"].rule_text
    assert "上期" in rules["Zg04_Rule17"].rule_text
    assert "不等于0" in rules["Zg04_Rule17"].rule_text
    assert "当月年化收益率为0" in rules["Zg04_Rule17"].rule_text
    assert "20%" in rules["Zg04_Rule19"].rule_text
