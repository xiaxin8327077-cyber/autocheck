import logging
import pytest
from types import SimpleNamespace
from unittest.mock import Mock

from auto_check.modules.data_validation.model_calls import LOGGER, failure, semantic_completion
from auto_check.modules.data_validation.module import create_module
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.semantic_generation import _model_json_object


@pytest.fixture(autouse=True)
def clear_log_directory_override(monkeypatch):
    monkeypatch.delenv("AUTO_CHECK_ANALYSIS_LOG_DIR", raising=False)


def context(tmp_path):
    return SimpleNamespace(config_path=tmp_path / "application.json", logger=Mock(),
                           application_database=None, services=SimpleNamespace(resolve=lambda *_: None))


def test_module_opens_filters_and_closes_diagnostics_once(tmp_path):
    root = logging.getLogger()
    root_state = (root.level, list(root.handlers))
    level = LOGGER.level
    ctx, module = context(tmp_path), create_module()
    log = tmp_path / "logs/data_validation/analysis.log"
    try:
        module.start(ctx)
        module.start(ctx)
        secret = "untrusted-secret.example/private"
        model = SimpleNamespace(complete_with_options=lambda *args, **kwargs: {
            "content": secret, "usage": {"prompt_tokens": 17, "untrusted": secret}})
        semantic_completion(model, "m", secret, stage="repair_rule", public_stage="generate_rule",
                            round_number=2, analysis_id="123456abcdef", options={}, cancel_event=None)
        error = failure("MODEL_RESPONSE_INVALID", "select_table", category="invalid_json_object",
                        analysis_id="123456abcdef", round_number=2)
        LOGGER.warning("Other warning %s", secret)
        with_secret = failure("MODEL_RESPONSE_INVALID", "select_table", category=secret)
        content = log.read_text(encoding="utf-8")
        assert content.count(error.reference) == 1
        assert with_secret.reference in content
        assert "invalid_json_object" in content and "repair_rule" in content
        assert "prompt_tokens" in content and "duration_ms" in content
        assert secret not in content
        LOGGER.warning('Semantic JSON invalid reference=%s analysis=%s round=%d stage=%s chars=%d reason=%s line=%d column=%d',
                       error.reference, '123456abcdef', 2, 'repair_json', 42, 'syntax', 1, 14)
        raw = '{"draft":"' + secret + '"},"ai_suggestions":[]}'
        assert _model_json_object(raw)["draft"] == secret
        content = log.read_text(encoding='utf-8')
        assert 'chars=42 reason=syntax line=1 column=14' in content
        assert f"Semantic JSON recovered early_root_close chars={len(raw)}" in content
        assert secret not in content
        assert root_state == (root.level, list(root.handlers))
    finally:
        module.stop()
        module.stop()
    assert LOGGER.level == level
    content = log.read_text(encoding="utf-8")
    failure("MODEL_RESPONSE_INVALID", "select_table")
    assert log.read_text(encoding="utf-8") == content
    module.start(ctx)
    try:
        assert log.read_text(encoding="utf-8") == content
        reference = failure("MODEL_TIMEOUT", "generate_rule").reference
        assert log.read_text(encoding="utf-8").count(reference) == 1
    finally:
        module.stop()


def test_unwritable_diagnostics_warns_and_still_starts(tmp_path):
    (tmp_path / "logs").write_text("occupied")
    ctx, module = context(tmp_path), create_module()
    try:
        module.start(ctx)
        assert module.health().healthy
        ctx.logger.warning.assert_called_once()
        assert str(tmp_path) not in str(ctx.logger.warning.call_args)
    finally:
        module.stop()


@pytest.mark.parametrize("invalid", ["relative", "occupied"])
def test_invalid_explicit_directory_warns_without_falling_back(tmp_path, monkeypatch, invalid):
    value = "private-relative-directory"
    if invalid == "occupied":
        blocked = tmp_path / "private-file"
        blocked.write_text("occupied")
        value = str(blocked)
    monkeypatch.setenv("AUTO_CHECK_ANALYSIS_LOG_DIR", value)
    ctx, module = context(tmp_path), create_module()
    try:
        module.start(ctx)
        assert module.health().healthy
        ctx.logger.warning.assert_called_once()
        assert "private" not in str(ctx.logger.warning.call_args)
        assert not (tmp_path / "logs").exists()
    finally:
        module.stop()


def test_full_urlsafe_analysis_id_is_correlated_by_short_id_without_disclosing_rest(tmp_path):
    module = create_module()
    analysis_id = "aB_37-x9" + "p" * 24
    try:
        module.start(context(tmp_path))
        error = failure("MODEL_TIMEOUT", "generate_rule", analysis_id=analysis_id, round_number=2)
        text = (tmp_path / "logs/data_validation/analysis.log").read_text(encoding="utf-8")
        assert "analysis=aB_37-x9 round=2" in text
        assert analysis_id not in text and error.reference in text
    finally:
        module.stop()


@pytest.mark.parametrize("reply", ["timeout", "empty", "truncated", "legacy_timeout"])
def test_failed_model_round_log_contains_its_reference_and_analysis_id(tmp_path, reply):
    def respond(*args, **kwargs):
        if reply.endswith("timeout"):
            raise TimeoutError("private timeout details")
        return {"content": "" if reply == "empty" else "private fragment",
                "finish_reason": "length" if reply == "truncated" else "stop"}
    model = SimpleNamespace(**{"complete" if reply == "legacy_timeout" else "complete_with_options": respond})
    module = create_module()
    try:
        module.start(context(tmp_path))
        with pytest.raises(AppError) as failed:
            semantic_completion(model, "m", "p", stage="repair_rule", public_stage="generate_rule",
                                round_number=2, analysis_id="abcd1234", options={}, cancel_event=None)
        lines = (tmp_path / "logs/data_validation/analysis.log").read_text(encoding="utf-8").splitlines()
        error, = (line for line in lines if failed.value.reference in line)
        assert "analysis=abcd1234 round=2" in error
        assert all("private" not in line for line in lines)
    finally:
        module.stop()


@pytest.mark.parametrize("override", [False, True])
def test_diagnostic_rotation_has_a_fixed_file_count(tmp_path, monkeypatch, override):
    from auto_check.modules.data_validation import diagnostic_logging

    monkeypatch.setattr(diagnostic_logging, "MAX_LOG_BYTES", 1024)
    directory = tmp_path / "logs/data_validation"
    if override:
        directory = tmp_path / "appointed"
        monkeypatch.setenv("AUTO_CHECK_ANALYSIS_LOG_DIR", str(directory))
    module = create_module()
    try:
        module.start(context(tmp_path))
        for _ in range(80):
            failure("MODEL_RESPONSE_INVALID", "select_table")
    finally:
        module.stop()
    files = sorted(directory.iterdir())
    if override:
        assert not (tmp_path / "logs").exists()
    assert [f.name for f in files] == ["analysis.log", "analysis.log.1", "analysis.log.2", "analysis.log.3"]
    assert all(0 < f.stat().st_size <= 1024 for f in files)


def test_rotation_write_failure_warns_once_and_preserves_analysis_errors(tmp_path, monkeypatch):
    from auto_check.modules.data_validation import diagnostic_logging

    monkeypatch.setattr(diagnostic_logging, "MAX_LOG_BYTES", 1)
    def fail_write(_handler):
        raise OSError("sensitive disk information")
    monkeypatch.setattr(diagnostic_logging._AnalysisFile, "doRollover", fail_write)
    ctx, module = context(tmp_path), create_module()
    try:
        module.start(ctx)
        for _ in range(2):
            assert failure("MODEL_TIMEOUT", "generate_rule").code == "MODEL_TIMEOUT"
        ctx.logger.warning.assert_called_once()
        assert "sensitive" not in str(ctx.logger.warning.call_args)
        assert module.health().healthy
    finally:
        module.stop()


@pytest.mark.parametrize("override", [False, True])
def test_same_output_file_is_shared_until_last_instance_stops(tmp_path, monkeypatch, override):
    ctx = context(tmp_path)
    first, second = create_module(), create_module()
    path = tmp_path / "logs/data_validation/analysis.log"
    if override:
        path = tmp_path / "different directory" / "analysis.log"
        monkeypatch.setenv("AUTO_CHECK_ANALYSIS_LOG_DIR", str(path.parent))
    try:
        first.start(ctx)
        second.start(ctx)
        reference = failure("MODEL_TIMEOUT", "generate_rule").reference
        assert path.read_text(encoding="utf-8").count(reference) == 1
        first.stop()
        reference = failure("MODEL_TIMEOUT", "generate_rule").reference
        assert path.read_text(encoding="utf-8").count(reference) == 1
    finally:
        first.stop()
        second.stop()


@pytest.mark.parametrize("first_is_canonical", [False, True])
def test_lexically_equivalent_directories_share_rotation_and_close_on_last_stop(tmp_path, monkeypatch, first_is_canonical):
    from auto_check.modules.data_validation import diagnostic_logging

    monkeypatch.setattr(diagnostic_logging, "MAX_LOG_BYTES", 1024)
    directory = tmp_path / "appointed"
    alternate = tmp_path / "segments" / ".." / "appointed"
    ctx = context(tmp_path)
    first, second = create_module(), create_module()
    try:
        monkeypatch.setenv("AUTO_CHECK_ANALYSIS_LOG_DIR", str(directory if first_is_canonical else alternate))
        first.start(ctx)
        monkeypatch.setenv("AUTO_CHECK_ANALYSIS_LOG_DIR", str(alternate))
        second.start(ctx)
        assert first._diagnostics is second._diagnostics
        handler = first._diagnostics
        first.stop()
        refs = [failure("MODEL_TIMEOUT", "generate_rule").reference for _ in range(12)]
        files = list(directory.glob("analysis.log*"))
        assert 1 < len(files) <= 4
        content = "".join(file.read_text(encoding="utf-8") for file in files)
        assert all(content.count(ref) == 1 for ref in refs)
        second.stop()
        assert handler.stream is None and handler not in LOGGER.handlers
        ctx.logger.warning.assert_not_called()
    finally:
        first.stop()
        second.stop()
