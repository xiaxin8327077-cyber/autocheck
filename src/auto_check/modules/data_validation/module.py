"""数据校验模块生命周期。"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
import json
from typing import Any

from auto_check.app.module_system.contracts import ModuleHealth, ModuleManifest

from .api import register_routes
from .service import DataValidationService
from .storage import RuleStorage


def _manifest() -> ModuleManifest:
    payload = json.loads(resources.files(__package__).joinpath("manifest.json").read_text(encoding="utf-8"))
    return ModuleManifest.from_mapping(payload)


MANIFEST = _manifest()


@dataclass
class DataValidationModule:
    manifest: ModuleManifest = field(default=MANIFEST)
    _service: DataValidationService | None = field(default=None, init=False, repr=False)

    def register_routes(self, router: Any) -> None:
        register_routes(router, self._require_service)

    def register_schema(self, registry: Any) -> None:
        registry.add("data_validation_rules", {
            "id", "rule_code", "name", "description", "creator_user_id", "status",
            "current_version_id", "source_id", "table_name", "report_category", "rule_type", "updated_at",
        })
        registry.add("data_validation_rule_versions", {
            "id", "rule_id", "version_no", "definition_json", "sql_text", "mapping_version",
            "content_sha256", "generation_mode", "status", "created_at",
        })
        registry.add("data_validation_settings", {
            "id", "source_allowlist_json", "max_rules_per_task", "source_concurrency",
            "rule_timeout_seconds", "task_timeout_seconds", "issue_preview_limit",
        })
        registry.add("data_validation_audit_logs", {
            "id", "rule_id", "task_id", "action_code", "operator_user_id", "detail_json", "created_at",
        })
        registry.add("data_validation_ai_invocations", {
            "id", "operator_user_id", "model_id", "model_name", "prompt_version",
            "tool_names", "duration_ms", "error_code", "created_at",
        })
        registry.add("data_validation_test_cases", {
            "id", "rule_id", "version_no", "case_name", "input_json", "expected_count",
            "actual_count", "status", "created_at",
        })
        registry.add("data_validation_confirmations", {
            "id", "rule_id", "version_no", "version_id", "content_sha256", "confirmer_user_id",
            "passed_count", "failed_count", "not_run_count", "created_at",
        })
        registry.add("data_validation_documents", {
            "id", "name", "file_name", "content_sha256", "version_no", "status", "table_count",
            "field_count", "warnings_json", "imported_by", "imported_at", "activated_at",
        })
        registry.add("data_validation_doc_tables", {
            "id", "document_id", "data_source_name", "table_name", "table_name_cn", "sheet_name",
            "source_desc", "dimension", "period", "scope", "sort_order",
        })
        registry.add("data_validation_doc_fields", {
            "id", "table_id", "field_name", "field_cn", "data_type", "is_pk", "nullable",
            "default_value", "dictionary", "logic", "source_table", "source_field",
            "source_field_cn", "source_table_cn", "sort_order",
        })
        registry.add("data_validation_prompt_templates", {
            "id", "stage", "content", "version_no", "is_active", "updated_by", "updated_at",
        })
        registry.add("data_validation_trust_knowledge", {
            "id", "revision", "active_revision", "draft_json", "active_json", "updated_by", "updated_at",
        })
        registry.add("data_validation_doc_source_rules", {
            "id", "sheet_prefix", "data_source_name", "sort_order",
        })
        registry.add("data_validation_tasks", {
            "id", "creator_user_id", "source_id", "report_period", "status", "params_json", "truncated", "created_at",
        })
        registry.add("data_validation_task_rules", {
            "id", "task_id", "rule_id", "version_id", "version_no", "content_sha256",
            "sql_summary", "status", "violation_count", "truncated", "error_code",
        })
        registry.add("data_validation_issues", {
            "id", "task_id", "rule_id", "version_no", "business_key", "project_code", "project_name",
            "project_name_status", "issue_kind", "message", "created_at",
        })

    def start(self, context: Any) -> None:
        self._service = DataValidationService(
            RuleStorage(context.application_database),
            metadata=context.services.resolve("platform.data_sources", 1),
            model=context.services.resolve("platform.language_models", 1),
            report_navigation=context.services.resolve("platform.report_navigation", 1),
        )

    def stop(self) -> None:
        if self._service is not None:
            self._service.join()
        self._service = None

    def health(self) -> ModuleHealth:
        return ModuleHealth(healthy=self._service is not None)

    def _require_service(self) -> DataValidationService:
        if self._service is None:
            raise RuntimeError("module service is unavailable")
        return self._service


def create_module() -> DataValidationModule:
    return DataValidationModule()
