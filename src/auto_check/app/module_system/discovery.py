from __future__ import annotations

import importlib
import json
import pkgutil
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable
from typing import cast

from .contracts import AutoCheckModule, ModuleManifest


class ModuleDiscoveryError(ValueError):
    """Raised when built-in module discovery cannot produce a valid load order."""


@dataclass(frozen=True)
class DiscoveredModule:
    package_name: str
    package_root: Traversable
    manifest: ModuleManifest


def discover_modules(package_name: str = "auto_check.modules") -> list[DiscoveredModule]:
    """Discover direct child packages that declare a module manifest."""
    package = importlib.import_module(package_name)
    modules = []
    for item in sorted(pkgutil.iter_modules(package.__path__), key=lambda value: value.name):
        if not item.ispkg or item.name.startswith("_"):
            continue
        child_package = f"{package_name}.{item.name}"
        root = resources.files(child_package)
        manifest_path = root.joinpath("manifest.json")
        if not manifest_path.is_file():
            continue
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        modules.append(
            DiscoveredModule(
                package_name=child_package,
                package_root=root,
                manifest=ModuleManifest.from_mapping(payload),
            )
        )
    return modules


def sort_modules(modules: Iterable[DiscoveredModule]) -> list[DiscoveredModule]:
    """Return modules in stable dependency order without changing the input."""
    discovered = list(modules)
    by_id = {module.manifest.id: module for module in discovered}
    if len(by_id) != len(discovered):
        raise ModuleDiscoveryError("模块 ID 重复")

    remaining = {
        module_id: set(module.manifest.dependencies) for module_id, module in by_id.items()
    }
    for module_id, dependencies in remaining.items():
        missing = sorted(dependency for dependency in dependencies if dependency not in by_id)
        if missing:
            raise ModuleDiscoveryError(f"模块 {module_id} 缺少依赖: {', '.join(missing)}")

    ordered: list[DiscoveredModule] = []
    ready = sorted(module_id for module_id, dependencies in remaining.items() if not dependencies)
    while ready:
        module_id = ready.pop(0)
        ordered.append(by_id[module_id])
        remaining.pop(module_id)
        for candidate_id in sorted(remaining):
            dependencies = remaining[candidate_id]
            dependencies.discard(module_id)
            if not dependencies and candidate_id not in ready:
                ready.append(candidate_id)
        ready.sort()

    if remaining:
        cycle_members = ", ".join(sorted(remaining))
        raise ModuleDiscoveryError(f"检测到循环依赖: {cycle_members}")
    return ordered


def declaration_conflicts(modules: Iterable[DiscoveredModule]) -> dict[str, str]:
    """Return stable declaration errors without importing any module factories."""
    discovered = tuple(modules)
    errors: dict[str, list[str]] = defaultdict(list)

    for module in discovered:
        entry_module, _, _ = module.manifest.backend_entry.partition(":")
        if entry_module != module.package_name and not entry_module.startswith(
            f"{module.package_name}."
        ):
            errors[module.manifest.id].append("backend_entry does not belong to the discovered package")

    claims: dict[str, dict[str, list[str]]] = {
        "api_prefix": defaultdict(list),
        "navigation.id": defaultdict(list),
        "navigation.route": defaultdict(list),
        "permission": defaultdict(list),
        "service": defaultdict(list),
    }
    prefixes: list[tuple[str, str]] = []
    for module in discovered:
        manifest = module.manifest
        claims["api_prefix"][manifest.api_prefix].append(manifest.id)
        for item in manifest.navigation:
            claims["navigation.id"][item.id].append(manifest.id)
            claims["navigation.route"][item.route].append(manifest.id)
        for permission in manifest.permissions:
            claims["permission"][permission].append(manifest.id)
        for service in manifest.services:
            claims["service"][service.name].append(manifest.id)
        prefixes.append((manifest.id, manifest.table_prefix))

    for kind, values in claims.items():
        for value, owners in values.items():
            if len(owners) > 1:
                for owner in owners:
                    errors[owner].append(f"duplicate {kind}: {value}")
    for index, (left_id, left_prefix) in enumerate(prefixes):
        for right_id, right_prefix in prefixes[index + 1 :]:
            if left_prefix.startswith(right_prefix) or right_prefix.startswith(left_prefix):
                errors[left_id].append(f"conflicting table_prefix: {left_prefix}, {right_prefix}")
                errors[right_id].append(f"conflicting table_prefix: {left_prefix}, {right_prefix}")

    return {
        module_id: "; ".join(sorted(set(messages)))
        for module_id, messages in sorted(errors.items())
    }


def load_module_factory(entry: str) -> Callable[[], AutoCheckModule]:
    """Load a callable module factory from a ``package.module:function`` entry."""
    if entry.count(":") != 1:
        raise ModuleDiscoveryError("模块入口必须使用 package.module:function")
    module_name, attribute_name = entry.split(":", maxsplit=1)
    if not module_name or "." not in module_name or not attribute_name:
        raise ModuleDiscoveryError("模块入口必须使用 package.module:function")

    try:
        module = importlib.import_module(module_name)
        factory = getattr(module, attribute_name)
    except (ImportError, AttributeError) as error:
        raise ModuleDiscoveryError(f"无法加载模块工厂: {entry}") from error
    if not callable(factory):
        raise ModuleDiscoveryError(f"模块工厂不可调用: {entry}")
    return cast(Callable[[], AutoCheckModule], factory)
