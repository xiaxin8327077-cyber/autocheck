"""Optional optimistic context for existing-rule editor writes."""

from typing import Any

from .contracts import AppError
from .project_driver import DRIVER_VERSION, normalize_project_driver


def restore_saved_semantics(draft: dict, saved: dict) -> None:
    """Use the stored business obligations when compiling a new rule version."""
    intent = saved["semantic_intent"]
    old_driver = saved.get("project_driver")
    if isinstance(old_driver, dict) and old_driver.get("version") == 1:
        old_driver = normalize_project_driver(old_driver)
        submitted = normalize_project_driver(draft.get("project_driver"))
        if (not isinstance(intent, dict)
                or normalize_project_driver(intent.get("expected_project_driver")) != old_driver
                or submitted["table_role"] != old_driver["table_role"]
                or any(draft.get(key) != saved.get(key) for key in (
                    "source_id", "report_category", "table_name", "business_key", "report_date_field",
                ))):
            raise AppError("VALIDATION_ERROR")
        # The editor submits the old marker; regenerated drafts already carry the current one.
        driver = {**old_driver, "version": DRIVER_VERSION}
        draft["project_driver"] = driver
        intent = {**intent, "expected_project_driver": driver}
    draft.update(analysis_protocol=2, semantic_intent=intent)


def check_edit_context(rule: dict[str, Any], version: dict[str, Any], expected: dict | None) -> None:
    if expected is None:
        return
    keys = {"version_no", "content_sha256", "status", "current_version_id"}
    if not isinstance(expected, dict) or set(expected) != keys:
        raise AppError("VALIDATION_ERROR")
    actual = {"version_no": version["version_no"], "content_sha256": version["content_sha256"],
              "status": rule["status"], "current_version_id": rule.get("current_version_id")}
    if actual != expected:
        raise AppError("CONFLICT_VERSION")
