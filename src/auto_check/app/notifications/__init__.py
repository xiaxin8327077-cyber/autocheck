"""通用系统通知平台 — 稳定类型与工厂导出。"""

from auto_check.app.notifications.contracts import (
    NotificationAction,
    NotificationItem,
    NotificationLevel,
    NotificationPage,
    NotificationPublishRequest,
    NotificationPublishResult,
    NotificationStreamEvent,
    NotificationStreamPublisher,
    NotificationValidationError,
    validate_publish_request,
    validate_source_module,
)

__all__ = [
    "NotificationAction",
    "NotificationItem",
    "NotificationLevel",
    "NotificationPage",
    "NotificationPublishRequest",
    "NotificationPublishResult",
    "NotificationStreamEvent",
    "NotificationStreamPublisher",
    "NotificationValidationError",
    "validate_publish_request",
    "validate_source_module",
]
