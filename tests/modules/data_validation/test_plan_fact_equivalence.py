from copy import deepcopy

import pytest

from auto_check.modules.data_validation.documented_choices import _covers


TEMP = {"left": "temperature", "op": "lt", "right_type": "value", "right": 5}
PRESSURE = {"left": "pressure", "op": "is_null"}


def facts(parts, logic="any"):
    return {"table": {"id": 1}, "related": None, "null": "skip", "join": None,
            "filters": set(), "filters_complete": True, "scopes": [], "scopes_complete": True,
            "parts": deepcopy(parts), "logic": logic}


@pytest.mark.parametrize("logic", ["any", "all"])
def test_commuting_complete_predicates_preserves_verified_facts(logic):
    before = facts([TEMP, PRESSURE], logic)
    after = facts([PRESSURE, TEMP], logic)
    assert _covers(after, before)


def test_commuting_partial_predicates_keeps_one_to_one_binding():
    assert _covers(facts([PRESSURE, TEMP]), facts([{"left": "temperature"}, PRESSURE]))
    assert not _covers(facts([TEMP, TEMP]), facts([{"left": "temperature"}, PRESSURE]))


@pytest.mark.parametrize("replacement", [
    {**TEMP, "op": "lte"}, {**TEMP, "right": 6}, {**TEMP, "left": "other_temperature"},
    {**TEMP, "right_type": "field", "right": "pressure", "right_table": "related"},
])
def test_reordering_does_not_hide_changed_predicates(replacement):
    assert not _covers(facts([PRESSURE, replacement]), facts([TEMP, PRESSURE]))


def test_reordering_preserves_logic_branch_count_and_multiplicity():
    assert not _covers(facts([PRESSURE, TEMP], "all"), facts([TEMP, PRESSURE], "any"))
    assert not _covers(facts([TEMP]), facts([TEMP, PRESSURE]))
    assert not _covers(facts([TEMP, PRESSURE]), facts([TEMP, TEMP]))
