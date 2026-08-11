from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from auto_check.app.module_system.contracts import ServiceDeclaration
from auto_check.app.module_system.discovery import (
    ModuleDiscoveryReport,
    ModuleDiscoveryError,
    declaration_conflicts,
    discover_modules,
    load_module_factory,
    plan_module_runtime,
    sort_modules,
)


FIXTURE_PARENT = Path(__file__).resolve().parents[1] / "fixtures"


def test_discovers_direct_child_packages_and_sorts_dependencies(monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))

    modules = discover_modules("module_packages")
    ordered = sort_modules(
        [module for module in modules if module.manifest.id in {"alpha", "beta"}]
    )

    assert [module.manifest.id for module in ordered] == ["alpha", "beta"]


def test_sorts_independent_modules_by_id_without_mutating_input(monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    modules = discover_modules("module_packages")
    unordered = [
        next(module for module in modules if module.manifest.id == "beta"),
        next(module for module in modules if module.manifest.id == "alpha"),
    ]

    ordered = sort_modules(unordered)

    assert [module.manifest.id for module in unordered] == ["beta", "alpha"]
    assert [module.manifest.id for module in ordered] == ["alpha", "beta"]


def test_loads_declared_factory(monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))

    factory = load_module_factory("module_packages.alpha.module:create_module")

    assert callable(factory)
    assert factory().manifest.id == "alpha"


@pytest.mark.parametrize(("module_id", "required"), [("broken_optional", False), ("broken_required", True)])
def test_loads_failing_factory_without_starting_it(monkeypatch, module_id, required):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    module = next(item for item in discover_modules("module_packages") if item.manifest.id == module_id)

    factory = load_module_factory(module.manifest.backend_entry)

    assert module.manifest.required is required
    with pytest.raises(RuntimeError, match="fixture startup failure"):
        factory()


def test_rejects_missing_dependency(monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    beta = next(item for item in discover_modules("module_packages") if item.manifest.id == "beta")
    missing_dependency = replace(beta, manifest=replace(beta.manifest, dependencies=("missing",)))

    with pytest.raises(ModuleDiscoveryError, match="缺少依赖"):
        sort_modules([missing_dependency])


def test_rejects_dependency_cycle(monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    modules = discover_modules("module_packages")
    alpha = next(module for module in modules if module.manifest.id == "alpha")
    beta = next(module for module in modules if module.manifest.id == "beta")
    cycled_alpha = replace(alpha, manifest=replace(alpha.manifest, dependencies=("beta",)))

    with pytest.raises(ModuleDiscoveryError, match="循环依赖"):
        sort_modules([cycled_alpha, beta])


def test_runtime_plan_isolates_duplicate_ids_and_invalid_dependency_graphs(monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    modules = discover_modules("module_packages")
    alpha = next(module for module in modules if module.manifest.id == "alpha")
    beta = next(module for module in modules if module.manifest.id == "beta")
    duplicate_a = replace(alpha, package_name="module_packages.duplicate_a")
    duplicate_b = replace(alpha, package_name="module_packages.duplicate_b")
    missing = replace(
        beta,
        manifest=replace(beta.manifest, dependencies=("not_installed",)),
    )

    plan = plan_module_runtime(
        ModuleDiscoveryReport(
            modules=(duplicate_a, duplicate_b, missing),
            issues=(),
        )
    )

    assert [module.manifest.id for module in plan.modules] == ["beta"]
    assert plan.incompatibilities == {"beta": "module dependency is missing"}
    assert [issue.module_id for issue in plan.issues] == ["duplicate_a", "duplicate_b"]
    assert all(issue.error == "module manifest id is duplicated" for issue in plan.issues)


@pytest.mark.parametrize(
    "entry",
    [
        "module_packages.alpha.module",
        "module_packages.alpha.module:",
        "module_packages.alpha.module:not_present",
    ],
)
def test_rejects_invalid_or_missing_factory(monkeypatch, entry):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))

    with pytest.raises(ModuleDiscoveryError):
        load_module_factory(entry)


def test_declaration_preflight_rejects_an_entry_outside_its_discovered_package(monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    modules = discover_modules("module_packages")
    alpha = next(module for module in modules if module.manifest.id == "alpha")
    foreign_entry = replace(
        alpha,
        manifest=replace(alpha.manifest, backend_entry="module_packages.beta.module:create_module"),
    )

    conflicts = declaration_conflicts([foreign_entry])

    assert "alpha" in conflicts
    assert "backend_entry" in conflicts["alpha"]


@pytest.mark.parametrize("kind", ["api_prefix", "navigation.id", "navigation.route", "permission", "service"])
def test_declaration_preflight_reports_each_global_declaration_conflict(monkeypatch, kind):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    alpha, beta = [
        next(
            module
            for module in discover_modules("module_packages")
            if module.manifest.id == module_id
        )
        for module_id in ("alpha", "beta")
    ]
    if kind == "api_prefix":
        beta = replace(beta, manifest=replace(beta.manifest, api_prefix=alpha.manifest.api_prefix))
    elif kind == "navigation.id":
        beta_navigation = replace(beta.manifest.navigation[0], id=alpha.manifest.navigation[0].id)
        beta = replace(beta, manifest=replace(beta.manifest, navigation=(beta_navigation,)))
    elif kind == "navigation.route":
        beta_navigation = replace(beta.manifest.navigation[0], route=alpha.manifest.navigation[0].route)
        beta = replace(beta, manifest=replace(beta.manifest, navigation=(beta_navigation,)))
    elif kind == "permission":
        beta = replace(beta, manifest=replace(beta.manifest, permissions=alpha.manifest.permissions))
    else:
        service = ServiceDeclaration("alpha.lookup", 1)
        alpha = replace(alpha, manifest=replace(alpha.manifest, services=(service,)))
        beta = replace(beta, manifest=replace(beta.manifest, services=(service,)))

    conflicts = declaration_conflicts([alpha, beta])

    assert alpha.manifest.id in conflicts
    assert beta.manifest.id in conflicts
    assert kind in conflicts[alpha.manifest.id]


def test_declaration_preflight_rejects_nested_api_prefixes(monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    alpha, beta = [
        next(module for module in discover_modules("module_packages") if module.manifest.id == module_id)
        for module_id in ("alpha", "beta")
    ]
    alpha = replace(alpha, manifest=replace(alpha.manifest, api_prefix="/api/modules/shared"))
    beta = replace(
        beta,
        manifest=replace(beta.manifest, api_prefix="/api/modules/shared/nested"),
    )

    conflicts = declaration_conflicts([alpha, beta])

    assert "conflicting api_prefix" in conflicts["alpha"]
    assert "conflicting api_prefix" in conflicts["beta"]


def test_declaration_preflight_isolates_only_later_conflicting_navigation_group(monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    alpha, beta = [
        next(module for module in discover_modules("module_packages") if module.manifest.id == module_id)
        for module_id in ("alpha", "beta")
    ]
    alpha_navigation = replace(
        alpha.manifest.navigation[0],
        group_id="data-entry",
        group_label="数据录入",
        group_order=10,
    )
    beta_navigation = replace(
        beta.manifest.navigation[0],
        group_id="data-entry",
        group_label="数据治理",
        group_order=10,
    )
    alpha = replace(alpha, manifest=replace(alpha.manifest, navigation=(alpha_navigation,)))
    beta = replace(beta, manifest=replace(beta.manifest, navigation=(beta_navigation,)))

    conflicts = declaration_conflicts([alpha, beta])

    assert conflicts == {"beta": "conflicting navigation group declaration: data-entry"}
