from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from auto_check.app.module_system.discovery import (
    ModuleDiscoveryError,
    discover_modules,
    load_module_factory,
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
