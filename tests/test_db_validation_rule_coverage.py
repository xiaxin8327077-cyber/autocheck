from auto_check.db_validation.legacy_rules import ACTIVE_LEGACY_RULES
from auto_check.db_validation.rules.basic import IMPLEMENTED_RULE_IDS


def test_database_engine_covers_every_active_legacy_rule():
    expected = {rule.rule_id for rule in ACTIVE_LEGACY_RULES}
    missing = sorted(expected - IMPLEMENTED_RULE_IDS)

    assert missing == []
