"""通知主体与收件状态的 SQLAlchemy Core 仓储。"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import (
    JSON,
    CHAR,
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Text,
    and_,
    delete,
    insert,
    or_,
    select,
    update,
)

from auto_check.app.notifications.contracts import (
    NotificationAction,
    NotificationItem,
    NotificationPage,
    NotificationPublishRequest,
    NotificationPublishResult,
    action_from_json,
    encode_cursor,
)

METADATA = MetaData()

NOTIFICATIONS = Table(
    "system_notifications",
    METADATA,
    Column("id", CHAR(32), primary_key=True),
    Column("source_module", String(64), nullable=False),
    Column("event_type", String(64), nullable=False),
    Column("category", String(64), nullable=False),
    Column("level", String(16), nullable=False),
    Column("title", String(191), nullable=False),
    Column("content", Text, nullable=False),
    Column("action_json", JSON, nullable=True),
    Column("dedupe_key", String(191), nullable=False),
    Column("dedupe_hash", CHAR(64), nullable=False),
    Column("created_at", DateTime(6), nullable=False),
    Column("expires_at", DateTime(6), nullable=False),
)

RECIPIENTS = Table(
    "system_notification_recipients",
    METADATA,
    Column("notification_id", CHAR(32), primary_key=True),
    Column("user_id", String(64), primary_key=True),
    Column("received_at", DateTime(6), nullable=False),
    Column("read_at", DateTime(6), nullable=True),
    Column("cleared_at", DateTime(6), nullable=True),
)


class NotificationStorage:
    def __init__(self, database: Any) -> None:
        self._database = database

    @property
    def database(self) -> Any:
        return self._database

    @staticmethod
    def _row_to_dict(row: Any) -> dict:
        if hasattr(row, '_mapping'):
            return dict(row._mapping)
        return dict(row)

    def create_or_get(
        self,
        source_module: str,
        request: NotificationPublishRequest,
        now: datetime,
    ) -> NotificationPublishResult:
        dedupe_hash = hashlib.sha256(request.dedupe_key.encode("utf-8")).hexdigest()
        with self._database.transaction() as conn:
            existing = conn.execute(
                select(NOTIFICATIONS.c.id).where(
                    and_(
                        NOTIFICATIONS.c.source_module == source_module,
                        NOTIFICATIONS.c.event_type == request.event_type,
                        NOTIFICATIONS.c.dedupe_hash == dedupe_hash,
                    )
                )
            ).first()
            if existing is not None:
                existing_dict = self._row_to_dict(existing)
                return NotificationPublishResult(
                    notification_id=existing_dict["id"],
                    created=False,
                    recipient_count=0,
                )
            notification_id = uuid.uuid4().hex
            conn.execute(
                insert(NOTIFICATIONS).values(
                    id=notification_id,
                    source_module=source_module,
                    event_type=request.event_type,
                    category=request.category,
                    level=request.level,
                    title=request.title,
                    content=request.content,
                    action_json=self._action_json_value(request.action),
                    dedupe_key=request.dedupe_key,
                    dedupe_hash=dedupe_hash,
                    created_at=now,
                    expires_at=now + timedelta(days=30),
                )
            )
            recipient_values = [
                {
                    "notification_id": notification_id,
                    "user_id": user_id,
                    "received_at": now,
                    "read_at": None,
                    "cleared_at": None,
                }
                for user_id in request.recipient_user_ids
            ]
            if recipient_values:
                conn.execute(insert(RECIPIENTS), recipient_values)
        return NotificationPublishResult(
            notification_id=notification_id,
            created=True,
            recipient_count=len(request.recipient_user_ids),
        )

    def get_for_user(
        self,
        user_id: str,
        notification_id: str,
        now: datetime,
    ) -> NotificationItem | None:
        with self._database.connect() as conn:
            notif_row = conn.execute(
                select(NOTIFICATIONS).where(NOTIFICATIONS.c.id == notification_id)
            ).first()
            if notif_row is None:
                return None
            notif_dict = self._row_to_dict(notif_row)
            if notif_dict["expires_at"] <= now:
                return None
            recip_row = conn.execute(
                select(RECIPIENTS).where(
                    and_(
                        RECIPIENTS.c.notification_id == notification_id,
                        RECIPIENTS.c.user_id == user_id,
                        RECIPIENTS.c.cleared_at == None,
                    )
                )
            ).first()
            if recip_row is None:
                return None
        return self._item_from_rows(notif_dict, self._row_to_dict(recip_row))

    def list_for_user(
        self,
        user_id: str,
        *,
        unread_only: bool,
        limit: int,
        cursor: tuple[datetime, str] | None,
        now: datetime,
        read_only: bool = False,
    ) -> NotificationPage:
        with self._database.connect() as conn:
            # Query recipients with filters pushed to database
            recip_conditions = [
                RECIPIENTS.c.user_id == user_id,
                RECIPIENTS.c.cleared_at == None,
            ]
            if unread_only:
                recip_conditions.append(RECIPIENTS.c.read_at == None)
            elif read_only:
                recip_conditions.append(RECIPIENTS.c.read_at != None)
            if cursor is not None:
                cursor_time, cursor_id = cursor
                recip_conditions.append(
                    or_(
                        RECIPIENTS.c.received_at < cursor_time,
                        and_(
                            RECIPIENTS.c.received_at == cursor_time,
                            RECIPIENTS.c.notification_id < cursor_id,
                        ),
                    )
                )
            recip_rows = conn.execute(
                select(RECIPIENTS)
                .where(and_(*recip_conditions))
                .order_by(RECIPIENTS.c.received_at.desc(), RECIPIENTS.c.notification_id.desc())
                .limit(limit + 1)
            ).all()
            recip_rows = [self._row_to_dict(r) for r in recip_rows]
            has_more = len(recip_rows) > limit
            recip_rows = recip_rows[:limit]
            # Batch query notifications
            notif_ids = [r["notification_id"] for r in recip_rows]
            notif_map: dict[str, dict] = {}
            if notif_ids:
                for row in conn.execute(
                    select(NOTIFICATIONS).where(NOTIFICATIONS.c.id.in_(notif_ids))
                ).all():
                    d = self._row_to_dict(row)
                    notif_map[d["id"]] = d
            items = []
            for rr in recip_rows:
                notif = notif_map.get(rr["notification_id"])
                if notif and notif["expires_at"] > now:
                    items.append(self._item_from_rows(notif, rr))
            unread_count = self._count_unread(conn, user_id, now)
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = encode_cursor(last.received_at, last.id)
        return NotificationPage(
            items=tuple(items),
            unread_count=unread_count,
            next_cursor=next_cursor,
        )

    def unread_count(self, user_id: str, now: datetime) -> int:
        with self._database.connect() as conn:
            return self._count_unread(conn, user_id, now)

    def mark_read(
        self,
        user_id: str,
        notification_id: str,
        read_at: datetime,
    ) -> NotificationItem | None:
        with self._database.transaction() as conn:
            conn.execute(
                update(RECIPIENTS)
                .values(read_at=read_at)
                .where(
                    and_(
                        RECIPIENTS.c.notification_id == notification_id,
                        RECIPIENTS.c.user_id == user_id,
                    )
                )
            )
        return self.get_for_user(user_id, notification_id, read_at)

    def mark_all_read(self, user_id: str, read_at: datetime) -> int:
        with self._database.transaction() as conn:
            result = conn.execute(
                update(RECIPIENTS)
                .values(read_at=read_at)
                .where(RECIPIENTS.c.user_id == user_id)
            )
            return result.rowcount if hasattr(result, "rowcount") else 0

    def delete_all_for_user(self, user_id: str, now: datetime) -> int:
        with self._database.transaction() as conn:
            result = conn.execute(
                update(RECIPIENTS)
                .values(cleared_at=now)
                .where(
                    and_(
                        RECIPIENTS.c.user_id == user_id,
                        RECIPIENTS.c.cleared_at == None,
                    )
                )
            )
            return result.rowcount if hasattr(result, "rowcount") else 0

    def delete_expired_batch(self, now: datetime, limit: int = 1000) -> int:
        with self._database.transaction() as conn:
            # Directly select expired notifications by expires_at,
            # regardless of whether recipients have been cleared.
            expired_ids = [
                self._row_to_dict(row)["id"]
                for row in conn.execute(
                    select(NOTIFICATIONS.c.id)
                    .where(NOTIFICATIONS.c.expires_at <= now)
                    .limit(limit)
                ).all()
            ]
            if not expired_ids:
                return 0
            # Delete all recipient rows for these notifications (including cleared)
            conn.execute(
                delete(RECIPIENTS).where(RECIPIENTS.c.notification_id.in_(expired_ids))
            )
            conn.execute(
                delete(NOTIFICATIONS).where(NOTIFICATIONS.c.id.in_(expired_ids))
            )
        return len(expired_ids)

    def _count_unread(self, conn: Any, user_id: str, now: datetime) -> int:
        # Get unread recipient notification IDs (exclude cleared)
        unread_rows = conn.execute(
            select(RECIPIENTS.c.notification_id)
            .where(
                and_(
                    RECIPIENTS.c.user_id == user_id,
                    RECIPIENTS.c.read_at == None,
                    RECIPIENTS.c.cleared_at == None,
                )
            )
        ).all()
        unread_ids = {self._row_to_dict(r)["notification_id"] for r in unread_rows}
        if not unread_ids:
            return 0
        # Count how many are still unexpired
        notif_rows = conn.execute(
            select(NOTIFICATIONS.c.id)
            .where(
                and_(
                    NOTIFICATIONS.c.id.in_(list(unread_ids)),
                    NOTIFICATIONS.c.expires_at > now,
                )
            )
        ).all()
        return len(notif_rows)

    def _item_from_rows(self, notif_row: Any, recip_row: Any) -> NotificationItem:
        notif_dict = self._row_to_dict(notif_row) if not isinstance(notif_row, dict) else notif_row
        recip_dict = self._row_to_dict(recip_row) if not isinstance(recip_row, dict) else recip_row
        action_json = notif_dict.get("action_json")
        action = action_from_json(action_json)
        received_at = recip_dict["received_at"]
        read_at = recip_dict["read_at"]
        return NotificationItem(
            id=notif_dict["id"],
            source_module=notif_dict["source_module"],
            event_type=notif_dict["event_type"],
            category=notif_dict["category"],
            level=notif_dict["level"],
            title=notif_dict["title"],
            content=notif_dict["content"],
            action=action,
            created_at=notif_dict["created_at"],
            received_at=received_at,
            read_at=read_at,
            is_read=read_at is not None,
        )

    @staticmethod
    def _action_json_value(action: NotificationAction | None) -> Any:
        if action is None:
            return None
        return {
            "type": action.type,
            "route": action.route,
            "query": dict(action.query),
        }
