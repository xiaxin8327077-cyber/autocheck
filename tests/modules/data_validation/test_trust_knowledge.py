from datetime import date

import pytest

from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.trust_knowledge import TrustKnowledge, applicable_dates
from tests.modules.data_validation.support import service, user
from tests.modules.data_validation.test_ai_service import _generate_payload, _request, _rules_with_doc, _select_payload


def save(knowledge, revision, entries):
    return knowledge.save(user(), {"expected_revision": revision, "entries": entries})


def activate(knowledge, revision, enabled=True):
    return knowledge.save(user(), {"expected_revision": revision, "enabled": enabled}, activation=True)


def test_only_explicit_activation_changes_context_and_preview_is_read_only():
    _, rules = service()
    knowledge = rules.knowledge
    state = knowledge.settings()
    assert state["revision"] == state["active_revision"] == 0 and state["draft"]
    assert rules.storage.knowledge_record() is None
    assert knowledge.preview({"entries": state["draft"]})["entries"] == state["draft"]
    assert rules.storage.knowledge_record() is None
    assert save(knowledge, 0, state["draft"])["active"] == []
    assert knowledge.context("1", "src", "监管报送集市", "doc", "项目实收") == ("", {})
    state = activate(knowledge, 1)
    assert state["active_revision"] == 2
    old_context, _ = knowledge.context("1", "src", "监管报送集市", "doc", "项目实收")
    assert "项目实收与合同合计" in old_context
    edited = [dict(item, summary="新版摘要") for item in state["draft"]]
    assert save(knowledge, 2, edited)["active_revision"] == 2
    assert knowledge.context("1", "src", "监管报送集市", "doc", "项目实收")[0] == old_context
    with pytest.raises(AppError) as conflict:
        activate(knowledge, 2)
    assert conflict.value.code == "CONFLICT_VERSION"
    assert activate(knowledge, 3)["active_revision"] == 4
    assert "新版摘要" in knowledge.context("1", "src", "监管报送集市", "doc", "项目实收")[0]
    assert activate(knowledge, 4, False)["active_revision"] == 0
    assert knowledge.context("1", "src", "监管报送集市", "doc", "项目实收") == ("", {})
    assert rules.storage.visible_rules("1") == []


def test_reuses_catalog_and_same_matching_summary_not_previous_request():
    _, rules = service()
    ticks = [0]
    knowledge = TrustKnowledge(rules.storage, ("监管报送集市", "监管报表"), clock=lambda: ticks[0], today=lambda: date(2026, 11, 18))
    draft = knowledge.settings()["draft"]
    save(knowledge, 0, draft)
    activate(knowledge, 1)
    args = ("1", "src", "监管报送集市", "doc")
    first, meta = knowledge.context(*args, "项目实收不得小于0，前次需求专属文本")
    assert meta["summary_reused"] is False and meta["catalog_reused"] is False
    second, meta = knowledge.context(*args, "项目实收一般不为0")
    assert first == second and meta["summary_reused"] and meta["catalog_reused"]
    assert "前次需求专属文本" not in second
    third, meta = knowledge.context(*args, "产品终止日期不能为空")
    assert "项目实收与合同合计" not in third and meta["catalog_reused"] and not meta["summary_reused"]
    for other in [("2", *args[1:]), ("1", "other", "监管报表", "doc"), (*args[:3], "new-doc")]:
        text, independent = knowledge.context(*other, "项目实收")
        assert not independent["catalog_reused"]
        if other[2] == "监管报表":
            assert "项目实收与合同合计" not in text
    ticks[0] = 601
    assert not knowledge.context(*args, "项目实收")[1]["catalog_reused"]
    assert "资产管理信托产品适用范围" not in knowledge.context(*args, "资产管理信托产品")[0]
    assert "资产管理信托产品适用范围" in knowledge.context(*args, "2027年1月资产管理信托产品")[0]
    assert "资产管理信托产品适用范围" not in knowledge.context(*args, "2026年12月和2027年1月资产管理信托产品")[0]
    assert applicable_dates("2027-00-01", date(2026, 1, 1)) is None


@pytest.mark.parametrize("change", [{"source_name": "other"}, {"reference": "javascript:bad"}, {"keywords": []},
                                    {"valid_from": "2026-02-30"}, {"valid_to": "2000-02-01"}, {"extra": "x"}])
def test_preview_rejects_inputs_without_writing(change):
    _, rules = service()
    draft = [dict(rules.knowledge.settings()["draft"][0], **change)]
    with pytest.raises(AppError) as error:
        rules.knowledge.preview({"entries": draft})
    assert error.value.code == "VALIDATION_ERROR"
    assert rules.storage.knowledge_record() is None


def test_consecutive_analysis_has_two_model_calls_each_no_separate_study_turn():
    payloads = [_select_payload(), _generate_payload()] * 2
    rules, model = _rules_with_doc(payloads)
    save(rules.knowledge, 0, rules.knowledge.settings()["draft"])
    activate(rules.knowledge, 1)
    first = rules.parse_rule_request(user(), _request(request_text="信托产品贷款到期日期不能早于贷款发放日期"))
    second = rules.parse_rule_request(user(), _request(request_text="信托产品贷款到期日期不得早于贷款发放日期"))
    assert len(model.calls) == 4
    for call in model.calls:
        prompt = call["messages"][0]["content"]
        assert prompt.startswith("请先阅读本次匹配的业务知识")
        assert "信托业务分类与粒度" in prompt
    assert first["knowledge_context"]["summary_reused"] is False
    assert second["knowledge_context"]["summary_reused"] is True
    assert rules.storage.visible_rules("1") == []


def test_knowledge_routes_use_existing_admin_permission_and_body_limits():
    from auto_check.modules.data_validation.api import register_routes

    class Router:
        def __init__(self):
            self.endpoints = []

        def add(self, method, path, endpoint, **options):
            if path.startswith("/settings/knowledge"):
                self.endpoints.append((method, path, options))

    router = Router()
    register_routes(router, lambda: None)
    assert len(router.endpoints) == 4
    assert all(opts["permission"] == "data_validation.admin" and opts["max_body_bytes"] <= 100_000
               for _, _, opts in router.endpoints)
