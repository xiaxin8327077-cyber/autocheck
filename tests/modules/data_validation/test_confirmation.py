import pytest

from auto_check.modules.data_validation.contracts import AppError
from tests.modules.data_validation.support import Metadata, loan_definition, service, user


def _ready(rules, owner, **overrides):
    saved = rules.save_draft(owner, loan_definition(**overrides))
    version = rules.storage.latest_version(saved["id"])
    return saved, version


def test_field_compare_matrix_records_expected_and_actual() -> None:
    _database, rules = service(metadata=Metadata())
    owner = user()
    saved, version = _ready(rules, owner)
    result = rules.run_tests(owner, saved["id"], 1)
    assert result["failed_count"] == 0
    assert [case["actual_count"] for case in result["cases"]] == [0, 1, 0, 0]
    failed = rules.run_tests(owner, saved["id"], 1, [
        {**case, "expected_count": 0 if case["name"] == "明显异常" else case["expected_count"]}
        for case in result["cases"]
    ])
    assert failed["failed_count"] == 1


def test_default_cases_are_generated_from_real_column_types() -> None:
    """默认测试用例按真实表结构字段类型合成样本值，不内置固定演示数据。"""
    _database, rules = service(metadata=Metadata())
    owner = user()
    saved, _version = _ready(rules, owner)
    result = rules.run_tests(owner, saved["id"], 1)
    cases = result["cases"]
    assert [case["name"] for case in cases] == ["正常", "明显异常", "边界", "空值"]
    # 日期列样本值必须是 ISO 日期形态，且不是内置的固定演示日期。
    for case in cases[:3]:
        for value in case["row"].values():
            assert value != "2026-12-31" and value != "2026-01-01"
    # 空值样本一侧为 None，另一侧为合成的真实类型值。
    assert cases[3]["row"]["maturity_date"] is None
    assert cases[3]["expected_count"] == 0
    # 数值列生成数值样本，与日期列形态不同。
    number_metadata = Metadata(columns=[
        {"column_name": "project_code", "data_type": "varchar"},
        {"column_name": "left_amount", "data_type": "decimal"},
        {"column_name": "right_amount", "data_type": "decimal"},
        {"column_name": "report_date", "data_type": "date"},
    ])
    _database, numeric_rules = service(metadata=number_metadata)
    saved_numeric = numeric_rules.save_draft(owner, loan_definition(
        expression={"left": "left_amount", "op": "lt", "right": "right_amount"},
    ))
    numeric_result = numeric_rules.run_tests(owner, saved_numeric["id"], 1)
    assert numeric_result["failed_count"] == 0
    for case in numeric_result["cases"][:3]:
        assert isinstance(case["row"]["left_amount"], (int, float))
    # 相等口径与比较方向决定边界样本期望，独立于执行器推导。
    reject_metadata = Metadata()
    _database, reject_rules = service(metadata=reject_metadata)
    saved_eq = reject_rules.save_draft(owner, loan_definition(
        expression={"left": "maturity_date", "op": "eq", "right": "issue_date"},
        equality_policy="reject_equal",
    ))
    eq_result = reject_rules.run_tests(owner, saved_eq["id"], 1)
    boundary = [case for case in eq_result["cases"] if case["name"] == "边界"][0]
    assert boundary["expected_count"] == 1 and boundary["actual_count"] == 1


def test_run_tests_without_metadata_cannot_fabricate_default_cases() -> None:
    """数据源不可达时不得用写死样本冒充测试，必须显式失败；自定义用例仍可用。"""
    _database, rules = service()
    owner = user()
    saved, _version = _ready(rules, owner)
    with pytest.raises(AppError) as error:
        rules.run_tests(owner, saved["id"], 1)
    assert error.value.code == "SOURCE_UNAVAILABLE"
    custom = rules.run_tests(owner, saved["id"], 1, [{
        "name": "明显异常",
        "row": {"maturity_date": "2026-01-01", "issue_date": "2026-12-31"},
        "expected_count": 1,
    }])
    assert custom["failed_count"] == 0


def test_unresolved_policy_blocks_confirm() -> None:
    _database, rules = service()
    owner = user()
    saved, version = _ready(rules, owner, null_policy="unresolved")
    with pytest.raises(AppError) as error:
        rules.confirm_rule(owner, saved["id"], 1, version["content_sha256"])
    assert error.value.code == "VALIDATION_ERROR"
    assert rules.storage.get_rule(saved["id"])["status"] == "draft"


def test_failed_test_blocks_confirm() -> None:
    _database, rules = service()
    owner = user()
    saved, version = _ready(rules, owner)
    rules.run_tests(owner, saved["id"], 1, [{
        "name": "明显异常",
        "row": {"maturity_date": "2026-01-01", "issue_date": "2026-12-31"},
        "expected_count": 0,
    }])
    with pytest.raises(AppError) as error:
        rules.confirm_rule(owner, saved["id"], 1, version["content_sha256"])
    assert error.value.code == "VALIDATION_ERROR"


def test_model_claim_cannot_set_actual_result() -> None:
    _database, rules = service()
    owner = user()
    saved, _version = _ready(rules, owner)
    result = rules.run_tests(owner, saved["id"], 1, [{
        "name": "明显异常",
        "row": {"maturity_date": "2026-01-01", "issue_date": "2026-12-31"},
        "expected_count": 1,
        "model_passed": True,
        "actual_count": 0,
    }])
    assert result["cases"][0]["actual_count"] == 1


def test_edit_enabled_rule_does_not_replace_version() -> None:
    _database, rules = service(metadata=Metadata())
    owner = user()
    saved, version = _ready(rules, owner)
    rules.run_tests(owner, saved["id"], 1)
    rules.confirm_rule(owner, saved["id"], 1, version["content_sha256"])
    original = rules.storage.get_version(saved["id"], 1)
    rules.save_draft(owner, loan_definition(violation_message="新口径"), saved["id"])
    assert rules.storage.get_version(saved["id"], 1)["content_sha256"] == original["content_sha256"]
    assert rules.storage.get_version(saved["id"], 1)["sql_text"] == original["sql_text"]
    latest = rules.storage.latest_version(saved["id"])
    assert latest["version_no"] == 2
    assert latest["status"] == "draft"
    assert rules.storage.get_rule(saved["id"])["current_version_id"] == original["id"]


def test_stale_hash_returns_conflict() -> None:
    _database, rules = service(metadata=Metadata())
    owner = user()
    saved, _version = _ready(rules, owner)
    rules.run_tests(owner, saved["id"], 1)
    with pytest.raises(AppError) as error:
        rules.confirm_rule(owner, saved["id"], 1, "0" * 64)
    assert error.value.code == "CONFLICT_VERSION"


def test_admin_cannot_confirm_others_rule() -> None:
    _database, rules = service(metadata=Metadata())
    saved, version = _ready(rules, user("1"))
    rules.run_tests(user("1"), saved["id"], 1)
    with pytest.raises(AppError) as error:
        rules.confirm_rule(user("9", "admin"), saved["id"], 1, version["content_sha256"])
    assert error.value.code == "FORBIDDEN"
    assert rules.storage.latest_audit(saved["id"])["action_code"] == "access_denied"


def test_disable_keeps_versions() -> None:
    _database, rules = service(metadata=Metadata())
    owner = user()
    saved, version = _ready(rules, owner)
    rules.run_tests(owner, saved["id"], 1)
    rules.confirm_rule(owner, saved["id"], 1, version["content_sha256"])
    before = rules.storage.get_version(saved["id"], 1)["content_sha256"]
    disabled = rules.disable_rule(owner, saved["id"])
    assert disabled["status"] == "disabled"
    assert rules.storage.get_version(saved["id"], 1)["content_sha256"] == before
