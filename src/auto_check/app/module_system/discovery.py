from __future__ import annotations

import importlib
import json
import pkgutil
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
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


@dataclass(frozen=True)
class ModuleDiscoveryIssue:
    """A sanitized, non-loadable child package discovered beside valid modules."""

    package_name: str
    module_id: str
    name: str
    version: str
    required: bool
    error: str


@dataclass(frozen=True)
class ModuleDiscoveryReport:
    modules: tuple[DiscoveredModule, ...]
    issues: tuple[ModuleDiscoveryIssue, ...]


@dataclass(frozen=True)
class ModuleRuntimePlan:
    modules: tuple[DiscoveredModule, ...]
    issues: tuple[ModuleDiscoveryIssue, ...]
    incompatibilities: Mapping[str, str]


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


def discover_module_report(
    package_name: str = "auto_check.modules",
) -> ModuleDiscoveryReport:
    """Discover child packages while isolating failures local to one child."""
    package = importlib.import_module(package_name)
    modules: list[DiscoveredModule] = []
    issues: list[ModuleDiscoveryIssue] = []
    for item in sorted(pkgutil.iter_modules(package.__path__), key=lambda value: value.name):
        if not item.ispkg or item.name.startswith("_"):
            continue
        child_package = f"{package_name}.{item.name}"
        try:
            root = resources.files(child_package)
        except Exception:
            issues.append(
                _discovery_issue(
                    child_package,
                    required=False,
                    error="module package resources are unavailable",
                )
            )
            continue
        try:
            manifest_path = root.joinpath("manifest.json")
            if not manifest_path.is_file():
                continue
            manifest_text = manifest_path.read_text(encoding="utf-8")
        except Exception:
            issues.append(
                _discovery_issue(
                    child_package,
                    required=False,
                    error="module manifest is unreadable",
                )
            )
            continue
        try:
            payload = json.loads(manifest_text)
        except Exception:
            issues.append(
                _discovery_issue(
                    child_package,
                    required=False,
                    error="module manifest JSON is invalid",
                )
            )
            continue
        required = isinstance(payload, Mapping) and payload.get("required") is True
        try:
            if not isinstance(payload, Mapping):
                raise TypeError("module manifest must be an object")
            manifest = ModuleManifest.from_mapping(payload)
        except Exception:
            issues.append(
                _discovery_issue(
                    child_package,
                    required=required,
                    error="module manifest is invalid",
                )
            )
            continue
        modules.append(
            DiscoveredModule(
                package_name=child_package,
                package_root=root,
                manifest=manifest,
            )
        )
    return ModuleDiscoveryReport(tuple(modules), tuple(issues))


def plan_module_runtime(report: ModuleDiscoveryReport) -> ModuleRuntimePlan:
    """Build a deterministic load plan without rejecting unrelated healthy modules."""
    grouped: dict[str, list[DiscoveredModule]] = defaultdict(list)
    for module in report.modules:
        grouped[module.manifest.id].append(module)

    issues = list(report.issues)
    modules: list[DiscoveredModule] = []
    for module_id in sorted(grouped):
        owners = grouped[module_id]
        if len(owners) == 1:
            modules.append(owners[0])
            continue
        for owner in sorted(owners, key=lambda value: value.package_name):
            issues.append(
                _discovery_issue(
                    owner.package_name,
                    required=owner.manifest.required,
                    error="module manifest id is duplicated",
                    version=owner.manifest.version,
                )
            )

    by_id = {module.manifest.id: module for module in modules}
    incompatibilities: dict[str, str] = {}
    for module_id, module in by_id.items():
        if any(dependency not in by_id for dependency in module.manifest.dependencies):
            incompatibilities[module_id] = "module dependency is missing"

    _propagate_incompatibilities(by_id, incompatibilities)
    compatible_ids = set(by_id) - set(incompatibilities)
    remaining = {
        module_id: {
            dependency
            for dependency in by_id[module_id].manifest.dependencies
            if dependency in compatible_ids
        }
        for module_id in compatible_ids
    }
    ordered_ids: list[str] = []
    ready = sorted(module_id for module_id, dependencies in remaining.items() if not dependencies)
    while ready:
        module_id = ready.pop(0)
        ordered_ids.append(module_id)
        remaining.pop(module_id)
        for candidate_id in sorted(remaining):
            dependencies = remaining[candidate_id]
            dependencies.discard(module_id)
            if not dependencies and candidate_id not in ready:
                ready.append(candidate_id)
        ready.sort()
    if remaining:
        for module_id in remaining:
            incompatibilities[module_id] = "module dependency cycle detected"

    ordered_ids.extend(sorted(incompatibilities))
    unique_issues = _unique_issues(issues, reserved_ids=set(by_id))
    return ModuleRuntimePlan(
        modules=tuple(by_id[module_id] for module_id in ordered_ids),
        issues=tuple(unique_issues),
        incompatibilities=dict(sorted(incompatibilities.items())),
    )


def _propagate_incompatibilities(
    by_id: Mapping[str, DiscoveredModule], incompatibilities: dict[str, str]
) -> None:
    changed = True
    while changed:
        changed = False
        for module_id, module in by_id.items():
            if module_id in incompatibilities:
                continue
            if any(
                dependency in incompatibilities
                for dependency in module.manifest.dependencies
            ):
                incompatibilities[module_id] = "module dependency is incompatible"
                changed = True


def _discovery_issue(
    package_name: str,
    *,
    required: bool,
    error: str,
    version: str = "unknown",
) -> ModuleDiscoveryIssue:
    package_leaf = package_name.rsplit(".", maxsplit=1)[-1]
    module_id = re.sub(r"[^a-z0-9_]", "_", package_leaf.lower())
    if not module_id or not module_id[0].isalpha():
        module_id = f"module_{module_id}"
    return ModuleDiscoveryIssue(
        package_name=package_name,
        module_id=module_id,
        name=package_leaf,
        version=version,
        required=required,
        error=error,
    )


def _unique_issues(
    issues: Iterable[ModuleDiscoveryIssue], *, reserved_ids: set[str]
) -> list[ModuleDiscoveryIssue]:
    used = set(reserved_ids)
    result: list[ModuleDiscoveryIssue] = []
    for issue in sorted(issues, key=lambda value: value.package_name):
        base = issue.module_id
        candidate = base
        suffix = 1
        while candidate in used:
            suffix += 1
            candidate = f"{base}_discovery_{suffix}"
        used.add(candidate)
        result.append(replace(issue, module_id=candidate))
    return result


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
    api_prefixes: list[tuple[str, str]] = []
    prefixes: list[tuple[str, str]] = []
    navigation_groups: dict[str, tuple[str, int]] = {}
    for module in discovered:
        manifest = module.manifest
        claims["api_prefix"][manifest.api_prefix].append(manifest.id)
        api_prefixes.append((manifest.id, manifest.api_prefix))
        for item in manifest.navigation:
            claims["navigation.id"][item.id].append(manifest.id)
            claims["navigation.route"][item.route].append(manifest.id)
            if item.group_id is not None:
                group_declaration = (item.group_label, item.group_order)
                existing_group_declaration = navigation_groups.setdefault(
                    item.group_id, group_declaration
                )
                if existing_group_declaration != group_declaration:
                    errors[manifest.id].append(
                        f"conflicting navigation group declaration: {item.group_id}"
                    )
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
    for index, (left_id, left_prefix) in enumerate(api_prefixes):
        for right_id, right_prefix in api_prefixes[index + 1 :]:
            if left_prefix.startswith(f"{right_prefix}/") or right_prefix.startswith(
                f"{left_prefix}/"
            ):
                errors[left_id].append(
                    f"conflicting api_prefix: {left_prefix}, {right_prefix}"
                )
                errors[right_id].append(
                    f"conflicting api_prefix: {left_prefix}, {right_prefix}"
                )
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
