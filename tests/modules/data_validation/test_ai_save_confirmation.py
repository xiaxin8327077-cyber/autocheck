from uuid import uuid4

import pytest

from auto_check.modules.data_validation.contracts import AppError
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_batch_save import _definition, _rules


def _forbid_sql(monkeypatch):
    def blocked(*_args, **_kwargs):
        pytest.fail("尚未完成业务确认时已调用 SQL 编译器")

    monkeypatch.setattr("auto_check.modules.data_validation.service.compile_rule", blocked)
    monkeypatch.setattr("auto_check.modules.data_validation.candidate_preview.compile_rule", blocked)


@pytest.mark.parametrize("mode", ["ai", "manual", None])
def test_batch_checks_every_selected_ai_decision_before_compiling_the_first(monkeypatch, mode):
    rules = _rules()
    _forbid_sql(monkeypatch)
    ready = _definition(generation_mode="ai")
    pending = {**ready, "name": "待确认", "uncertainties": ["核对适用范围"], "uncertainty_resolutions": []}
    if mode is None:
        pending.pop("generation_mode")
    else:
        pending["generation_mode"] = mode
    with pytest.raises(AppError):
        rules.batch_save_candidates(user(), {"request_key": str(uuid4()), "definitions": [ready, pending]})
    assert rules.storage.visible_rules(str(user()["id"])) == []


@pytest.mark.parametrize("submitted_mode", [None, "manual"])
def test_edit_inherits_ai_mode_and_invalidates_old_answers_before_compilation(monkeypatch, submitted_mode):
    rules = _rules()
    ready = _definition(generation_mode="ai", include_result_fields=True,
                        uncertainties=["这项比较适用哪个范围？"], uncertainty_resolutions=["本期全部"])
    created = rules.save_draft(user(), ready)
    previous = rules.storage.latest_version(created["id"])
    changed = {**previous["definition"], "description": "本期部分记录"}
    for key in ("generation_mode", "uncertainties", "uncertainty_resolutions"):
        changed.pop(key)
    if submitted_mode:
        changed["generation_mode"] = submitted_mode
    _forbid_sql(monkeypatch)
    with pytest.raises(AppError):
        rules.save_draft(user(), changed, created["id"])
    assert rules.storage.latest_version(created["id"])["id"] == previous["id"]


def test_pending_ai_field_draft_never_compiles_and_manual_draft_keeps_legacy_behavior(monkeypatch):
    rules = _rules()
    ready = _definition(include_result_fields=True, uncertainties=["是否全量？"])
    manual = rules.save_draft(user(), ready)
    assert rules.storage.latest_version(manual["id"])["sql_text"]
    _forbid_sql(monkeypatch)
    with pytest.raises(AppError):
        rules.save_draft(user(), {**ready, "generation_mode": "ai"})


def test_old_ai_draft_remains_editable_without_storing_sql_until_reviewed(monkeypatch):
    rules = _rules()
    with monkeypatch.context() as guard:
        _forbid_sql(guard)
        pending = _definition(generation_mode="ai", uncertainties=["核对期间范围"])
        created = rules.save_draft(user(), pending)
        version = rules.storage.latest_version(created["id"])
        assert version["sql_text"] == ""
    answered = {**version["definition"], "uncertainty_resolutions": ["当期全部"]}
    answered.pop("generation_mode")
    rules.save_draft(user(), answered, created["id"])
    latest = rules.storage.latest_version(created["id"])
    assert latest["sql_text"] and latest["definition"]["generation_mode"] == "ai"


def test_edit_retains_answers_when_only_old_operand_defaults_become_explicit():
    rules = _rules()
    ready = _definition(generation_mode="ai", include_result_fields=True,
                        uncertainties=["确认适用范围"], uncertainty_resolutions=["全部记录"])
    created = rules.save_draft(user(), ready)
    previous = rules.storage.latest_version(created["id"])
    edit = {**previous["definition"], "name": "修改标题", "filters": [],
            "expression": {**ready["expression"], "right_type": "field", "right_table": "base"}}
    rules.save_draft(user(), edit, created["id"])
    latest = rules.storage.latest_version(created["id"])
    assert latest["definition"]["uncertainty_resolutions"] == ["全部记录"] and latest["sql_text"]


def test_reordering_in_values_does_not_invalidate_a_reviewed_scope():
    from tests.modules.data_validation.test_conditional_candidate_options import REQUEST, _conditional_rules
    from tests.modules.data_validation.test_ai_service import _request

    rules, _ = _conditional_rules()
    candidate = rules.parse_rule_request(user(), _request(request_text=REQUEST))
    definition = candidate["preview"]["definition"]
    saved = rules.save_draft(user(), {**definition, "uncertainties": ["确认范围"], "uncertainty_resolutions": ["本期"]})
    edit = rules.storage.latest_version(saved["id"])["definition"]
    edit["filters"][0]["value"].reverse()
    rules.save_draft(user(), edit, saved["id"])
    assert rules.storage.latest_version(saved["id"])["definition"]["uncertainty_resolutions"] == ["本期"]


def test_changed_ai_context_can_be_saved_after_explicit_fresh_answers(monkeypatch):
    rules = _rules()
    old = _definition(generation_mode="ai", include_result_fields=True,
                      uncertainties=["适用记录范围？", "在哪一期检查？"],
                      uncertainty_resolutions=["全部记录", "当前年度"])
    saved = rules.save_draft(user(), old)
    edit = rules.storage.latest_version(saved["id"])["definition"]
    edit["description"] = "发放日期不得早于到期日期"
    edit["expression"] = {"left": "issue_date", "op": "lt", "right": "maturity_date"}
    with monkeypatch.context() as guard:
        _forbid_sql(guard)
        for partial in (["已复核记录"], ["已复核记录", "当前年度"]):
            with pytest.raises(AppError):
                rules.save_draft(user(), {**edit, "uncertainty_resolutions": partial}, saved["id"])
        with pytest.raises(AppError):
            rules.save_draft(user(), {**edit, "uncertainties": [], "uncertainty_resolutions": []}, saved["id"])
    edit["uncertainty_resolutions"] = ["已复核记录", "只核对本月"]
    rules.save_draft(user(), edit, saved["id"])
    latest = rules.storage.latest_version(saved["id"])
    assert latest["version_no"] == 2 and latest["sql_text"]
    assert latest["definition"]["uncertainty_resolutions"] == edit["uncertainty_resolutions"]


def test_explicit_editor_reconfirmation_accepts_identical_answers_without_persisting_marks(monkeypatch):
    rules = _rules()
    saved = rules.save_draft(user(), _definition(
        generation_mode="ai", include_result_fields=True, uncertainties=["适用范围？", "时间口径？"],
        uncertainty_resolutions=["全部记录", "当期"],
    ))
    edit = rules.storage.latest_version(saved["id"])["definition"]
    edit["description"] = "核对新提交的日期比较定义"
    with monkeypatch.context() as guard:
        _forbid_sql(guard)
        with pytest.raises(AppError):
            rules.save_draft(user(), {**edit, "reviewed_uncertainties": ["时间口径？", "其他问题"]}, saved["id"])
    submitted = {**edit, "reviewed_uncertainties": ["时间口径？", "适用范围？"]}
    rules.save_draft(user(), submitted, saved["id"])
    latest = rules.storage.latest_version(saved["id"])
    assert latest["definition"]["uncertainty_resolutions"] == ["全部记录", "当期"]
    assert "reviewed_uncertainties" not in latest["definition"]
    assert latest["content_sha256"] == rules.preview_candidate(user(), edit)["content_sha256"]
