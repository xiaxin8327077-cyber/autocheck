from __future__ import annotations

import json
import inspect
from typing import Any, Iterable

from sqlalchemy import bindparam, text

from auto_check.app.time_utils import beijing_now
from auto_check.db_validation.mapping_models import CrossTableMapping, FieldMapping, TableMapping
from auto_check.db_validation.metadata import TableFieldCatalog


def _cross_table_override_values(value: str) -> dict[str, str]:
    try:
        payload = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("跨表映射值格式不合法") from exc
    if not isinstance(payload, dict):
        raise ValueError("跨表映射值格式不合法")
    result = {
        "template_table": str(payload.get("template_table") or "").strip(),
        "template_field": str(payload.get("template_field") or "").strip(),
    }
    if not all(result.values()):
        raise ValueError("跨表映射值不能为空")
    return result


class DbValidationMappingStorage:
    def __init__(self, database: Any) -> None:
        self.database = database

    def load_tables(self) -> tuple[TableMapping, ...]:
        with self.database.connect() as connection:
            rows = connection.execute(text("""
                SELECT relation_type, logical_code, scope_code, automatic_table_name,
                       override_table_name, mapping_status, COALESCE(status_message, '') status_message,
                       CAST(updated_at AS CHAR) refreshed_at
                FROM db_validation_mapping_tables
                ORDER BY relation_type, logical_code, scope_code
            """)).mappings().all()
        accepted = inspect.signature(TableMapping).parameters
        result = []
        for row in rows:
            values = {
                "relation_type": str(row.get("relation_type") or ""),
                "logical_code": str(row.get("logical_code") or ""),
                "scope_code": str(row.get("scope_code") or ""),
                "automatic_table_name": str(row.get("automatic_table_name") or ""),
                "override_table_name": str(row.get("override_table_name") or "") or None,
                "mapping_status": str(row.get("mapping_status") or "mapped"),
                "status_message": str(row.get("status_message") or ""),
                "refreshed_at": str(row.get("refreshed_at") or ""),
            }
            result.append(TableMapping(**{key: value for key, value in values.items() if key in accepted}))
        return tuple(result)

    def load_active_overrides(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(text("""
                SELECT mapping_kind, relation_type, logical_code, scope_code,
                       chinese_name, override_value, active
                FROM db_validation_mapping_overrides
                WHERE active = 1
            """)).mappings().all()
        return [dict(row) for row in rows]

    def load_cross_table_mappings(self) -> tuple[CrossTableMapping, ...]:
        with self.database.connect() as connection:
            rows = connection.execute(text("""
                SELECT mapping_code, logical_code, scope_code,
                       automatic_detail_field_name, override_detail_field_name,
                       automatic_template_table_name, override_template_table_name,
                       automatic_template_field_name, override_template_field_name,
                       mapping_status, COALESCE(status_message, '') status_message,
                       CAST(refreshed_at AS CHAR) refreshed_at
                FROM db_validation_cross_table_mappings
                ORDER BY logical_code, scope_code, mapping_code
            """)).mappings().all()
        return tuple(CrossTableMapping(**dict(row)) for row in rows)

    def effective_table(self, relation_type: str, logical_code: str, scope_code: str = "") -> str:
        for mapping in self.load_tables():
            if (mapping.relation_type, mapping.logical_code, mapping.scope_code) == (
                relation_type,
                logical_code,
                scope_code,
            ):
                return mapping.effective_table_name
        raise KeyError(f"{relation_type}.{logical_code}.{scope_code}")

    def latest_catalog(self) -> TableFieldCatalog | None:
        with self.database.connect() as connection:
            snapshot_id = connection.execute(text("""
                SELECT id FROM db_validation_mapping_snapshots
                WHERE status = 'success' ORDER BY id DESC LIMIT 1
            """)).scalar_one_or_none()
            if snapshot_id is None:
                return None
            rows = connection.execute(text("""
                SELECT t.effective_table_name, f.chinese_name, f.effective_field_name,
                       f.mapping_status
                FROM db_validation_mapping_fields f
                JOIN db_validation_mapping_tables t ON t.id = f.table_mapping_id
                WHERE f.snapshot_id = :snapshot_id
                  AND f.mapping_status = 'mapped'
                  AND f.chinese_name IS NOT NULL
                  AND f.effective_field_name IS NOT NULL
            """), {"snapshot_id": snapshot_id}).mappings().all()
            unmapped = connection.execute(text("""
                SELECT unmapped_field_count FROM db_validation_mapping_snapshots WHERE id = :snapshot_id
            """), {"snapshot_id": snapshot_id}).scalar_one()
        by_table: dict[str, dict[str, str]] = {}
        for row in rows:
            by_table.setdefault(str(row["effective_table_name"]), {})[str(row["chinese_name"])] = str(
                row["effective_field_name"]
            )
        table_mappings = {
            (item.relation_type, item.logical_code, item.scope_code): item.effective_table_name
            for item in self.load_tables()
        }
        cross_table_mappings: dict[tuple[str, str], list[CrossTableMapping]] = {}
        for item in self.load_cross_table_mappings():
            if item.mapping_status == "mapped":
                cross_table_mappings.setdefault((item.logical_code.upper(), item.scope_code), []).append(item)
        return TableFieldCatalog(
            by_table=by_table,
            unmapped_field_count=int(unmapped),
            table_mappings=table_mappings,
            cross_table_mappings={key: tuple(value) for key, value in cross_table_mappings.items()},
        )

    def save_snapshot(
        self,
        *,
        signature: tuple[Any, ...],
        refresh_source: str,
        tables: Iterable[TableMapping],
        fields: Iterable[FieldMapping],
    ) -> TableFieldCatalog:
        table_items = tuple(tables)
        field_items = tuple(fields)
        mapped = sum(item.mapping_status == "mapped" for item in field_items)
        unmapped = sum(item.mapping_status == "unmapped" for item in field_items)
        required_missing = sum(item.mapping_status == "required_missing" for item in field_items)
        missing_physical = sum(item.mapping_status == "missing_physical" for item in field_items)
        field_count = mapped + unmapped
        now = beijing_now()
        with self.database.transaction() as connection:
            result = connection.execute(text("""
                INSERT INTO db_validation_mapping_snapshots
                    (signature_json, refresh_source, status, table_count, field_count,
                     unmapped_field_count, required_missing_count, missing_physical_count,
                     error_message, created_at)
                VALUES (:signature, :source, 'success', :table_count, :field_count,
                        :unmapped, :required_missing, :missing_physical, NULL, :created_at)
            """), {
                "signature": json.dumps(signature, ensure_ascii=False, default=str),
                "source": refresh_source,
                "table_count": len(table_items),
                "field_count": field_count,
                "unmapped": unmapped,
                "required_missing": required_missing,
                "missing_physical": missing_physical,
                "created_at": now,
            })
            snapshot_id = int(result.lastrowid)
            table_ids: dict[tuple[str, str, str], int] = {}
            for item in table_items:
                connection.execute(text("""
                    UPDATE db_validation_mapping_tables
                    SET snapshot_id=:snapshot_id, automatic_table_name=:automatic,
                        effective_table_name=COALESCE(override_table_name, :automatic),
                        mapping_status=:status, status_message=:message, updated_at=:updated_at
                    WHERE relation_type=:relation_type AND logical_code=:logical_code AND scope_code=:scope_code
                """), {
                    "snapshot_id": snapshot_id,
                    "automatic": item.automatic_table_name,
                    "status": item.mapping_status,
                    "message": item.status_message or None,
                    "updated_at": now,
                    "relation_type": item.relation_type,
                    "logical_code": item.logical_code,
                    "scope_code": item.scope_code,
                })
                table_id = connection.execute(text("""
                    SELECT id FROM db_validation_mapping_tables
                    WHERE relation_type=:relation_type AND logical_code=:logical_code AND scope_code=:scope_code
                """), {
                    "relation_type": item.relation_type,
                    "logical_code": item.logical_code,
                    "scope_code": item.scope_code,
                }).scalar_one()
                table_ids[(item.relation_type, item.logical_code, item.scope_code)] = int(table_id)
            for item in field_items:
                table_id = table_ids[(item.relation_type, item.logical_code, item.scope_code)]
                connection.execute(text("""
                    INSERT INTO db_validation_mapping_fields
                        (snapshot_id, table_mapping_id, chinese_name, automatic_field_name,
                         override_field_name, effective_field_name, mapping_status, is_required,
                         status_message, updated_at)
                    VALUES (:snapshot_id, :table_id, :chinese_name, :automatic_field_name,
                            :override_field_name, :effective_field_name, :mapping_status,
                            :is_required, :status_message, :updated_at)
                """), {
                    "snapshot_id": snapshot_id,
                    "table_id": table_id,
                    "chinese_name": item.chinese_name or None,
                    "automatic_field_name": item.automatic_field_name,
                    "override_field_name": item.override_field_name,
                    "effective_field_name": item.effective_field_name,
                    "mapping_status": item.mapping_status,
                    "is_required": item.is_required,
                    "status_message": item.status_message or None,
                    "updated_at": now,
                })
        catalog = self.latest_catalog()
        return catalog or TableFieldCatalog({})

    def refresh_cross_table_mappings(self, mappings: Iterable[CrossTableMapping]) -> None:
        items = tuple(mappings)
        now = beijing_now()
        with self.database.transaction() as connection:
            for item in items:
                connection.execute(text("""
                    INSERT INTO db_validation_cross_table_mappings
                        (mapping_code, logical_code, scope_code,
                         automatic_detail_field_name, override_detail_field_name, effective_detail_field_name,
                         automatic_template_table_name, override_template_table_name, effective_template_table_name,
                         automatic_template_field_name, override_template_field_name, effective_template_field_name,
                         mapping_status, status_message, is_seed, refreshed_at, updated_at)
                    VALUES (:mapping_code, :logical_code, :scope_code,
                            :detail_field, NULL, :detail_field,
                            :template_table, NULL, :template_table,
                            :template_field, NULL, :template_field,
                            'mapped', NULL, 0, :now, :now)
                    ON DUPLICATE KEY UPDATE
                        automatic_detail_field_name=VALUES(automatic_detail_field_name),
                        effective_detail_field_name=COALESCE(override_detail_field_name, VALUES(automatic_detail_field_name)),
                        automatic_template_table_name=VALUES(automatic_template_table_name),
                        effective_template_table_name=COALESCE(override_template_table_name, VALUES(automatic_template_table_name)),
                        automatic_template_field_name=VALUES(automatic_template_field_name),
                        effective_template_field_name=COALESCE(override_template_field_name, VALUES(automatic_template_field_name)),
                        mapping_status='mapped', status_message=NULL,
                        refreshed_at=VALUES(refreshed_at), updated_at=VALUES(updated_at)
                """), {
                    "mapping_code": item.mapping_code,
                    "logical_code": item.logical_code,
                    "scope_code": item.scope_code,
                    "detail_field": item.automatic_detail_field_name,
                    "template_table": item.automatic_template_table_name,
                    "template_field": item.automatic_template_field_name,
                    "now": now,
                })
            active_codes = [item.mapping_code for item in items]
            if active_codes:
                connection.execute(text("""
                    UPDATE db_validation_cross_table_mappings
                    SET mapping_status='inactive', status_message='刷新后未发现该对应关系',
                        refreshed_at=:now, updated_at=:now
                    WHERE is_seed=0 AND mapping_code NOT IN :active_codes
                """).bindparams(bindparam("active_codes", expanding=True)), {
                    "active_codes": active_codes,
                    "now": now,
                })

    def record_failed_snapshot(
        self,
        *,
        signature: tuple[Any, ...],
        refresh_source: str,
        error_message: str,
    ) -> None:
        now = beijing_now()
        with self.database.transaction() as connection:
            connection.execute(text("""
                INSERT INTO db_validation_mapping_snapshots
                    (signature_json, refresh_source, status, table_count, field_count,
                     unmapped_field_count, required_missing_count, missing_physical_count,
                     error_message, created_at)
                VALUES (:signature, :source, 'failed', 0, 0, 0, 0, 0, :error_message, :created_at)
            """), {
                "signature": json.dumps(signature, ensure_ascii=False, default=str),
                "source": refresh_source,
                "error_message": (error_message or "")[:500] or None,
                "created_at": now,
            })

    def required_missing_for_tables(
        self,
        selected_tables: list[str] | tuple[str, ...] | None = None,
        *,
        include_template: bool = False,
        include_public_info: bool = False,
    ) -> list[dict[str, Any]]:
        codes = {str(code).strip().upper() for code in (selected_tables or ()) if str(code).strip()}
        with self.database.connect() as connection:
            snapshot_id = connection.execute(text("""
                SELECT id FROM db_validation_mapping_snapshots
                WHERE status='success' ORDER BY id DESC LIMIT 1
            """)).scalar_one_or_none()
            if snapshot_id is None:
                return []
            rows = connection.execute(text("""
                SELECT t.relation_type, t.logical_code, t.scope_code, t.effective_table_name,
                       f.chinese_name, f.mapping_status, COALESCE(f.status_message, '') status_message
                FROM db_validation_mapping_fields f
                JOIN db_validation_mapping_tables t ON t.id = f.table_mapping_id
                WHERE f.snapshot_id = :snapshot_id
                  AND f.is_required = 1
                  AND f.mapping_status IN ('required_missing', 'missing_physical')
            """), {"snapshot_id": snapshot_id}).mappings().all()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            relation = str(item.get("relation_type") or "")
            logical = str(item.get("logical_code") or "").upper()
            if relation == "detail":
                if codes and logical not in codes:
                    continue
                result.append(item)
            elif relation == "template" and include_template:
                result.append(item)
            elif relation == "public_info" and include_public_info:
                result.append(item)
        return result

    def save_override(
        self,
        *,
        mapping_kind: str,
        relation_type: str,
        logical_code: str,
        scope_code: str,
        chinese_name: str,
        override_value: str,
        reason: str,
        operator_user_id: str,
    ) -> None:
        if not reason.strip():
            raise ValueError("修改原因不能为空")
        now = beijing_now()
        with self.database.transaction() as connection:
            existing = connection.execute(text("""
                SELECT id, override_value FROM db_validation_mapping_overrides
                WHERE mapping_kind=:kind AND relation_type=:relation_type
                  AND logical_code=:logical_code AND scope_code=:scope_code
                  AND chinese_name=:chinese_name
            """), {
                "kind": mapping_kind,
                "relation_type": relation_type,
                "logical_code": logical_code,
                "scope_code": scope_code,
                "chinese_name": chinese_name,
            }).mappings().first()
            before = str(existing["override_value"]) if existing else None
            connection.execute(text("""
                INSERT INTO db_validation_mapping_overrides
                    (mapping_kind, relation_type, logical_code, scope_code, chinese_name,
                     override_value, reason, active, created_by, created_at, updated_by, updated_at)
                VALUES (:kind, :relation_type, :logical_code, :scope_code, :chinese_name,
                        :value, :reason, 1, :operator, :now, :operator, :now)
                ON DUPLICATE KEY UPDATE override_value=VALUES(override_value), reason=VALUES(reason),
                    active=1, updated_by=VALUES(updated_by), updated_at=VALUES(updated_at)
            """), {
                "kind": mapping_kind,
                "relation_type": relation_type,
                "logical_code": logical_code,
                "scope_code": scope_code,
                "chinese_name": chinese_name,
                "value": override_value.strip(),
                "reason": reason.strip(),
                "operator": operator_user_id,
                "now": now,
            })
            override_id = connection.execute(text("""
                SELECT id FROM db_validation_mapping_overrides
                WHERE mapping_kind=:kind AND relation_type=:relation_type
                  AND logical_code=:logical_code AND scope_code=:scope_code
                  AND chinese_name=:chinese_name
            """), {
                "kind": mapping_kind,
                "relation_type": relation_type,
                "logical_code": logical_code,
                "scope_code": scope_code,
                "chinese_name": chinese_name,
            }).scalar_one()
            connection.execute(text("""
                INSERT INTO db_validation_mapping_audit_logs
                    (override_id, action_code, mapping_kind, relation_type, logical_code,
                     scope_code, chinese_name, value_before, value_after, reason,
                     operator_user_id, occurred_at)
                VALUES (:override_id, 'save', :kind, :relation_type, :logical_code,
                        :scope_code, :chinese_name, :before, :after, :reason, :operator, :now)
            """), {
                "override_id": override_id,
                "kind": mapping_kind,
                "relation_type": relation_type,
                "logical_code": logical_code,
                "scope_code": scope_code,
                "chinese_name": chinese_name,
                "before": before,
                "after": override_value.strip(),
                "reason": reason.strip(),
                "operator": operator_user_id,
                "now": now,
            })
            if mapping_kind == "table":
                connection.execute(text("""
                    UPDATE db_validation_mapping_tables
                    SET override_table_name=:value, effective_table_name=:value, updated_at=:now
                    WHERE relation_type=:relation_type AND logical_code=:logical_code AND scope_code=:scope_code
                """), {
                    "value": override_value.strip(),
                    "now": now,
                    "relation_type": relation_type,
                    "logical_code": logical_code,
                    "scope_code": scope_code,
                })
            elif mapping_kind == "field":
                snapshot_id = connection.execute(text("""
                    SELECT id FROM db_validation_mapping_snapshots
                    WHERE status='success' ORDER BY id DESC LIMIT 1
                """)).scalar_one_or_none()
                if snapshot_id is not None:
                    # 修复：先查询当前字段状态，以便匹配无中文名的 unmapped 行
                    current_field = connection.execute(text("""
                        SELECT f.id, f.chinese_name, f.automatic_field_name, f.is_required
                        FROM db_validation_mapping_fields f
                        JOIN db_validation_mapping_tables t ON t.id=f.table_mapping_id
                        WHERE f.snapshot_id=:snapshot_id
                          AND t.relation_type=:relation_type AND t.logical_code=:logical_code
                          AND t.scope_code=:scope_code AND f.chinese_name=:chinese_name
                    """), {
                        "snapshot_id": snapshot_id,
                        "relation_type": relation_type,
                        "logical_code": logical_code,
                        "scope_code": scope_code,
                        "chinese_name": chinese_name,
                    }).mappings().first()
                    # 修复：无中文名的 unmapped 行，按 automatic_field_name 兜底匹配
                    if current_field is None:
                        current_field = connection.execute(text("""
                            SELECT f.id, f.chinese_name, f.automatic_field_name, f.is_required
                            FROM db_validation_mapping_fields f
                            JOIN db_validation_mapping_tables t ON t.id=f.table_mapping_id
                            WHERE f.snapshot_id=:snapshot_id
                              AND t.relation_type=:relation_type AND t.logical_code=:logical_code
                              AND t.scope_code=:scope_code AND f.chinese_name=''
                              AND f.automatic_field_name=:override_value
                        """), {
                            "snapshot_id": snapshot_id,
                            "relation_type": relation_type,
                            "logical_code": logical_code,
                            "scope_code": scope_code,
                            "override_value": override_value.strip(),
                        }).mappings().first()
                    if current_field is not None:
                        connection.execute(text("""
                            UPDATE db_validation_mapping_fields f
                            JOIN db_validation_mapping_tables t ON t.id=f.table_mapping_id
                            SET f.override_field_name=:value, f.effective_field_name=:value,
                                f.mapping_status='mapped', f.updated_at=:now
                            WHERE f.id=:field_id
                        """), {
                            "value": override_value.strip(),
                            "now": now,
                            "field_id": current_field["id"],
                        })
            elif mapping_kind == "cross_table":
                values = _cross_table_override_values(override_value)
                result = connection.execute(text("""
                    UPDATE db_validation_cross_table_mappings
                    SET override_detail_field_name=NULL,
                        effective_detail_field_name=automatic_detail_field_name,
                        override_template_table_name=:template_table,
                        effective_template_table_name=:template_table,
                        override_template_field_name=:template_field,
                        effective_template_field_name=:template_field,
                        mapping_status='mapped', status_message=NULL, updated_at=:now
                    WHERE mapping_code=:mapping_code
                """), {**values, "now": now, "mapping_code": chinese_name})
                if getattr(result, "rowcount", 0) == 0:
                    raise ValueError("跨表映射不存在")
            else:
                raise ValueError("映射类型不合法")
            # 必须在事务连接关闭前重算快照计数。
            self._recalculate_snapshot_counts(connection)

    def detail_payload(self) -> dict[str, Any]:
        tables = self.load_tables()
        cross_tables = self.load_cross_table_mappings()
        with self.database.connect() as connection:
            snapshot_id = connection.execute(text("""
                SELECT id FROM db_validation_mapping_snapshots
                WHERE status='success' ORDER BY id DESC LIMIT 1
            """)).scalar_one_or_none()
            fields = [] if snapshot_id is None else [dict(row) for row in connection.execute(text("""
                SELECT t.relation_type, t.logical_code, t.scope_code,
                       t.effective_table_name, f.chinese_name, f.automatic_field_name,
                       f.override_field_name, f.effective_field_name, f.mapping_status,
                       f.is_required, COALESCE(f.status_message, '') status_message,
                       CAST(f.updated_at AS CHAR) refreshed_at
                FROM db_validation_mapping_fields f
                JOIN db_validation_mapping_tables t ON t.id=f.table_mapping_id
                WHERE f.snapshot_id=:snapshot_id
                ORDER BY t.relation_type, t.logical_code, t.scope_code,
                         f.chinese_name, f.automatic_field_name
            """), {"snapshot_id": snapshot_id}).mappings().all()]
        return {
            "tables": [item.to_payload() for item in tables],
            "fields": fields,
            "cross_tables": [item.to_payload() for item in cross_tables],
        }

    def _recalculate_snapshot_counts(self, connection: Any) -> None:
        """重算最新成功快照的 field_count / unmapped / required_missing / missing_physical。"""
        snapshot_id = connection.execute(text("""
            SELECT id FROM db_validation_mapping_snapshots
            WHERE status='success' ORDER BY id DESC LIMIT 1
        """)).scalar_one_or_none()
        if snapshot_id is None:
            return
        row = connection.execute(text("""
            SELECT
                COUNT(*) AS field_count,
                SUM(CASE WHEN f.mapping_status = 'mapped' THEN 1 ELSE 0 END) AS mapped,
                SUM(CASE WHEN f.mapping_status = 'unmapped' THEN 1 ELSE 0 END) AS unmapped,
                SUM(CASE WHEN f.mapping_status = 'required_missing' THEN 1 ELSE 0 END) AS required_missing,
                SUM(CASE WHEN f.mapping_status = 'missing_physical' THEN 1 ELSE 0 END) AS missing_physical
            FROM db_validation_mapping_fields f
            WHERE f.snapshot_id=:snapshot_id
        """), {"snapshot_id": snapshot_id}).mappings().first()
        if row is None:
            return
        field_count = int(row["field_count"] or 0)
        mapped = int(row["mapped"] or 0)
        unmapped = int(row["unmapped"] or 0)
        required_missing = int(row["required_missing"] or 0)
        missing_physical = int(row["missing_physical"] or 0)
        connection.execute(text("""
            UPDATE db_validation_mapping_snapshots
            SET field_count=:field_count, unmapped_field_count=:unmapped,
                required_missing_count=:required_missing, missing_physical_count=:missing_physical
            WHERE id=:snapshot_id
        """), {
            "snapshot_id": snapshot_id,
            "field_count": mapped + unmapped,
            "unmapped": unmapped,
            "required_missing": required_missing,
            "missing_physical": missing_physical,
        })

    def restore_override(
        self,
        *,
        mapping_kind: str,
        relation_type: str,
        logical_code: str,
        scope_code: str,
        chinese_name: str,
        reason: str,
        operator_user_id: str,
    ) -> None:
        if mapping_kind not in {"table", "field", "cross_table"}:
            raise ValueError("映射类型不合法")
        if not reason.strip():
            raise ValueError("恢复原因不能为空")
        now = beijing_now()
        params = {
            "kind": mapping_kind, "relation_type": relation_type,
            "logical_code": logical_code, "scope_code": scope_code,
            "chinese_name": chinese_name, "reason": reason.strip(),
            "operator": operator_user_id, "now": now,
        }
        with self.database.transaction() as connection:
            existing = connection.execute(text("""
                SELECT id, override_value FROM db_validation_mapping_overrides
                WHERE mapping_kind=:kind AND relation_type=:relation_type
                  AND logical_code=:logical_code AND scope_code=:scope_code
                  AND chinese_name=:chinese_name AND active=1
            """), params).mappings().first()
            if existing is None:
                raise ValueError("当前映射没有人工覆盖")
            params.update(override_id=int(existing["id"]), before=str(existing["override_value"]))
            connection.execute(text("""
                UPDATE db_validation_mapping_overrides
                SET active=0, reason=:reason, updated_by=:operator, updated_at=:now
                WHERE id=:override_id
            """), params)
            connection.execute(text("""
                INSERT INTO db_validation_mapping_audit_logs
                    (override_id, action_code, mapping_kind, relation_type, logical_code,
                     scope_code, chinese_name, value_before, value_after, reason,
                     operator_user_id, occurred_at)
                VALUES (:override_id, 'restore', :kind, :relation_type, :logical_code,
                        :scope_code, :chinese_name, :before, NULL, :reason, :operator, :now)
            """), params)
            if mapping_kind == "table":
                connection.execute(text("""
                    UPDATE db_validation_mapping_tables
                    SET override_table_name=NULL, effective_table_name=automatic_table_name,
                        updated_at=:now
                    WHERE relation_type=:relation_type AND logical_code=:logical_code
                      AND scope_code=:scope_code
                """), params)
            elif mapping_kind == "field":
                snapshot_id = connection.execute(text("""
                    SELECT id FROM db_validation_mapping_snapshots
                    WHERE status='success' ORDER BY id DESC LIMIT 1
                """)).scalar_one_or_none()
                if snapshot_id is not None:
                    params = {**params, "snapshot_id": snapshot_id}
                    # 修复：恢复后根据 automatic 值重算 mapping_status
                    connection.execute(text("""
                        UPDATE db_validation_mapping_fields f
                        JOIN db_validation_mapping_tables t ON t.id=f.table_mapping_id
                        SET f.override_field_name=NULL,
                            f.effective_field_name=f.automatic_field_name,
                            f.mapping_status=CASE
                                WHEN f.automatic_field_name IS NOT NULL AND f.automatic_field_name <> ''
                                    THEN 'mapped'
                                WHEN f.is_required=1 THEN 'required_missing'
                                ELSE 'unmapped'
                            END,
                            f.status_message=CASE
                                WHEN f.automatic_field_name IS NOT NULL AND f.automatic_field_name <> ''
                                    THEN NULL
                                WHEN f.is_required=1
                                    THEN CONCAT('规则必需字段缺失：', f.chinese_name)
                                ELSE CONCAT('未找到字段映射：', f.chinese_name)
                            END,
                            f.updated_at=:now
                        WHERE f.snapshot_id=:snapshot_id
                          AND t.relation_type=:relation_type AND t.logical_code=:logical_code
                          AND t.scope_code=:scope_code AND f.chinese_name=:chinese_name
                    """), params)
            else:
                result = connection.execute(text("""
                    UPDATE db_validation_cross_table_mappings
                    SET override_detail_field_name=NULL,
                        effective_detail_field_name=automatic_detail_field_name,
                        override_template_table_name=NULL,
                        effective_template_table_name=automatic_template_table_name,
                        override_template_field_name=NULL,
                        effective_template_field_name=automatic_template_field_name,
                        mapping_status='mapped', status_message=NULL, updated_at=:now
                    WHERE mapping_code=:chinese_name
                """), params)
                if getattr(result, "rowcount", 0) == 0:
                    raise ValueError("跨表映射不存在")
            # 必须在事务连接关闭前重算快照计数。
            self._recalculate_snapshot_counts(connection)

    def status_payload(self) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(text("""
                SELECT id, refresh_source, table_count, field_count, unmapped_field_count,
                       required_missing_count, missing_physical_count, error_message, created_at
                FROM db_validation_mapping_snapshots
                WHERE status='success' ORDER BY id DESC LIMIT 1
            """)).mappings().first()
            failed = connection.execute(text("""
                SELECT id, error_message, created_at
                FROM db_validation_mapping_snapshots
                WHERE status='failed' ORDER BY id DESC LIMIT 1
            """)).mappings().first()
        failed_is_latest = bool(failed) and (row is None or int(failed["id"]) > int(row["id"]))
        last_error = str((failed or {}).get("error_message") or "") if failed_is_latest else ""
        last_failed_at = str((failed or {}).get("created_at") or "") if failed_is_latest else ""
        if row is None:
            return {
                "initialized": False, "refreshed_at": "", "refresh_source": "",
                "table_count": 0, "field_count": 0, "mapped_field_count": 0,
                "unmapped_field_count": 0, "required_missing_count": 0,
                "missing_physical_count": 0, "last_error": last_error,
                "last_failed_at": last_failed_at,
            }
        field_count = int(row["field_count"])
        unmapped = int(row["unmapped_field_count"])
        required_missing = int(row["required_missing_count"])
        missing_physical = int(row["missing_physical_count"])
        return {
            "initialized": True,
            "snapshot_id": int(row["id"]),
            "refreshed_at": str(row["created_at"]),
            "refresh_source": str(row["refresh_source"]),
            "table_count": int(row["table_count"]),
            "field_count": field_count,
            "mapped_field_count": max(field_count - unmapped, 0),
            "unmapped_field_count": unmapped,
            "required_missing_count": required_missing,
            "missing_physical_count": missing_physical,
            "last_error": last_error,
            "last_failed_at": last_failed_at,
        }
