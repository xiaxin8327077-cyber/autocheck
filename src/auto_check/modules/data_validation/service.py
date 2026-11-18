"""数据校验业务编排。创建人才能改、测、确认和导出自己的规则。"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import uuid
from typing import Any, Callable

from .analysis_jobs import AnalysisRegistry
from .ai_service import refine_candidate
from .ai_suggestions import build_ai_suggestions
from .candidate_choices import (
    TARGET_SELECT, comparison_suggestion, counterpart_fields, difference_lines, field_label,
    grain_label, option_id, recommended_index, resolve_uncertainty_clauses, semantic_core,
    target_ambiguity_indices,
)
from .candidate_preview import preview_definition, run_preview_cases
from .compiler import compile_rule
from .contracts import AppError, content_hash
from .executor import RuleRun, execute_version
from .exports import issues_csv, issues_xlsx, rule_pack
from .history import definition_changes, history_event
from .sql_guard import guard_sql
from .doc_parser import DEFAULT_SOURCE_RULES, is_pbc_report_sheet, parse_workbook
from .prompt_defaults import DEFAULT_PROMPTS, REQUIRED_PLACEHOLDERS, STAGE_LABELS, RULE_OUTPUT_CONTRACT, SELECT_OUTPUT_CONTRACT
from .generation_policy import (
    REVIEW_FIELDS, clarification_candidate, issues, merge, request_reviews, review_ready, shortlist_tables, validate_review,
)
from .model_calls import GENERATION_TIMEOUT_SECONDS, complete_text, failure
from .parallel_checks import project_parallel_checks
from .project_context import (
    infer_project_context, project_code_fields, project_name_fields, project_semantics_required,
)
from .query_grounding import field_profiles, ground_candidate_query, project_mart_target, resolve_report_date
from .query_spec import (
    apply_numeric_null_policy, is_new_spec, is_numeric_comparison, query_ready,
    validate_query_spec, validate_spec_against_columns,
)
from .storage import RuleStorage
from .test_runner import default_field_compare_cases, evaluate_case
from .trust_knowledge import TrustKnowledge

_PAGE_SIZES = {20, 50, 100}
# 临时：模块创建规则只开放这两个监管数据源；配置中出现同名数据源后自动生效。
_SELECTABLE_SOURCE_NAMES = ("监管报送集市", "监管报表")
_PBC_REPORT_CATEGORIES = frozenset({"pbc_central", "pbc_template"})
_TABLE_SHORTLIST_LIMIT = 80
_FIELD_CONTEXT_LIMIT = 60


class DataValidationService:
    def __init__(self, storage: RuleStorage, metadata: Any | None = None, model: Any | None = None, report_navigation: Any | None = None) -> None:
        self.storage = storage
        self.metadata = metadata
        self.model = model
        self.report_navigation = report_navigation
        self.inline = True
        self.gate: threading.Event | None = None
        self._threads: list[threading.Thread] = []
        # 临时分析只存在内存，模块停止时统一协作取消并回收线程。
        self.analyses = AnalysisRegistry(worker=self._execute_analysis)
        self.knowledge = TrustKnowledge(storage, _SELECTABLE_SOURCE_NAMES)

    def save_draft(self, user: dict[str, Any], payload: dict[str, Any], rule_id: int | None = None) -> dict[str, Any]:
        definition = dict(payload)
        definition.setdefault("generation_mode", "manual")
        if is_new_spec(definition):
            # Bind new scopes to real document fields/version; never persist client metadata/SQL as evidence.
            definition = self.preview_candidate(user, {"definition": definition})["definition"]
        validate_review(definition)
        if rule_id is None:
            sql_text, _params = self._compile_if_possible(definition)
            digest = content_hash(definition, str(definition.get("dialect") or ""), str(definition.get("mapping_version") or ""), sql_text)
            changes = definition_changes(None, definition)
            history = history_event(
                "create", user, version_no=1, content_sha256=digest, changes=changes,
                before_status=None, after_status="draft",
                summary=f"创建规则，保存版本 1，变更 {len(changes)} 项，哈希 {digest}",
            )
            return self.storage.create_rule(
                creator_user_id=str(user["id"]),
                name=str(definition.get("name") or definition.get("rule_name") or "未命名规则"),
                description=str(definition.get("description") or ""),
                definition=definition,
                sql_text=sql_text,
                mapping_version=str(definition.get("mapping_version") or ""),
                content_sha256=digest,
                generation_mode=str(definition.get("generation_mode") or "manual"),
                history=history,
            )
        rule = self._require_owner(user, rule_id)
        previous = self.storage.latest_version(rule_id)
        for key in REVIEW_FIELDS:
            if key not in definition and key in previous["definition"]:
                definition[key] = previous["definition"][key]
        changed_context = any(definition.get(key) != previous["definition"].get(key) for key in (
            "source_id", "table_name", "report_date_field", "expression", "filters", "join", "null_policy", "equality_policy", "description",
        ))
        if (definition.get("uncertainties") != previous["definition"].get("uncertainties")
                or (definition.get("uncertainties") and changed_context)):
            definition["uncertainty_resolutions"] = []
        validate_review(definition)
        sql_text, _params = self._compile_if_possible(definition)
        digest = content_hash(definition, str(definition.get("dialect") or ""), str(definition.get("mapping_version") or ""), sql_text)
        version_no = int(previous["version_no"]) + 1
        changes = definition_changes(previous["definition"], definition)
        history = history_event(
            "update", user, version_no=version_no, content_sha256=digest, changes=changes,
            before_status=str(rule["status"]), after_status=str(rule["status"]),
            summary=f"编辑保存版本 {version_no}，变更 {len(changes)} 项，哈希 {digest}",
        )
        version = self.storage.add_version(
            rule_id, definition, sql_text, str(definition.get("mapping_version") or ""), digest,
            history=history,
        )
        version["status"] = "draft"
        version["current_version_id"] = rule["current_version_id"]
        return version

    # ---- 多候选批量草稿：单事务、幂等回执、跨进程文档行锁 -------------

    def _bind_active_document(self, definition: dict[str, Any]) -> dict[str, Any]:
        """批量保存前把定义绑定到当前授权 source/活动文档，拒绝客户端伪造元数据。"""
        source_id = str(definition.get("source_id") or "")
        source = next((item for item in self.list_selectable_sources() if str(item["id"]) == source_id), None)
        if source is None:
            raise AppError("SOURCE_UNAVAILABLE")
        document = self.storage.active_document()
        if document is None:
            raise AppError("VALIDATION_ERROR")
        tables = self.storage.doc_tables(int(document["id"]), data_source_name=str(source["name"]))
        if not any(item["table_name"] == definition.get("table_name") for item in tables):
            raise AppError("VALIDATION_ERROR")
        mapping = f"doc-v{int(document['version_no'])}-{str(document['content_sha256'])[:12]}"
        if definition.get("mapping_version") not in (None, "", mapping):
            raise AppError("CONFLICT_VERSION")
        definition["source_id"] = source_id
        definition["dialect"] = str(source.get("dialect") or "")
        definition["mapping_version"] = mapping
        return definition

    def batch_save_candidates(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        raw_definitions = payload.get("definitions") if isinstance(payload, dict) else None
        if not isinstance(raw_definitions, list) or not 1 <= len(raw_definitions) <= 3:
            raise AppError("VALIDATION_ERROR")
        try:
            request_key = str(uuid.UUID(str(payload.get("request_key") or "")))
        except (ValueError, AttributeError, TypeError) as exc:
            raise AppError("VALIDATION_ERROR") from exc
        prepared = []
        fingerprint = []
        for item in raw_definitions:
            if not isinstance(item, dict):
                raise AppError("VALIDATION_ERROR")
            definition = dict(item)
            definition.setdefault("generation_mode", "manual")
            if str(definition.get("rule_type") or "") != "field_compare":
                raise AppError("VALIDATION_ERROR")
            definition = self._bind_active_document(definition)
            # 批量新接口一律按当前活动文档做完整规范化，忽略客户端列/SQL/状态。
            definition = self.preview_candidate(user, {"definition": definition})["definition"]
            validate_review(definition)
            # 批量只保存 preview 已规范化的同一 canonical 定义：不再追加描述/默认值，
            # 确保与预览哈希、单条保存完全一致。
            sql_text, _params = self._compile_if_possible(definition)
            digest = content_hash(
                definition, str(definition.get("dialect") or ""),
                str(definition.get("mapping_version") or ""), sql_text,
            )
            changes = definition_changes(None, definition)
            history = history_event(
                "create", user, version_no=1, content_sha256=digest, changes=changes,
                before_status=None, after_status="draft",
                summary=f"批量保存草稿，变更 {len(changes)} 项，哈希 {digest}",
            )
            prepared.append({
                "creator_user_id": str(user["id"]),
                "name": str(definition.get("name") or definition.get("rule_name") or "未命名规则"),
                "description": str(definition.get("description") or ""),
                "definition": definition,
                "sql_text": sql_text,
                "mapping_version": str(definition.get("mapping_version") or ""),
                "content_sha256": digest,
                "generation_mode": str(definition.get("generation_mode") or "manual"),
                "history": history,
            })
            fingerprint.append(definition)
        payload_hash = hashlib.sha256(json.dumps(
            fingerprint, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        result = self.storage.save_batch(
            creator_user_id=str(user["id"]), prepared=prepared,
            request_key=request_key, payload_hash=payload_hash,
        )
        views = []
        for rule_id in result["rule_ids"]:
            view = self.storage.get_rule(int(rule_id))
            version = self.storage.latest_version(int(rule_id))
            view["version_id"] = int(version["id"])
            view["version_no"] = int(version["version_no"])
            view["mapping_version"] = str(version["mapping_version"])
            view["content_sha256"] = str(version["content_sha256"])
            view["sql_text"] = str(version["sql_text"])
            views.append(view)
        return {"rules": views, "count": len(views), "reused": bool(result.get("reused"))}

    def list_rules(self, user: dict[str, Any], query: dict[str, Any]) -> dict[str, Any]:
        page_size = int(query.get("page_size") or 50)
        if page_size not in _PAGE_SIZES:
            page_size = 50
        page = max(int(query.get("page") or 1), 1)
        return self.storage.list_rules(
            creator_user_id=None if self._is_admin(user) else str(user["id"]),
            keyword=str(query.get("keyword") or ""),
            status=str(query.get("status") or ""),
            report_category=str(query.get("report_category") or ""),
            source_id=str(query.get("source_id") or ""),
            rule_type=str(query.get("rule_type") or ""),
            page=page,
            page_size=page_size,
        )

    def rule_stats(self, user: dict[str, Any]) -> dict[str, Any]:
        scope = None if self._is_admin(user) else str(user["id"])
        base = self.storage.stats(scope)
        grouped = {item["report_category"]: item for item in self.storage.category_stats(scope)}
        categories = []
        for process in self._report_processes():
            counts = grouped.pop(process["code"], {})
            categories.append({
                "code": process["code"], "name": process["name"],
                "total": int(counts.get("total") or 0), "enabled": int(counts.get("enabled") or 0),
                "draft": int(counts.get("draft") or 0), "disabled": int(counts.get("disabled") or 0),
            })
        unclassified = {"total": 0, "enabled": 0, "draft": 0, "disabled": 0}
        for counts in grouped.values():
            for key in unclassified:
                unclassified[key] += int(counts.get(key) or 0)
        return {**base, "categories": categories, "unclassified": unclassified}

    def list_report_categories(self) -> list[dict[str, str]]:
        return self._report_processes()

    def _report_processes(self) -> list[dict[str, str]]:
        if self.report_navigation is None or not hasattr(self.report_navigation, "list_report_processes"):
            return []
        try:
            processes = self.report_navigation.list_report_processes()
        except Exception:
            return []
        return [
            {"code": str(item.code), "name": str(item.name)}
            for item in processes if getattr(item, "active", True)
        ]

    def get_rule(self, user: dict[str, Any], rule_id: int) -> dict[str, Any]:
        rule = self.storage.get_rule(rule_id)
        if not self._visible(user, rule):
            self._deny(user, rule_id)
        version = self.storage.latest_version(rule_id)
        metadata = {}
        if version["definition"].get("join"):
            try:
                metadata["related_columns"] = self.preview_candidate(user, {"definition": version["definition"]})["related_columns"]
            except AppError as error:
                metadata = {"related_columns": [], "metadata_error": error.code}
        return {
            **rule,
            **metadata,
            "version_no": int(version["version_no"]),
            "version_id": int(version["id"]),
            "content_sha256": version["content_sha256"],
            "sql_text": version["sql_text"],
            "definition": version["definition"],
        }

    def list_rule_history(self, user: dict[str, Any], rule_id: int, query: dict[str, Any] | None = None) -> dict[str, Any]:
        rule = self.storage.get_rule(rule_id)
        if not self._visible(user, rule):
            self._deny(user, rule_id)
        query = query or {}
        page_size = int(query.get("page_size") or 20)
        if page_size not in _PAGE_SIZES:
            page_size = 20
        page = max(int(query.get("page") or 1), 1)
        return self.storage.list_rule_history(rule_id, page=page, page_size=page_size)


    # ---- 校验设置：文档 / 提示词 / 数据源映射 ----
    def import_document(self, user: dict[str, Any], file_name: str, content: bytes, name: str = "") -> dict[str, Any]:
        if not content:
            raise AppError("VALIDATION_ERROR")
        rules = self.storage.source_rules() or DEFAULT_SOURCE_RULES
        parsed = parse_workbook(content, rules=rules)
        if not parsed["tables"]:
            raise AppError("VALIDATION_ERROR")
        digest = hashlib.sha256(content).hexdigest()
        document = self.storage.create_document(
            name=name or file_name,
            file_name=file_name,
            content_sha256=digest,
            table_count=int(parsed["table_count"]),
            field_count=int(parsed["field_count"]),
            warnings=list(parsed["warnings"]),
            imported_by=str(user["id"]),
            tables=parsed["tables"],
        )
        return {
            "document": document,
            "warnings": parsed["warnings"],
            "table_count": parsed["table_count"],
            "field_count": parsed["field_count"],
        }

    def list_documents(self) -> list[dict[str, Any]]:
        return self.storage.list_documents()

    def activate_document(self, user: dict[str, Any], document_id: int) -> dict[str, Any]:
        return self.storage.activate_document(document_id)

    def active_document(self) -> dict[str, Any] | None:
        return self.storage.active_document()

    def list_prompts(self) -> list[dict[str, Any]]:
        result = []
        for stage, default in DEFAULT_PROMPTS.items():
            active = self.storage.active_prompt(stage)
            result.append({
                "stage": stage,
                "label": STAGE_LABELS.get(stage, stage),
                "content": active["content"] if active else default,
                "version_no": int(active["version_no"]) if active else 0,
                "is_default": active is None,
                "placeholders": list(REQUIRED_PLACEHOLDERS.get(stage, ())),
                "output_contract": {"select_table": SELECT_OUTPUT_CONTRACT, "generate_rule": RULE_OUTPUT_CONTRACT}.get(stage, ""),
            })
        return result

    def save_prompt(self, user: dict[str, Any], stage: str, content: str) -> dict[str, Any]:
        if stage not in DEFAULT_PROMPTS:
            raise AppError("VALIDATION_ERROR")
        text = str(content or "").strip()
        if not text:
            raise AppError("VALIDATION_ERROR")
        missing = [name for name in REQUIRED_PLACEHOLDERS.get(stage, ()) if "{" + name + "}" not in text]
        if missing:
            raise AppError("VALIDATION_ERROR")
        return self.storage.save_prompt(stage, text, str(user["id"]))

    def reset_prompt(self, user: dict[str, Any], stage: str) -> dict[str, Any]:
        if stage not in DEFAULT_PROMPTS:
            raise AppError("VALIDATION_ERROR")
        return self.storage.save_prompt(stage, DEFAULT_PROMPTS[stage], str(user["id"]))

    def list_source_rules(self) -> list[dict[str, Any]]:
        return self.storage.source_rules() or list(DEFAULT_SOURCE_RULES)

    def save_source_rules(self, user: dict[str, Any], rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
        prepared = []
        for item in rules or []:
            prefix = str(item.get("sheet_prefix") or "").strip()
            source = str(item.get("data_source_name") or "").strip()
            if not source:
                raise AppError("VALIDATION_ERROR")
            prepared.append({"sheet_prefix": prefix, "data_source_name": source})
        if not prepared or not any(item["sheet_prefix"] == "" for item in prepared):
            raise AppError("VALIDATION_ERROR")
        return self.storage.save_source_rules(prepared)

    def _prompt_text(self, stage: str) -> str:
        active = self.storage.active_prompt(stage)
        return active["content"] if active else DEFAULT_PROMPTS[stage]

    @staticmethod
    def _render(template: str, values: dict[str, Any]) -> str:
        # Replace template placeholders once; data containing {fields} stays data.
        return re.sub(
            r"\{([A-Za-z_][A-Za-z0-9_]*)\}",
            lambda match: str(values[match.group(1)]) if match.group(1) in values else match.group(0),
            template,
        )

    @staticmethod
    def _load_json(raw: str) -> dict[str, Any]:
        text_value = str(raw or "").strip()
        if text_value.startswith("```"):
            fenced = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\n?```", text_value, re.DOTALL | re.IGNORECASE)
            if fenced:
                text_value = fenced.group(1).strip()
        try:
            parsed = json.loads(text_value)
        except (TypeError, ValueError):
            start = text_value.find("{")
            end = text_value.rfind("}")
            if start < 0 or end <= start:
                raise AppError("VALIDATION_ERROR")
            try:
                parsed = json.loads(text_value[start:end + 1])
            except (TypeError, ValueError) as exc:
                raise AppError("VALIDATION_ERROR") from exc
        if not isinstance(parsed, dict):
            raise AppError("VALIDATION_ERROR")
        return parsed

    def _complete_json(self, prompt: str, model_id: str, *, stage: str = "generate_rule") -> dict[str, Any]:
        raw = complete_text(
            self.model, str(model_id or ""), prompt,
            stage=stage, timeout=GENERATION_TIMEOUT_SECONDS,
        )
        try:
            return self._load_json(raw)
        except AppError as exc:
            raise failure("MODEL_RESPONSE_INVALID", stage) from exc

    def _doc_category(self, categories: list[dict[str, str]], raw: str) -> dict[str, str] | None:
        value = str(raw or "").strip()
        return next((item for item in categories if value in {item["code"], item["name"]}), None)

    def _doc_columns(self, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # 保留真实源字段事实键：数值 NULL=0 约定只出现在 logic/dictionary/源字段说明中，
        # 仅 name/comment/data_type 会让文档证据不可见。
        return [
            {
                "column_name": item["field_name"],
                "comment": item.get("field_cn") or "",
                "data_type": item.get("data_type") or "",
                "field_cn": item.get("field_cn") or "",
                "logic": item.get("logic") or "",
                "dictionary": item.get("dictionary") or "",
                "source_field": item.get("source_field") or "",
                "source_field_cn": item.get("source_field_cn") or "",
                "is_pk": item.get("is_pk") or "",
                "nullable": item.get("nullable") or "",
                "default_value": item.get("default_value") or "",
            }
            for item in fields
        ]

    # ---- 项目身份：只按授权活动文档真实证据解析/重核 -------------------

    @staticmethod
    def _project_required(definition: dict[str, Any], table: dict[str, Any], fields: list[dict[str, Any]]) -> bool:
        # Authoritative document entity/scope and the fields' own roles count;
        # a model flag, physical-name guess, or lineage mention does not.
        return (project_semantics_required(definition, table)
                or bool(project_code_fields(fields)) or bool(project_name_fields(fields)))

    def _resolve_project_context(
        self,
        definition: dict[str, Any],
        table: dict[str, Any],
        fields: list[dict[str, Any]],
        tables: list[dict[str, Any]],
        fields_by_table: dict[int, list[dict[str, Any]]],
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]], list[str], bool]:
        """返回 (context|None, project_columns, questions, uncertainties, required)。

        完全交给已冻结的 infer_project_context：客户端 project_context 只作真实
        文档选择，证据/确认由文档重核；服务不复制 helper 逻辑。
        """
        required = self._project_required(definition, table, fields)
        inferred = infer_project_context(definition, table, fields, tables, fields_by_table)
        required = required or bool(inferred.get("required"))
        uncertainties = list(inferred.get("uncertainties") or []) if required else []
        return (
            inferred.get("context"),
            self._doc_columns(inferred.get("project_columns") or []),
            list(inferred.get("questions") or []), uncertainties, required,
        )


    def _field_context(self, fields: list[dict[str, Any]], request_text: str = "", *, limit: int = _FIELD_CONTEXT_LIMIT) -> tuple[str, bool]:
        def tokens(value: str) -> set[str]:
            text_value = str(value or "")
            parts = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text_value))
            for chunk in re.findall(r"[一-鿿]{2,}", text_value):
                for size in range(2, min(8, len(chunk)) + 1):
                    for offset in range(0, len(chunk) - size + 1):
                        parts.add(chunk[offset:offset + size])
            return parts

        wanted = tokens(request_text)
        scored = []
        for index, field in enumerate(fields):
            haystack = f"{field.get('field_name') or ''} {field.get('field_cn') or ''} {field.get('logic') or ''}"
            score = sum(1 for token in wanted if token and token in haystack)
            # Scope words often occur only in code dictionaries, not in the column label.
            score += 2 * sum(1 for token in wanted if token and token in str(field.get("dictionary") or ""))
            ranked_score = score + (100 if field.get("is_pk") == "Y" else 0)
            scored.append((ranked_score, index, field, score))
        if len(fields) <= limit:
            selected = [(field, score) for _ranked, _index, field, score in scored]
        else:
            ranked = sorted(scored, key=lambda item: (-item[0], item[1]))[:limit]
            selected = [(field, score) for _ranked, _index, field, score in sorted(ranked, key=lambda item: item[1])]
        lines = []
        for field, score in selected:
            pk = "|PK" if field.get("is_pk") == "Y" else ""
            line = f"{field['field_name']}|{field.get('field_cn') or ''}|{field.get('data_type') or ''}{pk}"
            logic = str(field.get("logic") or "").strip() if score > 0 else ""
            if len(logic) > 120:
                logic = logic[:120] + "…"
            if logic:
                line += f"|取数逻辑:{logic}"
            dictionary = str(field.get("dictionary") or "").strip()[:100] if score > 0 else ""
            if dictionary:
                line += f"|字典:{dictionary}"
            nullable = str(field.get("nullable") or "").strip()[:16]
            if nullable:
                line += f"|存储可空标记:{nullable}（非业务空值语义）"
            lines.append(line)
        return "\n".join(lines), len(fields) > len(selected)

    @staticmethod
    def _doc_category_scope(table: dict[str, Any], categories: list[dict[str, str]]) -> frozenset[str] | None:
        sheet = str(table.get("sheet_name") or "")
        if sheet.startswith("人行_"):
            return _PBC_REPORT_CATEGORIES
        prefix, separator, _ = sheet.partition("_")
        if separator:
            def normalize(text: str) -> str:
                return re.sub(r"\s+", "", text).casefold()

            names = frozenset(item["code"] for item in categories if normalize(item["name"]) == normalize(prefix))
            if names:
                return names
        return _PBC_REPORT_CATEGORIES if is_pbc_report_sheet(sheet) else None

    def _doc_table_context(self, tables: list[dict[str, Any]], categories: list[dict[str, str]]) -> str:
        lines = []
        for table in tables:
            desc = str(table.get("source_desc") or "").strip()
            if len(desc) > 120:
                desc = desc[:120] + "…"
            scope = str(table.get("scope") or "")[:160]
            category_scope = self._doc_category_scope(table, categories)
            names = [item["name"] for item in categories if category_scope is not None and item["code"] in category_scope]
            family = f"|文档报送分类:{' / '.join(names)}" if names else ""
            lines.append(f"{table['table_name']}|{table.get('table_name_cn') or ''}|{desc}|范围:{scope}{family}")
        return "\n".join(lines)

    def list_sources(self) -> list[dict[str, str]]:
        if self.metadata is None or not hasattr(self.metadata, "list_sources"):
            return []
        return [
            {"id": item.id, "name": item.name, "dialect": item.dialect}
            for item in self.metadata.list_sources()
        ]

    def list_selectable_sources(self) -> list[dict[str, str]]:
        return [
            item for item in self.list_sources()
            if str(item.get("name") or "") in _SELECTABLE_SOURCE_NAMES
        ]

    def describe_source_table(self, source_id: str, table_name: str) -> dict[str, Any]:
        if self.metadata is None or str(source_id) not in {str(item["id"]) for item in self.list_selectable_sources()}:
            raise AppError("SOURCE_UNAVAILABLE")
        return self.metadata.describe_table(source_id, table_name)

    def list_recent_tasks(self, user: dict[str, Any], query: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        period = str((query or {}).get("report_period") or "").strip()
        if period:
            period = _report_period(period)
        rows = self.storage.list_tasks(None if self._is_admin(user) else str(user["id"]), period)
        ordered = sorted(rows, key=lambda item: int(item["id"]))
        sequence = {int(item["id"]): index + 1 for index, item in enumerate(ordered)}
        for item in rows:
            item["run_no"] = sequence[int(item["id"])]
        return rows

    def copy_rule(self, user: dict[str, Any], rule_id: int) -> dict[str, Any]:
        rule = self.storage.get_rule(rule_id)
        if not self._is_admin(user) and str(rule["creator_user_id"]) != str(user["id"]):
            self._deny(user, rule_id)
        version = self.storage.latest_version(rule_id)
        definition = dict(version["definition"])
        definition["name"] = rule["name"]
        changes = definition_changes(None, definition)
        history = history_event(
            "copy", user, version_no=1, content_sha256=version["content_sha256"], changes=changes,
            before_status=None, after_status="draft",
            summary=(
                f"从 {rule['rule_code']} 的版本 {version['version_no']} 复制创建；"
                f"来源哈希 {version['content_sha256']}"
            ),
            details={
                "source_rule_id": int(rule["id"]),
                "source_rule_code": str(rule["rule_code"]),
                "source_version_no": int(version["version_no"]),
                "source_content_sha256": str(version["content_sha256"]),
            },
        )
        created = self.storage.create_rule(
            creator_user_id=str(user["id"]),
            name=rule["name"],
            description=rule["description"],
            definition=definition,
            sql_text=version["sql_text"],
            mapping_version=version["mapping_version"],
            content_sha256=version["content_sha256"],
            generation_mode="manual",
            history=history,
        )
        created["version_no"] = 1
        created["current_version_id"] = None
        return created

    def disable_rule(self, user: dict[str, Any], rule_id: int) -> dict[str, Any]:
        rule = self._require_owner(user, rule_id)
        version = (
            self.storage.get_version_by_id(int(rule["current_version_id"]))
            if rule.get("current_version_id")
            else self.storage.latest_version(rule_id)
        )
        history = history_event(
            "disable", user, version_no=int(version["version_no"]),
            content_sha256=str(version["content_sha256"]), changes=[],
            before_status=str(rule["status"]), after_status="disabled",
            summary=(
                f"停用规则，状态由 {rule['status']} 变为 disabled；"
                f"版本 {version['version_no']}，哈希 {version['content_sha256']}"
            ),
        )
        self.storage.set_status(rule_id, "disabled", history=history)
        return self.storage.get_rule(rule_id)

    def test_model(self, user: dict[str, Any], model_id: str) -> dict[str, Any]:
        """测试所选模型是否真正可用：发起一次最小对话请求，不保存任何规则。"""
        if self.model is None:
            raise AppError("MODEL_UNAVAILABLE")
        complete_text(
            self.model, str(model_id or ""), "可用性测试：请仅回复 ok",
            stage="test_model", timeout=10,
        )
        return {"available": True, "model_id": str(model_id or "")}

    def preview_candidate(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        """Preview an unsaved definition against the active document, never client SQL/columns."""
        if "definition" in payload and not isinstance(payload["definition"], dict):
            raise AppError("VALIDATION_ERROR")
        definition = dict(payload.get("definition", payload))
        source_id = str(definition.get("source_id") or "")
        source = next((item for item in self.list_selectable_sources() if str(item["id"]) == source_id), None)
        if source is None:
            raise AppError("SOURCE_UNAVAILABLE")
        document = self.storage.active_document()
        if document is None:
            raise AppError("VALIDATION_ERROR")
        mapping = f"doc-v{int(document['version_no'])}-{str(document['content_sha256'])[:12]}"
        if definition.get("mapping_version") not in (None, "", mapping):
            raise AppError("CONFLICT_VERSION")
        source_tables = self.storage.doc_tables(int(document["id"]), data_source_name=str(source["name"]))
        table = next((item for item in source_tables if item["table_name"] == definition.get("table_name")), None)
        if table is None:
            raise AppError("VALIDATION_ERROR")
        related_columns = None
        raw_join = definition.get("join")
        if raw_join is not None:
            if not isinstance(raw_join, dict):
                raise AppError("VALIDATION_ERROR")
            related = next((item for item in source_tables if item["table_name"] == raw_join.get("table_name")), None)
            if related is None or related["id"] == table["id"]:
                raise AppError("VALIDATION_ERROR")
            related_columns = self._doc_columns(self.storage.doc_fields(int(related["id"])))
        fields_by_table = self.storage.doc_fields_for_tables([int(item["id"]) for item in source_tables])
        fields = list(fields_by_table.get(int(table["id"])) or [])
        context, project_columns, context_questions, context_uncertainties, required = self._resolve_project_context(
            definition, table, fields, source_tables, fields_by_table,
        )
        if context is None and required:
            # 项目口径规则缺真实项目身份时拒绝完整预览，不能只出合同键。
            raise AppError("PROJECT_CONTEXT_REQUIRED")
        if context is not None:
            definition["project_context"] = context
        else:
            definition.pop("project_context", None)
        # 预览前按真实文档字段重新绑定数值空值策略；客户端 null_evidence/模型策略不作证据。
        related_fields_raw = (
            self.storage.doc_fields(int(related["id"]))
            if raw_join is not None
            else []
        )
        definition = apply_numeric_null_policy(
            definition, self._doc_columns(fields),
            self._doc_columns(related_fields_raw) if related_fields_raw else None,
        )
        definition.update({"source_id": source_id, "dialect": str(source.get("dialect") or ""), "mapping_version": mapping})
        definition.setdefault("generation_mode", "ai")
        preview = preview_definition(
            definition, self._doc_columns(fields), related_columns, project_columns,
        )
        if context_questions:
            all_questions = [*(preview.get("questions") or []), *context_questions]
            preview["questions"] = list({question["id"]: question for question in all_questions}.values())
        if context_uncertainties:
            preview["uncertainties"] = merge(preview.get("uncertainties") or [], context_uncertainties)
        return preview

    def test_candidate(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        preview = self.preview_candidate(user, payload)
        expected_hash = payload.get("expected_hash")
        if expected_hash is not None and expected_hash != preview["content_sha256"]:
            raise AppError("CONFLICT_VERSION")
        return run_preview_cases(preview, payload.get("cases"))

    # ---- 临时分析任务：内存快照、owner 隔离、协作取消 -------------------

    def start_analysis(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        if self.model is None:
            raise AppError("MODEL_UNAVAILABLE")
        return self.analyses.start(user, payload)

    def get_analysis(self, user: dict[str, Any], analysis_id: str) -> dict[str, Any]:
        return self.analyses.get(user, analysis_id)

    def cancel_analysis(self, user: dict[str, Any], analysis_id: str) -> dict[str, Any]:
        return self.analyses.cancel(user, analysis_id)

    def _execute_analysis(
        self,
        user: dict[str, Any],
        payload: dict[str, Any],
        progress: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        return self.parse_rule_request(user, payload, progress=progress)

    @staticmethod
    def _emit_progress(
        progress: Callable[[dict[str, Any]], None] | None,
        step: str,
        status: str,
        detail: str = "",
        **fields: Any,
    ) -> None:
        if progress is None:
            return
        event: dict[str, Any] = {"step": step, "status": status, "detail": detail}
        for key, value in fields.items():
            if value is not None:
                event[key] = value
        progress(event)

    def _materialize_candidate_option(
        self,
        *,
        user: dict[str, Any],
        other: dict[str, Any],
        left_match: dict[str, Any],
        right_match: dict[str, Any] | None,
        refined: dict[str, Any],
        request_text: str,
        option_number: int,
        match_reason: str,
        tables: list[dict[str, Any]],
        fields_by_table: dict[int, list[dict[str, Any]]],
    ) -> dict[str, Any] | None:
        """把一次真实文档字段匹配物化为完整候选；无法安全预览时返回 None。"""
        alternative = copy.deepcopy(refined)
        alternative.pop("candidate_options", None)
        alternative.pop("comparison_suggestions", None)
        # 换表后旧对象的项目身份/建议一律作废，必须按替代对象真实文档重绑。
        alternative.pop("project_context", None)
        alternative.pop("project_columns", None)
        alternative.pop("project_table", None)
        alternative.pop("null_handling", None)
        alternative.pop("null_evidence", None)
        alternative.pop("ai_suggestions", None)
        other_fields = self.storage.doc_fields(int(other["id"]))
        columns = self._doc_columns(other_fields)
        expression = copy.deepcopy(alternative.get("expression") or {})
        expression["left"] = left_match["field_name"]
        if str(expression.get("right_type") or "field") == "field" and right_match is not None:
            expression["right"] = right_match["field_name"]
            expression.pop("right_table", None)
        alternative["expression"] = expression
        alternative["table_name"] = str(other["table_name"])
        alternative["columns"] = columns
        alternative["related_columns"] = []
        alternative.pop("join", None)
        alternative["business_key"] = next(
            (field["field_name"] for field in other_fields if field.get("is_pk") == "Y"), "",
        )
        chosen_date, date_options = resolve_report_date(columns)
        alternative["report_date_field"] = chosen_date
        if not alternative["business_key"] or not chosen_date:
            # 缺真实主键或期间日期时不能编译成可执行规则，保留在原候选的人工问题中。
            return None

        kept_questions = [
            item for item in alternative.get("questions", [])
            if item.get("id") not in {"business_key", "report_date_field", "expression.left", "expression.right"}
            and not str(item.get("id") or "").startswith("project_context.")
        ]
        alternative["questions"] = kept_questions
        alternative = apply_numeric_null_policy(alternative, columns)
        # 换表后绝不沿用旧对象派生口径：筛选/关联清零；数值常量与单位需重新确认。
        had_filters = bool(alternative.get("filters"))
        alternative["filters"] = []
        alternative.pop("join", None)
        extra_uncertainties: list[str] = []
        if had_filters:
            extra_uncertainties.append(f"原筛选条件针对其它对象，替代对象需按 {other['table_name']} 的真实字段重新确认。")
        if (
            str(expression.get("right_type") or "field") == "value"
            and expression.get("right") is not None
            and expression.get("right") != 0
        ):
            # 非零阈值跨对象口径不能盲复制；“不得为 0”这类独立检查不受单位/币种影响。
            extra_uncertainties.append(
                f"数值常量 {expression.get('right')} 来自原对象口径，需确认在替代对象上的单位/币种/粒度。",
            )
        if extra_uncertainties:
            uncertainties = list(alternative.get("uncertainties") or []) + extra_uncertainties
            alternative["uncertainties"] = uncertainties
            alternative["uncertainty_resolutions"] = [""] * len(uncertainties)
        # 替代对象的项目身份独立重核，不沿用主表投影。
        context, _project_columns, context_questions, context_uncertainties, context_required = (
            self._resolve_project_context(alternative, other, other_fields, tables, fields_by_table)
        )
        if context is not None:
            alternative["project_context"] = context
        else:
            alternative.pop("project_context", None)
        if context_questions:
            alternative["questions"] = list(alternative.get("questions") or []) + context_questions
        if context_uncertainties:
            merged = merge(list(alternative.get("uncertainties") or []), context_uncertainties)
            alternative["uncertainties"] = merged
            alternative["uncertainty_resolutions"] = [""] * len(merged)
        alternative["scope_description"] = str(other.get("table_name_cn") or "所选项目数据")
        table_label = str(other.get("table_name_cn") or other["table_name"])
        grain = grain_label(other)
        alternative["description"] = (
            str(alternative.get("description") or "")
            + f"；候选方案：{table_label}（{grain or '粒度未标注'}）；依据：文档同义指标 {left_match.get('field_cn') or left_match['field_name']}"
        )
        # 每个方案按当前真实对象/字段独立命名与提示，绝不沿用原对象的口径标题。
        option_field_label = str(left_match.get("field_cn") or left_match["field_name"])
        alternative["rule_name"] = f"{table_label}·{option_field_label}校验"
        alternative["violation_message"] = (
            f"{option_field_label}（{other['table_name']}）命中异常条件，请人工核实"
        )
        definition = {**alternative, "name": alternative.get("rule_name") or other["table_name"], "generation_mode": "ai"}
        preview: dict[str, Any] | None = None
        if context is None and context_required:
            # 替代对象缺真实项目身份时不给完整预览，保留人工问题。
            alternative["preview_error"] = "所选对象无法从当前授权文档确定真实项目身份，需人工补充。"
        else:
            try:
                preview = self.preview_candidate(user, definition)
            except AppError:
                return None
        if preview is not None:
            alternative.update({
                key: value for key, value in preview["definition"].items()
                if key in {
                    "source_id", "dialect", "mapping_version", "report_category", "table_name",
                    "business_key", "report_date_field", "expression", "violation_message",
                    "null_policy", "null_handling", "null_evidence", "equality_policy", "filters", "join", "generation_mode",
                    "project_context",
                }
            })
            alternative["preview"] = preview
            alternative["preview_error"] = ""
        alternative["can_enable"] = (
            preview is not None
            and not alternative.get("questions") and not alternative.get("uncertainties")
            and not alternative.get("unsupported_requirements")
        )
        alternative["_option_meta"] = {
            "option_number": option_number,
            "table_label": table_label,
            "grain": grain,
            "field_label": str(left_match.get("field_cn") or left_match["field_name"]),
            "match_reason": match_reason,
        }
        return alternative

    def _refresh_candidate_preview(self, user: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
        """口径清理后统一重新编译，保证 preview.definition 等于最终候选定义。"""
        candidate.pop("candidate_options", None)
        candidate.pop("comparison_suggestions", None)
        candidate.pop("ai_suggestions", None)
        definition = {
            **candidate,
            "name": candidate.get("rule_name") or candidate.get("table_name") or "未命名规则",
            "generation_mode": "ai",
        }
        try:
            preview = self.preview_candidate(user, definition)
        except AppError:
            return candidate
        candidate.update({
            key: value for key, value in preview["definition"].items()
            if key in {
                "source_id", "dialect", "mapping_version", "report_category", "table_name",
                "business_key", "report_date_field", "expression", "violation_message",
                "null_policy", "equality_policy", "filters", "join", "generation_mode",
                "project_context",
            }
        })
        candidate["preview"] = preview
        candidate["preview_error"] = ""
        uncertainties = list(candidate.get("uncertainties") or [])
        resolutions = list(candidate.get("uncertainty_resolutions") or [])
        candidate["uncertainty_resolutions"] = (resolutions + [""] * len(uncertainties))[:len(uncertainties)]
        try:
            candidate["can_enable"] = bool(query_ready(candidate) and review_ready(candidate))
        except AppError:
            candidate["can_enable"] = False
        return candidate

    def _attach_candidate_options(
        self,
        *,
        user: dict[str, Any],
        source: dict[str, Any],
        tables: list[dict[str, Any]],
        fields_by_table: dict[int, list[dict[str, Any]]],
        table: dict[str, Any],
        refined: dict[str, Any],
        request_text: str,
    ) -> dict[str, Any]:
        """在现有选表/生成之后发现同源文档内的真实替代对象（最多 3 个）。"""
        # A counterpart measure does not prove that the original object's scope also maps.
        # Keep the existing grounded flow until filters/relationships can be mapped explicitly.
        if refined.get("join") is not None or refined.get("filters") or refined.get("status") == "needs_clarification":
            return refined
        expression = refined.get("expression") or {}
        right_type = str(expression.get("right_type") or "field")
        base_fields = fields_by_table.get(int(table["id"]), [])
        base_left = next((field for field in base_fields if field["field_name"] == expression.get("left")), None)
        if base_left is None:
            return refined
        base_right = None
        if right_type == "field" and expression.get("right"):
            base_right = next((field for field in base_fields if field["field_name"] == expression.get("right")), None)
            if base_right is None:
                return refined

        pool: list[dict[str, Any]] = []
        for other in tables:
            if int(other["id"]) == int(table["id"]):
                continue
            other_fields = fields_by_table.get(int(other["id"]))
            if other_fields is None:
                other_fields = self.storage.doc_fields(int(other["id"]))
            if not other_fields:
                continue
            left_matches = counterpart_fields(other_fields, base_left)
            if not left_matches:
                continue
            right_matches = [None]
            if base_right is not None:
                right_matches = counterpart_fields(other_fields, base_right)
                if not right_matches:
                    continue
            for left_match in left_matches[:1]:
                for right_match in right_matches[:1]:
                    core = semantic_core(field_label(base_left), field_label(left_match))
                    match_reason = (
                        f"共同业务语义“{core}”；规模/余额等限定不同，需确认口径（{other['table_name']}）"
                    )
                    alternative = self._materialize_candidate_option(
                        user=user, other=other, left_match=left_match, right_match=right_match,
                        refined=refined, request_text=request_text, option_number=len(pool) + 1,
                        match_reason=match_reason, tables=tables, fields_by_table=fields_by_table,
                    )
                    if alternative is not None:
                        pool.append(alternative)
                        break
                if len(pool) >= 3:
                    break
            if len(pool) >= 3:
                break
        if not pool:
            return refined

        base_copy = copy.deepcopy(refined)
        base_copy.pop("candidate_options", None)
        base_copy.pop("comparison_suggestions", None)
        base_copy.pop("ai_suggestions", None)
        base_grain = grain_label(table)
        base_label = str(table.get("table_name_cn") or table["table_name"])
        base_field_label = str(base_left.get("field_cn") or base_left["field_name"])
        base_copy["rule_name"] = f"{base_label}·{base_field_label}校验"
        base_copy["violation_message"] = (
            f"{base_field_label}（{table['table_name']}）命中异常条件，请人工核实"
        )
        base_copy["description"] = (
            str(base_copy.get("description") or "")
            + f"；候选方案：{base_label}（{base_grain or '粒度未标注'}）"
        )
        entries = [{
            "meta": {
                "option_number": 0, "table_label": base_label, "grain": base_grain,
                "field_label": base_field_label,
                "match_reason": f"模型选表结果：{table['table_name']}",
            },
            "candidate": base_copy,
        }] + [
            {"meta": alternative.pop("_option_meta"), "candidate": alternative}
            for alternative in pool
        ]

        grains = [str(entry["meta"].get("grain") or "") for entry in entries]
        recommended = recommended_index(grains, request_text)
        if recommended is not None and recommended != 0:
            promoted = entries.pop(recommended)
            entries.insert(0, promoted)
            recommended = 0
        for index, entry in enumerate(entries):
            entry["recommended"] = index == recommended if recommended is not None else False

        # 分句消解：有真实多候选时目标选择转差异；已确定期间日期时消除平台日期机制问法。
        for entry in entries:
            candidate = entry["candidate"]
            original_uncertainties = list(candidate.get("uncertainties") or [])
            cleaned = resolve_uncertainty_clauses(
                original_uncertainties,
                has_candidates=len(entries) > 1,
                has_period=bool(candidate.get("report_date_field")),
            )
            if cleaned != original_uncertainties:
                candidate["uncertainties"] = cleaned
                candidate["uncertainty_resolutions"] = [""] * len(cleaned)

        refreshed: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for entry in entries[:3]:
            candidate = copy.deepcopy(entry["candidate"])
            candidate.pop("candidate_options", None)
            candidate.pop("comparison_suggestions", None)
            candidate.pop("ai_suggestions", None)
            refreshed.append((entry, self._refresh_candidate_preview(user, candidate)))
        primary = copy.deepcopy(refreshed[0][1])
        options = []
        for entry, candidate in refreshed:
            options.append({
                "id": option_id(
                    str(source["id"]), str(candidate.get("table_name") or ""), str(base_field_label),
                    request_text, str(candidate.get("mapping_version") or ""),
                    str((candidate.get("expression") or {}).get("op") or ""),
                ),
                "label": f"{entry['meta'].get('table_label') or candidate.get('table_name')} · {entry['meta'].get('field_label') or base_field_label}",
                "recommended": bool(entry.get("recommended")),
                "match_reason": str(entry["meta"].get("match_reason") or "当前文档存在相关指标"),
                "grain": str(entry["meta"].get("grain") or ""),
                "table_label": str(entry["meta"].get("table_label") or ""),
                "field_label": str(entry["meta"].get("field_label") or ""),
                "differences": difference_lines(
                    str(entry["meta"].get("table_label") or ""), str(entry["meta"].get("grain") or ""),
                    str(entry["meta"].get("field_label") or ""), base_field_label,
                ),
                "candidate": candidate,
            })
        if options:
            primary["candidate_options"] = options
            suggestion = comparison_suggestion([
                str(entry.get("meta", {}).get("grain") or "") for entry in entries
            ])
            primary["comparison_suggestions"] = [suggestion] if suggestion else []
        return primary

    def _clarification_fallback(self, selection: dict[str, Any], tables: list[dict[str, Any]],
                               request_text: str = "") -> list[dict[str, Any]]:
        """从 typed target_ambiguities/candidates 或旧歧义句提取真实候选对象名单。

        仅在当前授权活动文档中存在至少两个不同真实表时返回，避免无证据猜测。
        """
        typed = selection.get("target_ambiguities") or selection.get("candidates") or []
        found: dict[int, dict[str, Any]] = {}
        if isinstance(typed, list):
            for item in typed:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("table") or item.get("table_name") or "").strip().strip("`\"'")
                name = name.rsplit(".", 1)[-1].strip()
                for table in tables:
                    if str(table["table_name"]).lower() == name.lower() and int(table["id"]) not in found:
                        found[int(table["id"])] = table
        if len(found) >= 2:
            targets = list(found.values())
        else:
            texts = [str(value) for value in (selection.get("uncertainties") or []) if isinstance(value, str)]
            if not any(TARGET_SELECT.search(text) for text in texts):
                return []
            mentioned: dict[int, dict[str, Any]] = {}
            positions: dict[int, tuple[int, int]] = {}
            for text_index, text in enumerate(texts):
                for table in tables:
                    position = text.find(str(table["table_name"]))
                    if position >= 0 and int(table["id"]) not in positions:
                        positions[int(table["id"])] = (text_index, position)
                        mentioned[int(table["id"])] = table
            targets = [mentioned[key] for key in sorted(positions, key=lambda item: positions[item])] if len(mentioned) >= 2 else []
        # 保持模型给出的候选顺序（typed 顺序或旧句中先出现的表），不在后端另作主观排序。
        return targets

    def _project_parallel_result(self, user, source, document, table, fields, plan, request_text,
                                 knowledge_context, progress):
        """Prepare independent preview definitions; never persist from analysis."""
        table_name = str(table["table_name"])
        mapping = f"doc-v{int(document['version_no'])}-{str(document['content_sha256'])[:12]}"
        columns = self._doc_columns(fields)
        period, dates = resolve_report_date(columns)
        keys = [item["field_name"] for item in fields if item.get("is_pk") == "Y"]
        context, project_columns, project_questions, project_issues, required = self._resolve_project_context(
            {}, table, fields, [table], {int(table["id"]): fields},
        )
        common = {"rule_type": "field_compare", "table_name": table_name, "source_id": str(source["id"]),
                  "dialect": str(source["dialect"]), "report_category": "", "generation_mode": "ai",
                  "mapping_version": mapping, "columns": columns, "project_columns": project_columns,
                  "report_date_field": period, "business_key": keys[0] if len(keys) == 1 else "",
                  "null_policy": "review", "equality_policy": "allow_equal", "parallel_check": True,
                  "uncertainties": request_reviews(request_text), "questions": [], "unsupported_requirements": [],
                  "uncertainty_resolutions": [], "scope_description": "存续项目" if plan["active"] else "项目",
                  "preview": None, "can_enable": False, "description": request_text}
        ground_candidate_query(common, {}, fields, [], request_text)
        if plan["active"] and not common.get("filters"):
            common["preview_error"] = "项目信息表的活动文档缺少可核验的存续状态与取值，不能按全量项目生成预览。"
        if context is not None:
            common["project_context"] = context
        common["questions"].extend(project_questions)
        if required and context is None and not project_questions:
            common["preview_error"] = project_issues[0] if project_issues else "活动文档不能确定项目编号与全称。"
        if not common["business_key"] and context:
            common["business_key"] = context["code_field"]
        if not common["business_key"] and not project_questions:
            common["preview_error"] = "活动文档未确定业务定位字段，不能生成预览。"
        if not period:
            if dates:
                common["questions"].append({"id": "report_date_field", "text": "按哪个日期检查这批记录？",
                    "options": [{"value": col["column_name"], "label": col.get("comment") or col["column_name"]} for col in dates]})
            else:
                common["preview_error"] = "活动文档缺少校验期间日期。"
        options = []
        for item in plan["checks"]:
            term, field = item["term"], item["field"]
            candidate = copy.deepcopy(common)
            name = f"项目{term}检查"
            candidate.update(rule_name=name, name=name, violation_message=f"{term}不符合要求，需核实。",
                             expression={"left": field["field_name"] if field else "", "op": plan["op"],
                                         "right_type": "value", "right": plan["constant"]})
            if not field:
                if item["options"]:
                    candidate["questions"].append({"id": "expression.left", "text": f"这里的“{term}”指哪个项目字段？",
                        "options": [{"value": col["field_name"], "label": f"{col['field_cn']}（{col['field_name']}）",
                                     "description": col.get("logic") or "活动文档中的项目字段"} for col in item["options"]]})
                else:
                    candidate["preview_error"] = f"活动文档没有核实到“{term}”的项目字段，请单独明确这一项。"
            if candidate.get("preview_error"):
                candidate["parallel_blocked"] = candidate["preview_error"]
            elif not candidate["questions"]:
                try:
                    candidate["preview"] = self.preview_candidate(user, candidate)
                except AppError as exc:
                    if exc.code != "VALIDATION_ERROR":
                        raise
                    candidate["preview_error"] = "当前字段与口径不能通过后端预览校验。"
            options.append({"id": option_id(str(source["id"]), table_name, term, request_text, mapping),
                            "label": name, "table_label": table.get("table_name_cn") or table_name,
                            "field_label": field_label(field) if field else f"{term}（待确认）", "grain": "项目级",
                            "recommended": field is not None, "match_reason": "同一项目主表上的独立检查",
                            "candidate": candidate})
        primary = next(option["candidate"] for option in options if option["recommended"])
        status = "needs_confirmation" if any(item["candidate"]["preview"] is None for item in options) else "completed"
        self._emit_progress(progress, "semantics", "completed", "原需求包含独立项目字段检查")
        self._emit_progress(progress, "metadata", "completed", "已核对活动文档项目主表", table_name=table_name, field_count=len(fields))
        self._emit_progress(progress, "generation", status, "已拆分为独立检查，共用项目存续口径")
        return {**primary, "candidate_options": options, "knowledge_context": knowledge_context, "ai_suggestions": []}

    def parse_rule_request(
        self,
        user: dict[str, Any],
        payload: dict[str, Any],
        *,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """AI 创建：完全按已导入的文档快照生成规则，不读取数据库。

        数据库不可用或表尚不存在都不影响生成；真实核验留到测试/确认启用阶段。
        ``progress`` 只用于内存任务的进度快照，不改变模型调用次数与返回内容。
        """
        self._emit_progress(progress, "semantics", "running", "正在解析业务语义与选表范围")
        if self.model is None:
            raise AppError("MODEL_UNAVAILABLE")
        source_id = str(payload.get("source_id") or "")
        sources = {str(item["id"]): item for item in self.list_selectable_sources()}
        if not source_id or source_id not in sources:
            raise AppError("SOURCE_UNAVAILABLE")
        source = sources[source_id]
        document = self.storage.active_document()
        if document is None:
            raise AppError("VALIDATION_ERROR")
        tables = self.storage.doc_tables(int(document["id"]), data_source_name=str(source["name"]))
        if not tables:
            raise AppError("VALIDATION_ERROR")
        categories = self._report_processes()
        existing = []
        for rule in self.storage.visible_rules(str(user["id"])):
            version = self.storage.latest_version(int(rule["id"]))
            existing.append({"rule_code": rule["rule_code"], "definition": version["definition"]})

        request_text = str(payload.get("request_text") or "")
        knowledge_prefix, knowledge_context = self.knowledge.context(
            str(user["id"]), source_id, str(source["name"]),
            f"{document['id']}:{document['content_sha256']}", request_text,
        )
        if knowledge_context:
            reused = knowledge_context["summary_reused"] or knowledge_context["catalog_reused"]
            self._emit_progress(progress, "semantics", "running",
                                "已复用业务知识，正在解析需求" if reused else "已加载业务知识，正在解析需求")
        shortlist = shortlist_tables(tables, request_text, _TABLE_SHORTLIST_LIMIT)
        project_target = project_mart_target(str(source["name"]), tables, request_text)
        if project_target is not None:
            shortlist = [project_target, *(item for item in shortlist if item["id"] != project_target["id"])][:_TABLE_SHORTLIST_LIMIT]
        fields_by_table = self.storage.doc_fields_for_tables([int(item["id"]) for item in shortlist])
        if project_target is not None:
            project_fields = fields_by_table.get(int(project_target["id"]), [])
            plan = project_parallel_checks(request_text, project_fields)
            if plan is not None:
                return self._project_parallel_result(
                    user, source, document, project_target, project_fields, plan, request_text, knowledge_context, progress,
                )
        selector_tables = self._doc_table_context(shortlist, categories)
        if project_target is not None:
            selector_tables = (f"本需求为集市层项目维度，主表固定为 {project_target['table_name']}。"
                               "其他表仅在有独立的关联需求和真实文档依据时作为关联表。\n" + selector_tables)
        hints = field_profiles(shortlist, fields_by_table, request_text)
        if hints:
            selector_tables += "\\n相关字段与字典线索（仍需核对口径，不是已确认事实）：\\n" + hints
        select_prompt = self._render(self._prompt_text("select_table"), {
            "request_text": str(payload.get("request_text") or ""),
            "source_name": str(source["name"]),
            "tables": selector_tables,
            "categories": json.dumps(
                [{"code": item["code"], "name": item["name"]} for item in categories], ensure_ascii=False,
            ),
        })
        selection = self._complete_json(knowledge_prefix + select_prompt + "\n" + SELECT_OUTPUT_CONTRACT,
                                        str(payload.get("model_id") or ""), stage="select_table")
        selection_issues = merge(issues(selection, "uncertainties", stage="select_table"), request_reviews(request_text))
        selection_unsupported = issues(selection, "unsupported_requirements", stage="select_table")
        context = {
            "source_id": source_id, "dialect": str(source.get("dialect") or ""),
            "doc_version": int(document["version_no"]), "doc_sha256": str(document["content_sha256"]),
        }
        if knowledge_context:
            context["knowledge_context"] = knowledge_context
        target = selection.get("target") if isinstance(selection.get("target"), dict) else {}
        selection_state = str(selection.get("result_type") or selection.get("status") or "").strip().lower()
        clarification_requested = selection_state in {"clarification", "needs_clarification"}
        if project_target is not None and not selection_unsupported:
            target = {"table": project_target["table_name"]}
            clarification_requested = False
        fallback_tables: list[dict[str, Any]] = []
        if (clarification_requested or not (target.get("table") or selection.get("table"))) and not selection_unsupported:
            fallback_tables = self._clarification_fallback(selection, tables, request_text)
        forced_fallback = bool(fallback_tables) and not selection_unsupported
        if forced_fallback:
            # 已有 >=2 个当前授权文档的真实候选对象：用第一个做种子继续一次生成，不泛化补需求。
            target = {"table": fallback_tables[0]["table_name"]}
            clarification_requested = False
        if clarification_requested or (not forced_fallback and not (target.get("table") or selection.get("table"))
                                       and (selection_issues or selection_unsupported)):
            # 选表未唯一命中或明确澄清：只保留真实已完成的选表结论，不调用第二次生成，也不虚报后续步骤。
            self._emit_progress(
                progress, "semantics", "needs_confirmation", "选表阶段需要人工澄清目标业务对象",
            )
            return clarification_candidate(selection_issues, selection_unsupported, **context)
        raw_table = str(target.get("table") or selection.get("table") or "").strip().strip("`\"'")
        raw_table = raw_table.rsplit(".", 1)[-1].strip() if "." in raw_table else raw_table
        table = next((item for item in shortlist if str(item["table_name"]).lower() == raw_table.lower()), None)
        if table is None:
            table = next((item for item in shortlist if str(item.get("table_name_cn") or "") == raw_table), None)
        if table is None:
            raise failure("MODEL_RESPONSE_INVALID", "select_table")
        table_name = str(table["table_name"])
        if int(table["id"]) not in fields_by_table:
            fields_by_table[int(table["id"])] = self.storage.doc_fields(int(table["id"]))
        related_target = selection.get("related_target") or {}
        if not isinstance(related_target, dict):
            raise failure("MODEL_RESPONSE_INVALID", "select_table")
        related_table = None
        related_fields = []
        related_name = str(related_target.get("table") or "").strip().strip("`\\\"'").rsplit(".", 1)[-1]
        if related_name and not (project_target is not None and related_name.lower() == table_name.lower()):
            related_table = next((item for item in shortlist if str(item["table_name"]).lower() == related_name.lower()), None)
            if related_table is None or related_table["id"] == table["id"]:
                raise failure("MODEL_RESPONSE_INVALID", "select_table")
            related_fields = fields_by_table.get(int(related_table["id"]), [])
            if not related_fields:
                raise failure("MODEL_RESPONSE_INVALID", "select_table")
        category_scope = self._doc_category_scope(table, categories)
        category_pool = [item for item in categories if item["code"] in category_scope] if category_scope is not None else categories
        category = self._doc_category(category_pool, str(selection.get("report_category") or ""))
        category_question = None
        if category_scope is not None and category is None and len(category_pool) == 1:
            category = category_pool[0]
        elif category_scope is not None and category is None and category_pool:
            category_question = {"id": "report_category", "text": "这条人行校验归属哪个报送类型？",
                                 "options": [{"value": item["code"], "label": item["name"]} for item in category_pool]}
        selection_notices = []
        if category is None:
            if selection.get("report_category") and category_scope is None:
                raise failure("MODEL_RESPONSE_INVALID", "select_table")
            category = {"code": "", "name": "未分类"}
            selection_notices = [item for item in selection_issues if re.search(r"报送.*分类|报送类型|无法.*分类", item)]
            selection_issues = [item for item in selection_issues if item not in selection_notices]

        general_reviews = ([item for item in request_reviews(request_text) if item.startswith("需求包含一般")]
                           if re.search(r"一般|通常|原则上", request_text) and not re.search(r"例外|除外|除.+外", request_text) else [])
        selection_issues = [item for item in selection_issues if item not in general_reviews]
        if general_reviews:
            selection_notices.append("“一般”保留合理例外，命中记录应先人工核实，不直接认定为错误。")
        scope_text = str(table.get("scope") or "").strip()
        scope_confirmed = ("存续" in str(table.get("table_name_cn") or "")
                           or scope_text in {"存续", "存续项目", "仅存续项目", "存续信托项目", "仅含存续项目"})
        # 合同级对象即使描述含“存续”也不得冒充项目范围。
        scope_confirmed = scope_confirmed and grain_label(table) != "合同级"
        scope_confirmed = scope_confirmed and not re.search(r"(?:非|不含)存续|清算|终止|全部|全量", str(table.get("table_name_cn") or "") + scope_text)
        if scope_confirmed:
            selection_issues = [item for item in selection_issues if item not in request_reviews("存续")]
        fields = fields_by_table.get(int(table["id"]), [])
        if not fields:
            raise AppError("VALIDATION_ERROR")
        # 目标与关联对象已真实校验；此处只陈述已完成的文档定位，不提前展示判断条件。
        self._emit_progress(
            progress, "semantics", "completed", "已完成初步业务对象匹配，具体条件待规则草稿确认",
        )
        self._emit_progress(progress, "metadata", "running", "正在读取文档字段结构")
        self._emit_progress(
            progress, "metadata", "completed", "已完成文档字段结构读取",
            table_name=table_name, field_count=len(fields),
            related_table_name=(str(related_table["table_name"]) if related_table is not None else None),
        )
        field_context, fields_truncated = self._field_context(fields, request_text)
        related_truncated = False
        if related_table is not None:
            related_context, related_truncated = self._field_context(related_fields, request_text)
            field_context = "主表(base)：\\n" + field_context + "\\n关联表(related)：" + str(related_table["table_name"]) + "\\n" + related_context
        generate_prompt = self._render(self._prompt_text("generate_rule"), {
            "request_text": str(payload.get("request_text") or ""),
            "table": f"{table_name}|{table.get('table_name_cn') or ''}",
            "fields": field_context,
        })
        # A bounded fact pack for optional suggestions in this SAME model call.
        # These tables are reference material, not permission to change the main
        # target/join. Existing-rule literals/SQL are not sent to the model.
        suggestion_tables = []
        for item in [table, related_table, *shortlist]:
            if item is not None and item["id"] not in {entry["id"] for entry in suggestion_tables}:
                suggestion_tables.append(item)
            if len(suggestion_tables) >= 3:
                break
        suggestion_facts = []
        for item in suggestion_tables:
            brief, omitted = self._field_context(fields_by_table.get(int(item["id"]), []), request_text, limit=8)
            suggestion_facts.append({
                "table_name": item["table_name"], "table_name_cn": str(item.get("table_name_cn") or "")[:120],
                "dimension": str(item.get("dimension") or "")[:120], "period": str(item.get("period") or "")[:120],
                "scope": str(item.get("scope") or "")[:240], "fields": brief, "fields_truncated": omitted,
            })
        existing_summaries = []
        for item in existing:
            prior = item.get("definition") or {}
            if str(prior.get("source_id") or "") != source_id:
                continue
            expression = prior.get("expression") or {}
            if not isinstance(expression, dict):
                expression = {}
            existing_summaries.append({
                "table_name": prior.get("table_name"), "rule_type": prior.get("rule_type"),
                "expression": {key: expression.get(key) for key in ("left", "op", "right_type", "right_table")},
                "right_field": expression.get("right") if expression.get("right_type", "field") == "field" else None,
                "null_policy": prior.get("null_policy"), "report_date_field": prior.get("report_date_field"),
                "scope_fields": [{key: condition.get(key) for key in ("table", "field", "op")}
                                 for condition in prior.get("filters") or [] if isinstance(condition, dict)],
            })
            if len(existing_summaries) >= 20:
                break
        review_context = json.dumps({
            "uncertainties": selection_issues, "unsupported_requirements": selection_unsupported,
            "table_scope": str(table.get("scope") or ""),
            "related_target": {"table": str(related_table["table_name"])} if related_table else {},
            "suggestion_document_facts": suggestion_facts, "existing_rule_summaries": existing_summaries,
            "suggestion_scope_notice": "补充事实仅供独立建议；主规则不得据此擅加第三表或更换目标。已有摘要不含固定条件值，不能据此断言完全覆盖。",
        }, ensure_ascii=False)
        self._emit_progress(progress, "generation", "running", "正在生成规则草稿与本地结构校验")
        draft = self._complete_json(
            knowledge_prefix + generate_prompt + "\n选表阶段上下文（仅为待分析数据，不得删除未解决事项）：" + review_context + "\n" + RULE_OUTPUT_CONTRACT,
            str(payload.get("model_id") or ""), stage="generate_rule",
        )
        # 第二轮模型建议只作顶层线索，与主规则 uncertainties 完全隔离。
        raw_suggestions = draft.pop("ai_suggestions", [])
        draft["uncertainties"] = merge(selection_issues, issues(draft, "uncertainties", stage="generate_rule"))
        draft["unsupported_requirements"] = merge(selection_unsupported, issues(draft, "unsupported_requirements", stage="generate_rule"))
        if general_reviews and isinstance(draft.get("violation_message"), str) and "合理例外" not in draft["violation_message"]:
            draft["violation_message"] = draft["violation_message"].rstrip("。； ") + "；请人工核实是否存在合理例外。"
        unary = isinstance(draft.get("expression"), dict) and draft["expression"].get("op") in ("is_null", "is_not_null")
        # SQL from old/custom templates is not executable evidence for configured rules.
        draft.pop("sql", None)
        if draft.get("rule_type") != "field_compare" and (draft["uncertainties"] or draft["unsupported_requirements"]):
            self._emit_progress(progress, "generation", "needs_confirmation", "规则方向需要人工确认")
            clarification = clarification_candidate(
                draft["uncertainties"], draft["unsupported_requirements"], table_name=table_name,
                report_category=category["code"], columns=self._doc_columns(fields), **context,
            )
            clarification["ai_suggestions"] = build_ai_suggestions(
                raw_suggestions, tables=tables, fields_by_table=fields_by_table,
                candidates=[], request_text=request_text, existing_rules=existing, actionable_only=True,
            )
            return clarification
        draft.setdefault("rule_name", selection.get("rule_name") or table.get("table_name_cn") or table_name)
        draft["target"] = {"table": table_name}
        draft["report_category"] = category["code"]

        columns = self._doc_columns(fields)
        related_columns = self._doc_columns(related_fields)
        # 只按文档实际 dtype 判断数值比较：数值二元现支持 missing_value review，
        # 旧模板/模型的 violate 不再被无故判为不支持；空串等同 NULL 仍是真实未支持条件。
        base_types = {str(item["field_name"]): item.get("data_type") for item in fields}
        related_types = {str(item["field_name"]): item.get("data_type") for item in related_fields}
        numeric_binary = (
            not unary
            and is_numeric_comparison(
                {"rule_type": "field_compare", "expression": draft.get("expression") or {}},
                base_types, related_types or None,
            )
        )
        if not unary and draft.get("null_policy") == "violate" and not numeric_binary:
            draft["unsupported_requirements"] = merge(draft["unsupported_requirements"], [
                "当前字段比较尚不能表达“空值也违规”要求，请调整需求或使用一元非空检查。",
            ])
        if not unary and draft.get("null_policy") == "empty_string_as_null":
            draft["unsupported_requirements"] = merge(draft["unsupported_requirements"], [
                "当前字段比较尚不能表达“空串等同 NULL”要求，请调整需求或使用适合的规则。",
            ])
        if draft.get("join") is not None:
            if (not isinstance(draft["join"], dict) or related_table is None
                    or draft["join"].get("table_name") != related_table["table_name"]):
                raise failure("MODEL_RESPONSE_INVALID", "generate_rule")
        elif isinstance(draft.get("expression"), dict) and draft["expression"].get("right_table") == "related":
            raise failure("MODEL_RESPONSE_INVALID", "generate_rule")
        refined = refine_candidate(
            draft, columns=columns, dialect=str(source.get("dialect") or ""), existing=existing,
            related_columns=related_columns, source_id=source_id, table_name=table_name,
        )
        ground_candidate_query(refined, draft, fields, related_fields, request_text, scope_confirmed=scope_confirmed)
        if len(tables) > len(shortlist):
            refined["uncertainties"].append(
                f"数据源文档表数量 {len(tables)} 超过单次选表上限 {len(shortlist)}，已按需求相关性筛选 {len(shortlist)} 张候选表，请人工核对目标表。"
            )
        if fields_truncated:
            refined["uncertainties"].append(
                f"目标表字段数量 {len(fields)} 超过字段上下文上限 {_FIELD_CONTEXT_LIMIT}，候选仅基于按相关性筛选的 {_FIELD_CONTEXT_LIMIT} 个字段，请人工核对。"
            )
        if refined["uncertainties"]:
            refined["can_enable"] = False
        refined.update({
            "table_name": table_name,
            "report_category": category["code"],
            "report_category_name": category["name"],
            "source_id": source_id,
            "dialect": str(source.get("dialect") or ""),
            "columns": columns,
            "related_columns": related_columns,
            "generation_mode": "ai",
            "mapping_version": f"doc-v{int(document['version_no'])}-{str(document['content_sha256'])[:12]}",
            "doc_version": int(document["version_no"]),
            "doc_sha256": str(document["content_sha256"]),
        })
        # In AI output op is the violation predicate; samples must not silently override its equality.
        implied_equality = ("reject_equal" if refined["expression"]["op"] in ("eq", "lte", "gte")
                            and refined["expression"].get("right_type") != "value" else "allow_equal")
        if (refined["expression"].get("right_type") != "value"
                and refined.get("equality_policy") not in ("unresolved", implied_equality)):
            refined["uncertainties"].append("模型对相等情况的判断与比较条件不一致，请明确边界要求后重新分析。")
            refined["can_enable"] = False
        refined["equality_policy"] = implied_equality
        primary_keys = [item["field_name"] for item in fields if item.get("is_pk") == "Y"]
        refined["business_key"] = primary_keys[0] if len(primary_keys) == 1 else ""
        refined["scope_description"] = "存续项目" if scope_confirmed else str(table.get("table_name_cn") or "所选项目数据")
        if knowledge_context:
            refined["knowledge_context"] = knowledge_context
            reuse_label = "（复用）" if reused else ""
            selection_notices.append(f"业务知识 v{knowledge_context['revision']}{reuse_label}："
                                     + "、".join(knowledge_context["topics"]))
        refined["notices"] = selection_notices
        refined["preview"] = None
        refined.setdefault("questions", [])
        if category_question:
            refined["questions"].append(category_question)
        # 项目身份按当前授权文档真实证据解析/重核，不靠模型 flag。
        (
            project_context, _project_columns, context_questions,
            context_uncertainties, context_required,
        ) = self._resolve_project_context(refined, table, fields, tables, fields_by_table)
        if project_context is not None:
            refined["project_context"] = project_context
        else:
            refined.pop("project_context", None)
        if context_questions:
            refined["questions"] = list(refined.get("questions") or []) + context_questions
        if context_uncertainties:
            refined["uncertainties"] = merge(
                list(refined.get("uncertainties") or []), context_uncertainties,
            )
            refined["uncertainty_resolutions"] = [""] * len(refined["uncertainties"])
        if project_context is None and context_required:
            refined["preview_error"] = (
                "当前授权文档无法确定真实项目身份，需人工补充后再预览；不能只出合同键。"
            )
        if not refined["business_key"]:
            identifiers = [item for item in columns if re.search(r"编号|编码|代码|标识", str(item.get("comment") or ""))
                           or re.search(r"(^id$|_id$|_code$)", item["column_name"], re.I)]
            refined["questions"].append({"id": "business_key", "text": "用哪个编号定位需要核实的记录？",
                "options": [{"value": item["column_name"], "label": item.get("comment") or item["column_name"]}
                            for item in (identifiers or columns)[:20]]})
        date_field, date_choices = resolve_report_date(
            columns, str(refined.get("report_date_field") or ""),
        )
        refined["report_date_field"] = date_field
        if not date_field:
            if date_choices:
                refined["questions"].append({"id": "report_date_field", "text": "按哪个日期检查这批记录？",
                    "options": [{"value": item["column_name"], "label": f"{item.get('comment') or '日期字段'}（{item['column_name']}）",
                                 "description": "请选择代表记录所属业务日期的字段，不是项目发生日期或采集时间。"}
                                for item in date_choices]})
            else:
                refined["preview_error"] = "文档未提供可按期筛选的日期字段，请补充文档中的业务日期；不能编造 report_date 或以采集时间替代。"
        # 独立单候选已确定期间日期时，消除模型伪“未指定业务日期”追问；范围/截止/跨期等真未决保留。
        if refined.get("uncertainties"):
            cleaned = resolve_uncertainty_clauses(
                list(refined["uncertainties"]), has_candidates=False,
                has_period=bool(refined.get("report_date_field")),
            )
            if cleaned != list(refined["uncertainties"]):
                refined["uncertainties"] = cleaned
                refined["uncertainty_resolutions"] = [""] * len(cleaned)
        if refined["questions"] or not refined["report_date_field"]:
            refined["can_enable"] = False
        if (refined["business_key"] and refined["report_date_field"]
                and not refined["questions"] and not refined.get("preview_error")):
            definition = {**refined, "name": refined["rule_name"], "description": request_text, "generation_mode": "ai"}
            try:
                refined["preview"] = self.preview_candidate(user, definition)
            except AppError as exc:
                if exc.code != "VALIDATION_ERROR":
                    raise
                refined["preview_error"] = "还不能生成 SQL，请补充准确的字段口径，或检查文档是否含校验日期。"
        # 已明确集市层项目粒度时，不再将合同/账户等同义指标作为主表替代方案。
        if project_target is None:
            peer_tables = [item for item in tables if self._doc_category_scope(item, categories) == category_scope]
            refined = self._attach_candidate_options(
                user=user, source=source, tables=peer_tables, fields_by_table=fields_by_table,
                table=table, refined=refined, request_text=request_text,
            )
        # 通用 AI 补充建议：只来自文档事实与当前候选，且只挂顶层，不进主定义/hash。
        flattened_candidates = [refined] + [
            option["candidate"] for option in refined.get("candidate_options", [])
        ]
        refined["ai_suggestions"] = build_ai_suggestions(
            raw_suggestions, tables=tables, fields_by_table=fields_by_table,
            candidates=flattened_candidates, request_text=request_text,
            existing_rules=existing, actionable_only=True,
        )
        needs_confirmation = (
            bool(refined.get("questions")) or bool(refined.get("uncertainties"))
            or bool(refined.get("unsupported_requirements")) or refined.get("status") == "needs_clarification"
            or refined.get("can_enable") is False or bool(refined.get("preview_error"))
        )
        self._emit_progress(
            progress,
            "generation",
            "needs_confirmation" if needs_confirmation else "completed",
            "规则草稿仍需人工确认口径" if needs_confirmation else "已生成规则草稿建议",
        )
        self.storage.audit(
            rule_id=None, task_id=None, action_code="ai_parse", operator_user_id=str(user["id"]),
            detail={"error_code": refined.get("error_code") or "", "doc_version": int(document["version_no"])},
        )
        return refined

    def run_tests(self, user: dict[str, Any], rule_id: int, version_no: int, cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        self._require_owner(user, rule_id)
        version = self.storage.get_version(rule_id, version_no)
        definition = version["definition"]
        if is_new_spec(definition):
            # A failed re-test must not leave an earlier all-passed receipt usable for enablement.
            self.storage.invalidate_cases(rule_id, version_no)
            base_columns = self._definition_columns(definition)
            related_columns = None
            if definition.get("join"):
                related_columns = list(self.describe_source_table(str(definition["source_id"]), str(definition["join"]["table_name"])).get("columns") or [])
            elif (
                isinstance(definition.get("project_context"), dict)
                and definition["project_context"].get("mode") == "lookup"
            ):
                related_columns = list(self.describe_source_table(
                    str(definition["source_id"]), str(definition["project_context"]["table_name"]),
                ).get("columns") or [])
            try:
                validate_spec_against_columns(definition, base_columns, related_columns)
            except AppError as error:
                if error.code == "VALIDATION_ERROR":
                    raise AppError("MAPPING_DRIFT") from error
                raise
            preview = self.preview_candidate(user, {"definition": definition})
            if (preview["content_sha256"] != version["content_sha256"]
                    or preview["sql_preview"] != version["sql_text"]):
                # A new projection/null policy must be saved as a new version;
                # never test a changed definition under an earlier receipt hash.
                raise AppError("CONFLICT_VERSION")
            result = run_preview_cases(preview, cases)
            self.storage.replace_cases(rule_id, version_no, result["cases"])
            return {**result, "persisted": True, "version_no": version_no, "content_sha256": version["content_sha256"]}
        if cases is None:
            # 默认用例按真实表结构字段类型动态合成；数据源不可达时不得用写死样本冒充测试。
            columns = self._definition_columns(definition)
            selected = default_field_compare_cases(definition, columns)
        else:
            selected = cases
        stored = []
        failed = 0
        for case in selected:
            actual = evaluate_case(definition, case["row"])
            status = "passed" if actual == int(case["expected_count"]) else "failed"
            if status == "failed":
                failed += 1
            stored.append({**case, "actual_count": actual, "status": status})
        self.storage.replace_cases(rule_id, version_no, stored)
        return {"failed_count": failed, "passed_count": len(stored) - failed, "not_run_count": 0, "cases": stored}

    def _definition_columns(self, definition: dict[str, Any]) -> list[dict[str, Any]]:
        described = self.describe_source_table(
            str(definition.get("source_id") or ""), str(definition.get("table_name") or ""),
        )
        return list(described.get("columns") or [])

    def confirm_rule(self, user: dict[str, Any], rule_id: int, version_no: int, expected_hash: str) -> dict[str, Any]:
        rule = self._require_owner(user, rule_id)
        version = self.storage.get_version(rule_id, version_no)
        definition = version["definition"]
        if (definition.get("null_policy") == "unresolved" or definition.get("equality_policy") == "unresolved"
                or not review_ready(definition) or not query_ready(definition)):
            raise AppError("VALIDATION_ERROR")
        if (version["content_sha256"] != expected_hash
                or int(self.storage.latest_version(rule_id)["id"]) != int(version["id"])):
            raise AppError("CONFLICT_VERSION")
        if is_new_spec(definition):
            preview = self.preview_candidate(user, {"definition": definition})
            if (preview["content_sha256"] != version["content_sha256"]
                    or preview["sql_preview"] != version["sql_text"]):
                raise AppError("CONFLICT_VERSION")
        cases = self.storage.list_cases(rule_id, version_no)
        failed = sum(1 for case in cases if case["status"] == "failed")
        if not cases or any(case["status"] != "passed" for case in cases):
            raise AppError("VALIDATION_ERROR")
        passed = len(cases) - failed
        history = history_event(
            "confirm", user, version_no=version_no, content_sha256=str(version["content_sha256"]),
            changes=[], before_status=str(rule["status"]), after_status="enabled",
            summary=(
                f"确认启用版本 {version_no}；测试通过 {passed}、失败 {failed}、未运行 0；"
                f"哈希 {version['content_sha256']}"
            ),
            details={
                "test_summary": {"passed_count": passed, "failed_count": failed, "not_run_count": 0},
            },
        )
        self.storage.set_status(rule_id, "enabled", int(version["id"]), history=history)
        self.storage.add_confirmation(
            rule_id=rule_id, version_no=version_no, version_id=int(version["id"]),
            content_sha256=version["content_sha256"], confirmer_user_id=str(user["id"]),
            passed_count=len(cases) - failed, failed_count=failed, not_run_count=0,
        )
        updated = self.storage.get_rule(rule_id)
        updated["current_version_id"] = int(version["id"])
        return updated

    def preview_batch(self, user: dict[str, Any], rule_ids: list[int]) -> dict[str, Any]:
        rules = [self.storage.get_rule(rule_id) for rule_id in rule_ids]
        enabled = [rule for rule in rules if rule["status"] == "enabled" and self._visible(user, rule)]
        return {"count": len(enabled), "rule_ids": [int(rule["id"]) for rule in enabled]}

    def start_task(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        rule_ids = [int(item) for item in payload.get("rule_ids") or []]
        skipped = []
        selected = []
        for rule_id in rule_ids:
            rule = self.storage.get_rule(rule_id)
            if not self._visible(user, rule):
                self._deny(user, rule_id)
            if rule["status"] != "enabled" or not rule.get("current_version_id"):
                skipped.append({"rule_id": rule_id, "reason": "规则未启用"})
                continue
            version = self.storage.get_version_by_id(int(rule["current_version_id"]))
            selected.append({
                "rule_id": rule_id,
                "version_id": int(version["id"]),
                "version_no": int(version["version_no"]),
                "content_sha256": version["content_sha256"],
                "sql_summary": (version["sql_text"] or "")[:180],
            })
        if not selected and skipped:
            raise AppError("VALIDATION_ERROR")
        period = _report_period(payload.get("report_period"))
        task = self.storage.create_task(
            creator_user_id=str(user["id"]),
            source_id=str(payload.get("source_id") or ""),
            report_period=period,
            params={**dict(payload), "report_period": period},
            rules=selected,
        )
        response = dict(task)
        response["status"] = "queued"
        response["skipped"] = skipped
        if self.inline:
            self._run_task(int(task["id"]))
        else:
            thread = threading.Thread(target=self._run_task, args=(int(task["id"]),), daemon=True)
            self._threads.append(thread)
            thread.start()
        return response

    def cancel_task(self, user: dict[str, Any], task_id: int) -> dict[str, Any]:
        task = self._require_task_owner(user, task_id)
        for item in self.storage.task_rules(task_id):
            if item["status"] in {"queued", "running"}:
                self.storage.update_task_rule(int(item["id"]), status="CANCELLED")
        self.storage.update_task(task_id, status="cancelled")
        return self.storage.get_task(task_id)

    def retry_failed(self, user: dict[str, Any], task_id: int) -> dict[str, Any]:
        self._require_task_owner(user, task_id)
        for item in self.storage.task_rules(task_id):
            if item["status"] in {"ERROR", "TIMEOUT", "CANCELLED"}:
                self.storage.update_task_rule(int(item["id"]), status="queued")
                self._execute_task_rule(item)
        return self._refresh_task_status(task_id)

    def export_issues(self, user: dict[str, Any], task_id: int, file_type: str) -> dict[str, Any]:
        task = self.storage.get_task(task_id)
        if str(task["creator_user_id"]) != str(user["id"]):
            self.storage.audit(rule_id=0, task_id=task_id, action_code="access_denied", operator_user_id=str(user["id"]))
            raise AppError("FORBIDDEN")
        issues: list[dict[str, Any]] = []
        page = 1
        total = 0
        while page <= 50:
            batch = self.storage.list_issues(task_id, page=page, page_size=200)
            total = int(batch["total"])
            issues.extend(batch["items"])
            if page * 200 >= total:
                break
            page += 1
        content = issues_xlsx(task, issues) if file_type == "xlsx" else issues_csv(task, issues)
        return {"truncated": bool(task["truncated"]) or total > len(issues), "content": content, "issues": issues}

    def export_rule_pack(self, user: dict[str, Any], rule_ids: list[int]) -> bytes:
        packed = []
        for rule_id in rule_ids:
            rule = self._require_owner(user, rule_id)
            version = self.storage.latest_version(rule_id)
            packed.append({"name": rule["name"], "definition": version["definition"], "sql_text": version["sql_text"]})
        return rule_pack(packed)

    def import_rule_pack(self, user: dict[str, Any], payload: bytes) -> list[dict[str, Any]]:
        document = json.loads(payload.decode("utf-8"))
        prepared = []
        for item in document.get("rules") or []:
            definition = dict(item.get("definition") or {})
            sql_text = str(item.get("sql") or "")
            if sql_text:
                guard_sql(str(definition.get("dialect") or "mysql"), sql_text, set(definition.get("identifiers") or []))
            definition["name"] = item.get("name") or definition.get("name") or "导入规则"
            definition["sql"] = sql_text
            prepared.append(definition)
        created = [self.save_draft(user, definition) for definition in prepared]
        for rule in created:
            if rule["status"] != "draft" or rule.get("current_version_id"):
                raise AppError("VALIDATION_ERROR")
        return created

    def list_models(self) -> list[dict[str, Any]]:
        if self.model is None or not hasattr(self.model, "list_enabled"):
            return []
        return [
            {"id": item.id, "name": item.name, "model_name": item.model_name, "is_default": item.is_default}
            for item in self.model.list_enabled()
        ]

    def list_task_issues(self, user: dict[str, Any], task_id: int, query: dict[str, Any] | None = None) -> dict[str, Any]:
        task = self._require_task_owner(user, task_id)
        query = query or {}
        page = self.storage.list_issues(
            task_id,
            page=int(query.get("page") or 1),
            page_size=int(query.get("page_size") or 50),
        )
        page["truncated"] = bool(task["truncated"])
        page["report_period"] = task.get("report_period") or ""
        page["task_id"] = int(task["id"])
        return page

    def join(self) -> None:
        for thread in self._threads:
            thread.join(timeout=3)
        # 模块停止/服务回收时协作取消未结束的临时分析，并等待线程退出。
        self.analyses.close(timeout=3)

    def _run_task(self, task_id: int) -> None:
        if self.gate is not None:
            self.gate.wait(2)
        for item in self.storage.task_rules(task_id):
            current = next(row for row in self.storage.task_rules(task_id) if row["id"] == item["id"])
            if current["status"] != "queued":
                continue
            self._execute_task_rule(current)
        self._refresh_task_status(task_id)

    def _project_context_required(self, version: dict[str, Any]) -> bool:
        """按当前授权文档与保存定义判断是否项目口径；旧项目规则缺 ctx 时拒执行。"""
        definition = version["definition"]
        known_required = project_semantics_required(definition, None) or bool(definition.get("project_context"))
        document = self.storage.active_document()
        if document is None:
            return known_required
        source = next(
            (item for item in self.list_selectable_sources()
             if str(item["id"]) == str(definition.get("source_id") or "")),
            None,
        )
        if source is None:
            return known_required
        tables = self.storage.doc_tables(int(document["id"]), data_source_name=str(source["name"]))
        table = next((item for item in tables if item["table_name"] == definition.get("table_name")), None)
        if table is None:
            return known_required
        return known_required or self._project_required(definition, table, self.storage.doc_fields(int(table["id"])))

    def _execute_task_rule(self, item: dict[str, Any]) -> None:
        version = self.storage.get_version_by_id(int(item["version_id"]))
        run: RuleRun | None = None
        if self.metadata is None:
            result_status, error_code, count, truncated = "ERROR", "SOURCE_UNAVAILABLE", 0, False
        else:
            try:
                task = self.storage.get_task(int(item["task_id"]))
                run = execute_version(
                    version,
                    {"max_rows": 200, "report_date": task.get("report_period") or ""},
                    self.metadata,
                    require_project_context=self._project_context_required(version),
                )
                result_status, error_code, count, truncated = (
                    run.status, run.error_code, run.violation_count, run.truncated,
                )
            except AppError as exc:
                result_status, error_code, count, truncated = "ERROR", exc.code, 0, False
            except Exception:
                # 数据源返回异常形态（如 rows 缺失）必须显式报错，不能伪 PASS。
                result_status, error_code, count, truncated = "ERROR", "SOURCE_UNAVAILABLE", 0, False
        issues: list[dict[str, Any]] = []
        for row in (getattr(run, "rows", None) or ()):
            issue = {
                "business_key": row.get("business_key"),
                "project_code": row.get("project_code"),
                "project_name": row.get("project_name"),
                "project_name_status": row.get("project_name_status") or "not_required",
                "message": row.get("violation_message") or str(version["definition"].get("violation_message") or ""),
            }
            if row.get("issue_kind"):
                issue["issue_kind"] = row["issue_kind"]
            issues.append(issue)
        self.storage.record_rule_result(
            int(item["id"]), status=result_status, error_code=error_code,
            violation_count=count, truncated=bool(truncated), issues=issues,
        )

    def _refresh_task_status(self, task_id: int) -> dict[str, Any]:
        rows = self.storage.task_rules(task_id)
        statuses = {row["status"] for row in rows}
        if statuses <= {"PASS", "VIOLATION"}:
            status = "completed"
        elif statuses & {"ERROR", "TIMEOUT", "CANCELLED"} and statuses & {"PASS", "VIOLATION"}:
            status = "partial_failed"
        elif statuses == {"CANCELLED"}:
            status = "cancelled"
        elif statuses <= {"ERROR", "TIMEOUT"}:
            status = "failed"
        else:
            status = "running"
        self.storage.update_task(task_id, status=status)
        return self.storage.get_task(task_id)

    def _compile_if_possible(self, definition: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        if definition.get("rule_type") == "custom_sql":
            return str(definition.get("sql") or ""), dict(definition.get("params") or {})
        try:
            return compile_rule({"definition": definition})
        except (AppError, KeyError):
            # Invalid constants must not silently become drafts with empty SQL.
            if (definition.get("expression") or {}).get("right_type") == "value":
                raise AppError("VALIDATION_ERROR")
            return "", {}

    def _require_owner(self, user: dict[str, Any], rule_id: int) -> dict[str, Any]:
        rule = self.storage.get_rule(rule_id)
        if str(rule["creator_user_id"]) != str(user["id"]):
            self._deny(user, rule_id)
        return rule

    def _require_task_owner(self, user: dict[str, Any], task_id: int) -> dict[str, Any]:
        task = self.storage.get_task(task_id)
        if str(task["creator_user_id"]) != str(user["id"]):
            self.storage.audit(rule_id=0, task_id=task_id, action_code="access_denied", operator_user_id=str(user["id"]))
            raise AppError("FORBIDDEN")
        return task

    def _visible(self, user: dict[str, Any], rule: dict[str, Any]) -> bool:
        return self._is_admin(user) or str(rule["creator_user_id"]) == str(user["id"])

    def _deny(self, user: dict[str, Any], rule_id: int) -> None:
        self.storage.audit(rule_id=rule_id, task_id=None, action_code="access_denied", operator_user_id=str(user["id"]))
        raise AppError("FORBIDDEN")

    def _is_admin(self, user: dict[str, Any]) -> bool:
        return str(user.get("role") or "") == "admin"


def _report_period(value: Any) -> str:
    text = str(value or "").strip()
    parts = text.split("-")
    if len(parts) == 3 and all(part.isdigit() for part in parts) and len(parts[0]) == 4 and len(parts[1]) == 2 and len(parts[2]) == 2:
        return text
    raise AppError("VALIDATION_ERROR")
