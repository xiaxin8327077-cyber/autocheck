from datetime import datetime, timezone, timedelta

import pytest

from auto_check.app.notifications.contracts import (
    NotificationAction,
    NotificationPublishRequest,
    NotificationStreamEvent,
    NotificationValidationError,
    action_from_json,
    action_to_json,
    decode_cursor,
    encode_cursor,
    validate_publish_request,
    validate_source_module,
)


class TestPublishRequestValidation:
    def test_normalizes_recipients_and_internal_action(self):
        request = validate_publish_request(
            NotificationPublishRequest(
                event_type="pending_confirmation_created",
                dedupe_key="rsp-pending:12:3:u1",
                recipient_user_ids=("u1", "u1", " u2 "),
                category="todo",
                level="info",
                title=" 报表特殊处理待确认 ",
                content="项目端 · 字段名",
                action=NotificationAction(
                    "navigate",
                    "report-special-processing",
                    {"record_id": "12"},
                ),
            )
        )
        assert request.recipient_user_ids == ("u1", "u2")
        assert request.title == "报表特殊处理待确认"
        assert request.action is not None
        assert request.action.route == "report-special-processing"
        assert request.action.query == {"record_id": "12"}

    def test_rejects_empty_recipients(self):
        with pytest.raises(NotificationValidationError, match="recipient"):
            validate_publish_request(
                NotificationPublishRequest(
                    event_type="test",
                    dedupe_key="test:1",
                    recipient_user_ids=(),
                    category="todo",
                    level="info",
                    title="Test",
                    content="",
                )
            )

    def test_rejects_empty_title(self):
        with pytest.raises(NotificationValidationError, match="title"):
            validate_publish_request(
                NotificationPublishRequest(
                    event_type="test",
                    dedupe_key="test:1",
                    recipient_user_ids=("u1",),
                    category="todo",
                    level="info",
                    title="   ",
                    content="",
                )
            )

    def test_rejects_invalid_route(self):
        with pytest.raises(NotificationValidationError, match="route"):
            validate_publish_request(
                NotificationPublishRequest(
                    event_type="test",
                    dedupe_key="test:1",
                    recipient_user_ids=("u1",),
                    category="todo",
                    level="info",
                    title="Test",
                    content="",
                    action=NotificationAction("navigate", "Invalid_Route", {}),
                )
            )

    def test_rejects_http_route(self):
        with pytest.raises(NotificationValidationError, match="route"):
            validate_publish_request(
                NotificationPublishRequest(
                    event_type="test",
                    dedupe_key="test:1",
                    recipient_user_ids=("u1",),
                    category="todo",
                    level="info",
                    title="Test",
                    content="",
                    action=NotificationAction("navigate", "https://evil.com", {}),
                )
            )

    def test_rejects_long_dedupe_key(self):
        with pytest.raises(NotificationValidationError, match="dedupe_key"):
            validate_publish_request(
                NotificationPublishRequest(
                    event_type="test",
                    dedupe_key="x" * 200,
                    recipient_user_ids=("u1",),
                    category="todo",
                    level="info",
                    title="Test",
                    content="",
                )
            )

    def test_rejects_long_content(self):
        with pytest.raises(NotificationValidationError, match="content"):
            validate_publish_request(
                NotificationPublishRequest(
                    event_type="test",
                    dedupe_key="test:1",
                    recipient_user_ids=("u1",),
                    category="todo",
                    level="info",
                    title="Test",
                    content="x" * 2001,
                )
            )


class TestSourceModuleValidation:
    def test_accepts_valid_source_module(self):
        assert validate_source_module("report_special_processing") == "report_special_processing"

    def test_rejects_invalid_source_module(self):
        with pytest.raises(NotificationValidationError):
            validate_source_module("Invalid-Module")


class TestCursorEncoding:
    def test_encode_decode_round_trip(self):
        now = datetime(2026, 8, 25, 10, 30, 0, tzinfo=timezone(timedelta(hours=8)))
        cursor = encode_cursor(now, "abcdef1234567890abcdef1234567890")
        decoded_time, decoded_id = decode_cursor(cursor)
        assert decoded_time == now
        assert decoded_id == "abcdef1234567890abcdef1234567890"

    def test_rejects_invalid_cursor(self):
        with pytest.raises(NotificationValidationError):
            decode_cursor("not-valid-base64!!!")


class TestActionSerialization:
    def test_round_trip(self):
        action = NotificationAction("navigate", "report-special-processing", {"record_id": "12"})
        json_value = action_to_json(action)
        restored = action_from_json(json_value)
        assert restored == action

    def test_none_round_trip(self):
        assert action_to_json(None) is None
        assert action_from_json(None) is None
