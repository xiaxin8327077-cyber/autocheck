"""真实 MySQL 集成测试库的安全门控（纯函数，不连接任何数据库）。

设计目标（R3）：
- 永远不把 DSN 自带的数据库名当作 CREATE/DROP 目标。
- 本轮 scratch 库名由本模块内部生成：``auto_check_it_rsp_<pid>_<8位随机>``，
  随机部分仅使用 ``[a-z0-9]``（secrets 采样）。
- 创建与删除前都必须通过 ``assert_scratch_schema`` 的固定前缀 + 完整正则断言；
  拒绝 MySQL 系统库、业务库 ``auto_check`` 及一切非测试前缀名称。
- 默认只允许本机回环地址；若确需远程测试实例，必须通过
  ``AUTO_CHECK_IT_MYSQL_ALLOWED_HOSTS``（逗号分隔主机列表）显式开放，
  不允许从普通 DSN 自动推断授权。
- 对外只暴露脱敏目标（主机、端口、scratch 库名），不输出用户名、密码或完整 DSN。
"""

from __future__ import annotations

import ipaddress
import os
import re
import secrets
import string
from dataclasses import dataclass

from sqlalchemy.engine import make_url

DSN_ENV = "AUTO_CHECK_IT_MYSQL_DSN"
ALLOWED_HOSTS_ENV = "AUTO_CHECK_IT_MYSQL_ALLOWED_HOSTS"
SCRATCH_PREFIX = "auto_check_it_rsp_"
BUSINESS_SCHEMA = "auto_check"
SYSTEM_SCHEMAS = frozenset(
    {"mysql", "information_schema", "performance_schema", "sys"}
)
# 完整正则：固定测试前缀 + 十进制 pid + 恰好 8 位小写字母数字随机后缀。
_SCRATCH_NAME_RE = re.compile(r"\Aauto_check_it_rsp_[0-9]{1,10}_[a-z0-9]{8}\Z")
_SUFFIX_ALPHABET = string.ascii_lowercase + string.digits
_MAX_SCHEMA_LENGTH = 63


@dataclass(frozen=True)
class ScratchTarget:
    """校验通过的测试目标：本轮唯一 scratch 库与脱敏后的连接信息。"""

    url: object
    host: str
    port: int
    schema: str

    def redacted(self) -> str:
        return f"host={self.host} port={self.port} schema={self.schema}"


def generate_scratch_schema_name() -> str:
    """生成本轮唯一 scratch 库名（随机部分使用受控字符集）。"""
    suffix = "".join(secrets.choice(_SUFFIX_ALPHABET) for _ in range(8))
    return f"{SCRATCH_PREFIX}{os.getpid()}_{suffix}"


def assert_scratch_schema(name: object) -> str:
    """CREATE/DROP 前的最终强制断言；不合法名称一律拒绝。"""
    if not isinstance(name, str) or not name:
        raise ValueError("scratch 库名必须是非空字符串")
    if len(name) > _MAX_SCHEMA_LENGTH:
        raise ValueError(f"scratch 库名超过长度上限 {_MAX_SCHEMA_LENGTH}：{name!r}")
    if _SCRATCH_NAME_RE.match(name) is None:
        raise ValueError(
            f"拒绝非测试前缀库名 {name!r}：必须匹配固定正则 "
            f"{_SCRATCH_NAME_RE.pattern}"
        )
    if name != name.lower():
        raise ValueError(f"scratch 库名必须为小写：{name!r}")
    if name.lower() in SYSTEM_SCHEMAS:
        raise ValueError(f"拒绝 MySQL 系统库：{name!r}")
    if name == BUSINESS_SCHEMA:
        raise ValueError(f"拒绝业务库：{name!r}")
    return name


def is_loopback_host(host: object) -> bool:
    """主机是否为允许默认使用的回环地址。"""
    if host is None:
        return False
    text = str(host).strip().lower()
    if text in ("", "localhost"):
        return True
    try:
        return ipaddress.ip_address(text).is_loopback
    except ValueError:
        return False


def allowed_hosts_from_env() -> set[str]:
    return {
        item.strip().lower()
        for item in os.environ.get(ALLOWED_HOSTS_ENV, "").split(",")
        if item.strip()
    }


def parse_and_validate_dsn(env_value: str | None) -> ScratchTarget:
    """解析 DSN 并产出经过完整安全校验的本轮 scratch 目标。

    注意：DSN 中的数据库名被彻底忽略——它永远不会成为建库/删库目标。
    """
    if not env_value:
        raise ValueError(f"未设置 {DSN_ENV}，禁止运行真实 MySQL 集成测试")
    url = make_url(env_value)
    if not url.drivername or not str(url.drivername).startswith("mysql"):
        raise ValueError(f"{DSN_ENV} 必须是 MySQL 方言 DSN")
    host = str(url.host or "127.0.0.1")
    port = int(url.port or 3306)
    if not (is_loopback_host(host) or host.lower() in allowed_hosts_from_env()):
        raise ValueError(
            f"测试主机 {host} 未获授权：默认仅允许本机回环地址；"
            f"远程测试实例必须通过 {ALLOWED_HOSTS_ENV} 显式开放"
        )
    schema = generate_scratch_schema_name()
    assert_scratch_schema(schema)
    return ScratchTarget(url=url, host=host, port=port, schema=schema)
