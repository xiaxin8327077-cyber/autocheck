from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from auto_check.app.time_utils import beijing_timestamp
from auto_check.db_validation.metadata import TableFieldCatalog


@dataclass(frozen=True)
class FieldMappingCacheStatus:
    initialized: bool
    refreshed_at: str
    refresh_source: str
    table_count: int
    field_count: int
    unmapped_field_count: int
    last_error: str
    last_failed_at: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "initialized": self.initialized,
            "refreshed_at": self.refreshed_at,
            "refresh_source": self.refresh_source,
            "table_count": self.table_count,
            "field_count": self.field_count,
            "unmapped_field_count": self.unmapped_field_count,
            "last_error": self.last_error,
            "last_failed_at": self.last_failed_at,
        }


class FieldMappingCache:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._catalog: TableFieldCatalog | None = None
        self._signature: tuple[Any, ...] | None = None
        self._refreshed_at = ""
        self._refresh_source = ""
        self._last_error = ""
        self._last_failed_at = ""

    def get_or_refresh(
        self,
        signature: tuple[Any, ...],
        loader: Callable[[], TableFieldCatalog],
        *,
        source: str,
    ) -> TableFieldCatalog:
        with self._lock:
            if self._catalog is not None and self._signature == signature:
                return self._catalog
        return self.refresh(signature, loader, source=source)

    def refresh(
        self,
        signature: tuple[Any, ...],
        loader: Callable[[], TableFieldCatalog],
        *,
        source: str,
    ) -> TableFieldCatalog:
        with self._lock:
            try:
                catalog = loader()
            except Exception as exc:
                self._last_failed_at = beijing_timestamp()
                self._last_error = _error_message(exc)
                raise
            self._catalog = catalog
            self._signature = signature
            self._refreshed_at = beijing_timestamp()
            self._refresh_source = source
            self._last_error = ""
            self._last_failed_at = ""
            return catalog

    def invalidate(self) -> None:
        with self._lock:
            self._catalog = None
            self._signature = None

    def status(self) -> FieldMappingCacheStatus:
        with self._lock:
            catalog = self._catalog
            table_count = len(catalog.by_table) if catalog is not None else 0
            field_count = sum(len(fields) for fields in catalog.by_table.values()) if catalog is not None else 0
            unmapped_field_count = catalog.unmapped_field_count if catalog is not None else 0
            return FieldMappingCacheStatus(
                initialized=catalog is not None,
                refreshed_at=self._refreshed_at,
                refresh_source=self._refresh_source,
                table_count=table_count,
                field_count=field_count,
                unmapped_field_count=unmapped_field_count,
                last_error=self._last_error,
                last_failed_at=self._last_failed_at,
            )

    def status_payload(self) -> dict[str, Any]:
        return self.status().to_payload()


def _error_message(exc: Exception) -> str:
    message = str(exc).strip()
    if not message:
        return "字段映射刷新失败"
    return message.splitlines()[0]
