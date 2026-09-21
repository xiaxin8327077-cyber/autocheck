from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Mapping, Sequence

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    and_,
    delete,
    insert,
    select,
    or_,
    update,
)
from sqlalchemy.exc import IntegrityError

from .catalog import BOARD_CATALOG, BUILTIN_FIELD_SEEDS, BUILTIN_REGION_SEEDS
from .contracts import VersionConflictError
from .year_snapshots import (
    INITIAL_2026_SNAPSHOT_ROWS,
    QUARTERLY_SPECIAL_PROCESSING,
    SnapshotRow,
)


class SchemaVersionConflictError(VersionConflictError):
    """The SQL test/save schema snapshot no longer matches the region."""


METADATA = MetaData()
IDENTIFIER_TYPE = BigInteger().with_variant(Integer, "sqlite")
BOARD_CODES = frozenset(seed.code for seed in BOARD_CATALOG)
REGIONS = Table(
    "dashboard_management_regions",
    METADATA,
    Column("id", IDENTIFIER_TYPE, primary_key=True, autoincrement=True),
    Column("board_code", String(64), nullable=False),
    Column("region_code", String(64), nullable=False, unique=True),
    Column("name", String(100), nullable=False),
    Column("shape", String(16), nullable=False),
    Column("built_in", Boolean, nullable=False),
    Column("enabled", Boolean, nullable=False),
    Column("system_supported", Boolean, nullable=False),
    Column("default_mode", String(16), nullable=False),
    Column("display_order", Integer, nullable=False),
    Column("description", String(500), nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
    Column("row_version", BigInteger, nullable=False),
)
FIELDS = Table(
    "dashboard_management_fields",
    METADATA,
    Column("id", IDENTIFIER_TYPE, primary_key=True, autoincrement=True),
    Column(
        "region_id",
        IDENTIFIER_TYPE,
        ForeignKey("dashboard_management_regions.id"),
        nullable=False,
    ),
    Column("field_alias", String(64), nullable=False),
    Column("name", String(100), nullable=False),
    Column("value_type", String(16), nullable=False),
    Column("nullable", Boolean, nullable=False),
    Column("built_in", Boolean, nullable=False),
    Column("enabled", Boolean, nullable=False),
    Column("display_order", Integer, nullable=False),
    Column("description", String(500), nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
    Column("row_version", BigInteger, nullable=False),
    UniqueConstraint("region_id", "field_alias", name="uq_dashboard_management_field_alias"),
)
SOURCE_CONFIGS = Table(
    "dashboard_management_source_configs",
    METADATA,
    Column(
        "region_id",
        IDENTIFIER_TYPE,
        ForeignKey("dashboard_management_regions.id"),
        primary_key=True,
    ),
    Column("source_mode", String(16), nullable=False),
    Column("datasource_id", String(64)),
    Column("sql_text", Text),
    Column("tested_signature", String(64)),
    Column("tested_at", DateTime),
    Column("tested_by", String(64)),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
    Column("row_version", BigInteger, nullable=False),
)
YEAR_SNAPSHOTS = Table(
    "dashboard_management_year_snapshots",
    METADATA,
    Column("id", IDENTIFIER_TYPE, primary_key=True, autoincrement=True),
    Column(
        "region_id",
        IDENTIFIER_TYPE,
        ForeignKey("dashboard_management_regions.id"),
        nullable=False,
    ),
    Column("period_year", Integer, nullable=False),
    Column("period_type", String(16), nullable=False),
    Column("period_value", Integer, nullable=False),
    Column("row_json", Text, nullable=False),
    Column("source_refreshed_at", DateTime),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
    UniqueConstraint(
        "region_id",
        "period_year",
        "period_type",
        "period_value",
        name="uq_dashboard_management_year_snapshot_period",
    ),
)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _database_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _snapshot_json(row: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(row), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _row(result: Any) -> dict[str, Any] | None:
    value = result.mappings().first()
    return dict(value) if value is not None else None


def _rows(result: Any) -> list[dict[str, Any]]:
    return [dict(value) for value in result.mappings().all()]


def _is_source_config_unique_conflict(error: IntegrityError) -> bool:
    """Return true only for the source config row's primary-key uniqueness race."""
    original = error.orig
    pgcode = getattr(original, "pgcode", None)
    if pgcode == "23505":
        return True
    args = getattr(original, "args", ())
    if args and args[0] == 1062:
        return True
    return "UNIQUE constraint failed: dashboard_management_source_configs.region_id" in str(original)


class DashboardManagementStorage:
    """看板目录和来源配置的持久化仓储。"""

    def __init__(self, database: Any) -> None:
        self.database = database

    def seed_builtin_catalog(self) -> None:
        """Add missing builtin records without overwriting administrator settings."""
        now = _now()
        with self.database.transaction() as connection:
            regions_by_code: dict[str, int] = {}
            for seed in BUILTIN_REGION_SEEDS:
                current = _row(connection.execute(
                    select(REGIONS).where(REGIONS.c.region_code == seed.code)
                ))
                if current is None:
                    result = connection.execute(insert(REGIONS).values(
                        board_code=seed.board_code,
                        region_code=seed.code,
                        name=seed.name,
                        shape=seed.shape,
                        built_in=True,
                        enabled=True,
                        system_supported=seed.system_supported,
                        default_mode=seed.default_mode,
                        display_order=seed.display_order,
                        description=seed.description,
                        created_at=now,
                        updated_at=now,
                        row_version=1,
                    ))
                    regions_by_code[seed.code] = int(result.inserted_primary_key[0])
                else:
                    regions_by_code[seed.code] = int(current["id"])
                    canonical = {
                        "board_code": seed.board_code,
                        "name": seed.name,
                        "shape": seed.shape,
                        "built_in": True,
                        "system_supported": seed.system_supported,
                        "default_mode": seed.default_mode,
                        "description": seed.description,
                    }
                    if any(current[key] != value for key, value in canonical.items()):
                        connection.execute(
                            update(REGIONS)
                            .where(REGIONS.c.id == current["id"])
                            .values(**canonical, updated_at=now, row_version=REGIONS.c.row_version + 1)
                        )

            for seed in BUILTIN_FIELD_SEEDS:
                region_id = regions_by_code[seed.region_code]
                current = _row(connection.execute(
                    select(FIELDS).where(and_(
                        FIELDS.c.region_id == region_id,
                        FIELDS.c.field_alias == seed.alias,
                    ))
                ))
                if current is None:
                    connection.execute(insert(FIELDS).values(
                        region_id=region_id,
                        field_alias=seed.alias,
                        name=seed.name,
                        value_type=seed.value_type,
                        nullable=seed.nullable,
                        built_in=True,
                        enabled=True,
                        display_order=seed.display_order,
                        description=seed.description,
                        created_at=now,
                        updated_at=now,
                        row_version=1,
                    ))
                else:
                    canonical = {
                        "name": seed.name,
                        "value_type": seed.value_type,
                        "nullable": seed.nullable,
                        "built_in": True,
                        "description": seed.description,
                    }
                    if any(current[key] != value for key, value in canonical.items()):
                        connection.execute(
                            update(FIELDS)
                            .where(FIELDS.c.id == current["id"])
                            .values(**canonical, updated_at=now, row_version=FIELDS.c.row_version + 1)
                        )

            for seed in BUILTIN_REGION_SEEDS:
                region_id = regions_by_code[seed.code]
                current = _row(connection.execute(
                    select(SOURCE_CONFIGS.c.region_id).where(SOURCE_CONFIGS.c.region_id == region_id)
                ))
                if current is None:
                    connection.execute(insert(SOURCE_CONFIGS).values(
                        region_id=region_id,
                        source_mode=seed.default_mode,
                        datasource_id=None,
                        sql_text=None,
                        tested_signature=None,
                        tested_at=None,
                        tested_by=None,
                        created_at=now,
                        updated_at=now,
                        row_version=1,
                    ))
            self._seed_initial_year_snapshots_with_connection(connection, regions_by_code, now)

    def seed_initial_year_snapshots(self) -> None:
        """Add the confirmed 2026 baseline without replacing collected values."""
        now = _now()
        with self.database.transaction() as connection:
            regions_by_code = {
                str(row["region_code"]): int(row["id"])
                for row in _rows(connection.execute(
                    select(REGIONS.c.id, REGIONS.c.region_code).where(
                        REGIONS.c.region_code.in_(tuple(INITIAL_2026_SNAPSHOT_ROWS))
                    )
                ))
            }
            self._seed_initial_year_snapshots_with_connection(
                connection, regions_by_code, now
            )

    def upsert_year_snapshots(
        self,
        region_id: int,
        rows: Sequence[SnapshotRow],
        refreshed_at: datetime,
    ) -> None:
        if not rows:
            return
        normalized_refreshed_at = _database_datetime(refreshed_at)
        try:
            self._upsert_year_snapshots(region_id, rows, normalized_refreshed_at)
        except IntegrityError:
            # A concurrent preview can insert the same period after our UPDATE
            # misses it. Retrying turns that race into an UPDATE.
            self._upsert_year_snapshots(region_id, rows, normalized_refreshed_at)

    def refresh_year_snapshots(
        self,
        region_id: int,
        rows: Sequence[SnapshotRow],
        *,
        period_year: int,
        refreshed_at: datetime,
    ) -> list[dict[str, Any]]:
        """Upsert live rows and read the merged year in one transaction.

        A result collected earlier cannot replace a newer snapshot when two
        board preview requests finish out of order.
        """
        normalized_refreshed_at = _database_datetime(refreshed_at)
        try:
            return self._refresh_year_snapshots(
                region_id, rows, period_year, normalized_refreshed_at
            )
        except IntegrityError:
            # Another request can win the initial INSERT race. Retrying sees
            # that row and applies the timestamp guard before returning it.
            return self._refresh_year_snapshots(
                region_id, rows, period_year, normalized_refreshed_at
            )

    def list_year_snapshots(
        self, region_id: int, period_year: int
    ) -> list[dict[str, Any]]:
        statement = self._year_snapshot_statement(region_id, period_year)
        with self.database.connect() as connection:
            stored = _rows(connection.execute(statement))
        return self._deserialize_year_snapshots(stored)

    @staticmethod
    def _year_snapshot_statement(region_id: int, period_year: int) -> Any:
        return (
            select(YEAR_SNAPSHOTS)
            .where(and_(
                YEAR_SNAPSHOTS.c.region_id == region_id,
                YEAR_SNAPSHOTS.c.period_year == period_year,
            ))
            .order_by(
                YEAR_SNAPSHOTS.c.period_type.asc(),
                YEAR_SNAPSHOTS.c.period_value.asc(),
                YEAR_SNAPSHOTS.c.id.asc(),
            )
        )

    @staticmethod
    def _deserialize_year_snapshots(
        stored: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        snapshots: list[dict[str, Any]] = []
        for item in stored:
            try:
                row = json.loads(str(item.pop("row_json")))
            except (TypeError, ValueError, json.JSONDecodeError):
                raise ValueError("快照数据无效") from None
            if not isinstance(row, dict) or any(not isinstance(key, str) for key in row):
                raise ValueError("快照数据无效")
            item["row"] = row
            snapshots.append(item)
        return snapshots

    def _refresh_year_snapshots(
        self,
        region_id: int,
        rows: Sequence[SnapshotRow],
        period_year: int,
        refreshed_at: datetime,
    ) -> list[dict[str, Any]]:
        with self.database.transaction() as connection:
            self._upsert_year_snapshots_with_connection(
                connection, region_id, rows, refreshed_at
            )
            stored = _rows(connection.execute(
                self._year_snapshot_statement(region_id, period_year)
            ))
        return self._deserialize_year_snapshots(stored)

    def _upsert_year_snapshots(
        self,
        region_id: int,
        rows: Sequence[SnapshotRow],
        refreshed_at: datetime,
    ) -> None:
        now = _now()
        with self.database.transaction() as connection:
            self._upsert_year_snapshots_with_connection(
                connection, region_id, rows, refreshed_at, now=now
            )

    @staticmethod
    def _upsert_year_snapshots_with_connection(
        connection: Any,
        region_id: int,
        rows: Sequence[SnapshotRow],
        refreshed_at: datetime,
        *,
        now: datetime | None = None,
    ) -> None:
        written_at = now or _now()
        for snapshot in rows:
            key = and_(
                YEAR_SNAPSHOTS.c.region_id == region_id,
                YEAR_SNAPSHOTS.c.period_year == snapshot.period_year,
                YEAR_SNAPSHOTS.c.period_type == snapshot.period_type,
                YEAR_SNAPSHOTS.c.period_value == snapshot.period_value,
            )
            values = {
                "row_json": _snapshot_json(snapshot.row),
                "source_refreshed_at": refreshed_at,
                "updated_at": written_at,
            }
            result = connection.execute(
                update(YEAR_SNAPSHOTS)
                .where(and_(
                    key,
                    or_(
                        YEAR_SNAPSHOTS.c.source_refreshed_at.is_(None),
                        YEAR_SNAPSHOTS.c.source_refreshed_at <= refreshed_at,
                    ),
                ))
                .values(**values)
            )
            if result.rowcount != 0:
                continue
            exists = connection.execute(
                select(YEAR_SNAPSHOTS.c.id).where(key)
            ).first()
            if exists is not None:
                continue
            connection.execute(insert(YEAR_SNAPSHOTS).values(
                region_id=region_id,
                period_year=snapshot.period_year,
                period_type=snapshot.period_type,
                period_value=snapshot.period_value,
                **values,
                created_at=written_at,
            ))

    @staticmethod
    def _seed_initial_year_snapshots_with_connection(
        connection: Any,
        regions_by_code: Mapping[str, int],
        now: datetime,
    ) -> None:
        DashboardManagementStorage._upgrade_legacy_special_processing_baseline(
            connection, regions_by_code.get(QUARTERLY_SPECIAL_PROCESSING), now
        )
        for region_code, snapshots in INITIAL_2026_SNAPSHOT_ROWS.items():
            region_id = regions_by_code.get(region_code)
            if region_id is None:
                continue
            existing = {
                (str(period_type), int(period_value))
                for period_type, period_value in connection.execute(
                    select(YEAR_SNAPSHOTS.c.period_type, YEAR_SNAPSHOTS.c.period_value)
                    .where(and_(
                        YEAR_SNAPSHOTS.c.region_id == region_id,
                        YEAR_SNAPSHOTS.c.period_year == 2026,
                    ))
                ).all()
            }
            for snapshot in snapshots:
                if (snapshot.period_type, snapshot.period_value) in existing:
                    continue
                connection.execute(insert(YEAR_SNAPSHOTS).values(
                    region_id=region_id,
                    period_year=snapshot.period_year,
                    period_type=snapshot.period_type,
                    period_value=snapshot.period_value,
                    row_json=_snapshot_json(snapshot.row),
                    source_refreshed_at=None,
                    created_at=now,
                    updated_at=now,
                ))

    @staticmethod
    def _upgrade_legacy_special_processing_baseline(
        connection: Any, region_id: int | None, now: datetime
    ) -> None:
        """Replace only the original Q1/Q2 seed rows with fixed monthly estimates.

        Older installations may contain quarter snapshots.  Only the two
        unrefreshed, known default rows are safe to convert: they were the
        shipped baseline rather than collected data.  Any user-edited or
        real-time legacy quarter row remains stored for audit, but is excluded
        from month-based presentation to avoid duplicated totals.
        """
        if region_id is None:
            return
        expected_totals = {1: 31, 2: 34}
        legacy_rows = _rows(connection.execute(
            select(YEAR_SNAPSHOTS).where(and_(
                YEAR_SNAPSHOTS.c.region_id == region_id,
                YEAR_SNAPSHOTS.c.period_year == 2026,
                YEAR_SNAPSHOTS.c.period_type == "quarter",
                YEAR_SNAPSHOTS.c.period_value.in_(tuple(expected_totals)),
                YEAR_SNAPSHOTS.c.source_refreshed_at.is_(None),
            ))
        ))
        monthly_baselines = {
            snapshot.period_value: snapshot
            for snapshot in INITIAL_2026_SNAPSHOT_ROWS[QUARTERLY_SPECIAL_PROCESSING]
        }
        for legacy in legacy_rows:
            try:
                legacy_count = json.loads(str(legacy["row_json"])).get(
                    "special_processing_count"
                )
                quarter = int(legacy["period_value"])
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if legacy_count != expected_totals[quarter]:
                continue
            existing_months = {
                int(value[0])
                for value in connection.execute(
                    select(YEAR_SNAPSHOTS.c.period_value).where(and_(
                        YEAR_SNAPSHOTS.c.region_id == region_id,
                        YEAR_SNAPSHOTS.c.period_year == 2026,
                        YEAR_SNAPSHOTS.c.period_type == "month",
                        YEAR_SNAPSHOTS.c.period_value.between(
                            (quarter - 1) * 3 + 1, quarter * 3
                        ),
                    ))
                ).all()
            }
            for month in range((quarter - 1) * 3 + 1, quarter * 3 + 1):
                if month in existing_months:
                    continue
                snapshot = monthly_baselines[month]
                connection.execute(insert(YEAR_SNAPSHOTS).values(
                    region_id=region_id,
                    period_year=snapshot.period_year,
                    period_type=snapshot.period_type,
                    period_value=snapshot.period_value,
                    row_json=_snapshot_json(snapshot.row),
                    source_refreshed_at=None,
                    created_at=now,
                    updated_at=now,
                ))
            connection.execute(delete(YEAR_SNAPSHOTS).where(
                YEAR_SNAPSHOTS.c.id == legacy["id"]
            ))

    def list_regions(
        self, board_code: str, include_disabled: bool = True
    ) -> list[dict[str, Any]]:
        statement = select(REGIONS).where(REGIONS.c.board_code == board_code)
        if not include_disabled:
            statement = statement.where(REGIONS.c.enabled.is_(True))
        statement = statement.order_by(REGIONS.c.display_order.asc(), REGIONS.c.id.asc())
        with self.database.connect() as connection:
            return _rows(connection.execute(statement))

    def get_region(self, region_id: int) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            return _row(connection.execute(select(REGIONS).where(REGIONS.c.id == region_id)))

    def create_region(self, values: Mapping[str, Any]) -> dict[str, Any]:
        if values["board_code"] not in BOARD_CODES:
            raise ValueError("不支持的固定看板编码")
        now = _now()
        row = {
            "board_code": values["board_code"],
            "region_code": values["region_code"],
            "name": values["name"],
            "shape": values["shape"],
            "built_in": bool(values.get("built_in", False)),
            "enabled": bool(values.get("enabled", True)),
            "system_supported": bool(values.get("system_supported", False)),
            "default_mode": values.get("default_mode", "sql"),
            "display_order": values["display_order"],
            "description": values.get("description", ""),
            "created_at": now,
            "updated_at": now,
            "row_version": 1,
        }
        with self.database.transaction() as connection:
            result = connection.execute(insert(REGIONS).values(**row))
            return self._get_region_with_connection(connection, int(result.inserted_primary_key[0]))

    def create_region_with_default_sql(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Create a custom region and its required SQL source in one transaction."""
        if values["board_code"] not in BOARD_CODES:
            raise ValueError("不支持的固定看板编码")
        now = _now()
        row = {
            "board_code": values["board_code"],
            "region_code": values["region_code"],
            "name": values["name"],
            "shape": values["shape"],
            "built_in": bool(values.get("built_in", False)),
            "enabled": bool(values.get("enabled", True)),
            "system_supported": bool(values.get("system_supported", False)),
            "default_mode": values.get("default_mode", "sql"),
            "display_order": values["display_order"],
            "description": values.get("description", ""),
            "created_at": now,
            "updated_at": now,
            "row_version": 1,
        }
        with self.database.transaction() as connection:
            result = connection.execute(insert(REGIONS).values(**row))
            region_id = int(result.inserted_primary_key[0])
            self._create_default_source_config_with_connection(connection, region_id)
            return self._get_region_with_connection(connection, region_id)

    def create_region_with_fields_and_default_sql(
        self, values: Mapping[str, Any], fields: list[Mapping[str, Any]]
    ) -> dict[str, Any]:
        """Atomically create a custom region, its first fields, and SQL source."""
        if values["board_code"] not in BOARD_CODES:
            raise ValueError("不支持的固定看板编码")
        now = _now()
        row = {
            "board_code": values["board_code"], "region_code": values["region_code"],
            "name": values["name"], "shape": values["shape"],
            "built_in": bool(values.get("built_in", False)), "enabled": bool(values.get("enabled", True)),
            "system_supported": bool(values.get("system_supported", False)), "default_mode": values.get("default_mode", "sql"),
            "display_order": values["display_order"], "description": values.get("description", ""),
            "created_at": now, "updated_at": now, "row_version": 1,
        }
        with self.database.transaction() as connection:
            result = connection.execute(insert(REGIONS).values(**row))
            region_id = int(result.inserted_primary_key[0])
            for field in fields:
                self._create_field_with_connection(connection, region_id, field)
            self._create_default_source_config_with_connection(connection, region_id)
            return self._get_region_with_connection(connection, region_id)

    def update_region(
        self, region_id: int, values: Mapping[str, Any], expected_version: int
    ) -> dict[str, Any]:
        allowed = {"name", "shape", "enabled", "system_supported", "default_mode", "display_order", "description"}
        changes = {key: value for key, value in values.items() if key in allowed}
        changes["updated_at"] = _now()
        with self.database.transaction() as connection:
            result = connection.execute(
                update(REGIONS)
                .where(and_(REGIONS.c.id == region_id, REGIONS.c.row_version == expected_version))
                .values(**changes, row_version=REGIONS.c.row_version + 1)
            )
            if result.rowcount != 1:
                raise VersionConflictError("数据区域已被其他操作更新，请刷新后重试")
            return self._get_region_with_connection(connection, region_id)

    def delete_custom_region(self, region_id: int, expected_version: int) -> None:
        with self.database.transaction() as connection:
            current = _row(connection.execute(
                select(REGIONS).where(REGIONS.c.id == region_id).with_for_update()
            ))
            if current is None or current["row_version"] != expected_version:
                raise VersionConflictError("数据区域已被其他操作更新，请刷新后重试")
            if current["built_in"]:
                raise ValueError("内置数据区域不能删除")
            connection.execute(delete(SOURCE_CONFIGS).where(SOURCE_CONFIGS.c.region_id == region_id))
            connection.execute(delete(FIELDS).where(FIELDS.c.region_id == region_id))
            result = connection.execute(
                delete(REGIONS).where(and_(
                    REGIONS.c.id == region_id,
                    REGIONS.c.row_version == expected_version,
                    REGIONS.c.built_in.is_(False),
                ))
            )
            if result.rowcount != 1:
                raise VersionConflictError("数据区域已被其他操作更新，请刷新后重试")

    def list_fields(
        self, region_id: int, include_disabled: bool = True
    ) -> list[dict[str, Any]]:
        statement = select(FIELDS).where(FIELDS.c.region_id == region_id)
        if not include_disabled:
            statement = statement.where(FIELDS.c.enabled.is_(True))
        statement = statement.order_by(FIELDS.c.display_order.asc(), FIELDS.c.id.asc())
        with self.database.connect() as connection:
            return _rows(connection.execute(statement))

    def get_field(self, field_id: int) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            return _row(connection.execute(select(FIELDS).where(FIELDS.c.id == field_id)))

    def create_field(self, region_id: int, values: Mapping[str, Any]) -> dict[str, Any]:
        now = _now()
        row = {
            "region_id": region_id,
            "field_alias": values["field_alias"],
            "name": values["name"],
            "value_type": values["value_type"],
            "nullable": bool(values["nullable"]),
            "built_in": bool(values.get("built_in", False)),
            "enabled": bool(values.get("enabled", True)),
            "display_order": values["display_order"],
            "description": values.get("description", ""),
            "created_at": now,
            "updated_at": now,
            "row_version": 1,
        }
        with self.database.transaction() as connection:
            try:
                region = self._lock_region_with_connection(connection, region_id)
            except ValueError:
                # Preserve the Task 3 public contract: a missing parent is a
                # foreign-key write failure, while valid writes use the safe
                # region-then-source lock order below.
                connection.execute(insert(FIELDS).values(**row))
                raise RuntimeError("字段写入后无法读取")
            result = connection.execute(insert(FIELDS).values(**row))
            self._bump_region_schema_version_with_connection(connection, region)
            self._invalidate_source_test_with_connection(
                connection, region_id, source_mode="sql"
            )
            return self._get_field_with_connection(connection, int(result.inserted_primary_key[0]))

    def _create_field_with_connection(
        self, connection: Any, region_id: int, values: Mapping[str, Any]
    ) -> dict[str, Any]:
        now = _now()
        row = {
            "region_id": region_id, "field_alias": values["field_alias"], "name": values["name"],
            "value_type": values["value_type"], "nullable": bool(values["nullable"]),
            "built_in": bool(values.get("built_in", False)), "enabled": bool(values.get("enabled", True)),
            "display_order": values["display_order"], "description": values.get("description", ""),
            "created_at": now, "updated_at": now, "row_version": 1,
        }
        result = connection.execute(insert(FIELDS).values(**row))
        return self._get_field_with_connection(connection, int(result.inserted_primary_key[0]))

    def create_field_and_invalidate_source(
        self, region_id: int, values: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Add a field and atomically require a fresh SQL source test."""
        now = _now()
        row = {
            "region_id": region_id,
            "field_alias": values["field_alias"],
            "name": values["name"],
            "value_type": values["value_type"],
            "nullable": bool(values["nullable"]),
            "built_in": bool(values.get("built_in", False)),
            "enabled": bool(values.get("enabled", True)),
            "display_order": values["display_order"],
            "description": values.get("description", ""),
            "created_at": now,
            "updated_at": now,
            "row_version": 1,
        }
        with self.database.transaction() as connection:
            region = self._lock_region_with_connection(connection, region_id)
            result = connection.execute(insert(FIELDS).values(**row))
            self._bump_region_schema_version_with_connection(connection, region)
            self._invalidate_source_test_with_connection(
                connection, region_id, source_mode="sql"
            )
            return self._get_field_with_connection(connection, int(result.inserted_primary_key[0]))

    def update_field(
        self, field_id: int, values: Mapping[str, Any], expected_version: int
    ) -> dict[str, Any]:
        allowed = {"name", "value_type", "nullable", "enabled", "display_order", "description"}
        changes = {key: value for key, value in values.items() if key in allowed}
        changes["updated_at"] = _now()
        with self.database.transaction() as connection:
            field_identity = _row(connection.execute(
                select(FIELDS.c.region_id).where(FIELDS.c.id == field_id)
            ))
            if field_identity is None:
                raise VersionConflictError("字段已被其他操作更新，请刷新后重试")
            region_id = int(field_identity["region_id"])
            region = self._lock_region_with_connection(connection, region_id)
            result = connection.execute(
                update(FIELDS)
                .where(and_(FIELDS.c.id == field_id, FIELDS.c.row_version == expected_version))
                .values(**changes, row_version=FIELDS.c.row_version + 1)
            )
            if result.rowcount != 1:
                raise VersionConflictError("字段已被其他操作更新，请刷新后重试")
            self._bump_region_schema_version_with_connection(connection, region)
            self._invalidate_source_test_with_connection(
                connection, region_id, source_mode="sql"
            )
            return self._get_field_with_connection(connection, field_id)

    def update_field_and_invalidate_source(
        self, field_id: int, values: Mapping[str, Any], expected_version: int
    ) -> dict[str, Any]:
        """Update a field without allowing its region to lose all active fields."""
        allowed = {"name", "value_type", "nullable", "enabled", "display_order", "description"}
        changes = {key: value for key, value in values.items() if key in allowed}
        changes["updated_at"] = _now()
        with self.database.transaction() as connection:
            field_identity = _row(connection.execute(
                select(FIELDS.c.region_id).where(FIELDS.c.id == field_id)
            ))
            if field_identity is None:
                raise ValueError("字段不存在")
            region_id = int(field_identity["region_id"])
            region = self._lock_region_with_connection(connection, region_id)
            current = _row(connection.execute(
                select(FIELDS).where(FIELDS.c.id == field_id).with_for_update()
            ))
            if current is None:
                raise ValueError("字段不存在")
            if current["enabled"] and changes.get("enabled") is False:
                another_enabled = connection.execute(
                    select(FIELDS.c.id)
                    .where(and_(
                        FIELDS.c.region_id == region_id,
                        FIELDS.c.id != field_id,
                        FIELDS.c.enabled.is_(True),
                    ))
                    .limit(1)
                    .with_for_update()
                ).first()
                if another_enabled is None:
                    raise ValueError("至少保留一个启用字段")
            result = connection.execute(
                update(FIELDS)
                .where(and_(FIELDS.c.id == field_id, FIELDS.c.row_version == expected_version))
                .values(**changes, row_version=FIELDS.c.row_version + 1)
            )
            if result.rowcount != 1:
                raise VersionConflictError("字段已被其他操作更新，请刷新后重试")
            self._bump_region_schema_version_with_connection(connection, region)
            self._invalidate_source_test_with_connection(
                connection, region_id, source_mode="sql"
            )
            return self._get_field_with_connection(connection, field_id)

    def get_source_config(self, region_id: int) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            return _row(connection.execute(
                select(SOURCE_CONFIGS).where(SOURCE_CONFIGS.c.region_id == region_id)
            ))

    def invalidate_source_test(self, region_id: int) -> None:
        """Clear a region's successful test marker after its field set changes."""
        with self.database.transaction() as connection:
            self._invalidate_source_test_with_connection(connection, region_id)

    def record_successful_sql_test(
        self, region_id: int, tested_signature: str, tested_by: str, expected_schema_version: int
    ) -> dict[str, Any]:
        """Persist the one-time SQL test marker using the field-change lock order."""
        with self.database.transaction() as connection:
            region = self._lock_region_with_connection(connection, region_id)
            if region["row_version"] != expected_schema_version:
                raise SchemaVersionConflictError("字段已变化，SQL 测试结果已失效")
            current = self._get_source_config_with_connection(connection, region_id)
            if current is None:
                raise ValueError("来源配置不存在")
            locked = _row(connection.execute(
                select(SOURCE_CONFIGS)
                .where(SOURCE_CONFIGS.c.region_id == region_id)
                .with_for_update()
            ))
            if locked is None:
                raise ValueError("来源配置不存在")
            result = connection.execute(
                update(SOURCE_CONFIGS)
                .where(and_(
                    SOURCE_CONFIGS.c.region_id == region_id,
                    SOURCE_CONFIGS.c.row_version == locked["row_version"],
                ))
                .values(
                    tested_signature=tested_signature,
                    tested_at=_now(),
                    tested_by=tested_by,
                    updated_at=_now(),
                    row_version=SOURCE_CONFIGS.c.row_version + 1,
                )
            )
            if result.rowcount != 1:
                raise VersionConflictError("来源配置已发生变化，请刷新后重试")
            source = self._get_source_config_with_connection(connection, region_id)
            if source is None:
                raise RuntimeError("来源配置写入后无法读取")
            return source

    def save_source_config(
        self,
        region_id: int,
        values: Mapping[str, Any],
        expected_version: int | None,
        *,
        expected_region_version: int | None = None,
    ) -> dict[str, Any]:
        allowed = {"source_mode", "datasource_id", "sql_text", "tested_signature", "tested_at", "tested_by"}
        changes = {key: value for key, value in values.items() if key in allowed}
        now = _now()
        with self.database.transaction() as connection:
            region = self._lock_region_with_connection(connection, region_id)
            if expected_region_version is not None and region["row_version"] != expected_region_version:
                raise SchemaVersionConflictError("字段或数据区域形态已变化，请重新测试")
            current = _row(connection.execute(
                select(SOURCE_CONFIGS)
                .where(SOURCE_CONFIGS.c.region_id == region_id)
                .with_for_update()
            ))
            if current is None:
                if expected_version is not None:
                    raise VersionConflictError("来源配置已发生变化，请刷新后重试")
                try:
                    connection.execute(insert(SOURCE_CONFIGS).values(
                        region_id=region_id,
                        source_mode=changes.get("source_mode", "sql"),
                        datasource_id=changes.get("datasource_id"),
                        sql_text=changes.get("sql_text"),
                        tested_signature=changes.get("tested_signature"),
                        tested_at=changes.get("tested_at"),
                        tested_by=changes.get("tested_by"),
                        created_at=now,
                        updated_at=now,
                        row_version=1,
                    ))
                except IntegrityError as error:
                    if _is_source_config_unique_conflict(error):
                        raise VersionConflictError("来源配置已发生变化，请刷新后重试") from None
                    raise
            else:
                if expected_version is None:
                    raise VersionConflictError("来源配置已发生变化，请刷新后重试")
                result = connection.execute(
                    update(SOURCE_CONFIGS)
                    .where(and_(
                        SOURCE_CONFIGS.c.region_id == region_id,
                        SOURCE_CONFIGS.c.row_version == expected_version,
                    ))
                    .values(**changes, updated_at=now, row_version=SOURCE_CONFIGS.c.row_version + 1)
                )
                if result.rowcount != 1:
                    raise VersionConflictError("来源配置已发生变化，请刷新后重试")
            return self._get_source_config_with_connection(connection, region_id)

    @staticmethod
    def _get_region_with_connection(connection: Any, region_id: int) -> dict[str, Any]:
        row = _row(connection.execute(select(REGIONS).where(REGIONS.c.id == region_id)))
        if row is None:
            raise RuntimeError("数据区域写入后无法读取")
        return row

    @staticmethod
    def _lock_region_with_connection(connection: Any, region_id: int) -> dict[str, Any]:
        row = _row(connection.execute(
            select(REGIONS).where(REGIONS.c.id == region_id).with_for_update()
        ))
        if row is None:
            raise ValueError("数据区域不存在")
        return row

    @staticmethod
    def _bump_region_schema_version_with_connection(
        connection: Any, region: Mapping[str, Any]
    ) -> None:
        result = connection.execute(
            update(REGIONS)
            .where(and_(
                REGIONS.c.id == region["id"],
                REGIONS.c.row_version == region["row_version"],
            ))
            .values(updated_at=_now(), row_version=REGIONS.c.row_version + 1)
        )
        if result.rowcount != 1:
            raise VersionConflictError("数据区域已被其他操作更新，请刷新后重试")

    @staticmethod
    def _get_field_with_connection(connection: Any, field_id: int) -> dict[str, Any]:
        row = _row(connection.execute(select(FIELDS).where(FIELDS.c.id == field_id)))
        if row is None:
            raise RuntimeError("字段写入后无法读取")
        return row

    @staticmethod
    def _get_source_config_with_connection(connection: Any, region_id: int) -> dict[str, Any] | None:
        return _row(connection.execute(
            select(SOURCE_CONFIGS).where(SOURCE_CONFIGS.c.region_id == region_id)
        ))

    @staticmethod
    def _create_default_source_config_with_connection(connection: Any, region_id: int) -> None:
        now = _now()
        connection.execute(insert(SOURCE_CONFIGS).values(
            region_id=region_id,
            source_mode="sql",
            datasource_id=None,
            sql_text=None,
            tested_signature=None,
            tested_at=None,
            tested_by=None,
            created_at=now,
            updated_at=now,
            row_version=1,
        ))

    @staticmethod
    def _invalidate_source_test_with_connection(
        connection: Any, region_id: int, *, source_mode: str | None = None
    ) -> None:
        current = _row(connection.execute(
            select(SOURCE_CONFIGS)
            .where(SOURCE_CONFIGS.c.region_id == region_id)
            .with_for_update()
        ))
        if current is None:
            return
        values: dict[str, Any] = {
            "tested_signature": None,
            "tested_at": None,
            "tested_by": None,
            "updated_at": _now(),
            "row_version": SOURCE_CONFIGS.c.row_version + 1,
        }
        if source_mode is not None:
            values["source_mode"] = source_mode
        result = connection.execute(
            update(SOURCE_CONFIGS)
            .where(and_(
                SOURCE_CONFIGS.c.region_id == region_id,
                SOURCE_CONFIGS.c.row_version == current["row_version"],
            ))
            .values(**values)
        )
        if result.rowcount != 1:
            raise VersionConflictError("来源配置已发生变化，请刷新后重试")
