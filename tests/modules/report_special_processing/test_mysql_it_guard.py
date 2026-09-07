"""真实 MySQL 集成测试安全门控（mysql_it_guard）的无数据库单元测试。

这些测试不连接任何数据库，只证明门控纯函数的拒绝/放行语义（R3）。
"""

from __future__ import annotations

import os
import re

import pytest

from tests.modules.report_special_processing import mysql_it_guard as guard


def test_generated_name_matches_fixed_regex_and_is_unique():
    names = {guard.generate_scratch_schema_name() for _ in range(50)}
    assert len(names) == 50, "随机后缀必须保证同进程内多轮生成互不相同"
    for name in names:
        assert name.startswith(guard.SCRATCH_PREFIX)
        assert re.fullmatch(r"auto_check_it_rsp_[0-9]{1,10}_[a-z0-9]{8}", name)
        assert f"_{os.getpid()}_" in name
        assert guard.assert_scratch_schema(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "mysql",
        "MySQL",
        "sys",
        "information_schema",
        "performance_schema",
        "auto_check",
        "auto_check_prod",
        "auto_check_it_rsp",
        "auto_check_it_rsp_",
        # 前缀正确但后缀结构非法：pid 缺失/随机段长度或字符集不符。
        "auto_check_it_rsp_zzzzzzzz",
        "auto_check_it_rsp_1234_abc",
        "auto_check_it_rsp_1234_ABCDEFGH",
        "auto_check_it_rsp_1234_abc!defg",
        "auto_check_it_rsp_1234_abcd`efg",
        "auto_check_it_rsp_1234_-abcdefg",
        # 伪装成合法名字：前缀相同但整体结构不符固定正则。
        "auto_check_it_rsp_evil_prefix_1234_abcdef12extra",
        "",
        None,
        123,
        "auto_check_it_rsp_9999999999999999999999_abcdef12",
        "a" * 64,
    ],
)
def test_assert_scratch_schema_rejects_non_scratch_names(name):
    with pytest.raises(ValueError):
        guard.assert_scratch_schema(name)


def test_dsn_schema_never_used_as_target_and_host_restriction(monkeypatch):
    monkeypatch.delenv(guard.ALLOWED_HOSTS_ENV, raising=False)
    # DSN 带危险库名：目标库必须被替换为内部生成的 scratch 名，而不是 DSN 库名。
    target = guard.parse_and_validate_dsn(
        "mysql+pymysql://user:secret@127.0.0.1:3306/mysql"
    )
    assert target.schema != "mysql"
    assert guard.assert_scratch_schema(target.schema) == target.schema
    # 脱敏输出不得包含凭据。
    text = target.redacted()
    assert "secret" not in text and "user" not in text
    assert target.host == "127.0.0.1"
    # localhost 与 ::1 视为回环。
    assert guard.is_loopback_host("localhost")
    assert guard.is_loopback_host("::1")
    assert guard.is_loopback_host("127.0.0.1")
    assert not guard.is_loopback_host("192.168.107.72")
    assert not guard.is_loopback_host("db.internal.example.com")
    # 非回环主机默认拒绝；显式白名单才放行。
    with pytest.raises(ValueError):
        guard.parse_and_validate_dsn(
            "mysql+pymysql://u:p@192.168.107.72:3306/anything"
        )
    monkeypatch.setenv(guard.ALLOWED_HOSTS_ENV, "192.168.107.72")
    remote = guard.parse_and_validate_dsn(
        "mysql+pymysql://u:p@192.168.107.72:3306/anything"
    )
    assert remote.schema != "anything"
    assert guard.assert_scratch_schema(remote.schema) == remote.schema


def test_parse_rejects_missing_or_non_mysql_dsn(monkeypatch):
    monkeypatch.delenv(guard.ALLOWED_HOSTS_ENV, raising=False)
    with pytest.raises(ValueError):
        guard.parse_and_validate_dsn(None)
    with pytest.raises(ValueError):
        guard.parse_and_validate_dsn("")
    with pytest.raises(ValueError):
        guard.parse_and_validate_dsn("postgresql+psycopg://u:p@127.0.0.1:5432/db")
