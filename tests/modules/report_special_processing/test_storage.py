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
