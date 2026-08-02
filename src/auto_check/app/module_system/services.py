from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from threading import RLock
from typing import Callable, Mapping


_MODULE_ID_PATTERN = re.compile(r"[a-z][a-z0-9_]*")
_SERVICE_NAME_PATTERN = re.compile(r"([a-z][a-z0-9_]*)\.([a-z][a-z0-9_]*)")
_PLATFORM_SERVICE_NAME_PATTERN = re.compile(r"platform\.[a-z][a-z0-9_]*")


class ServiceVersionError(ValueError):
    """Raised when a public service does not meet a requested version."""


class ServiceAccessError(PermissionError):
    """Raised when a module accesses a service outside its declared boundary."""


class ServiceUnavailableError(KeyError):
    """Raised when a declared service provider is not currently available."""


@dataclass(frozen=True)
class BoundService:
    """An owner-specific service facade and its revocation callback."""

    value: object
    close: Callable[[], None]


@dataclass(frozen=True)
class PlatformServiceSpec:
    """A versioned platform service that binds a facade for each module owner."""

    name: str
    version: int
    binder: Callable[[str], BoundService]


@dataclass(frozen=True)
class _ServiceRegistration:
    version: int
    provider: object
    owner: str


@dataclass(frozen=True)
class _PlatformBinding:
    version: int
    bound: BoundService


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
        self._platform_services: dict[str, PlatformServiceSpec] = {}
        self._lock = RLock()

    def register_platform(self, spec: PlatformServiceSpec) -> None:
        if not isinstance(spec, PlatformServiceSpec):
            raise ValueError("platform service specification is invalid")
        if (
            not isinstance(spec.name, str)
            or _PLATFORM_SERVICE_NAME_PATTERN.fullmatch(spec.name) is None
        ):
            raise ValueError("platform service name is invalid")
        _validate_version(spec.version, field="version")
        if not callable(spec.binder):
            raise ValueError("platform service binder is invalid")
        with self._lock:
            if spec.name in self._platform_services:
                raise ValueError(f"platform service {spec.name!r} is already registered")
            self._platform_services[spec.name] = spec

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
        service_dependencies: Mapping[str, int] | None = None,
    ) -> ModuleServices:
        _validate_module_id(owner)
        declarations = dict(declared_services or {})
        platform_requirements = dict(service_dependencies or {})
        for name, minimum_version in platform_requirements.items():
            if (
                not isinstance(name, str)
                or _PLATFORM_SERVICE_NAME_PATTERN.fullmatch(name) is None
            ):
                raise ValueError("platform service requirement name is invalid")
            _validate_version(minimum_version, field="minimum_version")
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

        def bind_platform_for_owner(
            name: str, minimum_version: int
        ) -> _PlatformBinding:
            try:
                declared_minimum = platform_requirements[name]
            except KeyError:
                raise ServiceAccessError(
                    f"platform service {name!r} is not declared"
                ) from None
            required_version = max(declared_minimum, minimum_version)
            with self._lock:
                try:
                    spec = self._platform_services[name]
                except KeyError:
                    raise ServiceUnavailableError(
                        f"platform service {name!r} is unavailable"
                    ) from None
            if spec.version < required_version:
                raise ServiceVersionError(
                    f"platform service {name!r} version {spec.version} does not satisfy "
                    f"minimum version {required_version}"
                )
            try:
                bound = spec.binder(owner)
            except BaseException:
                raise ServiceUnavailableError("platform service binding failed") from None
            if not isinstance(bound, BoundService) or not callable(bound.close):
                raise ServiceUnavailableError("platform service binding failed") from None
            return _PlatformBinding(spec.version, bound)

        return ModuleServices(
            register=register_for_owner,
            resolve=resolve_for_owner,
            bind_platform=bind_platform_for_owner,
        )

    def unregister_owner(self, owner: str) -> None:
        """Remove public services when their owning module stops."""
        _validate_module_id(owner)
        with self._lock:
            for name, registration in tuple(self._services.items()):
                if registration.owner == owner:
                    del self._services[name]


class ModuleServices:
    """Module-scoped service registration and read-only resolution view."""

    __slots__ = (
        "_register",
        "_resolve",
        "_bind_platform",
        "_platform_bindings",
        "_closed",
        "_lock",
    )

    def __init__(
        self,
        *,
        register: Callable[[str, int, object], None],
        resolve: Callable[[str, int], object],
        bind_platform: Callable[[str, int], _PlatformBinding],
    ) -> None:
        self._register = register
        self._resolve = resolve
        self._bind_platform = bind_platform
        self._platform_bindings: dict[str, _PlatformBinding] = {}
        self._closed = False
        self._lock = RLock()

    def register(self, name: str, version: int, provider: object) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("module service view is closed")
            self._register(name, version, provider)

    def resolve(self, name: str, minimum_version: int) -> object:
        with self._lock:
            if self._closed:
                raise RuntimeError("module service view is closed")
            namespace = _validate_service_name(name)
            _validate_version(minimum_version, field="minimum_version")
            if namespace == "platform":
                binding = self._platform_bindings.get(name)
                if binding is None:
                    binding = self._bind_platform(name, minimum_version)
                    self._platform_bindings[name] = binding
                elif binding.version < minimum_version:
                    raise ServiceVersionError(
                        f"platform service {name!r} version {binding.version} does not satisfy "
                        f"minimum version {minimum_version}"
                    )
                return binding.bound.value
            return self._resolve(name, minimum_version)

    def close(self) -> None:
        """Reject late access after the owning module has been isolated or stopped."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            bindings = tuple(self._platform_bindings.values())
            self._platform_bindings.clear()
        for binding in reversed(bindings):
            try:
                binding.bound.close()
            except BaseException:
                logging.getLogger(__name__).warning("platform service close failed")
