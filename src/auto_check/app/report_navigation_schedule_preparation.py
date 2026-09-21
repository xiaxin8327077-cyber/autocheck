"""报送日期提前准备及异常通知，不执行报送数据统计。"""

from __future__ import annotations

from dataclasses import dataclass
from calendar import monthrange
from datetime import datetime, timedelta
import logging
from typing import Any

from auto_check.app.notifications.contracts import NotificationAction, NotificationPublishRequest
from auto_check.app.storage_report_navigation import ReportNavigationStore


logger = logging.getLogger("auto_check.report_navigation.schedule_preparation")


@dataclass(frozen=True)
class SchedulePreparationIssue:
    report_month: str
    process_code: str
    process_name: str
    reason: str


@dataclass(frozen=True)
class SchedulePreparationResult:
    months: tuple[str, ...]
    checked_count: int
    ready_count: int
    issues: tuple[SchedulePreparationIssue, ...]


def _target_months(now: datetime) -> tuple[str, str]:
    next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
    return now.strftime("%Y-%m"), next_month.strftime("%Y-%m")


def prepare_schedules(store: ReportNavigationStore, *, now: datetime) -> SchedulePreparationResult:
    months = _target_months(now)
    is_month_end = now.day == monthrange(now.year, now.month)[1]
    issues: list[SchedulePreparationIssue] = []
    checked_count = ready_count = 0
    for report_month in months:
        try:
            processes = store.load_configuration(report_month)
        except Exception:
            issues.append(SchedulePreparationIssue(report_month, "all", "报送流程配置", "configuration_failed"))
            continue
        for process in processes:
            checked_count += 1
            try:
                if report_month == months[0] or is_month_end:
                    # 当月补漏或月末兜底才写入；提前检查留出人工维护时间。
                    schedule = store.ensure_schedule(report_month, process.process_code, now=now)
                    if schedule is not None:
                        ready_count += 1
                        continue
                    reason = "missing_history"
                else:
                    year, month = (int(part) for part in report_month.split("-"))
                    current = store.load_schedule(report_month, process.process_code)
                    if current is not None:
                        if (current.report_date.year, current.report_date.month) != (year, month):
                            raise ValueError("报送日期不属于对应月份")
                        ready_count += 1
                        continue
                    previous = store.load_schedule(f"{year - 1:04d}-{month:02d}", process.process_code)
                    if previous is not None and (previous.report_date.year, previous.report_date.month) != (year - 1, month):
                        raise ValueError("上年报送日期不属于对应月份")
                    reason = "awaiting_maintenance" if previous is not None or process.process_code == "pbc_central" else "missing_history"
            except (ValueError, TypeError, OverflowError):
                reason = "invalid_date"
            except Exception:
                reason = "inheritance_failed"
            issues.append(SchedulePreparationIssue(report_month, process.process_code, process.process_name, reason))
    return SchedulePreparationResult(months, checked_count, ready_count, tuple(issues))


def _issue_content(issue: SchedulePreparationIssue) -> str:
    previous_month = f"{int(issue.report_month[:4]) - 1:04d}{issue.report_month[4:]}"
    reasons = {
        "awaiting_maintenance": "下月报送日期尚未维护，请核实监管要求并提前维护；若至本月最后一天仍未维护，将沿用上年同月日期。",
        "missing_history": f"未配置本月报送日期，且找不到 {previous_month} 的历史日期，无法自动继承。",
        "invalid_date": "本月或上年同月的日期配置异常，无法自动继承。请核对日期是否属于对应报送月份。",
        "configuration_failed": "无法读取报送流程配置，请检查配置或联系运维后重新执行任务。",
        "inheritance_failed": "报送日期自动继承失败，请检查日期配置或联系运维后重新执行任务。",
    }
    if issue.reason == "awaiting_maintenance" and issue.process_code == "pbc_central":
        reasons["awaiting_maintenance"] = "下月报送日期尚未维护，请提前维护；月末仍未维护时沿用上年同月日期，无历史配置时使用既有每月 1 日规则。"
    # 流程名称来自配置，限制长度以满足通知平台 2000 字节上限。
    process_name = issue.process_name[:128]
    return (
        f"报送月份：{issue.report_month}。报送流程：{process_name}（{issue.process_code}）。\n"
        f"问题原因：{reasons.get(issue.reason, reasons['inheritance_failed'])}\n"
        "处理建议：请核实监管要求并补充或修正对应月份的报送日期。"
    )


def run_schedule_preparation(
    service: Any, notification_service: Any, user_directory: Any, *, now: datetime
) -> None:
    try:
        result = service.prepare_schedules(now=now)
    except Exception:
        # 异常信息可能包含连接参数，不向任务状态或通知暴露原始异常。
        result = SchedulePreparationResult(
            _target_months(now), 0, 0,
            tuple(SchedulePreparationIssue(month, "all", "报送流程配置", "configuration_failed") for month in _target_months(now)),
        )
    if not result.issues:
        return

    notification_failures = 0
    try:
        # 启动补查可能早于清理任务；过期记录不能继续占用本次提醒的去重键。
        notification_service.cleanup_expired()
    except Exception:
        notification_failures += 1
        logger.warning("报送日期提醒发布前清理过期通知失败")
    try:
        recipients = tuple(user.id for user in user_directory.list_active_users() if user.active and user.role == "admin")
    except Exception:
        recipients = ()
    if not recipients:
        notification_failures += 1
    for issue in result.issues:
        for user_id in recipients:
            request = NotificationPublishRequest(
                event_type="schedule_preparation_issue",
                dedupe_key=f"{issue.report_month}:{issue.process_code}:{issue.reason}:{user_id}",
                recipient_user_ids=(user_id,),
                category="report_navigation",
                level="warning" if issue.reason in ("awaiting_maintenance", "missing_history", "invalid_date") else "error",
                title="报送日期待维护",
                content=_issue_content(issue),
                action=NotificationAction("navigate", "report-navigation", {}),
            )
            try:
                notification_service.publish("report_navigation", request)
            except Exception:
                notification_failures += 1
                logger.warning("报送日期待维护通知发送失败，月份=%s，流程=%s", issue.report_month, issue.process_code)
    reason_names = {"awaiting_maintenance": "尚未维护", "missing_history": "缺少上年配置", "invalid_date": "日期配置异常", "configuration_failed": "读取配置失败", "inheritance_failed": "继承失败"}
    details = "；".join(f"{issue.report_month} {issue.process_name[:64]}：{reason_names.get(issue.reason, '准备失败')}" for issue in result.issues)
    delivery = "；管理员通知发送失败或无可用收件人，后续执行将重试" if notification_failures else "；已提交管理员维护通知"
    raise RuntimeError(f"报送日期待维护 {len(result.issues)} 项；{details[:1400]}{delivery}") from None
