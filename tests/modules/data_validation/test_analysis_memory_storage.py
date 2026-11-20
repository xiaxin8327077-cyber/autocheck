from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re

from sqlalchemy import create_engine, func, select

from auto_check.modules.data_validation.storage import METADATA, RuleStorage
from tests.modules.data_validation.support import MemoryDatabase


CONTEXT = {"source_id": "src", "source_name": "测试报表", "dialect": "mysql", "doc_sha256": "a" * 64, "doc_version": 1,
           "model_id": "local", "prompt_fingerprint": "p", "knowledge_fingerprint": "k"}
REQUEST = "当前产品的单位净值通常不超过10"
BASELINE = {"table_name": "products", "report_category": "B", "rule_type": "field_compare", "has_join": False,
            "has_alternatives": False, "unsupported": False, "unstructured_review": False, "requires_selection": False}


def test_memory_survives_service_instances_and_keeps_only_reusable_data():
    database = MemoryDatabase()
    RuleStorage(database).remember_analysis_memory({**CONTEXT, "user_id": "A"}, REQUEST, {
        **BASELINE, "sql": "private sql", "test_cases": [123], "session": "private session", "operator": "A"})
    storage = RuleStorage(database)
    matches = storage.find_analysis_memories({**CONTEXT, "user_id": "B"}, REQUEST)
    assert matches == [{"request_text": REQUEST, "baseline": BASELINE}]
    for changed in [dict(source_id="src2"), dict(doc_version=2), dict(doc_sha256="b" * 64), dict(prompt_fingerprint="q"),
                    dict(knowledge_fingerprint="z"), dict(dialect="postgresql")]:
        assert not storage.find_analysis_memories({**CONTEXT, **changed}, REQUEST)
    assert storage.find_analysis_memories(CONTEXT, "当前产品的单位净值通常不超过25")[0]["request_text"] == REQUEST
    assert storage.find_analysis_memories(CONTEXT, "产品的单位净值一般不得超过25")[0]["request_text"] == REQUEST
    assert storage.find_analysis_memories(CONTEXT, "换一种措辞") == matches  # recent examples remain available to the model


def test_same_text_with_distinct_grounded_fields_stays_ambiguous_after_retries():
    database = MemoryDatabase()
    storage = RuleStorage(database)
    for name in ["net", "total_net", "net"]:
        storage.remember_analysis_memory(CONTEXT, REQUEST, {**BASELINE, "field_bindings": [{"field": name, "role": "metric"}]})
    rows = storage.find_analysis_memories(CONTEXT, REQUEST)
    assert len(rows) == 2
    assert {row["baseline"]["field_bindings"][0]["field"] for row in rows} == {"net", "total_net"}
    assert all(row["baseline"]["requires_selection"] for row in rows)
    assert storage.find_analysis_memories(CONTEXT, REQUEST, limit=1)[0]["baseline"]["requires_selection"]


def test_concurrent_recordings_deduplicate_and_reopen(tmp_path):
    engine = create_engine("sqlite:///" + (tmp_path / "memory.sqlite").as_posix())
    try:
        METADATA.create_all(engine)
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda _: RuleStorage(engine).remember_analysis_memory(CONTEXT, REQUEST, BASELINE), range(20)))
        table = METADATA.tables["data_validation_analysis_memories"]
        with engine.connect() as conn:
            assert conn.execute(select(func.count()).select_from(table)).scalar_one() == 1
        engine.dispose()
        assert RuleStorage(engine).find_analysis_memories(CONTEXT, REQUEST) == [{"request_text": REQUEST, "baseline": BASELINE}]
    finally:
        engine.dispose()


def test_filtered_example_retains_predicate_structure_and_excludes_query_contents():
    database = MemoryDatabase()
    storage = RuleStorage(database)
    baseline = {**BASELINE, "report_category": "group:pbc", "expression": {"logic": "any", "conditions": [
        {"left": "net", "op": "gt", "right_type": "value", "right": 10}, {"left": "net", "op": "is_null"},
    ]}, "filters": [{"field": "kind", "op": "in", "value": ["private"], "confirmed": True}], "sql_preview": "SELECT * FROM t"}
    storage.remember_analysis_memory(CONTEXT, REQUEST, baseline)
    storage.remember_analysis_memory(CONTEXT, REQUEST, {**baseline, "expression": {"logic": "any", "conditions": baseline["expression"]["conditions"][::-1]}})
    for request in ["请检查大于零。附 SQL：SELECT * FROM t", "这次请执行SELECT 1", '请检查如下测试样本 [{"account":"business row"}]']:
        storage.remember_analysis_memory(CONTEXT, request, baseline)
    stored, = storage.find_analysis_memories(CONTEXT, REQUEST)
    assert stored["baseline"]["expression"] == baseline["expression"]
    assert stored["baseline"]["filters"] == [{"field": "kind", "op": "in", "table": "base"}]
    assert not stored["baseline"]["has_alternatives"] and "private" not in str(stored) and "sql_preview" not in str(stored)


def test_analysis_memory_migration_columns_and_indexes_match_metadata():
    package = Path(__file__).resolve().parents[3] / "src/auto_check/modules/data_validation"
    assert json.loads((package / "manifest.json").read_text(encoding="utf-8"))["schema_version"] >= 12
    ddl = (package / "migrations/012_analysis_memories.sql").read_text(encoding="utf-8")
    table = METADATA.tables["data_validation_analysis_memories"]
    assert set(re.findall(r"^    (\w+) (?:INTEGER|VARCHAR|TEXT)\b", ddl, re.M)) == set(table.c.keys())
    assert {idx.name: tuple(c.name for c in idx.columns) for idx in table.indexes} == {
        name: tuple(cols.split(", ")) for name, cols in re.findall(r"^    KEY (\w+) \(([^)]+)\)", ddl, re.M)}
    assert table.c.memory_key.unique and "UNIQUE KEY dv_memory_unique (memory_key)" in ddl
