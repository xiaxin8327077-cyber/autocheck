from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from threading import Event
from typing import Any

from auto_check.app.module_system.contracts import ModuleHealth, ModuleHttpResponse, ModuleManifest


CALLS: list[str] = []


@dataclass
class FixtureTaskState:
    started: Event = field(default_factory=Event)
    release: Event = field(default_factory=Event)
    stop_entered: Event = field(default_factory=Event)
    future: Any = None


TASK_STATE = FixtureTaskState()


def _load_manifest() -> ModuleManifest:
    payload = json.loads(resources.files(__package__).joinpath("manifest.json").read_text(encoding="utf-8"))
    return ModuleManifest.from_mapping(payload)


MANIFEST = _load_manifest()


def reset_fixture_state() -> None:
    CALLS.clear()
    TASK_STATE.started.clear()
    TASK_STATE.release.clear()
    TASK_STATE.stop_entered.clear()
    TASK_STATE.future = None


@dataclass
class ReportDemoModule:
    manifest: ModuleManifest = field(default=MANIFEST)

    def register_routes(self, router: Any) -> None:
        router.add(
            "GET",
            "/health",
            lambda request: ModuleHttpResponse.json(
                200, {"module": "report_demo", "status": "ok"}
            ),
            permission="report_demo.view",
            max_body_bytes=0,
        )

    def register_schema(self, registry: Any) -> None:
        registry.add("report_demo_items", {"id", "name"})

    def start(self, context: Any) -> None:
        CALLS.append("report_demo:start")

        def task() -> None:
            TASK_STATE.started.set()
            TASK_STATE.release.wait(1)

        TASK_STATE.future = context.background_executor.submit(task)

    def stop(self) -> None:
        CALLS.append("report_demo:stop")
        TASK_STATE.stop_entered.set()

    def health(self) -> ModuleHealth:
        return ModuleHealth(healthy=True)


def create_module() -> ReportDemoModule:
    return ReportDemoModule()
