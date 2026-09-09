"""报送导航"报表校验"统计卡 provider：按可配置 SQL 查询 reg-report-analysis。"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

from auto_check.app.config import load_store
from auto_check.app.db import DatabaseClient
from auto_check.app.report_check_config import REPORT_PERIOD_TOKEN, load_report_check_config
from auto_check.app.report_navigation import (
    format_business_report_date,
    report_navigation_business_report_date,
)
from auto_check.app.report_navigation_platform import (
    CardStatisticsRequest,
    CardStatisticsResult,
)
from auto_check.app.storage_config import load_setting, save_setting
from auto_check.app.time_utils import beijing_now

SHANGHAI = ZoneInfo("Asia/Shanghai")
SEMANTICS_VERSION = 2
PROVIDER_OWNER = "builtin.report_check"
DAILY_COMPLETED_SETTING_KEY = "report_navigation.report_check_daily_completed"
DAILY_COMPLETED_RETENTION_DAYS = 62

# 剩余口径 SQL 中的显式报送期占位符，执行时替换为参数绑定标记。
REPORT_PERIOD_PLACEHOLDER = re.compile(re.escape(REPORT_PERIOD_TOKEN))


def _scalar(row: Mapping[str, Any] | None, label: str) -> int:
    if row is None:
        raise ValueError(f"{label}查询未返回结果")
    value = next(iter(row.values()), None)
    if value in (None, ""):
        raise ValueError(f"{label}查询返回空值")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}查询返回值不是整数") from exc
    if number < 0:
        raise ValueError(f"{label}查询返回值不能为负数")
    return number


def resolve_report_check_entry(config: Mapping[str, str], data_sources: Any):
    entries = {entry.name: entry for entry in data_sources}
    entry = entries.get(config["data_source"])
    if entry is None:
        raise ValueError(f"数据源不存在：{config['data_source']}")
    return entry


def bind_report_period(sql: str, report_date: date) -> tuple[str, tuple[str, ...]]:
    bound_sql, replacements = REPORT_PERIOD_PLACEHOLDER.subn("%s", sql)
    if replacements <= 0:
        raise ValueError(f"剩余 SQL 必须包含报送期占位符 {REPORT_PERIOD_TOKEN}")
    value = format_business_report_date(report_date, "date")
    return bound_sql, (value,) * replacements


def fetch_report_check_counts(
    config: Mapping[str, str], client: Any, report_date: date
) -> tuple[int, int]:
    total = _scalar(
        client.fetch_one(f"select count(1) from ({config['total_sql']}) t"),
        "总数",
    )
    remaining_sql, remaining_params = bind_report_period(config["remaining_sql"], report_date)
    remaining = _scalar(client.fetch_one(remaining_sql, remaining_params), "剩余")
    return total, remaining


def record_daily_completed(
    database: Any, observed_on: date, completed: int
) -> int:
    today_key = observed_on.isoformat()
    previous_key = (observed_on - timedelta(days=1)).isoformat()
    with database.transaction() as connection:
        raw_history = load_setting(connection, DAILY_COMPLETED_SETTING_KEY, {})
        history = {
            str(key): int(value)
            for key, value in (raw_history.items() if isinstance(raw_history, Mapping) else ())
            if str(value).isdigit()
        }
        previous_completed = history.get(previous_key, completed)
        history[today_key] = completed
        history = dict(sorted(history.items())[-DAILY_COMPLETED_RETENTION_DAYS:])
        save_setting(connection, DAILY_COMPLETED_SETTING_KEY, history)
    return previous_completed


class ReportCheckStatistics:
    """总数=总数 SQL 行数；未完成=剩余 SQL 标量；已完成=总数-未完成。"""

    def __init__(
        self,
        database: Any,
        *,
        config_loader: Callable[[Any], Mapping[str, str]] | None = None,
        data_source_loader: Callable[[], Any] | None = None,
        client_factory: Callable[[Any], Any] = DatabaseClient,
        now: Callable[[], Any] | None = None,
    ) -> None:
        self._database = database
        self._config_loader = config_loader or self._default_config_loader
        self._data_source_loader = data_source_loader or self._default_data_source_loader
        self._client_factory = client_factory
        self._now = now or beijing_now

    def _default_config_loader(self, connection: Any) -> Mapping[str, str]:
        return load_report_check_config(connection)

    def _default_data_source_loader(self) -> Any:
        return load_store(database=self._database).data_sources

    def _generated_at(self):
        generated_at = self._now()
        if generated_at.tzinfo is None or generated_at.utcoffset() is None:
            generated_at = generated_at.replace(tzinfo=SHANGHAI)
        return generated_at.astimezone(SHANGHAI)

    def __call__(self, request: CardStatisticsRequest) -> CardStatisticsResult:
        with self._database.connect() as connection:
            config = dict(self._config_loader(connection))
        entry = resolve_report_check_entry(config, self._data_source_loader())
        client = self._client_factory(entry.config)
        report_date = report_navigation_business_report_date(request.as_of)
        total, remaining = fetch_report_check_counts(config, client, report_date)
        completed = max(total - remaining, 0)
        observed_at = request.as_of
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            observed_at = observed_at.replace(tzinfo=SHANGHAI)
        previous_completed = record_daily_completed(
            self._database,
            observed_at.astimezone(SHANGHAI).date(),
            completed,
        )
        return CardStatisticsResult(
            total=total,
            completed=completed,
            incomplete=remaining,
            previous_completed=previous_completed,
            generated_at=self._generated_at(),
            semantics_version=SEMANTICS_VERSION,
        )
