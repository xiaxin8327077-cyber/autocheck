from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from auto_check.app.platform_services import PublicDictionaryItem
from auto_check.app.report_navigation_platform import ReportProcess
from auto_check.modules.report_special_processing.contracts import ValidationError
from auto_check.modules.report_special_processing.service import SpecialProcessingService
from auto_check.modules.report_special_processing.storage import (
    PROCESSES,
    RECORDS,
    SpecialProcessingStorage,
)
from auto_check.modules.report_special_processing.validator import PageQuery


NOW = datetime(2026, 9, 21, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
ACTOR = {
    "id": "admin",
    "username": "admin",
    "display_name": "管理员",
    "role": "admin",
    "capabilities": ["rsp.view", "rsp.create", "rsp.edit"],
}


class _User:
    def __init__(self, user_id: str, name: str) -> None:
        self.id = user_id
        self.username = name
        self.display_name = name
        self.active = True


class _Users:
    def __init__(self) -> None:
        self._items = {"admin": _User("admin", "管理员"), "handler": _User("handler", "处理人")}

    def list_active_users(self):
        return tuple(self._items.values())

    def get_user(self, user_id):
        return self._items.get(str(user_id))


class _Reports:
    def __init__(self) -> None:
        self.items = (
            ReportProcess("pbc_central", "人行大集中", 10, True),
            ReportProcess("pbc_template", "资管产品模板逐笔", 20, True),
            ReportProcess("credit", "征信报送", 30, True),
            ReportProcess("inactive_code", "停用原目录", 40, False),
        )

    def list_report_processes(self):
        return self.items


class _Dictionary:
    def __init__(self, extra_items=()) -> None:
        self.extra_items = list(extra_items)

    def list_active_items(self, dictionary_code):
        if dictionary_code == "rsp_extra_report_process":
            return tuple(self.extra_items)
        if dictionary_code == "business_system":
            return (PublicDictionaryItem("valuation", "估值系统", 1),)
        return ()

    def get_active_item(self, dictionary_code, item_code):
        return next(
            (item for item in self.list_active_items(dictionary_code) if item.code == str(item_code)),
            None,
        )


class _MemoryStorage:
    def __init__(self) -> None:
        self.records = {}
        self._next_id = 1

    def create(self, record, reports, processes, audit, **_kwargs):
        result = {
            **record,
            "id": self._next_id,
            "record_no": f"RSP-{self._next_id}",
            "report_processes": [dict(item) for item in processes],
            "report_process_codes": [item["code"] for item in processes],
        }
        self._next_id += 1
        self.records[result["id"]] = result
        return deepcopy(result)

    def get(self, record_id):
        value = self.records.get(record_id)
        return deepcopy(value) if value is not None else None

    def update(self, record_id, row_version, changes, reports, processes, audit, **_kwargs):
        result = self.records[record_id]
        assert result["row_version"] == row_version
        result.update(changes)
        result["report_processes"] = [dict(item) for item in processes]
        result["report_process_codes"] = [item["code"] for item in processes]
        result["row_version"] += 1
        return deepcopy(result)


def _service(dictionary: _Dictionary) -> SpecialProcessingService:
    return SpecialProcessingService(
        _MemoryStorage(), _Users(), _Reports(), now=lambda: NOW, dictionary_service=dictionary
    )


def _payload(**changes):
    value = {
        "save_mode": "record",
        "report_process_codes": ["extra", "pbc_central"],
        "report_period": "2026-09-30",
        "reports": [],
        "summary": "原摘要",
        "processing_content": "",
        "processing_script": None,
        "special_handling_at": "2026-09-21T10:00:00+08:00",
        "handler_user_id": "handler",
        "dimension": "project",
        "business_system_code": "valuation",
        "governance_owner_user_id": "admin",
        "table_name": "示例表｜t_demo",
        "field_name": "金额｜amount",
        "value_before": "1",
        "value_after": "2",
    }
    value.update(changes)
    return value


def test_catalog_merges_only_non_conflicting_active_extra_items_and_builds_pbc_tabs():
    dictionary = _Dictionary(
        [
            PublicDictionaryItem(" extra ", " 扩展报送 ", 10),
            PublicDictionaryItem("PBC_CENTRAL", "编码冲突", 20),
            PublicDictionaryItem("name_conflict", " 人行大集中 ", 30),
            PublicDictionaryItem("EXTRA", "重复编码", 40),
            PublicDictionaryItem("inactive_code", "与停用原目录冲突", 50),
            PublicDictionaryItem("bad:code", "非法编码", 60),
            PublicDictionaryItem("combined", "人行报送", 70),
        ]
    )

    catalog = _service(dictionary).catalog(ACTOR)

    assert [(item["code"], item["name"]) for item in catalog["report_processes"]] == [
        ("pbc_central", "人行大集中"),
        ("pbc_template", "资管产品模板逐笔"),
        ("credit", "征信报送"),
        ("extra", "扩展报送"),
    ]
    assert [(item["code"], item["name"]) for item in catalog["report_process_tabs"]] == [
        ("group:pbc", "人行报送"),
        ("credit", "征信报送"),
        ("extra", "扩展报送"),
    ]
    empty_catalog = _service(_Dictionary()).catalog(ACTOR)
    assert [item["code"] for item in empty_catalog["report_processes"]] == [
        "pbc_central", "pbc_template", "credit",
    ]


def test_extra_reports_follow_original_order_and_other_report_is_always_last():
    dictionary = _Dictionary([
        PublicDictionaryItem("other", " 其他报送 ", -100),
        PublicDictionaryItem("first_extra", "第一扩展报送", 10),
        PublicDictionaryItem("second_extra", "第二扩展报送", 20),
    ])
    catalog = _service(dictionary).catalog(ACTOR)
    assert [item["code"] for item in catalog["report_processes"]] == [
        "pbc_central", "pbc_template", "credit", "first_extra", "second_extra", "other",
    ]
    assert [item["code"] for item in catalog["report_process_tabs"]] == [
        "group:pbc", "credit", "first_extra", "second_extra", "other",
    ]
    assert catalog["report_processes"][-1]["name"] == "其他报送"


def test_create_and_update_keep_existing_extra_process_snapshot_after_dictionary_change():
    dictionary = _Dictionary([PublicDictionaryItem("extra", "旧扩展名称", 10)])
    service = _service(dictionary)
    created = service.create(_payload(), ACTOR, request_id="create")
    assert created["report_processes"] == [
        {"code": "extra", "name": "旧扩展名称"},
        {"code": "pbc_central", "name": "人行大集中"},
    ]

    dictionary.extra_items = [PublicDictionaryItem("extra", "新扩展名称", 10)]
    updated = service.update(
        created["id"],
        _payload(summary="仅修改摘要", row_version=created["row_version"]),
        ACTOR,
        request_id="rename",
    )
    assert updated["report_processes"][0] == {"code": "extra", "name": "旧扩展名称"}

    dictionary.extra_items = []
    retained = service.update(
        updated["id"],
        _payload(summary="字典删除后继续修改", row_version=updated["row_version"]),
        ACTOR,
        request_id="removed",
    )
    assert retained["report_processes"][0] == {"code": "extra", "name": "旧扩展名称"}

    with pytest.raises(ValidationError):
        service.create(_payload(report_process_codes=["extra"]), ACTOR, request_id="new-extra")
    with pytest.raises(ValidationError):
        service.create(_payload(report_process_codes=["group:pbc"]), ACTOR, request_id="group")


class _SqliteDatabase:
    def __init__(self) -> None:
        from sqlalchemy import create_engine

        self.engine = create_engine("sqlite://")
        with self.engine.begin() as connection:
            connection.exec_driver_sql("""
                CREATE TABLE report_special_processing_records (
                    id INTEGER PRIMARY KEY,
                    report_period DATE,
                    status TEXT,
                    report_process_code TEXT
                )
            """)
            connection.exec_driver_sql("""
                CREATE TABLE report_special_processing_processes (
                    record_id INTEGER,
                    report_process_code TEXT,
                    report_process_name_snapshot TEXT
                )
            """)

    @contextmanager
    def connect(self):
        with self.engine.connect() as connection:
            yield connection


def test_storage_pbc_tab_filter_uses_two_real_codes_and_summary_deduplicates_records():
    from sqlalchemy.dialects import mysql
    from sqlalchemy import select

    conditions = SpecialProcessingStorage._conditions({"report_process_code": "group:pbc"})
    compiled = str(
        select(RECORDS).where(*conditions).compile(
            dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "pbc_central" in compiled and "pbc_template" in compiled
    assert "group:pbc" not in compiled

    database = _SqliteDatabase()
    with database.engine.begin() as connection:
        connection.exec_driver_sql("""
            INSERT INTO report_special_processing_records (id, report_period, status, report_process_code)
            VALUES
                (1, '2026-09-30', 'pending', 'pbc_central'),
                (2, '2026-09-30', 'completed', 'pbc_central'),
                (3, '2026-09-30', 'draft', 'pbc_template'),
                (4, '2026-09-30', 'processing', 'pbc_template')
        """)
        connection.exec_driver_sql("""
            INSERT INTO report_special_processing_processes (record_id, report_process_code, report_process_name_snapshot)
            VALUES
                (1, 'pbc_central', '旧大集中'),
                (1, 'pbc_template', '资管产品模板逐笔'),
                (2, 'pbc_central', '新人行大集中'),
                (3, 'pbc_template', '资管产品模板逐笔')
        """)
    with database.engine.connect() as connection:
        filtered_ids = connection.execute(
            select(RECORDS.c.id).where(
                *SpecialProcessingStorage._conditions({"report_process_code": "group:pbc"})
            ).order_by(RECORDS.c.id)
        ).scalars().all()
    assert filtered_ids == [1, 2, 3, 4]
    by_process = SpecialProcessingStorage(database).summary_for_report_period(date(2026, 9, 30))[1]
    central = next(item for item in by_process if item["code"] == "pbc_central")
    assert central["effective_count"] == 2
    assert central["name"] in {"旧大集中", "新人行大集中"}
    assert next(item for item in by_process if item["code"] == "group:pbc") == {
        "code": "group:pbc", "name": "人行报送", "effective_count": 3,
    }
