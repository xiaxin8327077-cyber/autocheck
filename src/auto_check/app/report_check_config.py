"""报送导航"报表校验"统计卡的可配置查询口径。"""

from __future__ import annotations

from typing import Any, Mapping

from auto_check.app.storage_config import load_setting, save_setting

REPORT_CHECK_SETTING_KEY = "report_navigation.report_check_query"
DEFAULT_REPORT_CHECK_DATA_SOURCE = "reg-report-analysis"
DEFAULT_REPORT_CHECK_DESCRIPTION = "仅统计不可提交的报文错误"
MAX_REPORT_CHECK_SQL_LENGTH = 8000
MAX_REPORT_CHECK_DESCRIPTION_LENGTH = 100
REPORT_PERIOD_TOKEN = "${report_period}"

DEFAULT_REPORT_CHECK_TOTAL_SQL = (
    "select * from ck_rule where rule_identification='不可提交的报文错误'"
)

DEFAULT_REPORT_CHECK_REMAINING_SQL = """select count(1) from (select
    ru.rule_code,
    ru.rule_explain,
    ru.table_name_c,
    ru.table_name_e,
    substring_index(ru.rule_limiters,' ',1) colname_cn ,
    upper(substring_index(ru.rule_limiters,'_',-1)) colname_en,
    substring_index(substring_index(ru.rule_cycle,',',2),',',-1)   rule_cycle,
    count(ru.id) as errorNum, ru.manage_code, rule_identification
from
    ck_result res
left join ck_rule ru on
    res.ck_id = ru.id
where
    res.status = '0'
    and ru.del_flag = '0'
    and res.period = ${report_period}
    and rule_identification!='不可提交的报文错误'
    and manage_code !='rccheck'
group by
    res.ck_id
) a"""


def default_report_check_config() -> dict[str, str]:
    return {
        "data_source": DEFAULT_REPORT_CHECK_DATA_SOURCE,
        "total_sql": DEFAULT_REPORT_CHECK_TOTAL_SQL,
        "remaining_sql": DEFAULT_REPORT_CHECK_REMAINING_SQL,
        "description": DEFAULT_REPORT_CHECK_DESCRIPTION,
    }


def validate_report_check_sql(value: Any) -> str:
    sql = str(value or "").strip()
    if not sql:
        raise ValueError("SQL 不能为空")
    if len(sql) > MAX_REPORT_CHECK_SQL_LENGTH:
        raise ValueError(f"SQL 长度不能超过 {MAX_REPORT_CHECK_SQL_LENGTH} 个字符")
    lowered = sql.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise ValueError("SQL 必须以 select 或 with 开头")
    tail = sql.split(";", 1)[1] if ";" in sql else ""
    if tail.strip():
        raise ValueError("SQL 不支持多条语句")
    return sql.rstrip(";").strip()


def normalize_report_check_config(payload: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(payload, Mapping):
        raise ValueError("报表校验配置格式不正确")
    data_source = str(payload.get("data_source") or "").strip()
    if not data_source:
        raise ValueError("数据源名称不能为空")
    remaining_sql = validate_report_check_sql(payload.get("remaining_sql"))
    if REPORT_PERIOD_TOKEN not in remaining_sql:
        raise ValueError(f"remaining_sql 必须包含报送期占位符 {REPORT_PERIOD_TOKEN}")
    description = str(
        payload.get("description", DEFAULT_REPORT_CHECK_DESCRIPTION) or ""
    ).strip()
    if len(description) > MAX_REPORT_CHECK_DESCRIPTION_LENGTH:
        raise ValueError(
            f"描述文字不能超过 {MAX_REPORT_CHECK_DESCRIPTION_LENGTH} 个字符"
        )
    return {
        "data_source": data_source,
        "total_sql": validate_report_check_sql(payload.get("total_sql")),
        "remaining_sql": remaining_sql,
        "description": description,
    }


def load_report_check_config(connection: Any) -> dict[str, str]:
    saved = load_setting(connection, REPORT_CHECK_SETTING_KEY, None)
    if not isinstance(saved, Mapping):
        return default_report_check_config()
    try:
        return normalize_report_check_config(saved)
    except ValueError:
        return default_report_check_config()


def save_report_check_config(
    connection: Any, payload: Mapping[str, Any]
) -> dict[str, str]:
    config = normalize_report_check_config(payload)
    save_setting(connection, REPORT_CHECK_SETTING_KEY, config)
    return config
