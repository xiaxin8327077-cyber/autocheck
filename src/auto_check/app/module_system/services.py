from __future__ import annotations

import re
from dataclasses import dataclass
from threading import RLock
from typing import Callable


_MODULE_ID_PATTERN = re.compile(r"[a-z][a-z0-9_]*")
_SERVICE_NAME_PATTERN = re.compile(r"([a-z][a-z0-9_]*)\.([a-z][a-z0-9_]*)")


class ServiceVersionError(ValueError):
    """Raised when a public service does not meet a requested version."""


class ServiceAccessError(PermissionError):
    """Raised when a module accesses a service outside its declared boundary."""


class ServiceUnavailableError(KeyError):
    """Raised when a declared service provider is not currently available."""


@dataclass(frozen=True)
class _ServiceRegistration:
    version: int
    provider: object
    owner: str


def _validate_module_id(owner: str) -> None:
    if not isinstance(owner, str) or not _MODULE_ID_PATTERN.fullmatch(owner):
        raise ValueError("owner must be a valid module namespace")


def _validate_service_name(name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("service name must use a namespace")
    match = _SERVICE_NAME_PATTERN.fullmatch(name)
    if match is None:
        raise ValueError("service name must use a namespace")
    return match.group(1)


def _validate_version(version: int, *, field: str) -> None:
    if type(version) is not int or version < 1:
        raise ValueError(f"{field} must be a positive integer")


class ServiceRegistry:
    """Versioned public services owned by module namespaces."""

    def __init__(self) -> None:
        self._services: dict[str, _ServiceRegistration] = {}
        self._lock = RLock()

    def register(self, name: str, version: int, provider: object, owner: str) -> None:
        namespace = _validate_service_name(name)
        _validate_module_id(owner)
        _validate_version(version, field="version")
        if namespace != owner:
            raise ValueError("service name must use the owner's namespace")
        with self._lock:
            if name in self._services:
                raise ValueError(f"service {name!r} is already registered")
            self._services[name] = _ServiceRegistration(
                version=version, provider=provider, owner=owner
            )

    def resolve(self, name: str, minimum_version: int) -> object:
        _validate_service_name(name)
        _validate_version(minimum_version, field="minimum_version")
        with self._lock:
            try:
                registration = self._services[name]
            except KeyError:
                raise ServiceUnavailableError(f"service {name!r} is unavailable") from None
        if registration.version < minimum_version:
            raise ServiceVersionError(
                f"service {name!r} version {registration.version} does not satisfy "
                f"minimum version {minimum_version}"
            )
        return registration.provider

    def for_module(
        self,
        owner: str,
        *,
        declared_services: dict[str, int] | None = None,
        dependencies: tuple[str, ...] = (),
    ) -> ModuleServices:
        _validate_module_id(owner)
        declarations = dict(declared_services or {})
        allowed_namespaces = {owner, *dependencies}

        def register_for_owner(name: str, version: int, provider: object) -> None:
            if declarations.get(name) is None:
                raise ServiceAccessError(f"service {name!r} is not declared")
            if declarations[name] != version:
                raise ServiceVersionError(f"service {name!r} version does not match its declaration")
            self.register(name, version, provider, owner)

        def resolve_for_owner(name: str, minimum_version: int) -> object:
            namespace = _validate_service_name(name)
            if namespace not in allowed_namespaces:
                raise ServiceAccessError(f"service {name!r} is outside declared dependencies")
            return self.resolve(name, minimum_version)

        return ModuleServices(register=register_for_owner, resolve=resolve_for_owner)

    def unregister_owner(self, owner: str) -> None:
        """Remove public services when their owning module stops."""
        _validate_module_id(owner)
        with self._lock:
            for name, registration in tuple(self._services.items()):
                if registration.owner == owner:
                    del self._services[name]


class ModuleServices:
    """Module-scoped service registration and read-only resolution view."""

    __slots__ = ("_register", "_resolve")

    def __init__(
        self,
        *,
        register: Callable[[str, int, object], None],
        resolve: Callable[[str, int], object],
    ) -> None:
        self._register = register
        self._resolve = resolve

    def register(self, name: str, version: int, provider: object) -> None:
        self._register(name, version, provider)

    def resolve(self, name: str, minimum_version: int) -> object:
        return self._resolve(name, minimum_version)
