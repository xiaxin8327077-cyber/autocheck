from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from auto_check.db_validation.mapping_models import CrossTableMapping, FieldMapping, TableMapping
from auto_check.db_validation.mapping_storage import DbValidationMappingStorage


@dataclass
class _Result:
    rows: list[dict[str, Any]] = field(default_factory=list)
    scalar: Any = None
    lastrowid: int | None = None
    rowcount: int = 0

    def mappings(self) -> "_Result":
        return self

    def all(self) -> list[dict[str, Any]]:
        return list(self.rows)

    def first(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None

    def scalar_one(self) -> Any:
        return self.scalar

    def scalar_one_or_none(self) -> Any:
        return self.scalar


class FakeMappingDatabase:
    """轻量内存库：用 dict 存映射表行，覆盖 storage 所需读写路径。"""

    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {
            "db_validation_mapping_snapshots": [],
            "db_validation_mapping_tables": [],
            "db_validation_mapping_fields": [],
            "db_validation_cross_table_mappings": [],
            "db_validation_mapping_overrides": [],
            "db_validation_mapping_audit_logs": [],
        }
        self._seq = {name: 0 for name in self.tables}

    def seed_table(self, **values: Any) -> dict[str, Any]:
        self._seq["db_validation_mapping_tables"] += 1
        row = {
            "id": self._seq["db_validation_mapping_tables"],
            "snapshot_id": None,
            "relation_type": values["relation_type"],
            "logical_code": values["logical_code"],
            "scope_code": values.get("scope_code", ""),
            "automatic_table_name": values["automatic_table_name"],
            "override_table_name": values.get("override_table_name"),
            "effective_table_name": values.get("override_table_name") or values["automatic_table_name"],
            "mapping_status": values.get("mapping_status", "mapped"),
            "status_message": values.get("status_message"),
            "is_seed": 1,
            "updated_at": datetime.now(),
        }
        self.tables["db_validation_mapping_tables"].append(row)
        return row

    def seed_cross_table(self, **values: Any) -> dict[str, Any]:
        self._seq["db_validation_cross_table_mappings"] += 1
        row = {
            "id": self._seq["db_validation_cross_table_mappings"],
            "mapping_code": values["mapping_code"],
            "logical_code": values["logical_code"],
            "scope_code": values.get("scope_code", ""),
            "automatic_detail_field_name": values["automatic_detail_field_name"],
            "override_detail_field_name": values.get("override_detail_field_name"),
            "automatic_template_table_name": values["automatic_template_table_name"],
            "override_template_table_name": values.get("override_template_table_name"),
            "automatic_template_field_name": values["automatic_template_field_name"],
            "override_template_field_name": values.get("override_template_field_name"),
            "mapping_status": "mapped",
            "status_message": "",
            "refreshed_at": str(datetime.now()),
        }
        self.tables["db_validation_cross_table_mappings"].append(row)
        return row

    @contextmanager
    def connect(self):
        yield self

    @contextmanager
    def transaction(self):
        yield self

    def execute(self, statement: Any, params: dict[str, Any] | None = None):
        sql = str(getattr(statement, "text", statement)).strip()
        params = dict(params or {})
        upper = " ".join(sql.upper().split())

        if upper.startswith("SELECT RELATION_TYPE, LOGICAL_CODE, SCOPE_CODE, AUTOMATIC_TABLE_NAME"):
            rows = sorted(
                self.tables["db_validation_mapping_tables"],
                key=lambda item: (item["relation_type"], item["logical_code"], item["scope_code"]),
            )
            return _Result(rows=[
                {
                    "relation_type": row["relation_type"],
                    "logical_code": row["logical_code"],
                    "scope_code": row["scope_code"],
                    "automatic_table_name": row["automatic_table_name"],
                    "override_table_name": row["override_table_name"],
                    "mapping_status": row["mapping_status"],
                    "status_message": row["status_message"] or "",
                }
                for row in rows
            ])

        if upper.startswith("SELECT MAPPING_CODE, LOGICAL_CODE, SCOPE_CODE") and "FROM DB_VALIDATION_CROSS_TABLE_MAPPINGS" in upper:
            return _Result(rows=[{
                key: row.get(key)
                for key in (
                    "mapping_code", "logical_code", "scope_code",
                    "automatic_detail_field_name", "override_detail_field_name",
                    "automatic_template_table_name", "override_template_table_name",
                    "automatic_template_field_name", "override_template_field_name",
                    "mapping_status", "status_message", "refreshed_at",
                )
            } for row in self.tables["db_validation_cross_table_mappings"]])

        if "FROM DB_VALIDATION_MAPPING_OVERRIDES" in upper and "ACTIVE = 1" in upper and upper.startswith("SELECT"):
            return _Result(rows=[
                {
                    "mapping_kind": row["mapping_kind"],
                    "relation_type": row["relation_type"],
                    "logical_code": row["logical_code"],
                    "scope_code": row["scope_code"],
                    "chinese_name": row["chinese_name"],
                    "override_value": row["override_value"],
                    "active": row["active"],
                }
                for row in self.tables["db_validation_mapping_overrides"]
                if row.get("active")
            ])

        if upper.startswith("INSERT INTO DB_VALIDATION_MAPPING_SNAPSHOTS"):
            self._seq["db_validation_mapping_snapshots"] += 1
            snapshot_id = self._seq["db_validation_mapping_snapshots"]
            self.tables["db_validation_mapping_snapshots"].append({
                "id": snapshot_id,
                "signature_json": params.get("signature"),
                "refresh_source": params.get("source"),
                "status": "failed" if params.get("status") == "failed" or ":status" in sql and params.get("status") == "failed" else params.get("status", "success"),
                "table_count": int(params.get("table_count") or 0),
                "field_count": int(params.get("field_count") or 0),
                "unmapped_field_count": int(params.get("unmapped") or 0),
                "required_missing_count": int(params.get("required_missing") or 0),
                "missing_physical_count": int(params.get("missing_physical") or 0),
                "error_message": params.get("error_message") or params.get("error"),
                "created_at": params.get("created_at"),
            })
            # Detect failed insert by presence of error param and status literal in SQL
            if "'failed'" in sql.lower() or params.get("status") == "failed":
                self.tables["db_validation_mapping_snapshots"][-1]["status"] = "failed"
            result = _Result(scalar=snapshot_id, lastrowid=snapshot_id)
            return result

        if upper.startswith("UPDATE DB_VALIDATION_MAPPING_TABLES") and "SET SNAPSHOT_ID" in upper:
            for row in self.tables["db_validation_mapping_tables"]:
                if (
                    row["relation_type"] == params["relation_type"]
                    and row["logical_code"] == params["logical_code"]
                    and row["scope_code"] == params["scope_code"]
                ):
                    row["snapshot_id"] = params["snapshot_id"]
                    row["automatic_table_name"] = params["automatic"]
                    row["effective_table_name"] = row["override_table_name"] or params["automatic"]
                    row["mapping_status"] = params["status"]
                    row["status_message"] = params.get("message")
                    row["updated_at"] = params["updated_at"]
            return _Result()

        if upper.startswith("SELECT ID FROM DB_VALIDATION_MAPPING_TABLES"):
            for row in self.tables["db_validation_mapping_tables"]:
                if (
                    row["relation_type"] == params["relation_type"]
                    and row["logical_code"] == params["logical_code"]
                    and row["scope_code"] == params["scope_code"]
                ):
                    return _Result(scalar=row["id"])
            return _Result(scalar=None)

        if upper.startswith("INSERT INTO DB_VALIDATION_MAPPING_FIELDS"):
            self._seq["db_validation_mapping_fields"] += 1
            self.tables["db_validation_mapping_fields"].append({
                "id": self._seq["db_validation_mapping_fields"],
                "snapshot_id": params["snapshot_id"],
                "table_mapping_id": params["table_id"],
                "chinese_name": params.get("chinese_name"),
                "automatic_field_name": params.get("automatic_field_name"),
                "override_field_name": params.get("override_field_name"),
                "effective_field_name": params.get("effective_field_name"),
                "mapping_status": params["mapping_status"],
                "is_required": params.get("is_required"),
                "status_message": params.get("status_message"),
                "updated_at": params.get("updated_at"),
            })
            return _Result(lastrowid=self._seq["db_validation_mapping_fields"])

        if "FROM DB_VALIDATION_MAPPING_SNAPSHOTS" in upper and "STATUS" in upper and "ORDER BY ID DESC" in upper:
            status_filter = "success"
            if "STATUS='FAILED'" in upper.replace(" ", "") or "STATUS = 'FAILED'" in upper:
                status_filter = "failed"
            elif ":STATUS" in upper and params.get("status"):
                status_filter = str(params["status"])
            elif "STATUS='SUCCESS'" in upper.replace(" ", "") or "STATUS = 'SUCCESS'" in upper or "STATUS = 'success'" in sql:
                status_filter = "success"
            rows = [row for row in self.tables["db_validation_mapping_snapshots"] if row["status"] == status_filter]
            rows = sorted(rows, key=lambda item: item["id"], reverse=True)
            if "SELECT ID," in upper or upper.startswith("SELECT ID FROM"):
                if not rows:
                    return _Result(scalar=None, rows=[])
                if "REFRESH_SOURCE" in upper or "ERROR_MESSAGE" in upper:
                    return _Result(rows=[rows[0]], scalar=rows[0]["id"])
                return _Result(scalar=rows[0]["id"], rows=[{"id": rows[0]["id"]}])
            if not rows:
                return _Result(rows=[], scalar=None)
            return _Result(rows=[rows[0]], scalar=rows[0]["id"])

        if "FROM DB_VALIDATION_MAPPING_FIELDS F" in upper and "JOIN DB_VALIDATION_MAPPING_TABLES" in upper:
            snapshot_id = params.get("snapshot_id")
            rows = []
            for field_row in self.tables["db_validation_mapping_fields"]:
                if snapshot_id is not None and field_row["snapshot_id"] != snapshot_id:
                    continue
                if "F.IS_REQUIRED = 1" in upper and not field_row.get("is_required"):
                    continue
                if "F.MAPPING_STATUS IN ('REQUIRED_MISSING', 'MISSING_PHYSICAL')" in upper:
                    if field_row["mapping_status"] not in {"required_missing", "missing_physical"}:
                        continue
                if "MAPPING_STATUS = 'MAPPED'" in upper.replace(" ", "") or "MAPPING_STATUS='MAPPED'" in upper.replace(" ", ""):
                    if field_row["mapping_status"] != "mapped":
                        continue
                table = next(
                    (
                        item for item in self.tables["db_validation_mapping_tables"]
                        if item["id"] == field_row["table_mapping_id"]
                    ),
                    None,
                )
                if table is None:
                    continue
                # 处理新的查询模式：按 relation_type/logical_code/scope_code/chinese_name 过滤
                if "T.RELATION_TYPE=:RELATION_TYPE" in upper.replace(" ", "") or "T.RELATION_TYPE = :RELATION_TYPE" in upper.replace(" ", ""):
                    if table["relation_type"] != params.get("relation_type"):
                        continue
                    if table["logical_code"] != params.get("logical_code"):
                        continue
                    if table["scope_code"] != params.get("scope_code"):
                        continue
                    if field_row["chinese_name"] != params.get("chinese_name"):
                        continue
                rows.append({
                    "id": field_row["id"],
                    "effective_table_name": table["effective_table_name"],
                    "chinese_name": field_row["chinese_name"],
                    "effective_field_name": field_row["effective_field_name"],
                    "mapping_status": field_row["mapping_status"],
                    "relation_type": table["relation_type"],
                    "logical_code": table["logical_code"],
                    "scope_code": table["scope_code"],
                    "automatic_field_name": field_row["automatic_field_name"],
                    "override_field_name": field_row["override_field_name"],
                    "is_required": field_row["is_required"],
                    "status_message": field_row["status_message"] or "",
                })
            return _Result(rows=rows)

        if upper.startswith("SELECT UNMAPPED_FIELD_COUNT FROM DB_VALIDATION_MAPPING_SNAPSHOTS"):
            for row in self.tables["db_validation_mapping_snapshots"]:
                if row["id"] == params["snapshot_id"]:
                    return _Result(scalar=row["unmapped_field_count"])
            return _Result(scalar=0)

        if upper.startswith("SELECT ID, OVERRIDE_VALUE FROM DB_VALIDATION_MAPPING_OVERRIDES"):
            for row in self.tables["db_validation_mapping_overrides"]:
                if (
                    row["mapping_kind"] == params["kind"]
                    and row["relation_type"] == params["relation_type"]
                    and row["logical_code"] == params["logical_code"]
                    and row["scope_code"] == params["scope_code"]
                    and row["chinese_name"] == params["chinese_name"]
                    and (("ACTIVE=1" not in upper.replace(" ", "") and "AND ACTIVE=1" not in upper.replace(" ", "")) or row["active"])
                ):
                    if "ACTIVE=1" in upper.replace(" ", "") and not row["active"]:
                        continue
                    return _Result(rows=[{
                        "id": row["id"],
                        "override_value": row["override_value"],
                    }])
            return _Result(rows=[])

        if upper.startswith("INSERT INTO DB_VALIDATION_MAPPING_OVERRIDES"):
            existing = None
            for row in self.tables["db_validation_mapping_overrides"]:
                if (
                    row["mapping_kind"] == params["kind"]
                    and row["relation_type"] == params["relation_type"]
                    and row["logical_code"] == params["logical_code"]
                    and row["scope_code"] == params["scope_code"]
                    and row["chinese_name"] == params["chinese_name"]
                ):
                    existing = row
                    break
            if existing is None:
                self._seq["db_validation_mapping_overrides"] += 1
                existing = {
                    "id": self._seq["db_validation_mapping_overrides"],
                    "mapping_kind": params["kind"],
                    "relation_type": params["relation_type"],
                    "logical_code": params["logical_code"],
                    "scope_code": params["scope_code"],
                    "chinese_name": params["chinese_name"],
                    "created_by": params["operator"],
                    "created_at": params["now"],
                }
                self.tables["db_validation_mapping_overrides"].append(existing)
            existing.update({
                "override_value": params["value"],
                "reason": params["reason"],
                "active": 1,
                "updated_by": params["operator"],
                "updated_at": params["now"],
            })
            return _Result(lastrowid=existing["id"])

        if upper.startswith("SELECT ID FROM DB_VALIDATION_MAPPING_OVERRIDES"):
            for row in self.tables["db_validation_mapping_overrides"]:
                if (
                    row["mapping_kind"] == params["kind"]
                    and row["relation_type"] == params["relation_type"]
                    and row["logical_code"] == params["logical_code"]
                    and row["scope_code"] == params["scope_code"]
                    and row["chinese_name"] == params["chinese_name"]
                ):
                    return _Result(scalar=row["id"])
            return _Result(scalar=None)

        if upper.startswith("INSERT INTO DB_VALIDATION_MAPPING_AUDIT_LOGS"):
            self._seq["db_validation_mapping_audit_logs"] += 1
            self.tables["db_validation_mapping_audit_logs"].append({
                "id": self._seq["db_validation_mapping_audit_logs"],
                **params,
            })
            return _Result(lastrowid=self._seq["db_validation_mapping_audit_logs"])

        if upper.startswith("UPDATE DB_VALIDATION_MAPPING_TABLES") and "OVERRIDE_TABLE_NAME" in upper:
            for row in self.tables["db_validation_mapping_tables"]:
                if (
                    row["relation_type"] == params["relation_type"]
                    and row["logical_code"] == params["logical_code"]
                    and row["scope_code"] == params["scope_code"]
                ):
                    if params.get("value") is not None or "OVERRIDE_TABLE_NAME=:VALUE" in upper:
                        if "NULL" in upper and "OVERRIDE_TABLE_NAME=NULL" in upper.replace(" ", ""):
                            row["override_table_name"] = None
                            row["effective_table_name"] = row["automatic_table_name"]
                        else:
                            row["override_table_name"] = params.get("value")
                            row["effective_table_name"] = params.get("value")
                    row["updated_at"] = params.get("now")
            return _Result()

        if upper.startswith("UPDATE DB_VALIDATION_MAPPING_FIELDS"):
            # 新 SQL 模式：按 f.id 直接匹配
            if "WHEREF.ID=:FIELD_ID" in upper.replace(" ", ""):
                field_id = params.get("field_id")
                for field_row in self.tables["db_validation_mapping_fields"]:
                    if field_row["id"] == field_id:
                        field_row["override_field_name"] = params.get("value")
                        field_row["effective_field_name"] = params.get("value")
                        field_row["mapping_status"] = "mapped"
                        field_row["updated_at"] = params.get("now")
                        break
                return _Result()
            # 旧 SQL 模式：按 snapshot_id + relation_type + logical_code + scope_code + chinese_name
            snapshot_id = params.get("snapshot_id")
            for field_row in self.tables["db_validation_mapping_fields"]:
                if snapshot_id is not None and field_row["snapshot_id"] != snapshot_id:
                    continue
                table = next(
                    (
                        item for item in self.tables["db_validation_mapping_tables"]
                        if item["id"] == field_row["table_mapping_id"]
                    ),
                    None,
                )
                if table is None:
                    continue
                if "T.RELATION_TYPE" in upper.replace(" ", ""):
                    if table["relation_type"] != params.get("relation_type"):
                        continue
                    if table["logical_code"] != params.get("logical_code"):
                        continue
                    if table["scope_code"] != params.get("scope_code"):
                        continue
                if field_row.get("chinese_name") != params.get("chinese_name"):
                    continue
                if "OVERRIDE_FIELD_NAME=NULL" in upper.replace(" ", ""):
                    field_row["override_field_name"] = None
                    field_row["effective_field_name"] = field_row["automatic_field_name"]
                    if field_row["automatic_field_name"]:
                        field_row["mapping_status"] = "mapped"
                        field_row["status_message"] = None
                    elif field_row.get("is_required"):
                        field_row["mapping_status"] = "required_missing"
                        field_row["status_message"] = f"规则必需字段缺失：{field_row['chinese_name']}"
                    else:
                        field_row["mapping_status"] = "unmapped"
                        field_row["status_message"] = f"未找到字段映射：{field_row['chinese_name']}"
                else:
                    field_row["override_field_name"] = params.get("value")
                    field_row["effective_field_name"] = params.get("value")
                    field_row["mapping_status"] = "mapped"
                field_row["updated_at"] = params.get("now")
            return _Result()

        if upper.startswith("UPDATE DB_VALIDATION_CROSS_TABLE_MAPPINGS"):
            count = 0
            for row in self.tables["db_validation_cross_table_mappings"]:
                mapping_code = params.get("mapping_code", params.get("chinese_name"))
                if row["mapping_code"] != mapping_code:
                    continue
                count += 1
                if "template_table" not in params:
                    row["override_detail_field_name"] = None
                    row["override_template_table_name"] = None
                    row["override_template_field_name"] = None
                else:
                    row["override_detail_field_name"] = None
                    row["override_template_table_name"] = params["template_table"]
                    row["override_template_field_name"] = params["template_field"]
            return _Result(rowcount=count)

        if "COUNT(*) AS FIELD_COUNT" in upper and "FROM DB_VALIDATION_MAPPING_FIELDS" in upper:
            snapshot_id = params.get("snapshot_id")
            rows = [f for f in self.tables["db_validation_mapping_fields"] if f["snapshot_id"] == snapshot_id]
            mapped = sum(1 for f in rows if f["mapping_status"] == "mapped")
            unmapped = sum(1 for f in rows if f["mapping_status"] == "unmapped")
            required_missing = sum(1 for f in rows if f["mapping_status"] == "required_missing")
            missing_physical = sum(1 for f in rows if f["mapping_status"] == "missing_physical")
            return _Result(rows=[{
                "field_count": len(rows),
                "mapped": mapped,
                "unmapped": unmapped,
                "required_missing": required_missing,
                "missing_physical": missing_physical,
            }])

        if upper.startswith("UPDATE DB_VALIDATION_MAPPING_SNAPSHOTS") and "SET FIELD_COUNT" in upper:
            for row in self.tables["db_validation_mapping_snapshots"]:
                if row["id"] == params.get("snapshot_id"):
                    row["field_count"] = params.get("field_count")
                    row["unmapped_field_count"] = params.get("unmapped")
                    row["required_missing_count"] = params.get("required_missing")
                    row["missing_physical_count"] = params.get("missing_physical")
            return _Result()

        if upper.startswith("UPDATE DB_VALIDATION_MAPPING_OVERRIDES") and "ACTIVE=0" in upper.replace(" ", ""):
            for row in self.tables["db_validation_mapping_overrides"]:
                if row["id"] == params["override_id"]:
                    row["active"] = 0
                    row["reason"] = params["reason"]
                    row["updated_by"] = params["operator"]
                    row["updated_at"] = params["now"]
            return _Result()

        raise AssertionError(f"Unsupported SQL in FakeMappingDatabase: {sql}")


def test_table_mapping_accepts_refresh_timestamp_returned_by_storage_query():
    mapping = TableMapping(
        relation_type="detail",
        logical_code="ZG09",
        scope_code="",
        automatic_table_name="zg09",
        refreshed_at="2026-08-13 15:45:52",
    )

    assert mapping.to_payload()["refreshed_at"] == "2026-08-13 15:45:52"


def test_load_tables_ignores_unexpected_database_columns():
    class ExtraColumnDatabase(FakeMappingDatabase):
        def execute(self, statement: Any, params: dict[str, Any] | None = None):
            result = super().execute(statement, params)
            sql = str(getattr(statement, "text", statement)).upper()
            if "SELECT RELATION_TYPE, LOGICAL_CODE, SCOPE_CODE, AUTOMATIC_TABLE_NAME" in sql:
                for row in result.rows:
                    row["driver_extra_column"] = "ignored"
            return result

    db = ExtraColumnDatabase()
    db.seed_table(relation_type="detail", logical_code="ZG09", automatic_table_name="zg09")

    mappings = DbValidationMappingStorage(db).load_tables()

    assert len(mappings) == 1
    assert mappings[0].logical_code == "ZG09"


def test_load_tables_is_compatible_with_model_without_refreshed_at(monkeypatch):
    class LegacyTableMapping:
        def __init__(self, relation_type, logical_code, scope_code, automatic_table_name,
                     override_table_name=None, mapping_status="mapped", status_message=""):
            self.logical_code = logical_code

    db = FakeMappingDatabase()
    db.seed_table(relation_type="detail", logical_code="ZG09", automatic_table_name="zg09")
    monkeypatch.setattr("auto_check.db_validation.mapping_storage.TableMapping", LegacyTableMapping)

    mappings = DbValidationMappingStorage(db).load_tables()

    assert mappings[0].logical_code == "ZG09"


def test_save_snapshot_and_load_active_overrides():
    db = FakeMappingDatabase()
    db.seed_table(relation_type="detail", logical_code="ZG01", automatic_table_name="zg01_old")
    storage = DbValidationMappingStorage(db)

    catalog = storage.save_snapshot(
        signature=("sig",),
        refresh_source="manual",
        tables=[TableMapping("detail", "ZG01", "", "zg01_new")],
        fields=[
            FieldMapping("detail", "ZG01", "", "产品代码", "projcode", mapping_status="mapped", is_required=True),
            FieldMapping("detail", "ZG01", "", "", "orphan", mapping_status="unmapped"),
        ],
    )

    assert catalog.table_for("detail", "ZG01") == "zg01_new"
    assert catalog.field_for("zg01_new", "产品代码") == "projcode"
    status = storage.status_payload()
    assert status["initialized"] is True
    assert status["unmapped_field_count"] == 1
    assert storage.load_active_overrides() == []


def test_required_missing_query_excludes_optional_unmapped_fields():
    db = FakeMappingDatabase()
    db.seed_table(relation_type="detail", logical_code="ZG06", automatic_table_name="zg06")
    storage = DbValidationMappingStorage(db)
    storage.save_snapshot(
        signature=("sig",),
        refresh_source="manual",
        tables=[TableMapping("detail", "ZG06", "", "zg06")],
        fields=[
            FieldMapping(
                "detail", "ZG06", "", "资产收益权内部编码", None,
                mapping_status="required_missing", is_required=True,
            ),
            FieldMapping(
                "detail", "ZG06", "", "数据管理机构", None,
                mapping_status="unmapped", is_required=False,
            ),
        ],
    )

    missing = storage.required_missing_for_tables(["ZG06"])

    assert [item["chinese_name"] for item in missing] == ["资产收益权内部编码"]


def test_field_override_only_updates_latest_success_snapshot():
    db = FakeMappingDatabase()
    db.seed_table(relation_type="detail", logical_code="ZG01", automatic_table_name="zg01")
    storage = DbValidationMappingStorage(db)

    storage.save_snapshot(
        signature=("old",),
        refresh_source="manual",
        tables=[TableMapping("detail", "ZG01", "", "zg01")],
        fields=[FieldMapping("detail", "ZG01", "", "产品代码", "projcode_old", mapping_status="mapped")],
    )
    old_snapshot_id = db.tables["db_validation_mapping_snapshots"][0]["id"]
    storage.save_snapshot(
        signature=("new",),
        refresh_source="manual",
        tables=[TableMapping("detail", "ZG01", "", "zg01")],
        fields=[FieldMapping("detail", "ZG01", "", "产品代码", "projcode_old", mapping_status="mapped")],
    )
    new_snapshot_id = db.tables["db_validation_mapping_snapshots"][1]["id"]

    storage.save_override(
        mapping_kind="field",
        relation_type="detail",
        logical_code="ZG01",
        scope_code="",
        chinese_name="产品代码",
        override_value="projcode_new",
        reason="人工调整",
        operator_user_id="u1",
    )

    old_fields = [row for row in db.tables["db_validation_mapping_fields"] if row["snapshot_id"] == old_snapshot_id]
    new_fields = [row for row in db.tables["db_validation_mapping_fields"] if row["snapshot_id"] == new_snapshot_id]
    assert old_fields[0]["override_field_name"] is None
    assert old_fields[0]["effective_field_name"] == "projcode_old"
    assert new_fields[0]["override_field_name"] == "projcode_new"
    assert new_fields[0]["effective_field_name"] == "projcode_new"
    overrides = storage.load_active_overrides()
    assert len(overrides) == 1
    assert overrides[0]["override_value"] == "projcode_new"


def test_restore_optional_field_without_automatic_mapping_returns_to_unmapped():
    db = FakeMappingDatabase()
    db.seed_table(relation_type="detail", logical_code="ZG06", automatic_table_name="zg06")
    storage = DbValidationMappingStorage(db)
    storage.save_snapshot(
        signature=("optional",),
        refresh_source="manual",
        tables=[TableMapping("detail", "ZG06", "", "zg06")],
        fields=[
            FieldMapping(
                "detail", "ZG06", "", "数据管理机构", None,
                mapping_status="unmapped", is_required=False,
            ),
        ],
    )
    target = dict(
        mapping_kind="field",
        relation_type="detail",
        logical_code="ZG06",
        scope_code="",
        chinese_name="数据管理机构",
        operator_user_id="u1",
    )

    storage.save_override(
        **target,
        override_value="data_manage_org",
        reason="人工调整",
    )
    storage.restore_override(**target, reason="恢复默认")

    field = db.tables["db_validation_mapping_fields"][0]
    assert field["override_field_name"] is None
    assert field["effective_field_name"] is None
    assert field["mapping_status"] == "unmapped"
    assert field["is_required"] is False


def test_record_failed_snapshot_keeps_previous_success_status():
    db = FakeMappingDatabase()
    db.seed_table(relation_type="detail", logical_code="ZG01", automatic_table_name="zg01")
    storage = DbValidationMappingStorage(db)
    storage.save_snapshot(
        signature=("ok",),
        refresh_source="manual",
        tables=[TableMapping("detail", "ZG01", "", "zg01")],
        fields=[FieldMapping("detail", "ZG01", "", "产品代码", "projcode", mapping_status="mapped")],
    )

    storage.record_failed_snapshot(
        signature=("bad",),
        refresh_source="manual",
        error_message="连接失败",
    )

    status = storage.status_payload()
    assert status["initialized"] is True
    assert status["refresh_source"] == "manual"
    assert status["last_error"] == "" or status["last_failed_at"]
    assert status["last_failed_at"]
    assert "连接失败" in status["last_error"] or any(
        row["status"] == "failed" for row in db.tables["db_validation_mapping_snapshots"]
    )
    failed = [row for row in db.tables["db_validation_mapping_snapshots"] if row["status"] == "failed"]
    assert len(failed) == 1
    assert failed[0]["error_message"] == "连接失败"


def test_successful_refresh_after_failure_clears_stale_last_error():
    db = FakeMappingDatabase()
    db.seed_table(relation_type="detail", logical_code="ZG01", automatic_table_name="zg01")
    storage = DbValidationMappingStorage(db)
    storage.record_failed_snapshot(
        signature=("bad",), refresh_source="manual", error_message="旧失败",
    )
    storage.save_snapshot(
        signature=("ok",), refresh_source="manual",
        tables=[TableMapping("detail", "ZG01", "", "zg01")],
        fields=[FieldMapping("detail", "ZG01", "", "产品代码", "projcode", mapping_status="mapped")],
    )

    status = storage.status_payload()

    assert status["last_error"] == ""
    assert status["last_failed_at"] == ""


def test_cross_table_override_and_restore_update_catalog_and_audit():
    db = FakeMappingDatabase()
    db.seed_table(relation_type="detail", logical_code="ZG09", automatic_table_name="zg09")
    db.seed_cross_table(
        mapping_code="ZG09:1:asset", logical_code="ZG09", scope_code="1",
        automatic_detail_field_name="asset", automatic_template_table_name="template_1",
        automatic_template_field_name="f1",
    )
    storage = DbValidationMappingStorage(db)
    storage.save_snapshot(
        signature=("ok",), refresh_source="manual",
        tables=[TableMapping("detail", "ZG09", "", "zg09")], fields=[],
    )

    target = dict(
        mapping_kind="cross_table", relation_type="cross_table", logical_code="ZG09",
        scope_code="1", chinese_name="ZG09:1:asset", operator_user_id="u1",
    )
    override = '{"template_table":"template_new","template_field":"f1_new"}'
    storage.save_override(**target, override_value=override, reason="模板调整")
    current = storage.latest_catalog().cross_table_mappings_for("ZG09", "1")[0]
    assert current.effective_detail_field_name == "asset"
    assert current.effective_template_table_name == "template_new"
    assert current.effective_template_field_name == "f1_new"
    assert current.difference_fields == ("template_table", "template_field")

    storage.restore_override(**target, reason="恢复默认")
    restored = storage.latest_catalog().cross_table_mappings_for("ZG09", "1")[0]
    assert restored.effective_detail_field_name == "asset"
    assert restored.effective_template_field_name == "f1"
    assert len(db.tables["db_validation_mapping_audit_logs"]) == 2


def test_cross_table_mapping_ignores_legacy_detail_field_override():
    db = FakeMappingDatabase()
    db.seed_cross_table(
        mapping_code="ZG09:1:asset", logical_code="ZG09", scope_code="1",
        automatic_detail_field_name="asset", override_detail_field_name="asset_old_override",
        automatic_template_table_name="template_1", automatic_template_field_name="f1",
    )

    current = DbValidationMappingStorage(db).load_cross_table_mappings()[0]

    assert current.effective_detail_field_name == "asset"
    assert "detail_field" not in current.difference_fields


def test_save_override_recalculates_counts_before_transaction_connection_closes():
    class ClosingTransactionDatabase(FakeMappingDatabase):
        connection_closed = False

        @contextmanager
        def transaction(self):
            self.connection_closed = False
            try:
                yield self
            finally:
                self.connection_closed = True

        def execute(self, statement: Any, params: dict[str, Any] | None = None):
            if self.connection_closed:
                raise RuntimeError("connection is closed")
            return super().execute(statement, params)

    db = ClosingTransactionDatabase()
    db.seed_cross_table(
        mapping_code="ZG09:1:asset", logical_code="ZG09", scope_code="1",
        automatic_detail_field_name="asset", automatic_template_table_name="template_1",
        automatic_template_field_name="f1",
    )

    DbValidationMappingStorage(db).save_override(
        mapping_kind="cross_table", relation_type="cross_table", logical_code="ZG09",
        scope_code="1", chinese_name="ZG09:1:asset",
        override_value='{"template_table":"template_new","template_field":"f1_new"}',
        reason="模板调整", operator_user_id="u1",
    )
