from copy import deepcopy
import json
import sqlite3
import time

import pytest

from auto_check.modules.data_validation.contracts import AppError
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request
from tests.modules.data_validation.test_compared_grain_evidence import compared_sources, KEY
from tests.modules.data_validation.test_supplement_adoption import analyze_suggestion


def period_request(*, two_scopes=False, second_threshold=None, child_scope=None, joined=False, applicability=None,
                   parent_filters=True, extra_references=(), configured_facts=(), metric_first=False):
    rules, parent = analyze_suggestion()
    candidate = parent["candidate_options"][int(joined)]["candidate"]
    if not parent_filters:
        candidate["semantic_intent"].update(scopes=[], dictionary_snapshots={})
        definition = {**candidate["preview"]["definition"], "semantic_intent": candidate["semantic_intent"], "filters": []}
        candidate["preview"] = rules.preview_candidate(user(), {"definition": definition})
    previews = [candidate["preview"]]
    if two_scopes or second_threshold is not None:
        other = deepcopy(candidate)
        intent = other["semantic_intent"]
        if two_scopes:
            intent["scopes"][0].update(category="终止", memberships={"transfer_flag": {"include": ["2"], "exclude": ["1"]}})
            other["filters"][0]["value"] = "2"
        if second_threshold is not None:
            other["expression"]["right"] = second_threshold
            intent["expected_expression"] = deepcopy(other["expression"])
        d = {**other["preview"]["definition"], "semantic_intent": intent, "filters": other["filters"],
             "expression":other["expression"]}
        other["preview"] = rules.preview_candidate(user(), {"definition": d})
        previews.append(other["preview"])
        parent["candidate_options"].append({"candidate": other, "id": "ended", "recommended": False})
    # A completed analysis and an actual preview supply the trusted parent facts.
    parent["ai_suggestions"] = [{"id": "opening-check", "category": "period", "adoption": {"operations": []},
                                 "references": [{"table_name": "project_snapshot", "field_name": "project_received"}]}]
    if applicability:
        parent["ai_suggestions"][0]["applicability_filters"] = applicability
    if joined:
        parent["ai_suggestions"][0]["references"] = [{"table_name": candidate["table_name"],
                                                   "field_name": candidate["expression"]["left"]}]
    references = parent["ai_suggestions"][0]["references"]
    if metric_first:
        references.extend(extra_references)
    else:
        references[:0] = extra_references
    args = _request(request_text=parent["analysis_request_text"], analysis_protocol=2)
    if configured_facts:
        from auto_check.modules.data_validation.adoption_scope import attach_period_applicability
        inputs = rules._analysis_inputs(user(), args)
        source_id = parent["source_id"]
        settings = "\n".join("PERIOD_APPLICABILITY " + json.dumps({**fact, "source_id": source_id}) for fact in configured_facts)
        attach_period_applicability(parent["ai_suggestions"], settings, source_id, inputs["tables"], inputs["fields_by_table"])
    job = rules.analyses.start(user(), args, worker=lambda *_: parent)
    for _ in range(100):
        if rules.analyses.completed_result(user(), job["analysis_id"]):
            break
        time.sleep(.01)
    draft = deepcopy(rules.model.payloads[0]["plans"][0]["draft"])
    draft.pop("ai_suggestions", None)
    draft["semantic_intent"]["scopes"] = []
    if child_scope:
        draft["semantic_intent"]["scopes"] = [{"table": "base", "category": "期间分类", "fields": ["transfer_flag"],
                                              "memberships": {"transfer_flag": {"include": [child_scope],
                                                                              "exclude": ["1" if child_scope=="2" else "2"]}}}]
    rules.model.payloads += [{"target": {"table": "project_snapshot"}, "draft": draft}, draft, {"ai_suggestions": []}]
    context = {"parent_analysis_id": job["analysis_id"], "parent_context": parent["analysis_context"],
               "suggestion_id": "opening-check",
               "parents": [{"definition": p["definition"], "hash": p["content_sha256"]} for p in previews]}
    return rules, _request(request_text="期初实收不得小于0", analysis_protocol=2, adoption_context=context)


def test_period_scope_survives_omission_and_revalidation():
    rules, request = period_request()
    child = rules.parse_rule_request(user(), request)
    preview = child["preview"]
    definition = preview["definition"]
    expected = [{"table": "base", "field": "transfer_flag", "op": "eq", "value": "1", "confirmed": True}]
    assert definition["filters"] == definition["semantic_intent"]["explicit_filters"] == expected
    assert 'transfer_flag' in preview["sql_preview"]
    assert rules.test_candidate(user(), {"definition": definition, "expected_hash": preview["content_sha256"],
                                         "cases": preview["cases"]})["failed_count"] == 0
    tampered = deepcopy(definition)
    tampered["filters"] = []
    with pytest.raises(AppError):
        rules.preview_candidate(user(), {"definition": tampered})


def test_period_scope_rejects_foreign_or_forged_parent_evidence():
    rules, request = period_request()
    context = request["adoption_context"]
    context["parents"][0]["hash"] = "bad"
    with pytest.raises(AppError, match="ANALYSIS_CONTEXT_CHANGED"):
        rules.parse_rule_request(user(), request)
    with pytest.raises(AppError, match="ANALYSIS_CONTEXT_CHANGED"):
        rules.parse_rule_request({**user(), "id":"another-owner"}, request)


def test_distinct_confirmed_scopes_produce_independent_candidates():
    rules, request = period_request(two_scopes=True)
    p = request["adoption_context"]["parents"]
    p.append(deepcopy(p[0]))
    child = rules.parse_rule_request(user(), request)
    groups = [o["candidate"]["preview"]["definition"]["filters"] for o in child["candidate_options"]]
    assert sorted([f["value"] for f in group] for group in groups) == [["1"], ["2"]]


def test_conflict_with_a_confirmed_scope_requests_a_decision():
    rules, request = period_request(child_scope="2")
    child = rules.parse_rule_request(user(), request)
    assert not child.get("preview")
    assert any("范围" in question and "transfer_flag" in question for question in child["uncertainties"])


def test_child_cannot_silently_intersect_different_parent_dimensions():
    from auto_check.modules.data_validation.adoption_scope import bind_period_filters, verify_bound_period_filters
    from auto_check.modules.data_validation.documented_choices import ScopeEvidenceRequired
    def condition(field, owner):
        return {"table": owner, "field": field, "op": "eq", "value": "1", "confirmed": True}
    groups = [[condition("current_category", "entries")], [condition("original_category", "entries")]]
    scope = {"table": "entries", "fields": ["opening_value"], "groups": groups}
    # The generated check already names the first parent branch.
    draft = {"expression": {"left": "opening_value", "op": "is_null"},
             "filters": [condition("current_category", "base"), condition("new_this_period", "base")]}
    other = bind_period_filters(draft, "entries", None, scope, groups[1])
    with pytest.raises(ScopeEvidenceRequired, match="current_category"):
        verify_bound_period_filters({**draft, "table_name": "entries"}, other, groups)


def test_identical_child_request_has_a_separate_cache_key_for_each_parent_scope():
    from auto_check.modules.data_validation.adoption_scope import verified_period_scope
    rules, request = period_request(two_scopes=True)
    one, two = request["adoption_context"]["parents"]
    request["adoption_context"]["parents"] = [one]
    first = rules.parse_rule_request(user(), request)
    def cache_context():
        scope = verified_period_scope(rules, user(), request)
        return rules._analysis_inputs(user(), request, period_scope=scope)["context"]
    key = cache_context()
    cached = rules.storage.cached_analysis_result(key, request["request_text"])
    assert cached and not cached["draft"].get("filters")
    assert first["preview"]["definition"]["filters"][0]["value"] == "1"
    request["adoption_context"]["parents"] = [two]
    other = cache_context()
    assert other != key and rules.storage.cached_analysis_result(other, request["request_text"]) is None


@pytest.mark.parametrize(("conditions", "policy"), [
    ([{"op": "is_null"}, {"op": "gt", "right_type": "value", "right": 10}], "review"),
    ([{"op": "lt", "right_type": "value", "right": 0}, {"op": "gt", "right_type": "value", "right": 5}], "skip"),
])
def test_original_condition_templates_replace_a_truncated_period_check(conditions, policy):
    from auto_check.modules.data_validation.adoption_scope import period_check, apply_period_check
    cols = [{"column_name": n, "data_type": "numeric", "comment": n} for n in ["current", "opening"]]
    original = {"expression": {"logic": "any", "conditions": [dict(left="current", **p) for p in conditions]},
                "null_policy": policy, "equality_policy": "allow_equal"}
    check = period_check(original, cols, "opening")
    draft = {"expression": {"left": "opening", "op": "is_null"}, "semantic_intent": {"scopes": [], "metrics": []}}
    apply_period_check(draft, check, "opening", "期初值")
    assert draft["expression"] == {"logic": "any", "conditions": [dict(left="opening", **p) for p in conditions]}
    assert draft["null_policy"] == policy and draft["equality_policy"] == "allow_equal"
    assert "current" not in str(draft["semantic_intent"]["metrics"])


def test_adoption_only_analysis_does_not_generate_or_return_further_suggestions():
    rules, request = period_request()
    before = len(rules.model.calls)
    ordinary = rules._analysis_inputs(user(), request)["context"]
    request["include_suggestions"] = False
    child = rules.parse_rule_request(user(), request)
    assert child["preview"] and child["ai_suggestions"] == []
    assert child["include_suggestions"] is False and rules._analysis_inputs(user(), request)["context"] != ordinary
    prompts = [c["messages"][0]["content"] for c in rules.model.calls[before:]]
    assert all("主规则阶段的待审建议" not in p for p in prompts)
    parent = rules.analyses.completed_result(user(), request["adoption_context"]["parent_analysis_id"])
    assert parent["ai_suggestions"][0]["id"] == "opening-check"


def test_explicitly_selected_condition_uses_same_scope_and_pattern_once():
    rules, request = period_request(two_scopes=True)
    base, other = request["adoption_context"]["parents"]
    request["adoption_context"].update(inherit_check=True, parents=[base, deepcopy(base), other])
    request["include_suggestions"] = False
    for response in rules.model.payloads[2:4]:
        d = response.get("draft", response)
        d["expression"] = {"left":"project_received","op":"is_null"}
        d["null_policy"] = "violate"
    result = rules.parse_rule_request(user(), request)
    definitions = [o["candidate"]["preview"]["definition"] for o in result["candidate_options"]]
    assert len(definitions) == 2 and {d["filters"][0]["value"] for d in definitions} == {"1","2"}
    assert all(d["expression"] == {"left":"project_received","op":"lt","right_type":"value","right":0} for d in definitions)
    assert all(d["null_policy"] == "zero" for d in definitions)
    assert result["ai_suggestions"] == []


def test_unsupported_period_inheritance_keeps_independent_analysis_available():
    from auto_check.modules.data_validation.adoption_scope import period_check
    cols = [{"column_name": n, "data_type": t} for n,t in [("current","numeric"),("opening","numeric"),("name","varchar")]]
    def check(expression, field="opening"):
        return period_check({"expression":expression,"null_policy":"skip","equality_policy":"allow_equal"}, cols, field)
    assert check({"left":"current","op":"gt","right_type":"field","right":"opening"}) is None
    assert check({"left":"current","op":"gt","right_type":"value","right":5}, "name") is None
    assert check({"left_type":"formula","left":{"field":"current"},"op":"gt","right_type":"value","right":5}) is None
    assert check({"logic":"all","conditions":[{"left":"current","op":"is_null"},{"left":"opening","op":"is_null"}]}) is None


def test_child_can_choose_independent_condition_and_suppress_further_suggestions():
    rules, request = period_request()
    request["include_suggestions"] = False
    for response in rules.model.payloads[2:4]:
        d = response.get("draft", response)
        d["expression"] = {"left":"project_received","op":"is_null"}
        d["null_policy"] = "violate"
    result = rules.parse_rule_request(user(), request)
    assert result["preview"]["definition"]["expression"] == {"left":"project_received","op":"is_null"}
    assert result["ai_suggestions"] == []


@pytest.mark.parametrize("different_scope", [False, True])
def test_selected_templates_stay_paired_with_their_own_filters(different_scope):
    rules, request = period_request(two_scopes=different_scope, second_threshold=7)
    request["include_suggestions"] = False
    request["adoption_context"]["inherit_check"] = True
    result = rules.parse_rule_request(user(), request)
    pairs = [(o["candidate"]["expression"]["right"], o["candidate"]["filters"][0]["value"])
             for o in result["candidate_options"]]
    assert sorted(pairs) == [(0, "1"), (7, "2" if different_scope else "1")]

@pytest.mark.parametrize("exact", [False, True])
def test_joined_parent_preview_cannot_be_reduced_to_a_single_table_scope(exact):
    rules, request = period_request(joined=True)
    context = request["adoption_context"]
    parent = context["parents"][0]
    assert parent["definition"]["join"]["unmatched_policy"] == "exclude"
    assert parent["hash"] == rules.preview_candidate(user(), {"definition": parent["definition"]})["content_sha256"]
    context["inherit_check"] = exact
    with pytest.raises(AppError, match="VALIDATION_ERROR"):
        rules.parse_rule_request(user(), request)

def test_configured_period_facts_belong_to_a_documented_source_table_and_metric():
    from auto_check.modules.data_validation.adoption_scope import attach_period_applicability
    item = {"category": "period", "adoption": {"operations": []}, "references": [
        {"table_name": "orders", "field_name": "opening"}]}
    tables = [{"id": 7, "table_name": "orders"}]
    fields = {7: [{"field_name": "opening", "data_type": "decimal"},
                  {"field_name": "is_first", "data_type": "varchar", "dictionary": "A-是\nB-否"}]}
    fact = {"source_id": "src", "table": "orders", "field": "opening",
            "filters": [{"field": "is_first", "op": "eq", "value": "A"}]}
    def apply(f, source="src", target=item):
        return attach_period_applicability([deepcopy(target)], "PERIOD_APPLICABILITY " + json.dumps(f),
                                            source, tables, fields)[0]
    assert apply(fact)["applicability_filters"] == [
        {"table": "orders", "field": "is_first", "op": "eq", "value": "A", "confirmed": True}]
    assert "applicability_filters" not in apply(fact, "other")
    assert "applicability_filters" not in apply({**fact, "field": "closing"})
    assert "applicability_filters" not in apply(fact, target={**item, "category": "consistency"})
    for invalid in ("X", 1):
        rejected = apply({**fact, "filters": [{"field": "is_first", "op": "eq", "value": invalid}]})
        assert "adoption" not in rejected and rejected["limitations"]


def test_owned_period_applicability_is_still_bound_when_child_omits_it():
    applicability = [{"table": "project_snapshot", "field": "project_received", "op": "gte",
                      "value": 0, "confirmed": True}]
    rules, request = period_request(applicability=applicability)
    request["adoption_context"]["inherit_check"] = True
    child = rules.parse_rule_request(user(), request)
    filters = child["preview"]["definition"]["filters"]
    assert {f["field"] for f in filters} == {"project_received", "transfer_flag"}
    assert {**applicability[0], "table": "base"} in filters
    assert child["preview"]["definition"]["semantic_intent"]["explicit_filters"] == filters

def test_configured_period_filter_contradicting_a_parent_scope_requires_a_decision():
    rules, request = period_request(applicability=[{
        "table": "project_snapshot", "field": "transfer_flag", "op": "eq", "value": "2", "confirmed": True}])
    child = rules.parse_rule_request(user(), request)
    assert not child.get("preview") and "transfer_flag" in str(child["uncertainties"])

def test_independent_period_suggestion_binds_its_own_filters_with_a_joined_parent():
    fact = {"table": "funding_rows", "field": "funding_received", "op": "neq", "value": -2, "confirmed": True}
    rules, request = period_request(joined=True, applicability=[fact])
    context = request["adoption_context"]
    assert context.pop("parents")[0]["definition"]["join"]
    context["mode"] = "suggestion_only"
    request["include_suggestions"] = False
    proposal = deepcopy(rules.model.payloads[0]["plans"][1])
    proposal["draft"]["semantic_intent"]["scopes"] = []
    rules.model.payloads[-3:] = [proposal, proposal["draft"]]
    child = rules.parse_rule_request(user(), request)
    preview = child["preview"]
    assert preview["definition"]["filters"] == [{**fact, "table": "base"}]
    with sqlite3.connect(":memory:") as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE project_snapshot (day, project_key, project_name, transfer_flag, project_received)")
        conn.execute("CREATE TABLE funding_rows (day, funding_id, funding_owner, funding_received)")
        day = "2026-11-20"
        conn.executemany("INSERT INTO project_snapshot VALUES (?, ?, ?, '2', 0)", [(day, k, k) for k in ("eligible", "ineligible")])
        conn.executemany("INSERT INTO funding_rows VALUES (?, ?, ?, ?)", [(day, 1, "eligible", -1), (day, 2, "ineligible", -2)])
        rows = conn.execute(preview["sql_preview"], {**preview["sql_params"], "report_date": day}).fetchall()
        assert [r["TCMP编号"] for r in rows] == ["eligible"]

def test_suggestion_only_does_not_publish_an_unbound_owning_table():
    fact = {"table": "funding_rows", "field": "funding_received", "op": "neq", "value": -2, "confirmed": True}
    rules, request = period_request(joined=True, applicability=[fact])
    context = request["adoption_context"]
    context.pop("parents")
    context["mode"] = "suggestion_only"
    child = rules.parse_rule_request(user(), request)
    assert not child.get("preview") and "文档字段不一致" in str(child["uncertainties"])


@pytest.mark.parametrize("parent_filters", [False, True])
def test_adopted_period_preserves_parent_join_scope_and_predicate(parent_filters):
    rules, request = period_request(joined=True, parent_filters=parent_filters)
    request["include_suggestions"] = False
    request["adoption_context"]["mode"] = "inherit_selected"
    draft = deepcopy(rules.model.payloads[0]["plans"][1]["draft"])
    draft.pop("join")
    draft["expression"] = {"left": "funding_received", "op": "is_null"}
    draft["semantic_intent"]["scopes"] = []
    rules.model.payloads[-3:] = [{"target": {"table": "funding_rows"}, "draft": draft}, draft]

    preview = rules.parse_rule_request(user(), request)["preview"]
    definition = preview["definition"]
    assert definition["join"] == {
        "table_name": "project_snapshot", "on": [{"left": "funding_owner", "right": "project_key"}],
        "report_date_field": "day", "relationship_confirmed": True, "unmatched_policy": "exclude",
    }
    assert definition["expression"] == {"left": "funding_received", "op": "lt", "right_type": "value", "right": 0}
    expected = [{"table": "related", "field": "transfer_flag", "op": "eq", "value": "1", "confirmed": True}]
    assert definition["filters"] == (expected if parent_filters else [])
    assert definition["description"] == request["request_text"]
    assert definition["name"] == "募集实收小于0"


def test_adopted_period_distinguishes_names_for_distinct_scopes_only():
    rules, request = period_request(two_scopes=True)
    context = request["adoption_context"]
    context["mode"] = "inherit_selected"
    context["parents"].append(deepcopy(context["parents"][0]))
    request["include_suggestions"] = False

    options = rules.parse_rule_request(user(), request)["candidate_options"]
    assert len(options) == 2
    assert {option["label"] for option in options} == {"项目实收小于0（项目状态：存续）", "项目实收小于0（项目状态：终止）"}
    assert {option["candidate"]["preview"]["definition"]["name"] for option in options} == {option["label"] for option in options}


def sum_adoption_request(*, both_parents=False, extra_references=()):
    rules, parent = analyze_suggestion()
    [suggestion] = parent["ai_suggestions"]
    suggestion["references"] += list(extra_references)
    args = _request(request_text=parent["analysis_request_text"], analysis_protocol=2)
    job = rules.analyses.start(user(), args, worker=lambda *_: parent)
    for _ in range(100):
        if rules.analyses.completed_result(user(), job["analysis_id"]):
            break
        time.sleep(.01)
    parents = parent["candidate_options"] if both_parents else parent["candidate_options"][1:]
    receipts = [p["candidate"]["preview"] for p in parents]
    _, model, _ = compared_sources(shared_alias=True, join_keys=[KEY])
    rules.model.payloads.append(deepcopy(model.payloads[0]))
    request = _request(request_text=suggestion["title"], analysis_protocol=2, include_suggestions=False,
                       adoption_context={"mode": "inherit_selected", "parent_analysis_id": job["analysis_id"],
                                         "parent_context": parent["analysis_context"], "suggestion_id": suggestion["id"],
                                         "parents": [{"definition": p["definition"], "hash": p["content_sha256"]} for p in receipts]})
    return rules, request


def test_adopted_sum_keeps_scope_from_reverse_parent_join():
    rules, request = sum_adoption_request()

    preview = rules.parse_rule_request(user(), request)["preview"]
    definition = preview["definition"]
    assert definition["join"]["right_aggregate"] == "sum"
    assert definition["join"]["unmatched_policy"] == "exclude"
    assert definition["expression"] == {"left": "project_received", "op": "neq", "right_type": "field",
                                       "right": "funding_received", "right_table": "related"}
    assert definition["filters"] == [{"table": "base", "field": "transfer_flag", "op": "eq", "value": "1", "confirmed": True}]
    tampered = {**definition, "join": {**definition["join"], "unmatched_policy": "review"}}
    with pytest.raises(AppError, match="VALIDATION_ERROR"):
        rules.preview_candidate(user(), {"definition": tampered})
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE project_snapshot (day, project_key, project_name, transfer_flag, project_received)")
        db.execute("CREATE TABLE funding_rows (day, funding_id, funding_owner, funding_received)")
        day = "2026-11-20"
        db.executemany("INSERT INTO project_snapshot VALUES (?, ?, ?, ?, ?)", [
            (day, "A", "存续不一致", "1", 10), (day, "B", "终止不一致", "2", 20),
            (day, "C", "存续缺同日明细", "1", 30), (day, "D", "存续一致", "1", 9),
        ])
        db.executemany("INSERT INTO funding_rows VALUES (?, ?, ?, ?)", [
            (day, 1, "A", 4), (day, 2, "A", 5), (day, 3, "B", 19),
            ("2026-11-19", 4, "C", 29), (day, 5, "D", 4), (day, 6, "D", 5),
        ])
        rows = db.execute(preview["sql_preview"], {**preview["sql_params"], "report_date": day}).fetchall()
        assert [row["TCMP编号"] for row in rows] == ["A"]


@pytest.mark.parametrize("policies", [("zero", "review"), ("review", "zero")])
def test_adopted_sum_keeps_distinct_null_policies(policies):
    rules, request = sum_adoption_request()
    proposal = rules.model.payloads[-1]
    targets = {key: proposal[key] for key in ("target", "related_target")}
    rules.model.payloads[-1] = {**targets, "plan_mode": "alternatives", "plans": [
        {**targets, **deepcopy(proposal["draft"]), "null_policy": policy} for policy in policies]}

    options = rules.parse_rule_request(user(), request)["candidate_options"]
    assert len({option["id"] for option in options}) == 2
    assert {o["candidate"]["preview"]["definition"]["null_policy"] for o in options} == {"zero", "review"}
    assert {o["label"].split("（")[-1] for o in options} == {"空值按0）", "空值待核查）"}


def test_adopted_sum_names_distinct_missing_record_scopes():
    rules, request = sum_adoption_request(both_parents=True)

    options = rules.parse_rule_request(user(), request)["candidate_options"]
    names = {o["candidate"]["preview"]["definition"]["join"]["unmatched_policy"]: o["label"] for o in options}
    assert set(names) == {"exclude", "review"}
    assert "仅核查有同日关联的记录" in names["exclude"]
    assert "缺同日关联记录待核查" in names["review"]
    assert {o["candidate"]["preview"]["definition"]["name"] for o in options} == set(names.values())


def test_adopted_sum_accepts_relationship_and_scope_evidence_in_suggestion_references():
    rules, request = sum_adoption_request(extra_references=[
        {"table_name": "project_snapshot", "field_name": field} for field in ("project_key", "day", "transfer_flag")
    ] + [{"table_name": "funding_rows", "field_name": field} for field in ("funding_owner", "day")])

    definition = rules.parse_rule_request(user(), request)["preview"]["definition"]
    assert definition["expression"]["left"] == "project_received"
    assert definition["expression"]["right"] == "funding_received"
    assert definition["join"]["right_aggregate"] == "sum"


def test_adopted_sum_does_not_replace_a_metric_with_only_a_filter_reference():
    from auto_check.modules.data_validation.adoption_scope import verify_adopted_goal
    from auto_check.modules.data_validation.documented_choices import ScopeEvidenceRequired

    draft = {"expression": {"left": "other_value", "op": "neq", "right_type": "field", "right_table": "related", "right": "detail_value"},
             "join": {"right_aggregate": "sum", "table_name": "details"},
             "filters": [{"table": "base", "field": "owner_value", "op": "gt", "value": 0}]}
    scope = {"suggestion": {"kind": "aggregate_consistency", "references": [
        {"table_name": "owners", "field_name": "owner_value"}, {"table_name": "details", "field_name": "detail_value"}]}}
    with pytest.raises(ScopeEvidenceRequired):
        verify_adopted_goal(draft, "owners", "details", scope)


def test_adopted_period_binds_the_metric_even_when_scope_evidence_is_referenced_first():
    rules, request = period_request(joined=True, extra_references=[
        {"table_name": "project_snapshot", "field_name": "transfer_flag"},
        {"table_name": "funding_rows", "field_name": "day"},
    ])
    request["include_suggestions"] = False
    request["adoption_context"]["mode"] = "inherit_selected"
    draft = deepcopy(rules.model.payloads[0]["plans"][1]["draft"])
    draft.pop("join")
    draft["expression"] = {"left": "funding_received", "op": "is_null"}
    draft["semantic_intent"]["scopes"] = []
    rules.model.payloads[-3:] = [{"target": {"table": "funding_rows"}, "draft": draft}, draft]

    definition = rules.parse_rule_request(user(), request)["preview"]["definition"]
    assert definition["expression"] == {"left": "funding_received", "op": "lt", "right_type": "value", "right": 0}
    assert definition["filters"][0]["field"] == "transfer_flag"
    assert definition["report_date_field"] == "day"


@pytest.mark.parametrize("metric_first", [False, True])
def test_adopted_period_applies_only_the_actual_metrics_configured_scope(metric_first):
    table = "funding_rows"
    rules, request = period_request(joined=True, metric_first=metric_first,
        extra_references=[{"table_name": table, "field_name": field} for field in ("funding_id", "day")],
        configured_facts=[
            {"table": table, "field": "funding_received", "filters": [{"field": "funding_received", "op": "neq", "value": -2}]},
            {"table": table, "field": "funding_id", "filters": [{"field": "funding_received", "op": "gt", "value": 0}]},
        ])
    request["include_suggestions"] = False
    request["adoption_context"]["mode"] = "inherit_selected"
    draft = deepcopy(rules.model.payloads[0]["plans"][1]["draft"])
    draft.pop("join")
    draft["semantic_intent"]["scopes"] = []
    rules.model.payloads[-3:] = [{"target": {"table": table}, "draft": draft}, draft]

    preview = rules.parse_rule_request(user(), request)["preview"]
    assert {f["op"] for f in preview["definition"]["filters"]} == {"eq", "neq"}
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE project_snapshot (day, project_key, project_name, transfer_flag, project_received)")
        db.execute("CREATE TABLE funding_rows (day, funding_id, funding_owner, funding_received)")
        day = "2026-11-20"
        db.executemany("INSERT INTO project_snapshot VALUES (?, ?, ?, '1', 0)", [(day, k, k) for k in ("eligible", "excluded")])
        db.executemany("INSERT INTO funding_rows VALUES (?, ?, ?, ?)", [(day, 1, "eligible", -1), (day, 2, "excluded", -2)])
        rows = db.execute(preview["sql_preview"], {**preview["sql_params"], "report_date": day}).fetchall()
        assert [r["TCMP编号"] for r in rows] == ["eligible"]


def test_adopted_period_requests_clarification_for_different_checked_metric_scopes():
    from auto_check.modules.data_validation.adoption_scope import attach_period_applicability, bind_period_filters
    from auto_check.modules.data_validation.documented_choices import ScopeEvidenceRequired

    table = "entries"
    names = ("initial_value", "closing_value")
    suggestion = {"category": "period", "adoption": {"operations": []},
                  "references": [{"table_name": table, "field_name": name} for name in names]}
    settings = "\n".join("PERIOD_APPLICABILITY " + json.dumps({
        "source_id": "src", "table": table, "field": field,
        "filters": [{"field": "period", "op": "eq", "value": value}],
    }) for field, value in zip(names, ("A", "B")))
    attach_period_applicability([suggestion], settings, "src", [{"id": 1, "table_name": table}],
                                {1: [{"field_name": name, "data_type": "numeric"} for name in names]
                                 + [{"field_name": "period", "data_type": "varchar"}]})
    draft = {"expression": {"left": names[0], "op": "neq", "right_type": "field", "right": names[1]}}
    with pytest.raises(ScopeEvidenceRequired, match="适用范围不同"):
        bind_period_filters(draft, table, None, {"suggestion": suggestion}, [])


@pytest.mark.parametrize("case", ["captured", "new_scope", "conflicting_scope"])
def test_captured_period_reply_uses_confirmed_scope_without_reasking(case):
    from auto_check.modules.data_validation.adoption_scope import attach_period_applicability
    from tests.modules.data_validation.test_project_driver_binding import field, make_rules, table

    # Structured reply from the captured 2026-11-25 adoption. The positive code
    # matched the registered scope but the model returned 0 as the excluded code.
    owner = "proj_info_dtl_pboc"
    captured = {"target": {"table": owner}, "draft": {
        "business_key": "c_projinnercode", "project_driver": {"version": 1, "table_role": "base"},
        "rule_name": "当期新发项目初始净值非空检查", "rule_type": "field_compare",
        "expression": {"left": "f_initial_nav", "op": "is_null"},
        "violation_message": "当期新发项目初始净值为空", "null_policy": "violate",
        "semantic_intent": {"metrics": [{"side": "left", "term": "当期新发项目初始净值", "fields": ["f_initial_nav"]}],
            "scopes": [{"category": "当期新发项目", "fields": ["c_is_newproj"],
                        "memberships": {"c_is_newproj": {"include": ["1"], "exclude": ["0"]}}}], "open_questions": []},
    }}
    base = deepcopy(captured)
    base["draft"].update(rule_name="净值型项目单位净值非空检查", expression={"left": "f_netvalue", "op": "is_null"},
                         violation_message="单位净值为空")
    base["draft"]["semantic_intent"].update(
        metrics=[{"side": "left", "term": "单位净值", "fields": ["f_netvalue"]}],
        scopes=[{"category": "净值型", "fields": ["c_oper_mode"],
                 "memberships": {"c_oper_mode": {"include": ["1", "3"], "exclude": ["2"]}}}])
    docs = [table(1, owner, "项目明细", "项目", [
        field("c_projinnercode", "TCMP编号", pk="Y", source=("upstream.entity", "entity_id"),
              logic="直接取项目主数据的项目编号[entity_id]。"),
        field("project_name", "项目名全称"),
        field("d_cldate", "数据日期", "date"), field("f_netvalue", "单位净值", "numeric"),
        field("f_initial_nav", "初始净值", "numeric"), field("c_is_newproj", "是否当期新增", dictionary="1-是\n2-否"),
        field("c_oper_mode", "运行方式", dictionary="1-开放式净值型\n2-非净值型\n3-封闭式净值型"),
        field("delivery_kind", "交付方式", dictionary="A-现货\nB-远期"),
    ])]
    rules, model = make_rules([base], tables=docs)
    args = _request(request_text="净值型项目的单位净值不得为空，按运行方式判断净值型项目",
                    analysis_protocol=2, include_suggestions=False)
    parent = rules.parse_rule_request(user(), args)
    receipt = parent["preview"]
    assert receipt, (parent.get("questions"), parent.get("uncertainties"), parent.get("unsupported_requirements"), parent.get("preview_error"))
    [suggestion] = attach_period_applicability([{
        "id": "captured-period", "category": "period", "kind": "field_compare_unary", "adoption": {"operations": []},
        "references": [{"table_name": owner, "field_name": "f_initial_nav"}],
    }], "PERIOD_APPLICABILITY " + json.dumps({
        "source_id": "src", "table": owner, "field": "f_initial_nav",
        "filters": [{"field": "c_is_newproj", "op": "eq", "value": "1"}],
    }), "src", docs, {1: docs[0]["fields"]})
    parent["ai_suggestions"] = [suggestion]
    job = rules.analyses.start(user(), args, worker=lambda *_: parent)
    for _ in range(100):
        if rules.analyses.completed_result(user(), job["analysis_id"]):
            break
        time.sleep(.01)
    wrong = {"c_is_newproj": {"include": ["1"], "exclude": ["0"]}}
    if case == "new_scope":
        wrong = {"delivery_kind": {"include": ["0"], "exclude": ["A"]}}
        captured["draft"]["semantic_intent"]["scopes"].append({"category": "指定交付方式", "fields": ["delivery_kind"],
                                                             "memberships": deepcopy(wrong)})
    elif case == "conflicting_scope":
        captured["draft"]["semantic_intent"]["scopes"][0]["memberships"]["c_is_newproj"] = {"include": ["2"], "exclude": ["1"]}
    model.payloads.extend([captured, {"patch": {"memberships": wrong}}])
    request = _request(request_text="新增净值型项目的初始净值不得为空", analysis_protocol=2, include_suggestions=False,
                       adoption_context={"mode": "inherit_selected", "parent_analysis_id": job["analysis_id"],
                                         "parent_context": parent["analysis_context"], "suggestion_id": "captured-period",
                                         "parents": [{"definition": receipt["definition"], "hash": receipt["content_sha256"]}]})

    result = rules.parse_rule_request(user(), request)
    if case == "new_scope":
        assert not result.get("preview")
        [question] = result["questions"]
        assert {option["value"] for option in question["options"]} == {"delivery_kind=A", "delivery_kind=B"}
    elif case == "conflicting_scope":
        assert not result.get("preview")
        assert any("c_is_newproj" in item and "范围不同" in item for item in result["uncertainties"])
    else:
        assert not result.get("questions") and len(model.calls) == 2
        definition = result["preview"]["definition"]
        assert {f["field"]: f["value"] for f in definition["filters"]} == {"c_oper_mode": ["1", "3"], "c_is_newproj": "1"}
        assert definition["semantic_intent"]["scopes"][0]["memberships"]["c_is_newproj"]["exclude"] == ["2"]
