from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol


PLATFORM_API_VERSION = 1
_BACKEND_ENTRY_PATTERN = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+:[A-Za-z_][A-Za-z0-9_]*"
)


class ModuleManifestError(ValueError):
    """Raised when a module manifest does not satisfy the platform contract."""


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ModuleManifestError(f"{key} must be a non-empty string")
    return value.strip()


def _required_int(payload: Mapping[str, object], key: str, *, minimum: int) -> int:
    value = payload.get(key)
    if type(value) is not int or value < minimum:
        raise ModuleManifestError(f"{key} must be an integer greater than or equal to {minimum}")
    return value


def _required_text_tuple(payload: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ModuleManifestError(f"{key} must be a list of non-empty strings")
    normalized = tuple(item.strip() for item in value)
    if len(set(normalized)) != len(normalized):
        raise ModuleManifestError(f"{key} contains duplicate values")
    return normalized


class ModuleStatus(StrEnum):
    DISCOVERED = "discovered"
    LOADING = "loading"
    ENABLED = "enabled"
    DISABLED = "disabled"
    INCOMPATIBLE = "incompatible"
    MIGRATION_FAILED = "migration_failed"
    STARTUP_FAILED = "startup_failed"


@dataclass(frozen=True)
class NavigationDeclaration:
    id: str
    label: str
    route: str
    order: int
    permission: str


@dataclass(frozen=True)
class ModuleManifest:
    id: str
    name: str
    version: str
    platform_api: int
    required: bool
    backend_entry: str
    api_prefix: str
    frontend_entry: str
    frontend_style: str
    navigation: tuple[NavigationDeclaration, ...]
    permissions: tuple[str, ...]
    dependencies: tuple[str, ...]
    schema_version: int

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> ModuleManifest:
        module_id = _required_text(payload, "id")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", module_id):
            raise ModuleManifestError("id must use lowercase letters, digits, and underscores")

        version = _required_text(payload, "version")
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise ModuleManifestError("version must use MAJOR.MINOR.PATCH")

        platform_api = _required_int(payload, "platform_api", minimum=1)
        if platform_api != PLATFORM_API_VERSION:
            raise ModuleManifestError(
                f"platform_api {platform_api} is incompatible with {PLATFORM_API_VERSION}"
            )

        api_prefix = _required_text(payload, "api_prefix")
        if not api_prefix.startswith("/api/modules/"):
            raise ModuleManifestError("api_prefix must start with /api/modules/")

        backend_entry = _required_text(payload, "backend_entry")
        if not _BACKEND_ENTRY_PATTERN.fullmatch(backend_entry):
            raise ModuleManifestError("backend_entry must use package.module:function")

        permissions = _required_text_tuple(payload, "permissions")
        if any(not item.startswith(f"{module_id}.") for item in permissions):
            raise ModuleManifestError("permission must use the module namespace")

        dependencies = _required_text_tuple(payload, "dependencies")
        if module_id in dependencies:
            raise ModuleManifestError("dependencies cannot contain the module itself")
        if any(not re.fullmatch(r"[a-z][a-z0-9_]*", item) for item in dependencies):
            raise ModuleManifestError("dependencies contain an invalid module id")

        navigation_payload = payload.get("navigation")
        if not isinstance(navigation_payload, list):
            raise ModuleManifestError("navigation must be a list")
        navigation = tuple(
            NavigationDeclaration(
                id=_required_text(item, "id"),
                label=_required_text(item, "label"),
                route=_required_text(item, "route"),
                order=_required_int(item, "order", minimum=0),
                permission=_required_text(item, "permission"),
            )
            for item in navigation_payload
            if isinstance(item, Mapping)
        )
        if len(navigation) != len(navigation_payload):
            raise ModuleManifestError("navigation items must be objects")
        if any(item.permission not in permissions for item in navigation):
            raise ModuleManifestError("navigation permission is not declared")
        if len({item.id for item in navigation}) != len(navigation):
            raise ModuleManifestError("navigation contains a duplicate id")
        if len({item.route for item in navigation}) != len(navigation):
            raise ModuleManifestError("navigation contains a duplicate route")

        frontend_entry = _required_text(payload, "frontend_entry")
        frontend_style = _required_text(payload, "frontend_style")
        resource_prefix = f"/module-assets/{module_id}/"
        if not frontend_entry.startswith(resource_prefix):
            raise ModuleManifestError("frontend_entry must use the module asset namespace")
        if not frontend_style.startswith(resource_prefix):
            raise ModuleManifestError("frontend_style must use the module asset namespace")

        required = payload.get("required")
        if not isinstance(required, bool):
            raise ModuleManifestError("required must be a boolean")

        return cls(
            id=module_id,
            name=_required_text(payload, "name"),
            version=version,
            platform_api=platform_api,
            required=required,
            backend_entry=backend_entry,
            api_prefix=api_prefix,
            frontend_entry=frontend_entry,
            frontend_style=frontend_style,
            navigation=navigation,
            permissions=permissions,
            dependencies=dependencies,
            schema_version=_required_int(payload, "schema_version", minimum=0),
        )


@dataclass(frozen=True)
class ModuleRequest:
    method: str
    path: str
    path_params: Mapping[str, str]
    query: Mapping[str, str]
    body: Mapping[str, Any] | None
    current_user: Mapping[str, Any]


@dataclass(frozen=True)
class ModuleHttpResponse:
    status: int
    body: Mapping[str, Any] | bytes
    content_type: str
    headers: tuple[tuple[str, str], ...] = ()

    @classmethod
    def json(cls, status: int, body: Mapping[str, Any]) -> ModuleHttpResponse:
        return cls(status=status, body=body, content_type="application/json; charset=utf-8")

    @classmethod
    def bytes(
        cls,
        status: int,
        body: bytes,
        *,
        content_type: str,
        headers: tuple[tuple[str, str], ...] = (),
    ) -> ModuleHttpResponse:
        return cls(status=status, body=body, content_type=content_type, headers=headers)


@dataclass(frozen=True)
class ModuleHealth:
    healthy: bool
    message: str = ""


@dataclass(frozen=True)
class ModuleBootstrapContext:
    application_database: Any
    config_path: Path
    temp_root: Path
    now: Callable[[], Any]


@dataclass(frozen=True)
class ModuleContext(ModuleBootstrapContext):
    services: Any
    events: Any
    logger: Any
    background_executor: Any


class AutoCheckModule(Protocol):
    manifest: ModuleManifest

    def register_routes(self, router: Any) -> None:
        """Register relative API routes."""

    def register_schema(self, registry: Any) -> None:
        """Register expected module-owned tables and columns."""

    def start(self, context: ModuleContext) -> None:
        """Start module-owned services and background work."""

    def stop(self) -> None:
        """Stop module-owned services and release subscriptions."""

    def health(self) -> ModuleHealth:
        """Return current module health without exposing secrets."""
