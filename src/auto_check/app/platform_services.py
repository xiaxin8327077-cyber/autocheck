"""Small, versioned platform facades exposed to trusted built-in modules."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from auto_check.app.module_system.services import BoundService, PlatformServiceSpec
from auto_check.app.security import AuthManager


USER_DIRECTORY_SERVICE = "platform.user_directory"
USER_DIRECTORY_VERSION = 1
_CLOSED_FACADE_ERROR = "platform service facade is closed"


@dataclass(frozen=True)
class PublicUser:
    id: str
    username: str
    display_name: str
    active: bool
    role: str = ""


class _UserDirectoryFacade:
    """Read-only, revocable projection over the application's AuthManager."""

    def __init__(self, auth_manager: AuthManager) -> None:
        self._auth_manager = auth_manager
        self._closed = False
        self._lock = RLock()

    def list_active_users(self) -> tuple[PublicUser, ...]:
        with self._lock:
            self._require_open()
            return self._active_users()

    def get_user(self, user_id: str) -> PublicUser | None:
        with self._lock:
            self._require_open()
            requested_id = str(user_id)
            return next(
                (user for user in self._active_users() if user.id == requested_id),
                None,
            )

    def _active_users(self) -> tuple[PublicUser, ...]:
        return tuple(
            PublicUser(
                id=str(user["id"]),
                username=str(user["username"]),
                display_name=str(user["display_name"]),
                active=True,
                role=str(user.get("role") or ""),
            )
            for user in self._auth_manager.list_users()
            if bool(user.get("enabled"))
        )

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError(_CLOSED_FACADE_ERROR)

    def _close(self) -> None:
        with self._lock:
            self._closed = True


def create_user_directory_service(auth_manager: AuthManager) -> PlatformServiceSpec:
    """Create the v1 user-directory platform service backed by one AuthManager."""

    def bind(_owner: str) -> BoundService:
        facade = _UserDirectoryFacade(auth_manager)
        return BoundService(value=facade, close=facade._close)

    return PlatformServiceSpec(
        name=USER_DIRECTORY_SERVICE,
        version=USER_DIRECTORY_VERSION,
        binder=bind,
    )


DICTIONARY_SERVICE = "platform.dictionary"
DICTIONARY_SERVICE_VERSION = 1


@dataclass(frozen=True)
class PublicDictionaryItem:
    """对外暴露的最小字典项视图：编码、展示名与排序。"""

    code: str
    label: str
    sort_order: int


class _DictionaryFacade:
    """只读、可撤销的系统字典视图；仅返回启用分类下的启用字典项。"""

    def __init__(self, database) -> None:
        self._database = database
        self._closed = False
        self._lock = RLock()

    def list_active_items(self, dictionary_code: str) -> tuple[PublicDictionaryItem, ...]:
        with self._lock:
            self._require_open()
            from auto_check.app.storage_dictionaries import list_active_dictionary_items

            with self._database.connect() as connection:
                rows = list_active_dictionary_items(connection, str(dictionary_code or ""))
            return tuple(
                PublicDictionaryItem(
                    code=str(row["code"]),
                    label=str(row["name"]),
                    sort_order=int(row["sort_order"]),
                )
                for row in rows
            )

    def get_active_item(self, dictionary_code: str, item_code: str) -> PublicDictionaryItem | None:
        requested = str(item_code or "")
        return next(
            (item for item in self.list_active_items(dictionary_code) if item.code == requested),
            None,
        )

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError(_CLOSED_FACADE_ERROR)

    def _close(self) -> None:
        with self._lock:
            self._closed = True


def create_dictionary_service(application_database) -> PlatformServiceSpec:
    """创建 v1 只读字典平台服务；每个模块 owner 绑定独立 facade。"""

    def bind(_owner: str) -> BoundService:
        facade = _DictionaryFacade(application_database)
        return BoundService(value=facade, close=facade._close)

    return PlatformServiceSpec(
        name=DICTIONARY_SERVICE,
        version=DICTIONARY_SERVICE_VERSION,
        binder=bind,
    )
