"""scratch 库清理逻辑的无数据库单元测试（问题2）。

验证 ``_prepare_scratch_database`` 在引擎初始化、迁移执行、数据库关闭等
任一阶段失败时，都会尝试删除本轮创建的 scratch 库，绝不遗留临时测试库。
测试通过注入 fake engine / database / migrations loader 完成，不连接任何真实 MySQL。
"""

from __future__ import annotations

import pytest

from . import mysql_it_guard, test_storage_real_mysql as mysql_it


def _make_target() -> mysql_it_guard.ScratchTarget:
    """构造一个指向回环主机、内部生成 scratch 名的测试目标（不连接）。"""
    return mysql_it_guard.ScratchTarget(
        url=_FakeUrl(),
        host="127.0.0.1",
        port=3306,
        schema=mysql_it_guard.generate_scratch_schema_name(),
    )


class _FakeUrl:
    """仅实现 fixture 用到的 set()，返回自身以便断言。"""

    username = "test"
    password = "testpass"

    def set(self, **_kwargs):  # noqa: ANN003 - 测试替身
        return self


class _RecordingDropEngine:
    """记录建库/删库语句的 fake server engine。"""

    def __init__(self, *, fail_on: str | None = None):
        self.statements: list[str] = []
        self.fail_on = fail_on
        self.connect_calls = 0
        self.dispose_calls = 0

    def connect(self):
        self.connect_calls += 1
        return _RecordingConnection(self)

    def dispose(self):
        self.dispose_calls += 1


class _RecordingConnection:
    def __init__(self, engine: _RecordingDropEngine):
        self._engine = engine

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, statement):  # noqa: ANN001 - 测试替身
        text_value = str(getattr(statement, "text", statement))
        self._engine.statements.append(text_value)
        if self._engine.fail_on and self._engine.fail_on in text_value:
            raise RuntimeError(f"injected failure: {text_value}")
        return None


class _FakeAppDatabase:
    """替换 ApplicationDatabase：记录迁移语句，可选在 connect/close 抛错。"""

    def __init__(self, engine, fail_connect: bool = False, fail_close: bool = False):
        self.engine = engine
        self.migration_statements: list[str] = []
        self.fail_connect = fail_connect
        self.fail_close = fail_close
        self.closed = False

    def connect(self):
        if self.fail_connect:
            raise RuntimeError("injected migration failure")
        return _FakeMigrationConnection(self)

    def close(self):
        self.closed = True
        if self.fail_close:
            raise RuntimeError("injected close failure")


class _FakeMigrationConnection:
    def __init__(self, db: _FakeAppDatabase):
        self._db = db

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, statement):  # noqa: ANN001 - 测试替身
        self._db.migration_statements.append(str(getattr(statement, "text", statement)))
        return None


class _FakeMigration:
    def __init__(self, version: int, statements: list[str]):
        self.version = version
        self.statements = statements


def _migrations_ok(_package):  # noqa: ANN001 - 测试替身，忽略包名参数
    return [_FakeMigration(v, [f"CREATE TABLE t_{v} (id INT)"]) for v in (1, 2, 3, 4, 5, 6)]


class _CaptureEvents:
    """替换 sqlalchemy event.listens_for：直接返回被装饰函数，不真正注册。"""

    def __call__(self, _engine, _name):  # noqa: ANN001 - 测试替身
        def decorator(func):  # noqa: ANN001 - 测试替身
            return func

        return decorator


def _factory(target, server_engine, app_database_container, *, fail_close=False, fail_connect=False):
    app_database_container["instance"] = None

    def _app_database_factory(_config, engine=None):  # noqa: ANN001 - 测试替身
        db = _FakeAppDatabase(engine, fail_connect=fail_connect, fail_close=fail_close)
        app_database_container["instance"] = db
        return db

    # 迁移失败场景仍用正常版本序列，仅在迁移执行连接时由 fake 抛错。
    migrations_loader = _migrations_ok
    # event/listens_for 注入：工厂函数需要真实 engine 注册监听，但 fake engine
    # 不暴露事件总线，这里注入一个空实现。
    database, cleanup = mysql_it._prepare_scratch_database(
        target,
        server_engine_factory=lambda *_a, **_k: server_engine,
        app_engine_factory=lambda *_a, **_k: "fake-app-engine",
        database_factory=_app_database_factory,
        migrations_loader=migrations_loader,
        event_register=_CaptureEvents(),
    )
    return database, cleanup


def test_migration_failure_still_drops_scratch_database():
    """迁移失败时，初始化阶段即尝试删除本轮 scratch 库，并重新抛出原异常。"""
    target = _make_target()
    server_engine = _RecordingDropEngine()
    container: dict = {}
    with pytest.raises(RuntimeError, match="injected migration failure"):
        _factory(target, server_engine, container, fail_connect=True)
    # 建库 + 删库都发生了，且删库目标是本轮 scratch 名。
    create = [s for s in server_engine.statements if s.startswith("CREATE DATABASE")]
    drop = [s for s in server_engine.statements if s.startswith("DROP DATABASE")]
    assert len(create) == 1 and target.schema in create[0]
    assert len(drop) == 1 and target.schema in drop[0]
    assert container["instance"] is not None
    assert container["instance"].closed is True, "迁移失败路径也要关闭 database 句柄"
    assert server_engine.dispose_calls == 1


def test_close_failure_still_drops_scratch_database():
    """迁移成功后，即便 database.close() 抛异常，也必须尝试删除 scratch 库。"""
    target = _make_target()
    server_engine = _RecordingDropEngine()
    container: dict = {}
    database, cleanup = _factory(target, server_engine, container, fail_close=True)
    # 迁移成功完成（建库后无删库）。
    assert any(s.startswith("CREATE DATABASE") for s in server_engine.statements)
    assert not any(s.startswith("DROP DATABASE") for s in server_engine.statements)
    # 模拟 fixture 的 try/finally：yield 后进入清理；close 会抛错。
    cleanup()
    drop = [s for s in server_engine.statements if s.startswith("DROP DATABASE")]
    assert len(drop) == 1 and target.schema in drop[0], "close 失败仍须尝试删库"
    assert server_engine.dispose_calls == 1


def test_cleanup_revalidates_saved_schema_name(monkeypatch):
    """清理前重新严格校验名称：闭包保存本轮精确 scratch 名，DROP 目标不受外界影响。"""
    target = _make_target()
    saved = target.schema
    server_engine = _RecordingDropEngine()
    container: dict = {}
    _database, cleanup = _factory(target, server_engine, container)
    calls: list[str] = []
    real_assert = mysql_it_guard.assert_scratch_schema

    def spy(name):  # noqa: ANN001 - 测试替身
        calls.append(name)
        return real_assert(name)

    monkeypatch.setattr(mysql_it_guard, "assert_scratch_schema", spy)
    # 外界即使把环境变量 DSN 指向危险库，也不影响本轮保存的名称（不重算）。
    monkeypatch.setenv(mysql_it_guard.DSN_ENV, "mysql+pymysql://u:p@127.0.0.1:3306/mysql")
    cleanup()
    assert saved in calls, "cleanup 必须在 DROP 前重新校验本轮 scratch 名"
    drop = [s for s in server_engine.statements if s.startswith("DROP DATABASE")]
    assert len(drop) == 1 and saved in drop[0]
    assert "mysql" not in drop[0].replace(saved, "")
