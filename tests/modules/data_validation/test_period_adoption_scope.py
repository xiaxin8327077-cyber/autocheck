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
                   parent_filters=True, extra_references=(), configured_facts=(), metric_first=False, replacements=(),
                   suggestion_title=None):
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
    if suggestion_title:
        parent["ai_suggestions"][0]["title"] = suggestion_title
    if joined:
        parent["ai_suggestions"][0]["references"] = [{"table_name": candidate["table_name"],
                                                   "field_name": candidate["expression"]["left"]}]
    references = parent["ai_suggestions"][0]["references"]
    if extra_references:
        parent["ai_suggestions"][0]["scope_replacements"] = []
    if metric_first:
        references.extend(extra_references)
    else:
        references[:0] = extra_references
    args = _request(request_text=parent["analysis_request_text"], analysis_protocol=2)
    if configured_facts:
        from auto_check.modules.data_validation.adoption_scope import attach_period_applicability, normalize_supplement_scope_replacements
        inputs = rules._analysis_inputs(user(), args)
        source_id = parent["source_id"]
        settings = "\n".join("PERIOD_APPLICABILITY " + json.dumps({**fact, "source_id": source_id}) for fact in configured_facts)
        if replacements:
            from auto_check.modules.data_validation.ai_suggestions import build_ai_suggestions
            raw = {**parent["ai_suggestions"][0], "kind": "field_compare_binary", "title": "按指定分类核查期初实收",
                   "scope_replacements": list(replacements), "check_target": {"table_name": "project_snapshot",
                       "expression": {"left": "project_received", "op": "lt", "right_type": "value", "right": 0}}}
            candidates = [option["candidate"] for option in parent["candidate_options"]]
            normalized = normalize_supplement_scope_replacements([raw], settings, source_id, inputs["tables"], inputs["fields_by_table"], candidates)
            parent["ai_suggestions"] = build_ai_suggestions(normalized, tables=inputs["tables"], fields_by_table=inputs["fields_by_table"],
                                                            candidates=candidates, model_only=True)
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
               "suggestion_id": parent["ai_suggestions"][0]["id"],
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


def test_inherited_period_definition_describes_the_bound_check_and_keeps_original_advice():
    title = "项目实收非空检查"
    rules, request = period_request(suggestion_title=title)
    context = request["adoption_context"]
    context.update(mode="inherit_selected")
    request.update(request_text=title, include_suggestions=False)
    result = rules.parse_rule_request(user(), request)
    definition = result["preview"]["definition"]
    assert definition["name"] == definition["violation_message"] == "项目实收小于0"
    assert definition["description"] == "沿用所选主方案的检查条件，项目实收小于0时报告异常。"
    parent = rules.analyses.completed_result(user(), context["parent_analysis_id"])
    assert result["analysis_request_text"] == parent["ai_suggestions"][0]["title"] == title


def sum_adoption_request(*, both_parents=False, extra_references=()):
    rules, parent = analyze_suggestion()
    [suggestion] = parent["ai_suggestions"]
    suggestion["references"] += list(extra_references)
    if extra_references:
        suggestion["scope_replacements"] = []
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


@pytest.mark.parametrize("code", ["1", "2"])
def test_captured_period_advice_keeps_a_registered_additional_filter_on_first_run_and_replay(code):
    from auto_check.modules.data_validation.prompt_defaults import DEFAULT_PROMPTS
    from tests.modules.data_validation.test_project_driver_binding import field, make_rules, table

    owner = "proj_info_dtl_pboc"
    advice = {"category": "period", "kind": "field_compare_binary",
              "title": "非净值型当期新发项目初始净值不得大于1或小于0",
              "reason": "初始净值仅适用于当期新发项目，按已确认口径以c_is_newproj='1'限定范围，作为独立期间建议补充核查。",
              "references": [{"table_name": owner, "field_name": name} for name in ("f_initial_nav", "c_is_newproj")],
              "preconditions": [], "limitations": [],
              "scope_replacements": [{"table_name": owner, "field_name": "c_is_newproj", "op": "eq", "value": code}],
              "check_target": {"table_name": owner, "expression": {"logic": "any", "conditions": [
                  {"left": "f_initial_nav", "op": "gt", "right_type": "value", "right": 1},
                  {"left": "f_initial_nav", "op": "lt", "right_type": "value", "right": 0}]}},
              }
    docs = [table(1, owner, "项目明细", "项目", [
        field("c_projinnercode", "TCMP编号", pk="Y", source=("upstream.entity", "entity_id"),
              logic="直接取项目主数据的项目编号[entity_id]。"), field("project_name", "项目名全称"),
        field("d_cldate", "数据日期", "date"), field("f_netvalue", "单位净值", "numeric"),
        field("f_initial_nav", "初始净值", "numeric"), field("c_is_newproj", "是否当期新增", dictionary="1-是\n2-否"),
        field("c_oper_mode", "运行方式", dictionary="1-开放式净值型\n2-开放式非净值型\n3-封闭式净值型\n4-封闭式非净值型"),
    ])]
    def draft(metric, label, scopes):
        conditions = [{**item, "left": metric} for item in advice["check_target"]["expression"]["conditions"]]
        return {"target": {"table": owner}, "draft": {"business_key": "c_projinnercode",
            "project_driver": {"version": 1, "table_role": "base"}, "rule_name": label + "范围检查",
            "rule_type": "field_compare", "expression": {"logic": "any", "conditions": conditions},
            "null_policy": "skip", "violation_message": label + "超出范围", "semantic_intent": {
                "metrics": [{"condition_index": i, "side": "left", "term": label, "fields": [metric]} for i in range(2)],
                "scopes": scopes, "open_questions": []}}}
    main = draft("f_netvalue", "单位净值", [{"category": "非净值型", "fields": ["c_oper_mode"],
                                            "memberships": {"c_oper_mode": {"include": ["2", "4"], "exclude": ["1", "3"]}}}])
    main["ai_suggestions"] = [deepcopy(advice)]
    rules, model = make_rules([main, {"ai_suggestions": [deepcopy(advice)]}], tables=docs)
    fact = {"source_id": "src", "table": owner, "field": "f_initial_nav",
            "filters": [{"field": "c_is_newproj", "op": "eq", "value": "1"}]}
    rules.storage.save_prompt("business_scope", DEFAULT_PROMPTS["business_scope"] + "\nPERIOD_APPLICABILITY " + json.dumps(fact), "test")
    args = _request(request_text="非净值型项目的单位净值不得大于1或小于0。", analysis_protocol=2)
    parent = rules.parse_rule_request(user(), args)
    [suggestion] = parent["ai_suggestions"]
    assert bool(suggestion.get("adoption")) == (code == "1"), suggestion.get("limitations")
    assert parent.get("preview")
    retry = rules.parse_rule_request(user(), args)
    assert retry["analysis_reused"] and retry["ai_suggestions"] == [suggestion]
    if code == "2":
        return

    assert not suggestion["scope_replacements"]
    assert suggestion["applicability_by_metric"] == [{"table": owner, "field": "f_initial_nav", "filters": [
        {"table": owner, "field": "c_is_newproj", "op": "eq", "value": "1", "confirmed": True}]}]
    job = rules.analyses.start(user(), args, worker=lambda *_: parent)
    for _ in range(100):
        if rules.analyses.completed_result(user(), job["analysis_id"]):
            break
        time.sleep(.01)
    model.payloads.append(draft("f_initial_nav", "初始净值", []))
    receipt = parent["preview"]
    result = rules.parse_rule_request(user(), _request(request_text=suggestion["title"], analysis_protocol=2, include_suggestions=False,
        adoption_context={"mode": "inherit_selected", "parent_analysis_id": job["analysis_id"], "parent_context": parent["analysis_context"],
                          "suggestion_id": suggestion["id"], "parents": [{"definition": receipt["definition"], "hash": receipt["content_sha256"]}]}))
    definition = result["preview"]["definition"]
    assert definition["expression"] == advice["check_target"]["expression"]
    assert {f["field"]: f["value"] for f in definition["filters"]} == {"c_oper_mode": ["2", "4"], "c_is_newproj": "1"}


def test_captured_period_advice_repeating_one_parent_range_does_not_replace_the_other_ranges():
    from auto_check.modules.data_validation.adoption_scope import normalize_supplement_scope_replacements

    owner = "proj_info_dtl_pboc"
    advice = {"category": "period", "kind": "field_compare_unary", "title": "当期新发项目初始净值非空检查",
              "references": [{"table_name": owner, "field_name": name} for name in ("f_initial_nav", "c_is_newproj")],
              "check_target": {"table_name": owner, "expression": {"left": "f_initial_nav", "op": "is_null"}},
              "scope_replacements": [{"table_name": owner, "field_name": "c_oper_mode", "op": "in", "value": ["1", "3"]}]}
    candidates = [{"table_name": owner, "filters": [{"field": name, "op": "in", "value": ["1", "3"], "confirmed": True}]}
                  for name in ("c_oper_mode", "c_oper_mode_orig")]
    fact = {"source_id": "src", "table": owner, "field": "f_initial_nav", "filters": [{"field": "c_is_newproj", "op": "eq", "value": "1"}]}
    tables = [{"id": 1, "table_name": owner}]
    fields = {1: [{"field_name": "f_initial_nav", "data_type": "numeric"},
                  {"field_name": "c_is_newproj", "data_type": "varchar", "dictionary": "1-是\n2-否"}]}
    [normalized] = normalize_supplement_scope_replacements([advice], "PERIOD_APPLICABILITY " + json.dumps(fact), "src", tables, fields, candidates)
    assert normalized["scope_replacements"] == []
    assert [c["filters"][0]["field"] for c in candidates] == ["c_oper_mode", "c_oper_mode_orig"]


@pytest.mark.parametrize("repeated_field", ["mode", "original_mode"])
def test_period_advice_can_restate_a_documented_scope_option_before_selection(repeated_field):
    from auto_check.modules.data_validation.adoption_scope import normalize_supplement_scope_replacements

    table = "projects"
    options = [{"selection": {"table": "base", "field": field, "op": "in", "value": ["2", "4"], "confirmed": True}}
               for field in ("mode", "original_mode")]
    candidate = {"table_name": table, "filters": [{**options[0]["selection"], "confirmed": False}],
                 "questions": [{"id": "filters.0", "options": options}]}
    registered = {"field": "is_new", "op": "eq", "value": "1"}
    fact = {"source_id": "src", "table": table, "field": "initial_nav", "filters": [registered]}
    fields = {1: [{"field_name": "initial_nav", "data_type": "numeric"},
                  {"field_name": "is_new", "data_type": "varchar", "dictionary": "1-是\n2-否"}]}
    advice = {"category": "period", "kind": "field_compare_binary", "references": [{"table_name": table, "field_name": "initial_nav"}],
              "scope_replacements": [{"table_name": table, "field_name": repeated_field, "op": "in", "value": ["2", "4"]},
                                     {"table_name": table, "field_name": "is_new", "op": "eq", "value": "1"}]}
    args = ("PERIOD_APPLICABILITY " + json.dumps(fact), "src", [{"id": 1, "table_name": table}], fields, [candidate])
    assert normalize_supplement_scope_replacements([advice], *args)[0]["scope_replacements"] == []
    changed = deepcopy(advice)
    changed["scope_replacements"][0]["value"] = ["1", "3"]
    assert normalize_supplement_scope_replacements([changed], *args)[0]["scope_replacements"] == changed["scope_replacements"][:1]
    assert candidate["filters"][0]["confirmed"] is False


@pytest.mark.parametrize("bad_inclusion", [False, True])
def test_multi_plan_dictionary_grounding_attributes_the_partition_to_its_plan(bad_inclusion):
    from tests.modules.data_validation.test_project_driver_binding import make_rules

    seed, _ = analyze_suggestion()
    args = _request(request_text="存续项目的实收不得小于0", analysis_protocol=2, include_suggestions=False)
    inputs = seed._analysis_inputs(user(), args)
    docs = [{**table, "fields": inputs["fields_by_table"][table["id"]]} for table in inputs["tables"]]
    raw = deepcopy(seed.model.payloads[0])
    for index, plan in enumerate(raw["plans"]):
        partition = plan["draft"]["semantic_intent"]["scopes"][0]["memberships"]["transfer_flag"]
        if bad_inclusion and index == 1:
            partition["include"] = ["9"]
        else:
            partition["exclude"].extend(["3", "4", "5", "6", "7", "8", "9"])
    invalid_patch = {"patch": {"memberships": {"transfer_flag": {"include": ["9"], "exclude": ["1", "2"]}}}}
    rules, model = make_rules([raw, invalid_patch], docs)
    result = rules.parse_rule_request(user(), args)
    if bad_inclusion:
        assert len(model.calls) == 2
        assert result.get("preview") is None
        assert result["questions"][0]["id"].startswith("dictionary/")
        assert {option["value"] for option in result["questions"][0]["options"]} == {"transfer_flag=1", "transfer_flag=2"}
    else:
        assert len(model.calls) == 1
        definitions = [option["candidate"]["preview"]["definition"] for option in result["candidate_options"]]
        assert len(definitions) == 2
        for definition in definitions:
            assert definition["filters"][0]["value"] == "1"
            assert definition["semantic_intent"]["scopes"][0]["memberships"]["transfer_flag"] == {"include": ["1"], "exclude": ["2"]}


def test_period_advice_can_replace_different_values_on_the_same_parent_scope_field():
    rules, request = period_request(two_scopes=True,
        configured_facts=[{"table": "project_snapshot", "field": "project_received",
                           "filters": [{"field": "project_name", "op": "neq", "value": "排除记录"}]}],
        replacements=[{"table_name": "project_snapshot", "field_name": "transfer_flag", "op": "eq", "value": "2"}])
    request["adoption_context"]["mode"] = "inherit_selected"
    request["include_suggestions"] = False

    result = rules.parse_rule_request(user(), request)
    candidates = [option["candidate"] for option in result.get("candidate_options", [])] or [result]
    definitions = [candidate["preview"]["definition"] for candidate in candidates]
    assert len(definitions) == 1
    assert {f["field"]: f["value"] for f in definitions[0]["filters"]} == {"transfer_flag": "2", "project_name": "排除记录"}
    assert definitions[0]["name"] == definitions[0]["violation_message"] == result["period_scope"]["suggestion"]["title"]
    assert "inherited_period_check" not in definitions[0]["semantic_intent"]


@pytest.mark.parametrize("alternate_value", ["1", "2"])
def test_captured_aggregate_advice_can_repeat_a_shared_parent_range_without_replacing_it(alternate_value):
    from auto_check.modules.data_validation.adoption_scope import normalize_supplement_scope_replacements

    project, funding = "proj_info_dtl_pboc", "raise_info_dtl_pboc"
    advice = {"category": "consistency", "kind": "aggregate_consistency", "operations": ["sum"],
              "title": "项目端4001余额与募集端期末份额跨维度差异核对",
              "references": [{"table_name": table, "field_name": field} for table, field in (
                  (project, "f_equity_total_4001_bal"), (funding, "f_end_share"), (project, "c_projinnercode"),
                  (funding, "c_projinnercode"), (project, "d_cldate"), (funding, "d_cldate"))],
              "scope_replacements": [{"table_name": project, "field_name": "c_is_over", "op": "eq", "value": "1"}]}
    condition = {"field": "c_is_over", "op": "eq", "value": "1", "confirmed": True}
    candidates = [{"table_name": project, "filters": [condition]}, {"table_name": funding, "join": {"table_name": project},
                  "filters": [{**condition, "table": "related", "value": alternate_value}]}]
    [normalized] = normalize_supplement_scope_replacements([advice], "", "src", [], {}, candidates)
    assert normalized["scope_replacements"] == ([] if alternate_value == "1" else advice["scope_replacements"])


def replacement_request(source_value="1", reply_scope="target", *, declare_change=True, target_value=None,
                        scope_evidence=False, legacy_snapshot=False, selected_scopes=("matching",), scope_note=False,
                        replacement_fields=None, contradictory_scope=False, child_goal="correct", declare_goal=True):
    from auto_check.modules.data_validation.ai_suggestions import build_ai_suggestions
    from auto_check.modules.data_validation.analysis_result_cache import model_snapshot

    rules, parent = analyze_suggestion()
    candidate = parent["candidate_options"][1]["candidate"]
    definition = deepcopy(candidate["preview"]["definition"])
    target_value = target_value or ("2" if source_value == "1" else "1")
    intent = definition["semantic_intent"]
    intent["scopes"][0]["memberships"] = {"transfer_flag": {"include": [source_value], "exclude": ["2" if source_value == "1" else "1"]}}
    intent["scopes"][0]["category"] = "存续" if source_value == "1" else "终止"
    definition["filters"][0]["value"] = source_value
    extra = {"table": "related", "field": "project_name", "op": "neq", "value": "停用记录", "confirmed": True}
    definition["filters"].append(extra)
    intent["explicit_filters"].append(extra)
    receipt = rules.preview_candidate(user(), {"definition": definition})
    candidate.update(preview=receipt, semantic_intent=receipt["definition"]["semantic_intent"])
    receipts = {"matching": receipt}
    if "other" in selected_scopes:
        other = deepcopy(definition)
        other["filters"] = [extra]
        other["semantic_intent"].update(scopes=[], dictionary_snapshots={})
        alternate = rules.preview_candidate(user(), {"definition": other})
        receipts["other"] = alternate
        parent["candidate_options"].append({"id": "other", "candidate": {
            **candidate, "preview": alternate, "semantic_intent": alternate["definition"]["semantic_intent"]}})
    if "different" in selected_scopes:
        other = deepcopy(definition)
        state = "2" if source_value == "1" else "1"
        next(f for f in other["filters"] if f["field"] == "transfer_flag")["value"] = state
        other["semantic_intent"]["scopes"][0].update(category="终止" if state == "2" else "存续",
            memberships={"transfer_flag": {"include": [state], "exclude": [source_value]}})
        alternate = rules.preview_candidate(user(), {"definition": other})
        receipts["different"] = alternate
        parent["candidate_options"].append({"id": "different", "candidate": {
            **candidate, "preview": alternate, "semantic_intent": alternate["definition"]["semantic_intent"]}})

    raw = {"category": "coverage_gap", "kind": "field_compare_binary", "title": "补充核查另一项目状态的募集实收",
           "references": [{"table_name": "funding_rows", "field_name": "funding_received"}]}
    if scope_evidence:
        raw["references"].append({"table_name": "project_snapshot", "field_name": "transfer_flag"})
    if declare_change:
        raw["scope_replacements"] = [{"table_name": "project_snapshot", "field_name": "transfer_flag", "op": "eq", "value": target_value,
                                      **(replacement_fields or {})}]
        if scope_note:
            raw["scope_replacements"][0]["reason"] = "按已确认建议范围"
        if contradictory_scope:
            raw["scope_replacements"].append({**raw["scope_replacements"][0], "value": source_value})
        if declare_goal:
            raw["check_target"] = {"table_name": "funding_rows", "expression": {
                "left": "funding_received", "op": "gt" if source_value == "1" else "lte", "right_type": "value", "right": 0}}
    elif scope_evidence and not legacy_snapshot:
        raw.update(title="在同一项目状态补充核查募集实收", scope_replacements=[])
    elif not legacy_snapshot:
        raw["title"] = "在原项目状态补充核查募集实收"
    args = _request(request_text=parent["analysis_request_text"], analysis_protocol=2)
    inputs = rules._analysis_inputs(user(), args)
    replayable = model_snapshot({"ai_suggestions": [raw]})["selection"]["ai_suggestions"]
    def review(items):
        return build_ai_suggestions(items, tables=inputs["tables"], fields_by_table=inputs["fields_by_table"],
                                    candidates=[candidate], model_only=True)
    [suggestion] = review(replayable)
    if scope_note:
        assert review([raw]) == [suggestion]
    if legacy_snapshot:
        suggestion = {**raw, "id": "captured-legacy-scope", "adoption": {"operations": [], "preconditions": []}}
    parent["ai_suggestions"] = [suggestion]
    job = rules.analyses.start(user(), args, worker=lambda *_: parent)
    for _ in range(100):
        if rules.analyses.completed_result(user(), job["analysis_id"]):
            break
        time.sleep(.01)

    draft = deepcopy(rules.model.payloads[0]["plans"][1]["draft"])
    draft["rule_name"] = "补充状态下募集实收异常"
    draft["expression"]["op"] = "gt" if source_value == "1" else "lte"
    if child_goal == "parent":
        draft["expression"]["op"] = "lt"
    elif child_goal == "omit":
        draft.pop("expression")
        draft["semantic_intent"]["metrics"] = []
    scopes = draft["semantic_intent"]["scopes"] = []
    if reply_scope != "omit":
        stated = {"target": target_value, "old": source_value, "unknown": "X"}[reply_scope]
        scopes.append({"table": "related", "category": "补充分类", "fields": ["transfer_flag"],
                       "memberships": {"transfer_flag": {"include": [stated], "exclude": [source_value]}}})
    proposal = {"target": {"table": "funding_rows"}, "related_target": {"table": "project_snapshot"}, "draft": draft}
    rules.model.payloads.extend([proposal, draft, draft])
    request = _request(request_text=suggestion["title"], analysis_protocol=2, include_suggestions=False,
                       adoption_context={"mode": "inherit_selected", "parent_analysis_id": job["analysis_id"],
                                         "parent_context": parent["analysis_context"], "suggestion_id": suggestion["id"],
                                         "parents": [{"definition": receipts[scope]["definition"], "hash": receipts[scope]["content_sha256"]}
                                                     for scope in selected_scopes]})
    return rules, request, suggestion, receipt


@pytest.mark.parametrize(("source_value", "reply_scope"), [("1", "target"), ("2", "target"), ("1", "omit"), ("2", "old"), ("1", "unknown")])
def test_adoption_replaces_only_the_confirmed_alternate_scope(source_value, reply_scope):
    rules, request, suggestion, receipt = replacement_request(source_value, reply_scope)
    target_value, expected_label = ("2", "终止") if source_value == "1" else ("1", "存续")

    result = rules.parse_rule_request(user(), request)
    assert result.get("preview"), result.get("uncertainties")
    definition = result["preview"]["definition"]
    assert expected_label in suggestion["title"]
    assert definition["name"] == suggestion["title"]
    assert definition["violation_message"] == suggestion["title"]
    assert {f["field"]: f["value"] for f in definition["filters"]} == {"transfer_flag": target_value, "project_name": "停用记录"}
    assert definition["join"] == receipt["definition"]["join"]
    assert definition["report_date_field"] == receipt["definition"]["report_date_field"]
    assert definition["expression"]["op"] == ("gt" if source_value == "1" else "lte")
    assert receipt["definition"]["expression"]["op"] == "lt"
    assert receipt["definition"]["violation_message"] == "实收小于零"
    assert {f["field"]: f["value"] for f in receipt["definition"]["filters"]}["transfer_flag"] == source_value
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE project_snapshot (day, project_key, project_name, transfer_flag, project_received)")
        db.execute("CREATE TABLE funding_rows (day, funding_id, funding_owner, funding_received)")
        day = "2026-11-25"
        db.executemany("INSERT INTO project_snapshot VALUES (?, ?, ?, ?, 0)", [
            (day, "old", "原范围", source_value), (day, "new", "替换后范围", target_value), (day, "omitted", "停用记录", target_value),
        ])
        amount = 1 if source_value == "1" else 0
        db.executemany("INSERT INTO funding_rows VALUES (?, ?, ?, ?)", [(day, i, key, amount)
                                                                       for i, key in enumerate(("old", "new", "omitted"))])
        preview = result["preview"]
        rows = db.execute(preview["sql_preview"], {**preview["sql_params"], "report_date": day}).fetchall()
        assert [r["TCMP编号"] for r in rows] == ["new"]


@pytest.mark.parametrize("edited", [False, True])
def test_supplement_cannot_replace_a_confirmed_scope_by_its_own_draft(edited):
    rules, request, _, _ = replacement_request(declare_change=False)
    if edited:
        request["request_text"] += "。另核实项目状态"
    result = rules.parse_rule_request(user(), request)
    if edited:
        assert not result.get("preview")
        assert any("transfer_flag" in item and "范围不同" in item for item in result["uncertainties"])
    else:
        assert [f["value"] for f in result["preview"]["definition"]["filters"] if f["field"] == "transfer_flag"] == ["1"]


def test_invalid_advertised_replacement_does_not_fall_back_to_original_scope():
    _, _, suggestion, _ = replacement_request(target_value="X")
    assert not suggestion.get("adoption") and suggestion["limitations"]


def test_scope_replacement_cannot_compile_an_empty_dictionary_intersection():
    _, _, suggestion, _ = replacement_request(contradictory_scope=True)
    assert not suggestion.get("adoption")
    assert any("同时满足" in item for item in suggestion["limitations"])


@pytest.mark.parametrize(("op", "value", "adoptable"), [
    ("not_in", ["1", "2"], False), ("not_in", ["2"], True), ("is_null", None, True),
])
def test_single_scope_replacement_cannot_exclude_all_documented_codes(op, value, adoptable):
    _, _, suggestion, _ = replacement_request(replacement_fields={"op": op, "value": value})
    assert bool(suggestion.get("adoption")) == adoptable


def test_single_scope_replacement_can_exclude_values_from_an_open_numeric_domain():
    from auto_check.modules.data_validation.ai_suggestions import _possible_scope

    assert _possible_scope([{"op": "not_in", "value": [1, 2]}], {"field_name": "priority", "data_type": "numeric"})


@pytest.mark.parametrize("op,value", [("eq", "1"), ("in", ["1"])])
def test_scope_replacement_requires_an_actual_change_to_a_selected_parent(op, value):
    rules, request, _, _ = replacement_request(reply_scope="omit", replacement_fields={"op": op, "value": value})
    calls = len(rules.model.calls)
    result = rules.parse_rule_request(user(), request)
    assert not result.get("preview") and len(rules.model.calls) == calls
    assert any("范围相同" in item for item in result["uncertainties"])


def test_scope_replacement_still_applies_when_only_one_of_multiple_selected_ranges_changes():
    rules, request, _, _ = replacement_request(reply_scope="omit", target_value="1", selected_scopes=("matching", "different"))
    definition = rules.parse_rule_request(user(), request)["preview"]["definition"]
    assert next(f["value"] for f in definition["filters"] if f["field"] == "transfer_flag") == "1"


@pytest.mark.parametrize(("lower", "upper", "adoptable"), [(3, 8, True), (8, 3, False), (4, 4, True)])
def test_scope_replacement_keeps_supported_numeric_intervals(lower, upper, adoptable):
    from auto_check.modules.data_validation.ai_suggestions import build_ai_suggestions

    fields = [{"field_name": name, "data_type": "numeric"} for name in ("amount", "scope_value")]
    base = {"table_name": "entries", "filters": [{"field": "scope_value", "op": "lt", "value": 3, "confirmed": True}]}
    suggestion = {"title": "按另一数值范围检查金额", "category": "coverage_gap", "kind": "field_compare_binary",
                  "references": [{"table_name": "entries", "field_name": "amount"}],
                  "check_target": {"table_name": "entries", "expression": {"left": "amount", "op": "gt", "right_type": "value", "right": 7}},
                  "scope_replacements": [{"table_name": "entries", "field_name": "scope_value", "op": op, "value": value}
                                         for op, value in (("gte", lower), ("lte", upper))]}

    [result] = build_ai_suggestions([suggestion], tables=[{"id": 1, "table_name": "entries"}], fields_by_table={1: fields},
                                   candidates=[base], model_only=True)
    assert bool(result.get("adoption")) == adoptable
    if adoptable:
        assert result["scope_replacements"] == suggestion["scope_replacements"]


@pytest.mark.parametrize("child_goal", ["correct", "parent", "omit"])
def test_adoption_executes_the_confirmed_supplement_goal(child_goal):
    rules, request, _, parent = replacement_request(reply_scope="omit", child_goal=child_goal)
    result = rules.parse_rule_request(user(), request)
    assert result.get("preview"), result.get("uncertainties")
    assert result["preview"]["definition"]["expression"] == {
        "left": "funding_received", "op": "gt", "right_type": "value", "right": 0}
    assert parent["definition"]["expression"]["op"] == "lt"


def test_scope_replacement_requires_a_confirmed_supplement_goal():
    _, _, suggestion, _ = replacement_request(declare_goal=False)
    assert not suggestion.get("adoption") and suggestion["limitations"]


@pytest.mark.parametrize("change", [{}, {"value": "X"}, {"op": "unsupported"},
                                     {"table_name": "funding_rows", "field_name": "funding_id"}])
def test_scope_replacement_annotations_do_not_change_the_result_on_cache_replay(change):
    _, _, suggestion, _ = replacement_request(scope_note=True, replacement_fields=change)
    assert bool(suggestion.get("adoption")) == (not change)
    if not change:
        assert suggestion["scope_replacements"] == [{"table_name": "project_snapshot", "field_name": "transfer_flag",
                                                      "op": "eq", "value": "2"}]


@pytest.mark.parametrize("selected", [("other",), ("matching", "other")])
def test_scope_replacement_needs_the_original_predicate_on_each_selected_branch(selected):
    rules, request, _, _ = replacement_request(reply_scope="omit", selected_scopes=selected)
    len_before = len(rules.model.calls)

    result = rules.parse_rule_request(user(), request)
    assert len(rules.model.calls) == len_before
    assert not result.get("preview") and not result.get("candidate_options")
    assert "项目状态" in "".join(result["uncertainties"])
    assert "未使用" in "".join(result["uncertainties"])


def test_explicit_replacement_requires_the_same_parent_receipt():
    rules, request, _, _ = replacement_request()
    request["adoption_context"]["parents"][0]["definition"]["filters"][0]["value"] = "2"
    with pytest.raises(AppError, match="ANALYSIS_CONTEXT_CHANGED"):
        rules.parse_rule_request(user(), request)


def test_explicit_replacement_requires_the_same_active_document():
    rules, request, _, _ = replacement_request()
    inputs = rules._analysis_inputs(user(), request)
    replacements = [{**table, "fields": deepcopy(inputs["fields_by_table"][table["id"]])} for table in inputs["tables"]]
    project = next(t for t in replacements if t["table_name"] == "project_snapshot")
    state = next(f for f in project["fields"] if f["field_name"] == "transfer_flag")
    state["dictionary"] = "1-存续\n3-终止"
    rules.storage.create_document(name="同来源新范围字典", file_name="in-memory-doc", content_sha256="b" * 64,
                                  table_count=len(replacements), field_count=sum(len(t["fields"]) for t in replacements),
                                  warnings=[], imported_by="1", tables=replacements)
    with pytest.raises(AppError, match="ANALYSIS_CONTEXT_CHANGED"):
        rules.parse_rule_request(user(), request)


@pytest.mark.parametrize("reply_scope", ["omit", "old"])
def test_legacy_advice_missing_a_scope_declaration_cannot_preview_the_original_scope(reply_scope):
    rules, request, _, _ = replacement_request(reply_scope=reply_scope, declare_change=False,
                                              scope_evidence=True, legacy_snapshot=True)
    with pytest.raises(AppError, match="ANALYSIS_CONTEXT_CHANGED"):
        rules.parse_rule_request(user(), request)


def test_advice_with_scope_evidence_can_explicitly_keep_the_original_scope():
    rules, request, suggestion, _ = replacement_request(reply_scope="omit", declare_change=False, scope_evidence=True)
    definition = rules.parse_rule_request(user(), request)["preview"]["definition"]
    assert suggestion["scope_replacements"] == []
    assert {f["field"]: f["value"] for f in definition["filters"]}["transfer_flag"] == "1"


def test_suggestion_review_fills_missing_scope_declaration_using_the_existing_budget():
    from types import SimpleNamespace
    from auto_check.modules.data_validation.semantic_generation import SemanticAnalysis

    _, parent = analyze_suggestion()
    candidate = parent["candidate_options"][1]["candidate"]
    from_candidate = {"table_name": "project_snapshot", "field_name": "transfer_flag"}
    advice = {"category": "coverage_gap", "kind": "field_compare_binary", "title": "仅对另一分类补充检查",
              "references": [{"table_name": "funding_rows", "field_name": "funding_received"}, from_candidate]}
    same = {**advice, "title": "保持分类另查缺值", "scope_replacements": []}
    replacement = [{**from_candidate, "op": "eq", "value": "2"}]
    target = {"table_name": "funding_rows", "expression": {"left": "funding_received", "op": "gt", "right_type": "value", "right": 0}}
    missing_target = {**advice, "title": "更换分类并保持阈值", "scope_replacements": replacement}
    replies = iter([{"ai_suggestions": [advice, same, missing_target]}, {"ai_suggestions": [
        {**advice, "scope_replacements": replacement, "check_target": target}, {**missing_target, "check_target": target}]}])
    prompts = []
    analysis = SimpleNamespace(prompts={"business_scope": "募集实收应按确认的分类另提建议。"},
                               inputs={"source": {"name": "src"}}, request="存续项目的实收不得小于0",
                               round_number=1, output_tokens_used=0)

    def call(prompt, _):
        prompts.append(prompt)
        return next(replies)

    analysis.call = call
    assert SemanticAnalysis.supplement_suggestions(analysis, [candidate], [advice]) == [
        {**advice, "scope_replacements": replacement, "check_target": target}, same, {**missing_target, "check_target": target}]
    assert len(prompts) == 2 and "scope_replacements" in prompts[-1]


def test_aggregate_reference_to_the_selected_scope_inherits_without_redeclaring_it():
    from auto_check.modules.data_validation.ai_suggestions import build_ai_suggestions, scope_declaration_missing

    rules, parent = analyze_suggestion()
    candidate = parent["candidate_options"][1]["candidate"]
    inputs = rules._analysis_inputs(user(), _request(request_text=parent["analysis_request_text"], analysis_protocol=2))
    advice = {"category": "consistency", "kind": "aggregate_consistency", "title": "存续项目实收与募集实收合计一致",
              "operations": ["sum"], "references": [*parent["ai_suggestions"][0]["references"],
                  {"table_name": "project_snapshot", "field_name": "transfer_flag"}]}
    verified, = build_ai_suggestions([advice], tables=inputs["tables"], fields_by_table=inputs["fields_by_table"],
                                     candidates=[candidate], model_only=True)
    assert verified["adoption"]["operations"] == ["sum"]
    assert not scope_declaration_missing(verified, {("project_snapshot", "transfer_flag")})


@pytest.mark.parametrize("fault", ["string_target", "unchanged_range", "keep_scope_for_new_check"])
def test_captured_supplement_reply_is_reviewed_before_adoption(fault):
    from types import SimpleNamespace
    from auto_check.modules.data_validation.ai_suggestions import build_ai_suggestions
    from auto_check.modules.data_validation.analysis_result_cache import model_snapshot
    from auto_check.modules.data_validation.semantic_generation import SemanticAnalysis
    from tests.modules.data_validation.test_project_driver_binding import field, table, document_parts

    asset, project = "asset_income_right_dtl_pboc", "proj_info_dtl_pboc"
    captured = {"category": "consistency", "kind": "field_compare_binary", "title": "收益转让标识为是时资产收益权余额应大于0",
        "reason": "主规则当前筛选为否，补充建议将范围替换为是，检查余额应大于0。其余筛选、关联、数据日期均保留。",
        "references": [{"table_name": asset, "field_name": "f_end_bal"}, {"table_name": project, "field_name": "c_benefittransfer"}],
        "scope_replacements": [{"table_name": project, "field_name": "c_benefittransfer", "op": "eq", "value": "1"}],
        "check_target": {"table_name": asset, "expression": "f_end_bal <= 0"}, "preconditions": [], "limitations": []}
    correct = {"table_name": asset, "expression": {"left": "f_end_bal", "op": "lte", "right_type": "value", "right": 0}}
    corrected = {**captured, "check_target": correct}
    if fault != "string_target":
        corrected = {**corrected, "title": "收益转让为是的项目资产收益权余额应为正"}
        captured.update(title="收益转让标识为否的项目资产收益权余额不应大于0",
            reason="主规则在收益转让标识为是（1）的范围检查资产收益权余额，已确认业务口径要求补充标识为否（2）的项目资产收益权余额不应大于0。",
            scope_replacements=[{**captured["scope_replacements"][0], "value": "2"}],
            check_target={"table_name": asset, "expression": {**correct["expression"], "op": "gt"}})
    if fault == "keep_scope_for_new_check":
        corrected.update(title="保持原范围另行核查低于指定值的项目余额", scope_replacements=[])
    candidate = {"table_name": asset, "join": {"table_name": project}, "columns": [{"column_name": "f_end_bal", "field_cn": "资产收益权余额"}],
                 "related_columns": [{"column_name": "c_benefittransfer", "dictionary": "1-是\n2-否", "data_type": "varchar"}],
                 "expression": {**correct["expression"], "op": "gt"},
                 "filters": [{"table": "related", "field": "c_benefittransfer", "op": "eq", "value": "2", "confirmed": True}]}
    replies = iter([{"ai_suggestions": [deepcopy(captured)]}, {"ai_suggestions": [corrected]}])
    calls = []

    def call(prompt, stage):
        calls.append((prompt, stage))
        return next(replies)

    analysis = SimpleNamespace(prompts={"business_scope": corrected["reason"]}, inputs={"source": {"name": "内存文档"}, "context": {"source_id": "src"}},
                               request="收益转让为否的项目余额不应大于0", round_number=1, output_tokens_used=0,
                               tables=[], fields={}, call=call)
    items = SemanticAnalysis.supplement_suggestions(analysis, [candidate], [captured])
    assert len(calls) == 2
    for prompt, _ in calls:
        comparison = json.loads(prompt.split("当前已核实主方案与待审替换对照：", 1)[1].split("\n", 1)[0])[0]
        assert comparison["当前异常条件"] == {"table_name": asset, "expression": candidate["expression"]}
        [current] = comparison["已核实筛选"]
        assert (current["table_name"], current["field_name"], current["value"], current["文档码值"]) == (
            project, "c_benefittransfer", "2", [{"value": "2", "label": "否"}])
        [proposed] = current["待审替换"]
        expected = captured["scope_replacements"][0]["value"]
        assert proposed["文档码值"] == [{"value": expected, "label": {"1": "是", "2": "否"}[expected]}]
    tables, columns = document_parts([table(1, asset, "资产收益权明细", "资产", [field("f_end_bal", "期末余额", "numeric")]),
                                     table(2, project, "项目", "项目", [field("c_benefittransfer", "收益转让标识", dictionary="1-是\n2-否")])])
    options = {"tables": tables, "fields_by_table": columns, "candidates": [candidate], "model_only": True}
    [suggestion] = build_ai_suggestions(items, **options)
    assert suggestion.get("adoption") and suggestion["check_target"] == correct
    assert suggestion["scope_replacements"] == corrected["scope_replacements"]
    assert suggestion["title"].startswith(corrected["title"])
    replay = model_snapshot({"ai_suggestions": items})["selection"]["ai_suggestions"]
    assert build_ai_suggestions(replay, **options) == [suggestion]


@pytest.mark.parametrize("target_shape", ["missing", "malformed", "ambiguous"])
def test_captured_supplement_typed_expression_binds_only_one_documented_owner(target_shape):
    from types import SimpleNamespace
    from auto_check.modules.data_validation.ai_suggestions import build_ai_suggestions
    from auto_check.modules.data_validation.analysis_result_cache import model_snapshot
    from auto_check.modules.data_validation.semantic_generation import SemanticAnalysis
    from tests.modules.data_validation.test_project_driver_binding import field, table, document_parts

    asset, project = "asset_income_right_dtl_pboc", "proj_info_dtl_pboc"
    captured = {"category": "consistency", "kind": "field_compare_binary", "title": "收益转让标识为否的项目资产收益权余额不应大于0",
        "reason": "已确认业务口径要求：主规则在收益转让标识为是范围检查资产收益权余额时，应补充标识为否的项目资产收益权余额不应大于0的独立建议。本建议替换收益转让标识范围为否，其余条件（项目状态、关联对象、匹配键、数据日期等）保留主方案。",
        "references": [{"table_name": asset, "field_name": "f_end_bal"}, {"table_name": project, "field_name": "c_benefittransfer"}],
        "scope_replacements": [{"table_name": project, "field_name": "c_benefittransfer", "op": "eq", "value": "2"}],
        "expression": {"left": "f_end_bal", "op": "gt", "right_type": "value", "right": 0},
        "operations": [], "preconditions": [], "limitations": []}
    target = {"table_name": asset, "expression": captured["expression"]}
    if target_shape == "malformed":
        captured["check_target"] = {"table_name": asset, "expression": "f_end_bal > 0"}
    amount = field("f_end_bal", "期末余额", "numeric")
    project_fields = [field("c_benefittransfer", "收益转让标识", dictionary="1-是\n2-否")]
    if target_shape == "ambiguous":
        project_fields.append(amount)
        captured["references"].append({"table_name": project, "field_name": "f_end_bal"})
    tables, columns = document_parts([table(1, asset, "资产收益权明细", "资产", [amount]),
                                     table(2, project, "项目", "项目", project_fields)])
    candidate = {"table_name": asset, "join": {"table_name": project}, "columns": [{"column_name": "f_end_bal", "field_cn": "资产收益权余额"}],
                 "expression": {**captured["expression"], "op": "neq"},
                 "filters": [{"table": "related", "field": "c_benefittransfer", "op": "eq", "value": "1", "confirmed": True}]}
    calls = []

    def call(prompt, stage):
        calls.append(stage)
        return {"ai_suggestions": [deepcopy(captured)]}

    analysis = SimpleNamespace(prompts={"business_scope": captured["reason"]}, inputs={"source": {"name": "内存文档"}, "context": {"source_id": "src"}},
                               request="收益转让标识为是的项目资产收益权余额应为0", round_number=1, output_tokens_used=0,
                               tables=tables, fields=columns, call=call)
    items = SemanticAnalysis.supplement_suggestions(analysis, [candidate], [captured])
    ambiguous = target_shape == "ambiguous"
    assert calls == ["supplement_suggestions"] * (2 if ambiguous else 1)
    options = {"tables": tables, "fields_by_table": columns, "candidates": [candidate], "model_only": True}
    [suggestion] = build_ai_suggestions(items, **options)
    if ambiguous:
        assert suggestion["support_level"] == "needs_confirmation" and "adoption" not in suggestion
    else:
        assert items[0]["check_target"] == target
        assert suggestion.get("adoption") and suggestion["check_target"] == target
        assert suggestion["scope_replacements"] == captured["scope_replacements"]
    assert build_ai_suggestions([captured], **options) == [suggestion]
    replay = model_snapshot({"ai_suggestions": [captured]})["selection"]["ai_suggestions"]
    assert build_ai_suggestions(replay, **options) == [suggestion]
