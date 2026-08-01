"""Platform contracts and runtime support for Auto Check modules."""

from .runtime import (
    LoadedModule,
    ModuleRuntime,
    ModuleRuntimeError,
    ModuleStartupError,
    ModuleTaskLimitError,
)

__all__ = [
    "LoadedModule",
    "ModuleRuntime",
    "ModuleRuntimeError",
    "ModuleStartupError",
    "ModuleTaskLimitError",
]
