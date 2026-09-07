import inspect
from datetime import datetime
from zoneinfo import ZoneInfo


def test_record_numbers_are_namespaced_and_collision_resistant():
    from auto_check.modules.report_special_processing.storage import generate_record_no

    now = datetime(2026, 8, 2, tzinfo=ZoneInfo("Asia/Shanghai"))
    values = {generate_record_no(now) for _ in range(100)}
    assert len(values) == 100
    assert all(value.startswith("RSP-20260802-") and len(value) <= 32 for value in values)


def test_storage_uses_optimistic_lock_parameterization_and_has_no_record_delete():
    from auto_check.modules.report_special_processing import storage

    source = inspect.getsource(storage.SpecialProcessingStorage)
    assert "row_version" in source
    assert ".where(" in source
    assert "processing_script" not in source.split("connection.execute(", 1)[0]
    assert "def delete_record" in source
    assert "delete(RECORDS)" in source
    assert "delete(ATTACHMENTS)" in source
    assert "ATTACHMENTS" in source
    assert "SORTS" in source


def test_storage_statistics_use_left_closed_right_open_boundaries():
    from auto_check.modules.report_special_processing import storage

    source = inspect.getsource(storage.SpecialProcessingStorage.count_by_handling_period)
    assert ">= start" in source
    assert "< end_exclusive" in source


def test_summary_for_report_period_returns_distinct_record_total():
    from auto_check.modules.report_special_processing import storage

    source = inspect.getsource(storage.SpecialProcessingStorage.summary_for_report_period)
    assert "record_total" in source
    assert "func.count().label(\"record_total\")" in source
    assert "tuple[dict[str, int], list[dict[str, Any]], int]" in inspect.getsource(
        storage.SpecialProcessingStorage
    )


def test_record_attachments_table_is_defined_with_soft_delete_columns():
    from auto_check.modules.report_special_processing import storage

    table = storage.RECORD_ATTACHMENTS
    assert table.name == "report_special_processing_record_attachments"
    column_names = {column.name for column in table.columns}
    for expected in (
        "id",
        "record_id",
        "original_file_name",
        "file_extension",
        "content_type",
        "byte_size",
        "content_sha256",
        "content",
        "created_by_user_id",
        "created_by_username_snapshot",
        "created_at",
        "removed_by_user_id",
        "removed_by_username_snapshot",
        "removed_at",
    ):
        assert expected in column_names


def test_storage_exposes_record_attachment_read_and_write_integration():
    from auto_check.modules.report_special_processing import storage

    cls_source = inspect.getsource(storage.SpecialProcessingStorage)
    assert "def list_record_attachments(" in cls_source
    assert "def get_record_attachment(" in cls_source
    assert "def _insert_record_attachments(" in cls_source
    assert "def _apply_record_attachment_change(" in cls_source
    assert "def _record_attachment_metadata(" in cls_source
    # 读取默认仅返回当前附件，可按 ID 读取历史行，并按 created_at, id 稳定排序。
    list_source = inspect.getsource(
        storage.SpecialProcessingStorage._list_record_attachments_with_connection
    )
    assert "include_removed" in list_source
    assert "attachment_ids" in list_source
    assert "removed_at.is_(None)" in list_source
    assert "created_at.asc()" in list_source
    # 创建/修改签名接受附件变化与操作者，且删除清理记录附件。
    create_sig = inspect.signature(storage.SpecialProcessingStorage.create)
    assert "record_attachment_change" in create_sig.parameters
    assert "attachment_actor" in create_sig.parameters
    update_source = inspect.getsource(storage.SpecialProcessingStorage.update)
    assert "record_attachment_change" in update_source
    assert "_apply_record_attachment_change(" in update_source
    delete_source = inspect.getsource(storage.SpecialProcessingStorage.delete_record)
    assert "delete(RECORD_ATTACHMENTS)" in delete_source


class _FakeResult:
    def __init__(self, rows=None, inserted_primary_key=(1,)):
        self._rows = list(rows or [])
        self.inserted_primary_key = inserted_primary_key
        self.lastrowid = inserted_primary_key[0]
        self.rowcount = max(len(self._rows), 1)

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one(self):
        return next(iter(self._rows[0].values()))


class _AttachmentRecordingConnection:
    """记录真实执行 SQL 并返回预置结果，用于检查仓储生成的语句。"""

    def __init__(self, current_rows):
        self.current_rows = list(current_rows)
        self.selects = []  # [(原始 statement, MySQL 编译文本)]
        self.executed = []  # 执行序列（select/update/insert）
        self._next_id = 100

    def execute(self, statement, parameters=None, **kwargs):
        compiled = str(statement.compile(dialect=_mysql_dialect()))
        keyword = compiled.lstrip().split(None, 1)[0].upper()
        if keyword == "SELECT":
            self.selects.append((statement, compiled))
            self.executed.append("select")
            return _FakeResult(rows=self.current_rows)
        if keyword == "UPDATE":
            self.executed.append("update")
            return _FakeResult(rows=[], inserted_primary_key=(0,))
        if keyword == "INSERT":
            self.executed.append("insert")
            self._next_id += 1
            return _FakeResult(rows=[], inserted_primary_key=(self._next_id,))
        raise AssertionError(f"unexpected statement: {compiled!r}")


def _mysql_dialect():
    from sqlalchemy.dialects import mysql

    return mysql.dialect()


def test_apply_record_attachment_change_selects_id_only_without_content():
    """R2：附件修改事务的当前附件查询只取 ID，不得读取 content LONGBLOB。"""
    import hashlib
    import re

    from auto_check.modules.report_special_processing import storage
    from auto_check.modules.report_special_processing.contracts import (
        RecordAttachmentChange,
        RecordAttachmentFile,
        RecordNotFoundError,
    )

    def make_file(name: str) -> RecordAttachmentFile:
        content = b"new-payload"
        return RecordAttachmentFile(
            client_id=f"client-{name}",
            file_name=name,
            file_extension=name.rsplit(".", 1)[-1].lower(),
            content_type="image/png",
            content=content,
            content_sha256=hashlib.sha256(content).hexdigest(),
        )

    storage_obj = storage.SpecialProcessingStorage(database=None)
    connection = _AttachmentRecordingConnection(
        current_rows=[{"id": 1}, {"id": 2}]
    )
    now = datetime(2026, 9, 7, 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    audit = {"action_code": "update", "changed_fields_json": "{}"}
    change = RecordAttachmentChange(retained_ids=(1,), new_files=(make_file("新附件.png"),))
    result_audit = storage_obj._apply_record_attachment_change(
        connection,
        7,
        change,
        {"user_id": "u-1", "username": "zhangsan"},
        now,
        audit,
    )

    # 恰好一条对附件表的 SELECT，且编译 SQL 不含正文列 content。
    attachment_selects = [
        compiled
        for statement, compiled in connection.selects
        if "report_special_processing_record_attachments" in compiled
    ]
    assert len(attachment_selects) == 1
    sql = attachment_selects[0]
    assert re.search(r"\bcontent\b", sql) is None, f"附件修改查询不得选择正文列：{sql}"
    # content_type / content_sha256 等近似列名不得造成误报：正则本身已按词边界区分。
    assert "report_special_processing_record_attachments.id" in sql
    # 保留排序语义与 ID 校验语义。
    assert "ORDER BY" in sql.upper()
    assert "created_at ASC" in sql
    # 行为不变：软删除未保留 ID、插入新附件、审计记录新旧 ID 集合。
    assert "update" in connection.executed
    assert "insert" in connection.executed
    import json

    changed = json.loads(result_audit["changed_fields_json"])
    field = changed["record_attachments"]
    assert field["old_ids"] == [1, 2]
    assert field["removed_ids"] == [2]
    assert field["added_ids"] == [101]
    assert field["new_ids"] == [1, 101]

    # retained_ids 引用不存在/已移除的 ID 仍然抛 RecordNotFoundError。
    connection2 = _AttachmentRecordingConnection(current_rows=[{"id": 3}])
    try:
        storage_obj._apply_record_attachment_change(
            connection2,
            7,
            RecordAttachmentChange(retained_ids=(99,), new_files=()),
            {"user_id": "u-1", "username": "zhangsan"},
            now,
            audit,
        )
    except RecordNotFoundError:
        pass
    else:
        raise AssertionError("无效 retained id 必须抛 RecordNotFoundError")
    # 无变化（保留全部、无新文件）不产生空审计字段。
    connection3 = _AttachmentRecordingConnection(current_rows=[{"id": 4}])
    same = {"action_code": "update", "changed_fields_json": '{"x": 1}'}
    result3 = storage_obj._apply_record_attachment_change(
        connection3,
        7,
        RecordAttachmentChange(retained_ids=(4,), new_files=()),
        None,
        now,
        same,
    )
    assert result3["changed_fields_json"] == '{"x": 1}'


def test_record_attachment_metadata_select_excludes_content_column():
    import re

    from sqlalchemy import select
    from sqlalchemy.dialects import mysql

    from auto_check.modules.report_special_processing import storage

    names = {column.name for column in storage.RECORD_ATTACHMENT_METADATA_COLUMNS}
    assert "content" not in names
    assert {
        "id",
        "record_id",
        "original_file_name",
        "file_extension",
        "content_type",
        "byte_size",
        "content_sha256",
        "created_by_user_id",
        "created_by_username_snapshot",
        "created_at",
        "removed_at",
    } <= names
    compiled = str(
        select(*storage.RECORD_ATTACHMENT_METADATA_COLUMNS).compile(dialect=mysql.dialect())
    )
    assert re.search(r"\bcontent\b", compiled) is None
    list_source = inspect.getsource(
        storage.SpecialProcessingStorage._list_record_attachments_with_connection
    )
    hydrate_source = inspect.getsource(
        storage.SpecialProcessingStorage._hydrate_record_attachment_audits
    )
    for source in (list_source, hydrate_source):
        assert "RECORD_ATTACHMENT_METADATA_COLUMNS" in source
        assert "select(RECORD_ATTACHMENTS)" not in source
