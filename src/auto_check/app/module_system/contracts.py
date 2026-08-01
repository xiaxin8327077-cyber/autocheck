from __future__ import annotations

import json
import logging
import re
from concurrent.futures import Future
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from auto_check.app.module_system.events import ModuleEvents
from auto_check.app.module_system.services import ModuleServices


PLATFORM_API_VERSION = 1
_BACKEND_ENTRY_PATTERN = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+:[A-Za-z_][A-Za-z0-9_]*"
)
_SERVICE_NAME_PATTERN = re.compile(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*")
_HEADER_NAME_PATTERN = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
_MODULE_RESPONSE_HEADERS = frozenset(
    {"allow", "content-disposition", "etag", "last-modified", "location", "retry-after"}
)
MAX_MODULE_RESPONSE_BYTES = 50 * 1024 * 1024


class ModuleManifestError(ValueError):
    """Raised when a module manifest does not satisfy the platform contract."""


class ModuleResponseError(RuntimeError):
    """Raised when a module returns an unsafe or incompatible HTTP response."""


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
class ServiceDeclaration:
    name: str
    version: int


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
    table_prefix: str
    services: tuple[ServiceDeclaration, ...]

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

        services_payload = payload.get("services", [])
        if not isinstance(services_payload, list):
            raise ModuleManifestError("services must be a list")
        services = tuple(
            ServiceDeclaration(
                name=_required_text(item, "name"),
                version=_required_int(item, "version", minimum=1),
            )
            for item in services_payload
            if isinstance(item, Mapping)
        )
        if len(services) != len(services_payload):
            raise ModuleManifestError("service declarations must be objects")
        if any(
            not _SERVICE_NAME_PATTERN.fullmatch(service.name)
            or not service.name.startswith(f"{module_id}.")
            for service in services
        ):
            raise ModuleManifestError("service name must use the module namespace")
        if len({service.name for service in services}) != len(services):
            raise ModuleManifestError("service declarations contain duplicate names")

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
            table_prefix=_table_prefix(payload, module_id),
            services=services,
        )


def _table_prefix(payload: Mapping[str, object], module_id: str) -> str:
    value = payload.get("table_prefix", f"{module_id}_")
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_]*_", value):
        raise ModuleManifestError("table_prefix must be a lowercase table prefix")
    allowed = {f"{module_id}_"}
    if module_id.endswith("s"):
        allowed.add(f"{module_id[:-1]}_")
    if value.startswith("app_") or value not in allowed:
        raise ModuleManifestError("table_prefix is not in the module namespace")
    return value


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
    wire_body: bytes = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.status) is not int or not 200 <= self.status <= 599:
            raise ModuleResponseError("module response status is invalid")
        if type(self.content_type) is not str or not _safe_header_value(self.content_type):
            raise ModuleResponseError("module response content type is invalid")
        if "/" not in self.content_type or len(self.content_type) > 255:
            raise ModuleResponseError("module response content type is invalid")
        if type(self.headers) is not tuple:
            raise ModuleResponseError("module response headers are invalid")
        seen_headers: set[str] = set()
        for header in self.headers:
            if type(header) is not tuple or len(header) != 2:
                raise ModuleResponseError("module response headers are invalid")
            name, value = header
            if type(name) is not str or _HEADER_NAME_PATTERN.fullmatch(name) is None:
                raise ModuleResponseError("module response header name is invalid")
            normalized_name = name.lower()
            if normalized_name not in _MODULE_RESPONSE_HEADERS or normalized_name in seen_headers:
                raise ModuleResponseError("module response header is not allowed")
            if type(value) is not str or not _safe_header_value(value) or len(value) > 8192:
                raise ModuleResponseError("module response header value is invalid")
            seen_headers.add(normalized_name)
        if type(self.body) is bytes:
            wire_body = self.body
        elif isinstance(self.body, Mapping):
            if any(not isinstance(key, str) for key in self.body):
                raise ModuleResponseError("module JSON response keys must be strings")
            if not self.content_type.lower().startswith("application/json"):
                raise ModuleResponseError("module JSON response content type is invalid")
            try:
                wire_body = json.dumps(
                    dict(self.body), ensure_ascii=False, separators=(",", ":")
                ).encode(
                    "utf-8"
                )
            except (TypeError, ValueError, OverflowError):
                raise ModuleResponseError("module JSON response is not serializable") from None
        else:
            raise ModuleResponseError("module response body is invalid")
        if len(wire_body) > MAX_MODULE_RESPONSE_BYTES:
            raise ModuleResponseError("module response body is too large")
        if self.status in {204, 205, 304} and wire_body:
            raise ModuleResponseError("module response status does not allow a body")
        object.__setattr__(self, "wire_body", wire_body)

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


def _safe_header_value(value: str) -> bool:
    return bool(value) and all(
        32 <= ord(character) <= 255 and ord(character) != 127 for character in value
    )


def validate_module_response(response: object) -> ModuleHttpResponse:
    if not isinstance(response, ModuleHttpResponse):
        raise ModuleResponseError("module handler returned an invalid response")
    return response


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


class ModuleTaskExecutor(Protocol):
    """Module-owned background task executor supplied by the runtime."""

    def submit(self, callable: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Future:
        """Submit one module-owned task."""

    def shutdown(self, cancel_pending: bool) -> None:
        """Stop this module's executor and optionally cancel queued tasks."""


@dataclass(frozen=True)
class ModuleContext(ModuleBootstrapContext):
    services: ModuleServices
    events: ModuleEvents
    logger: logging.LoggerAdapter
    background_executor: ModuleTaskExecutor


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
