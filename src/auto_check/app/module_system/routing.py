from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping
from urllib.parse import unquote

from .contracts import ModuleHttpResponse, ModuleManifest, ModuleRequest, validate_module_response


RouteHandler = Callable[[ModuleRequest], ModuleHttpResponse]
PermissionEvaluator = Callable[[Mapping[str, Any] | None, str], bool]
_PATH_PARAMETER_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ModuleRouteConflict(ValueError):
    """Raised when a module registers a route more than once."""


@dataclass(frozen=True)
class ModuleRoutePreflight:
    """Route metadata determined without evaluating permissions or calling a handler."""

    status: int
    max_body_bytes: int | None = None
    headers: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class _ModuleRoute:
    method: str
    path: str
    pattern: re.Pattern[str]
    handler: RouteHandler
    permission: str
    max_body_bytes: int


class ModuleRouter:
    """Dispatch a module's namespaced HTTP requests to relative routes."""

    def __init__(self, manifest: ModuleManifest, permission_evaluator: PermissionEvaluator) -> None:
        self._manifest = manifest
        self._permission_evaluator = permission_evaluator
        self._routes: list[_ModuleRoute] = []

    def add(
        self,
        method: str,
        path: str,
        handler: RouteHandler,
        *,
        permission: str,
        max_body_bytes: int,
    ) -> None:
        normalized_method = self._normalize_method(method)
        pattern = self._compile_relative_path(path)
        if permission not in self._manifest.permissions:
            raise ValueError("route permission must be declared by the module manifest")
        if not callable(handler):
            raise ValueError("route handler must be callable")
        if type(max_body_bytes) is not int or max_body_bytes < 0:
            raise ValueError("max_body_bytes must be a non-negative integer")
        if any(route.method == normalized_method and route.path == path for route in self._routes):
            raise ModuleRouteConflict(f"duplicate module route: {normalized_method} {path}")

        self._routes.append(
            _ModuleRoute(
                method=normalized_method,
                path=path,
                pattern=pattern,
                handler=handler,
                permission=permission,
                max_body_bytes=max_body_bytes,
            )
        )

    def dispatch(self, request: ModuleRequest, *, body_size: int = 0) -> ModuleHttpResponse | None:
        if type(body_size) is not int or body_size < 0:
            return ModuleHttpResponse.json(400, {"error": "invalid request"})
        relative_path = self._relative_path(request.path)
        if relative_path is None:
            return None

        path_matches = [
            (route, route.pattern.fullmatch(relative_path))
            for route in self._routes
        ]
        path_matches = [(route, match) for route, match in path_matches if match is not None]
        if not path_matches:
            return None

        method = request.method.upper()
        method_matches = [
            (route, match) for route, match in path_matches if route.method == method
        ]
        if not method_matches:
            allowed_methods = ", ".join(route.method for route, _ in path_matches)
            return ModuleHttpResponse(
                status=405,
                body={"error": "method not allowed"},
                content_type="application/json; charset=utf-8",
                headers=(("Allow", allowed_methods),),
            )

        route, match = method_matches[0]
        try:
            if body_size > route.max_body_bytes:
                return ModuleHttpResponse.json(413, {"error": "request body too large"})
            if not self._permission_evaluator(request.current_user, route.permission):
                return ModuleHttpResponse.json(403, {"error": "permission denied"})
            path_params = {
                name: unquote(value)
                for name, value in match.groupdict().items()
            }
            return validate_module_response(
                route.handler(replace(request, path_params=path_params))
            )
        except ValueError:
            return ModuleHttpResponse.json(400, {"error": "invalid request"})
        except Exception:
            return ModuleHttpResponse.json(
                500,
                {
                    "error": "internal server error",
                    "module_id": self._manifest.id,
                    "error_id": uuid.uuid4().hex,
                },
            )

    def preflight(self, method: str, path: str) -> ModuleRoutePreflight | None:
        """Resolve a route's request-size contract without invoking module code."""
        relative_path = self._relative_path(path)
        if relative_path is None:
            return None
        path_matches = [
            route for route in self._routes if route.pattern.fullmatch(relative_path) is not None
        ]
        if not path_matches:
            return ModuleRoutePreflight(status=404)
        normalized_method = method.upper()
        method_matches = [route for route in path_matches if route.method == normalized_method]
        if not method_matches:
            return ModuleRoutePreflight(
                status=405,
                headers=(("Allow", ", ".join(route.method for route in path_matches)),),
            )
        return ModuleRoutePreflight(status=200, max_body_bytes=method_matches[0].max_body_bytes)

    def _relative_path(self, path: str) -> str | None:
        prefix = self._manifest.api_prefix
        if path == prefix:
            return "/"
        if not path.startswith(f"{prefix}/"):
            return None
        return path[len(prefix) :]

    @staticmethod
    def _normalize_method(method: str) -> str:
        if not isinstance(method, str) or not method.strip():
            raise ValueError("route method must be a non-empty string")
        return method.strip().upper()

    @staticmethod
    def _compile_relative_path(path: str) -> re.Pattern[str]:
        if not isinstance(path, str) or not path.startswith("/") or "/api/" in path:
            raise ValueError("module route path must be relative and start with '/'")

        pattern_parts: list[str] = []
        names: set[str] = set()
        for segment in path.split("/")[1:]:
            parameter = _PATH_PARAMETER_PATTERN.fullmatch(segment)
            if parameter:
                name = parameter.group(1)
                if name in names:
                    raise ValueError("route path cannot repeat a parameter name")
                names.add(name)
                pattern_parts.append(f"(?P<{name}>[^/]+)")
            elif "{" in segment or "}" in segment:
                raise ValueError("route path parameters must occupy one complete segment")
            else:
                pattern_parts.append(re.escape(segment))

        return re.compile("^/" + "/".join(pattern_parts) + "$")
