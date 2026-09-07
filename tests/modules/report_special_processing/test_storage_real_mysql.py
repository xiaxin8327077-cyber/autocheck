"""真实 MySQL 上的记录附件事务/回滚与元数据查询集成测试（环境变量门控）。

门控：设置 ``AUTO_CHECK_IT_MYSQL_DSN`` 才执行，例如::

    AUTO_CHECK_IT_MYSQL_DSN=mysql+pymysql://user:pass@127.0.0.1:3306/任意库名

安全约束（由 ``mysql_it_guard`` 强制，见 ``test_mysql_it_guard.py``）：
- 永远不把 DSN 自带的数据库名作为 CREATE/DROP 目标；DSN 库名被忽略。
- 本轮 scratch 库名由测试代码内部生成（``auto_check_it_rsp_<pid>_<随机>``），
  创建前与清理前都必须重新通过固定前缀 + 完整正则断言；拒绝系统库、
  业务库 ``auto_check`` 及一切非测试前缀名称。
- 默认只允许本机回环主机；远程测试实例必须另经
  ``AUTO_CHECK_IT_MYSQL_ALLOWED_HOSTS`` 显式开放，不从 DSN 自动推断授权。
- fixture 只创建、迁移并删除本轮内部生成的 scratch 库，绝不删除任何
  预先存在的 DSN 数据库；测试输出只显示脱敏主机与生成的库名。
- 建表使用模块真实迁移 001–006 的全部语句，不手工造 DDL。
- 会话强制 ``STRICT_TRANS_TABLES``，保证超长字段插入报错而不是静默截断，
  这样回滚断言才有意义。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, event, func, insert, select, text

from auto_check.modules.report_special_processing.contracts import (
    PageQuery,
    RecordAttachmentChange,
    RecordAttachmentFile,
    VersionConflictError,
)
from auto_check.modules.report_special_processing.storage import (
    AUDITS,
    RECORDS,
    RECORD_ATTACHMENTS,
    SpecialProcessingStorage,
)

from . import mysql_it_guard

DSN_ENV = mysql_it_guard.DSN_ENV
MODULE_PACKAGE = "auto_check.modules.report_special_processing"
SHANGHAI = ZoneInfo("Asia/Shanghai")

pytestmark = pytest.mark.skipif(
    not os.environ.get(DSN_ENV),
    reason=f"未设置 {DSN_ENV}，跳过真实 MySQL 集成测试",
)

def _prepare_scratch_database(
    target,  # noqa: ANN001 - ScratchTarget
    *,
    server_engine_factory=None,  # noqa: ANN001 - 测试注入：替代 create_engine（server）
    app_engine_factory=None,  # noqa: ANN001 - 测试注入：替代 create_engine（app）
    database_factory=None,  # noqa: ANN001 - 测试注入：替代 ApplicationDatabase
    migrations_loader=None,  # noqa: ANN001 - 测试注入：替代 load_module_migrations
    event_register=None,  # noqa: ANN001 - 测试注入：替代 sqlalchemy event.listens_for
) -> tuple:
    """创建本轮 scratch 库并执行迁移；返回 ``(database, cleanup)``。

    清理保证（问题2）：
    - 建库后的引擎构造、事件注册、迁移执行全部在 try 块内；
      任一阶段失败都先运行清理（删库+dispose）再向上抛原始异常。
    - 返回的 cleanup 无论 ``database.close()`` 是否失败，都一定尝试
      ``DROP DATABASE``；清理目标始终是本轮保存的精确 scratch 名
      （不从环境变量重新计算），且 DROP 前再次通过完整门控断言。

    ``*_factory`` / ``migrations_loader`` / ``event_register`` 仅供
    ``test_scratch_cleanup.py`` 在不连接真实 MySQL 的前提下注入替身，
    默认路径的行为与生产 fixture 完全一致。
    """
    from auto_check.app.app_database import (
        ApplicationDatabase,
        ApplicationDatabaseConfig,
    )
    from auto_check.app.module_system.schema import load_module_migrations

    server_engine_factory = server_engine_factory or create_engine
    app_engine_factory = app_engine_factory or create_engine
    database_factory = database_factory or ApplicationDatabase
    migrations_loader = migrations_loader or load_module_migrations
    event_register = event_register or event.listens_for

    scratch_name = target.schema
    url = target.url
    # 注意：URL.set(database=None) 会保留原库名，必须用空串移除。
    server_engine = server_engine_factory(url.set(database=""), isolation_level="AUTOCOMMIT")
    try:
        # 建库前再次断言：目标只能是本轮生成的 scratch 名。
        mysql_it_guard.assert_scratch_schema(scratch_name)
        with server_engine.connect() as connection:
            connection.execute(
                text(
                    f"CREATE DATABASE `{scratch_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
    except BaseException:
        # CREATE 失败时 scratch 库可能根本不存在，不盲删；释放连接池后抛出。
        server_engine.dispose()
        raise

    def _drop_scratch() -> None:
        # 清理目标必须是本轮保存的精确随机库名（不从环境变量重新计算），
        # 且删除前再次通过完整门控断言。
        mysql_it_guard.assert_scratch_schema(scratch_name)
        with server_engine.connect() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS `{scratch_name}`"))

    def _close_quietly(resource) -> None:  # noqa: ANN001 - 测试注入替身
        try:
            resource.close()
        except Exception:  # noqa: BLE001 - 关闭失败不得阻塞删库
            pass

    database = None
    try:
        config = ApplicationDatabaseConfig(
            host=target.host,
            port=target.port,
            database=scratch_name,
            username=url.username or "",
            password=url.password or "",
        )
        engine = app_engine_factory(
            url.set(database=scratch_name),
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=2,
        )

        @event_register(engine, "connect")
        def _force_strict_mode(dbapi_connection, _record):  # pragma: no cover - 事件回调
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute(
                    "SET SESSION sql_mode = CONCAT(@@SESSION.sql_mode, ',STRICT_TRANS_TABLES')"
                )
            finally:
                cursor.close()

        captured_statements: list[str] = []

        @event_register(engine, "before_cursor_execute")
        def _capture(_conn, _cursor, statement, _params, _context, _many):  # pragma: no cover
            captured_statements.append(statement)

        database = database_factory(config, engine=engine)
        migrations = migrations_loader(MODULE_PACKAGE)
        assert [item.version for item in migrations] == [1, 2, 3, 4, 5, 6]
        for migration in migrations:
            for statement in migration.statements:
                with database.connect() as connection:
                    connection.execute(text(statement))
        database.captured_statements = captured_statements  # type: ignore[attr-defined]
    except BaseException:
        # 引擎初始化/迁移/建库后任何失败：立即删掉本轮 scratch 库，绝不遗留。
        _close_quietly(database)
        _drop_scratch()
        server_engine.dispose()
        raise

    def cleanup() -> None:
        # close 失败也必须删库：先尝试关闭，再无条件进入删库流程。
        _close_quietly(database)
        _drop_scratch()
        server_engine.dispose()

    return database, cleanup


@pytest.fixture()
def scratch_database():
    """创建本轮唯一 scratch schema、执行模块迁移、测试后仅删除该 scratch 库。"""
    # 门控解析：DSN 库名被忽略，scratch 名称在本模块内部生成。
    try:
        target = mysql_it_guard.parse_and_validate_dsn(os.environ.get(DSN_ENV))
    except ValueError as error:
        pytest.fail(str(error))
    # 输出只允许脱敏主机与生成的测试库名，不含用户名/密码/完整 DSN。
    print(f"[mysql-it] 目标测试实例：{target.redacted()}")
    database, cleanup = _prepare_scratch_database(target)
    try:
        yield database
    finally:
        cleanup()


def _now() -> datetime:
    return datetime.now(SHANGHAI).replace(tzinfo=None)


def _record_values(now: datetime) -> dict:
    return {
        "report_process_code": "P_TEST",
        "report_process_name_snapshot": "真库测试流程",
        "report_period": date(2026, 9, 1),
        "dimension": "amount",
        "summary": "真库集成测试记录",
        "status": "pending",
        "special_handling_at": now,
        "creator_user_id": "u-1",
        "creator_username_snapshot": "zhangsan",
        "created_at": now,
        "updated_by_user_id": "u-1",
        "updated_by_username_snapshot": "zhangsan",
        "updated_at": now,
        "workflow_status": "not_enabled",
        "workflow_version": 0,
        "row_version": 1,
    }


def _audit(action: str, now: datetime, changed: dict, summary: str) -> dict:
    return {
        "action_code": action,
        "operator_user_id": "u-1",
        "operator_username_snapshot": "zhangsan",
        "operator_display_name_snapshot": "张三",
        "occurred_at": now,
        "from_status": None,
        "to_status": "pending",
        "changed_fields_json": json.dumps(changed, ensure_ascii=False),
        "action_summary": summary,
        "request_id": "it-req-1",
    }


def _attachment_file(name: str, content: bytes) -> RecordAttachmentFile:
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return RecordAttachmentFile(
        client_id=f"client-{name}",
        file_name=name,
        file_extension=extension,
        content_type="image/png",
        content=content,
        content_sha256=hashlib.sha256(content).hexdigest(),
    )


def _count(database, table, record_id: int | None = None) -> int:
    statement = select(func.count()).select_from(table)
    if record_id is not None:
        statement = statement.where(table.c.record_id == record_id)
    with database.connect() as connection:
        return int(connection.execute(statement).scalar_one())


def test_create_with_attachments_commits_in_single_transaction(scratch_database):
    storage = SpecialProcessingStorage(scratch_database)
    now = _now()
    content = b"\x89PNG-it-payload"
    created = storage.create(
        _record_values(now),
        ["测试报表"],
        [{"code": "P_TEST", "name": "真库测试流程"}],
        _audit("create", now, {"created": True}, "创建特殊处理记录"),
        record_attachment_change=RecordAttachmentChange(
            retained_ids=(), new_files=(_attachment_file("证据.png", content),)
        ),
        attachment_actor={"user_id": "u-1", "username": "zhangsan"},
    )
    record_id = int(created["id"])
    assert created["row_version"] == 1

    attachments = storage.list_record_attachments(record_id)
    assert len(attachments) == 1
    assert attachments[0]["file_name"] == "证据.png"
    assert attachments[0]["byte_size"] == len(content)

    audits = storage.audit(record_id, PageQuery())["items"]
    assert len(audits) == 1
    field = audits[0]["changed_fields"]["record_attachments"]
    assert field["count"] == 1
    assert field["ids"] == [attachments[0]["id"]]

    # 下载路径可读回正文且内容一致。
    full = storage.get_record_attachment(record_id, attachments[0]["id"])
    assert full is not None and full["content"] == content


def test_oversize_attachment_name_rolls_back_entire_create(scratch_database):
    storage = SpecialProcessingStorage(scratch_database)
    now = _now()
    long_name = "超长文件名" * 80 + ".png"  # 远超 original_file_name VARCHAR(255)
    assert len(long_name) > 255
    with pytest.raises(Exception):
        storage.create(
            _record_values(now),
            ["测试报表"],
            [{"code": "P_TEST", "name": "真库测试流程"}],
            _audit("create", now, {"created": True}, "创建特殊处理记录"),
            record_attachment_change=RecordAttachmentChange(
                retained_ids=(), new_files=(_attachment_file(long_name, b"payload"),)
            ),
            attachment_actor={"user_id": "u-1", "username": "zhangsan"},
        )
    # 回滚证据：记录、记录附件、审计三类行都不存在。
    assert _count(scratch_database, RECORDS) == 0
    assert _count(scratch_database, RECORD_ATTACHMENTS) == 0
    assert _count(scratch_database, AUDITS) == 0


def test_update_soft_removes_adds_and_audits_with_row_version(scratch_database):
    storage = SpecialProcessingStorage(scratch_database)
    now = _now()
    first = b"first-payload"
    created = storage.create(
        _record_values(now),
        ["测试报表"],
        [{"code": "P_TEST", "name": "真库测试流程"}],
        _audit("create", now, {"created": True}, "创建特殊处理记录"),
        record_attachment_change=RecordAttachmentChange(
            retained_ids=(), new_files=(_attachment_file("旧附件.png", first),)
        ),
        attachment_actor={"user_id": "u-1", "username": "zhangsan"},
    )
    record_id = int(created["id"])
    old_id = storage.list_record_attachments(record_id)[0]["id"]

    later = _now()
    second = b"second-payload"
    updated = storage.update(
        record_id,
        1,
        {
            "summary": "修改后的摘要",
            "updated_at": later,
            "updated_by_user_id": "u-2",
            "updated_by_username_snapshot": "lisi",
        },
        ["测试报表"],
        [{"code": "P_TEST", "name": "真库测试流程"}],
        _audit("update", later, {"updated": True}, "修改特殊处理记录"),
        record_attachment_change=RecordAttachmentChange(
            retained_ids=(), new_files=(_attachment_file("新附件.png", second),)
        ),
        attachment_actor={"user_id": "u-2", "username": "lisi"},
    )
    assert int(updated["row_version"]) == 2

    # 当前附件只剩新增的一条；旧行是软删除且内容不可变。
    current = storage.list_record_attachments(record_id)
    assert [item["id"] for item in current] != [old_id]
    assert current[0]["file_name"] == "新附件.png"
    old_full = storage.get_record_attachment(record_id, old_id)
    assert old_full is not None
    assert old_full["removed"] is True
    assert old_full["content"] == first

    audits = storage.audit(record_id, PageQuery())["items"]
    latest = audits[0]
    field = latest["changed_fields"]["record_attachments"]
    assert field["changed"] is True
    assert field["old_ids"] == [old_id]
    assert field["new_ids"] == [current[0]["id"]]
    assert field["added_ids"] == [current[0]["id"]]
    assert field["removed_ids"] == [old_id]
    # 审计双栏：old 标记 removed、new 标记 added，且全部为元数据（无 content 键）。
    assert [item["change"] for item in field["old"]] == ["removed"]
    assert [item["change"] for item in field["new"]] == ["added"]
    for item in field["old"] + field["new"]:
        assert "content" not in item
        assert item["content_sha256"]


def test_metadata_and_audit_queries_never_select_content_column(scratch_database):
    storage = SpecialProcessingStorage(scratch_database)
    now = _now()
    created = storage.create(
        _record_values(now),
        ["测试报表"],
        [{"code": "P_TEST", "name": "真库测试流程"}],
        _audit("create", now, {"created": True}, "创建特殊处理记录"),
        record_attachment_change=RecordAttachmentChange(
            retained_ids=(), new_files=(_attachment_file("证据.png", b"payload"),)
        ),
        attachment_actor={"user_id": "u-1", "username": "zhangsan"},
    )
    record_id = int(created["id"])
    attachment_id = storage.list_record_attachments(record_id)[0]["id"]
    captured: list[str] = scratch_database.captured_statements  # type: ignore[attr-defined]

    # R2 真库断言：清空捕获后执行整个附件修改 update（软删除旧附件并新增），
    # 整个 update 事务路径对附件表的 SELECT 都不得读取 content 正文列。
    later = _now()
    captured.clear()
    storage.update(
        record_id,
        1,
        {
            "summary": "再次修改",
            "updated_at": later,
            "updated_by_user_id": "u-1",
            "updated_by_username_snapshot": "zhangsan",
        },
        ["测试报表"],
        [{"code": "P_TEST", "name": "真库测试流程"}],
        _audit("update", later, {"updated": True}, "修改特殊处理记录"),
        record_attachment_change=RecordAttachmentChange(
            retained_ids=(), new_files=(_attachment_file("替换.png", b"replacement"),)
        ),
        attachment_actor={"user_id": "u-1", "username": "zhangsan"},
    )
    update_attachment_selects = [
        statement
        for statement in captured
        if "report_special_processing_record_attachments" in statement
        and statement.lstrip().upper().startswith("SELECT")
    ]
    assert update_attachment_selects, "update 路径必须实际命中附件表查询"
    for statement in update_attachment_selects:
        assert not re.search(r"\bcontent\b", statement), (
            f"update 路径不得选择 content 列：{statement}"
        )

    captured.clear()
    attachments = storage.list_record_attachments(record_id, include_removed=True)
    audit_page = storage.audit(record_id, PageQuery())
    attachment_selects = [
        statement
        for statement in captured
        if "report_special_processing_record_attachments" in statement
        and statement.lstrip().upper().startswith("SELECT")
    ]
    assert attachment_selects, "元数据/审计查询必须实际命中附件表"
    for statement in attachment_selects:
        assert not re.search(r"\bcontent\b", statement), (
            f"元数据查询不得选择 content 列：{statement}"
        )
    # 返回结构只含元数据键。
    for item in attachments:
        assert "content" not in item
    for item in audit_page["items"]:
        field = (item.get("changed_fields") or {}).get("record_attachments")
        if isinstance(field, dict):
            for entry in (field.get("old") or []) + (field.get("new") or []):
                assert "content" not in entry
    # 只有下载路径读取正文。
    captured.clear()
    full = storage.get_record_attachment(record_id, attachment_id)
    assert full is not None and full["content"] == b"payload"
    assert any(
        re.search(r"\bcontent\b", statement)
        for statement in captured
        if statement.lstrip().upper().startswith("SELECT")
    )


def test_audit_hydration_stays_small_with_bulk_removed_history(scratch_database):
    storage = SpecialProcessingStorage(scratch_database)
    now = _now()
    created = storage.create(
        _record_values(now),
        ["测试报表"],
        [{"code": "P_TEST", "name": "真库测试流程"}],
        _audit("create", now, {"created": True}, "创建特殊处理记录"),
    )
    record_id = int(created["id"])

    # 预置 12 条已移除的 1 MiB 历史附件（模拟多轮替换后的沉淀数据）。
    blob = b"x" * (1024 * 1024)
    history_ids: list[int] = []
    with scratch_database.transaction() as connection:
        for index in range(12):
            result = connection.execute(
                insert(RECORD_ATTACHMENTS).values(
                    record_id=record_id,
                    original_file_name=f"历史附件-{index:02d}.png",
                    file_extension="png",
                    content_type="image/png",
                    byte_size=len(blob),
                    content_sha256=hashlib.sha256(blob).hexdigest(),
                    content=blob,
                    created_by_user_id="u-1",
                    created_by_username_snapshot="zhangsan",
                    created_at=now,
                    removed_by_user_id="u-1",
                    removed_by_username_snapshot="zhangsan",
                    removed_at=now,
                )
            )
            history_ids.append(int(result.inserted_primary_key[0]))

    later = _now()
    # 一次更新把全部历史附件纳入审计 old_ids/new_ids 水化范围。
    storage.update(
        record_id,
        1,
        {
            "summary": "汇总历史附件",
            "updated_at": later,
            "updated_by_user_id": "u-1",
            "updated_by_username_snapshot": "zhangsan",
        },
        ["测试报表"],
        [{"code": "P_TEST", "name": "真库测试流程"}],
        _audit(
            "update",
            later,
            {
                "record_attachments": {
                    "changed": True,
                    "old_ids": history_ids,
                    "new_ids": history_ids,
                    "added_ids": [],
                    "removed_ids": [],
                }
            },
            "修改特殊处理记录",
        ),
    )

    captured: list[str] = scratch_database.captured_statements  # type: ignore[attr-defined]
    captured.clear()
    audit_page = storage.audit(record_id, PageQuery())
    payload_bytes = len(
        json.dumps(audit_page["items"], ensure_ascii=False, default=str).encode("utf-8")
    )
    # 12 MiB 正文沉淀下，审计返回只含元数据，体积应保持很小。
    assert payload_bytes < 64 * 1024, f"审计返回体积异常：{payload_bytes} 字节"
    for statement in captured:
        if "report_special_processing_record_attachments" in statement and statement.lstrip().upper().startswith("SELECT"):
            assert not re.search(r"\bcontent\b", statement)


def test_stale_row_version_conflict_leaves_no_attachment_side_effects(scratch_database):
    """stale row_version 冲突：不留下附件软删除、新附件或审计。"""
    storage = SpecialProcessingStorage(scratch_database)
    now = _now()
    created = storage.create(
        _record_values(now),
        ["测试报表"],
        [{"code": "P_TEST", "name": "真库测试流程"}],
        _audit("create", now, {"created": True}, "创建特殊处理记录"),
        record_attachment_change=RecordAttachmentChange(
            retained_ids=(), new_files=(_attachment_file("原始.png", b"original"),)
        ),
        attachment_actor={"user_id": "u-1", "username": "zhangsan"},
    )
    record_id = int(created["id"])
    original_id = storage.list_record_attachments(record_id)[0]["id"]

    later = _now()
    with pytest.raises(VersionConflictError):
        storage.update(
            record_id,
            999,  # 过期版本
            {
                "summary": "冲突不应生效",
                "updated_at": later,
                "updated_by_user_id": "u-2",
                "updated_by_username_snapshot": "lisi",
            },
            ["测试报表"],
            [{"code": "P_TEST", "name": "真库测试流程"}],
            _audit("update", later, {"updated": True}, "修改特殊处理记录"),
            record_attachment_change=RecordAttachmentChange(
                retained_ids=(), new_files=(_attachment_file("追加.png", b"extra"),)
            ),
            attachment_actor={"user_id": "u-2", "username": "lisi"},
        )

    # 冲突后终态：记录字段未变、原附件仍为当前、没有新附件、审计仍只有一条。
    refreshed = storage.get(record_id)
    assert refreshed is not None
    assert refreshed["summary"] == "真库集成测试记录"
    assert int(refreshed["row_version"]) == 1
    current = storage.list_record_attachments(record_id)
    assert [item["id"] for item in current] == [original_id]
    assert _count(scratch_database, RECORD_ATTACHMENTS, record_id) == 1
    assert _count(scratch_database, AUDITS, record_id) == 1


def test_attachment_insert_failure_rolls_back_entire_update(scratch_database):
    """插入新附件失败：主记录更新、旧附件软删除、新附件与审计全部回滚。"""
    storage = SpecialProcessingStorage(scratch_database)
    now = _now()
    created = storage.create(
        _record_values(now),
        ["测试报表"],
        [{"code": "P_TEST", "name": "真库测试流程"}],
        _audit("create", now, {"created": True}, "创建特殊处理记录"),
        record_attachment_change=RecordAttachmentChange(
            retained_ids=(), new_files=(_attachment_file("旧附件.png", b"old"),)
        ),
        attachment_actor={"user_id": "u-1", "username": "zhangsan"},
    )
    record_id = int(created["id"])
    old_id = storage.list_record_attachments(record_id)[0]["id"]

    later = _now()
    long_name = "超长附件名" * 80 + ".png"  # 超过 original_file_name VARCHAR(255)
    assert len(long_name) > 255
    with pytest.raises(Exception):
        storage.update(
            record_id,
            1,
            {
                "summary": "失败的修改",
                "updated_at": later,
                "updated_by_user_id": "u-2",
                "updated_by_username_snapshot": "lisi",
            },
            ["测试报表"],
            [{"code": "P_TEST", "name": "真库测试流程"}],
            _audit("update", later, {"updated": True}, "修改特殊处理记录"),
            record_attachment_change=RecordAttachmentChange(
                retained_ids=(),  # 意图软删除旧附件
                new_files=(
                    _attachment_file("先插入成功.png", b"first"),
                    _attachment_file(long_name, b"boom"),  # 第二条触发库内报错
                ),
            ),
            attachment_actor={"user_id": "u-2", "username": "lisi"},
        )

    refreshed = storage.get(record_id)
    assert refreshed is not None
    assert refreshed["summary"] == "真库集成测试记录"
    assert int(refreshed["row_version"]) == 1
    # 旧附件未被软删除，仍是当前唯一附件；任何新附件都不存在。
    current = storage.list_record_attachments(record_id)
    assert [item["id"] for item in current] == [old_id]
    assert _count(scratch_database, RECORD_ATTACHMENTS, record_id) == 1
    old_full = storage.get_record_attachment(record_id, old_id)
    assert old_full is not None and old_full["removed"] is False
    assert _count(scratch_database, AUDITS, record_id) == 1


def test_delete_record_clears_current_and_history_attachments(scratch_database):
    """删除记录：当前与历史（软删除）附件全部物理清理。"""
    storage = SpecialProcessingStorage(scratch_database)
    now = _now()
    created = storage.create(
        _record_values(now),
        ["测试报表"],
        [{"code": "P_TEST", "name": "真库测试流程"}],
        _audit("create", now, {"created": True}, "创建特殊处理记录"),
        record_attachment_change=RecordAttachmentChange(
            retained_ids=(), new_files=(_attachment_file("第一版.png", b"v1"),)
        ),
        attachment_actor={"user_id": "u-1", "username": "zhangsan"},
    )
    record_id = int(created["id"])
    later = _now()
    storage.update(
        record_id,
        1,
        {
            "summary": "替换附件",
            "updated_at": later,
            "updated_by_user_id": "u-1",
            "updated_by_username_snapshot": "zhangsan",
        },
        ["测试报表"],
        [{"code": "P_TEST", "name": "真库测试流程"}],
        _audit("update", later, {"updated": True}, "修改特殊处理记录"),
        record_attachment_change=RecordAttachmentChange(
            retained_ids=(), new_files=(_attachment_file("第二版.png", b"v2"),)
        ),
        attachment_actor={"user_id": "u-1", "username": "zhangsan"},
    )
    # 当前 1 条 + 历史软删除 1 条。
    assert _count(scratch_database, RECORD_ATTACHMENTS, record_id) == 2
    assert len(storage.list_record_attachments(record_id, include_removed=True)) == 2

    storage.delete_record(record_id, 2)
    assert storage.get(record_id) is None
    assert _count(scratch_database, RECORD_ATTACHMENTS, record_id) == 0
    assert _count(scratch_database, AUDITS, record_id) == 0


def test_history_soft_removed_attachment_readable_only_by_its_record(scratch_database):
    """历史软删除附件按 record_id + attachment_id 可读；跨记录访问被拒。"""
    storage = SpecialProcessingStorage(scratch_database)
    now = _now()
    first = b"first-payload"
    created = storage.create(
        _record_values(now),
        ["测试报表"],
        [{"code": "P_TEST", "name": "真库测试流程"}],
        _audit("create", now, {"created": True}, "创建特殊处理记录"),
        record_attachment_change=RecordAttachmentChange(
            retained_ids=(), new_files=(_attachment_file("历史.png", first),)
        ),
        attachment_actor={"user_id": "u-1", "username": "zhangsan"},
    )
    record_id = int(created["id"])
    old_id = storage.list_record_attachments(record_id)[0]["id"]
    later = _now()
    second_created = storage.create(  # 另一条记录，制造跨记录误读场景
        _record_values(later),
        ["测试报表"],
        [{"code": "P_TEST", "name": "真库测试流程"}],
        _audit("create", later, {"created": True}, "创建特殊处理记录"),
    )
    other_record_id = int(second_created["id"])
    storage.update(
        record_id,
        1,
        {
            "summary": "软删除历史附件",
            "updated_at": later,
            "updated_by_user_id": "u-1",
            "updated_by_username_snapshot": "zhangsan",
        },
        ["测试报表"],
        [{"code": "P_TEST", "name": "真库测试流程"}],
        _audit("update", later, {"updated": True}, "修改特殊处理记录"),
        record_attachment_change=RecordAttachmentChange(
            retained_ids=(), new_files=(_attachment_file("新附件.png", b"new"),)
        ),
        attachment_actor={"user_id": "u-1", "username": "zhangsan"},
    )

    history = storage.get_record_attachment(record_id, old_id)
    assert history is not None
    assert history["removed"] is True
    assert history["content"] == first
    # 用错误的 record_id 组合不得读到其它记录的附件。
    assert storage.get_record_attachment(other_record_id, old_id) is None
