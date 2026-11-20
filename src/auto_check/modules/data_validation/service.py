"""数据校验业务编排。创建人才能改、测、确认和导出自己的规则。"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
import threading
import uuid
from collections import Counter, defaultdict
from datetime import date
from typing import Any, Callable

from auto_check.app.module_system.contracts import ModuleTaskExecutor

from .semantic_generation import SemanticAnalysis, reviewed_semantic_choices
from .analysis_jobs import AnalysisRegistry
from .analysis_reuse import MEMORY_CONTRACT, analysis_baseline, apply_owner_selections, memory_choice, owner_selections
from .analysis_memory import digest, safe_example
from .preview_memory import selected_baseline
from .ai_service import model_expression, model_judgment, pending_judgment_reviews, refine_candidate
from .ai_suggestions import MAX_SUGGESTIONS, build_ai_suggestions
from .candidate_choices import (
    TARGET_SELECT, check_without_category_prefix, confirm_option_category, counterpart_fields, difference_lines, document_category, field_label,
    grain_label, option_id, other_category_expression, recommended_index, requested_category_codes, resolve_uncertainty_clauses, semantic_core,
    target_ambiguity_indices, document_display,
)
from .business_display import business_key_option, business_key_question
from .candidate_preview import candidate_definition, compile_checked_definition, preview_definition, run_preview_cases
from .compiler import compile_rule
from .result_aliases import build_result_aliases
from .conditional_reviews import (
    BoundReviewEvidence, bind_selector_choices, category_numeric_check, category_scope_only, conditional_null_check, metric_choices,
    plain_null_check, selector_field_choices,
)
from .contracts import AppError, PBC_REPORT_CATEGORIES, PBC_SHARED_CATEGORY, PBC_SHARED_CATEGORY_NAME, content_hash
from .executor import RuleRun, execute_version
from .execution_jobs import ExecutionJobs
from .exports import IssueExport, rule_pack
from .history import definition_changes, history_event
from .sql_guard import guard_sql
from .sql_display import saved_sql_display
from .doc_parser import DEFAULT_SOURCE_RULES, is_pbc_report_sheet, parse_workbook
from .dictionary_reviews import apply_dictionary_filter_answers, dictionary_question_text, documented_dictionary_entries
from .prompt_defaults import DEFAULT_PROMPTS, REQUIRED_PLACEHOLDERS, STAGE_LABELS, RULE_OUTPUT_CONTRACT, SELECT_OUTPUT_CONTRACT
from .generation_policy import (
    EXPLICIT_EXCLUSION, GENERAL_QUALIFIER, REVIEW_FIELDS, ai_review_pending, clarification_candidate,
    issues, merge, remaining_qualifier_reviews, request_reviews, review_ready,
    shortlist_tables, string_list, validate_review,
)
from .model_calls import SYNC_GENERATION_TIMEOUT_SECONDS, complete_text, failure
from .parallel_checks import project_parallel_checks
from .project_context import (
    infer_project_context, project_code_fields, project_name_fields, project_semantics_required,
)
from .project_driver import bind_project_driver, resolve_project_driver
from .semantic_grounding import align_project_driver_semantics
from .query_grounding import (
    documented_aggregate_join,
    check_request_coverage, dictionary_options, documented_scope_comparison, field_profiles, ground_candidate_query,
    metric_scope_binding, project_mart_target, resolve_report_date, scope_dimension_issue,
)
from .query_spec import (
    apply_numeric_null_policy, infer_numeric_null_handling, is_condition_group, is_new_spec, is_numeric_comparison,
    is_unary, query_ready, query_unresolved_reasons,
    validate_query_spec, validate_spec_against_columns,
)
from .storage import RuleStorage
from . import execution_queries, task_results
from .test_runner import default_field_compare_cases, evaluate_case
from .trust_knowledge import TrustKnowledge

_PAGE_SIZES = {20, 50, 100}
# 临时：模块创建规则只开放这两个监管数据源；配置中出现同名数据源后自动生效。
_SELECTABLE_SOURCE_NAMES = ("监管报送集市", "监管报表")
_TABLE_SHORTLIST_LIMIT = 80
_FIELD_CONTEXT_LIMIT = 60
_MISSING_COMPARISON_FIELDS = re.compile(
    r"(?:需求(?:要求|描述)[：:\s]?.{0,160}?[，,]\s*(?:但|而)?)?"
    r"(?:当前|选定的|所选)?(?:目标表|主表|活动文档)(?:中|里)?(?:缺少|缺失|未找到)"
    r"(?P<fields>[^，,；;。]{1,120}字段)"
    r"(?:[，,]\s*(?:因此)?无法(?:构造|生成|形成)(?:字段比较表达式|校验表达式|校验规则))?"
)


def _classification_only(issue: str) -> bool:
    return bool(re.search(r"(?:报送|报告)(?:分类|归属|类型)|分类归属", issue)
                and not re.search(r"字段|筛选|日期|关联|汇总|币种|单位|期限|粒度", issue))


def _document_covers_active_scope(table: dict[str, Any]) -> bool:
    title = str(table.get("table_name_cn") or "")
    scope = str(table.get("scope") or "").strip()
    return (("存续" in title or scope in {"存续", "存续项目", "仅存续项目", "存续信托项目", "仅含存续项目"})
            and grain_label(table) != "合同级"
            and not re.search(r"(?:非|不含)存续|清算|终止|全部|全量", title + scope))


def _documented_business_key(fields: list[dict[str, Any]]) -> str:
    keys = [field["field_name"] for field in fields if field.get("is_pk") == "Y"]
    if len(keys) > 1:
        report_date, _ = resolve_report_date(fields)
        if report_date in keys:
            keys.remove(report_date)
    if len(keys) > 1:
        # 项目编号已有独立投影，其余主键组成项仅在唯一时能作为明细定位字段。
        project_keys = [field["field_name"] for field in project_code_fields(fields)]
        if len(project_keys) == 1 and project_keys[0] in keys:
            keys.remove(project_keys[0])
    return keys[0] if len(keys) == 1 else ""


def _bare_metric_choices(request: str, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    term = request.strip()
    return metric_choices(term, fields) if re.fullmatch(r"\w{1,80}", term) else []


def _check_requirement(term: str) -> dict[str, Any]:
    question = f"要对“{term}”做哪项检查？"
    return {"id": "check_requirement", "text": question, "uncertainty": question,
            "options": [{"value": "not_empty", "label": "不得为空"}]}


class DataValidationService:
    def __init__(
        self, storage: RuleStorage, metadata: Any | None = None, model: Any | None = None,
        report_navigation: Any | None = None, *, background_executor: ModuleTaskExecutor | None = None,
    ) -> None:
        self.storage = storage
        self.metadata = metadata
        self.model = model
        self.report_navigation = report_navigation
        self._executions = ExecutionJobs(storage, background_executor)
        self.inline = True
        self.gate: threading.Event | None = None
        self._threads: list[threading.Thread] = []
        # 临时分析只存在内存，模块停止时统一协作取消并回收线程。
        self.analyses = AnalysisRegistry(worker=self._execute_analysis)
        self.knowledge = TrustKnowledge(storage, _SELECTABLE_SOURCE_NAMES)

    @staticmethod
    def _review_context(definition: dict[str, Any]) -> dict[str, Any]:
        context = {key: definition.get(key) for key in (
            "rule_type", "source_id", "table_name", "business_key", "report_date_field", "expression", "filters",
            "join", "project_context", "project_driver", "null_policy", "equality_policy", "description", "report_category",
            "mapping_version",
        )}
        if definition.get("rule_type") == "field_compare":
            # 老草稿省略的 base / field / 空筛选和显式默认值代表同一业务口径。
            spec = validate_query_spec(definition)
            expression = dict(definition.get("expression") or {})
            if not is_condition_group(definition):
                expression.setdefault("right_type", "field")
                expression["right_table"] = spec["right_table"]
            # 所有筛选以 AND 相连，IN 取值与筛选条件的顺序均不改变范围。
            filters = {(item["table"], item["field"], item["op"], item["confirmed"],
                        frozenset(item["value"]) if isinstance(item["value"], list) else item["value"])
                       for item in spec["filters"]}
            context.update(expression=expression, filters=filters, join=spec["join"],
                           project_context=spec["project_context"], project_driver=spec["project_driver"])
        return context

    def save_draft(self, user: dict[str, Any], payload: dict[str, Any], rule_id: int | None = None) -> dict[str, Any]:
        definition = dict(payload)
        definition.pop("result_aliases", None)
        expected_rule = definition.pop("expected_rule", None)
        reviewed = set(string_list(definition.pop("reviewed_uncertainties", [])))
        if rule_id is not None:
            rule = self._require_owner(user, rule_id)
            previous = self.storage.latest_version(rule_id)
            from .edit_context import check_edit_context, restore_saved_semantics
            check_edit_context(rule, previous, expected_rule)
            saved = previous["definition"]
            if saved.get("analysis_protocol") == 2:
                restore_saved_semantics(definition, saved)
            if saved.get("generation_mode") == "ai" or rule.get("generation_mode") == "ai":
                definition["generation_mode"] = "ai"
            else:
                definition.setdefault("generation_mode", "manual")
            for key in REVIEW_FIELDS:
                if key not in definition and key in saved:
                    definition[key] = saved[key]
            if definition["generation_mode"] == "ai" and saved.get("uncertainties"):
                # 编辑表单可以补充口径；删掉已有问题本身不能充当对该项的确认。
                validate_review(definition)
                definition["uncertainties"] = merge(definition.get("uncertainties") or [], saved["uncertainties"])
        else:
            definition.setdefault("generation_mode", "manual")
        identifiers = None
        document_bound = (is_new_spec(definition) or definition.get("include_result_fields") is True
                          or definition.get("analysis_protocol") == 2 or "semantic_intent" in definition)
        if document_bound:
            validated = self.preview_candidate(user, {"definition": definition}, validate_only=True)
            definition = validated["definition"]
            identifiers = validated["documented_identifiers"]
        elif definition.get("rule_type") != "custom_sql":
            source = next((item for item in self.list_sources() if str(item["id"]) == str(definition.get("source_id") or "")), None)
            if source:
                definition["dialect"] = str(source["dialect"])
        if rule_id is not None:
            questions = definition.get("uncertainties") or []
            old_questions = saved.get("uncertainties") or []
            if questions != old_questions or (questions and self._review_context(definition) != self._review_context(saved)):
                old_answers = dict(zip(old_questions, saved.get("uncertainty_resolutions") or ()))
                answers = definition.get("uncertainty_resolutions") or []
                explicitly_reviewed = (
                    definition.get("generation_mode") == "ai" and "uncertainty_resolutions" in payload
                    and len(answers) == len(questions) and all(
                        answer and (question in reviewed or answer != old_answers.get(question))
                        for question, answer in zip(questions, answers)
                    )
                )
                if not explicitly_reviewed:
                    definition["uncertainty_resolutions"] = []
        validate_review(definition)
        if document_bound and definition.get("generation_mode") == "ai" and ai_review_pending(definition):
            raise AppError("VALIDATION_ERROR")
        sql_text, _params = self._compile_if_possible(definition, identifiers)
        digest = content_hash(definition, str(definition.get("dialect") or ""), str(definition.get("mapping_version") or ""), sql_text)
        if rule_id is None:
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
        version_no = int(previous["version_no"]) + 1
        changes = definition_changes(previous["definition"], definition)
        history = history_event(
            "update", user, version_no=version_no, content_sha256=digest, changes=changes,
            before_status=str(rule["status"]), after_status=str(rule["status"]),
            summary=f"编辑保存版本 {version_no}，变更 {len(changes)} 项，哈希 {digest}",
        )
        version = self.storage.add_version(
            rule_id, definition, sql_text, str(definition.get("mapping_version") or ""), digest,
            history=history, expected_rule=expected_rule,
        )
        version["status"] = "draft"
        version["current_version_id"] = rule["current_version_id"]
        return version

    # ---- 多候选批量草稿：单事务、幂等回执、跨进程文档行锁 -------------

    def batch_save_candidates(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        raw_definitions = payload.get("definitions") if isinstance(payload, dict) else None
        # One field question can expand to 20 rules alongside the original and supplemental options.
        if not isinstance(raw_definitions, list) or not 1 <= len(raw_definitions) <= 26:
            raise AppError("VALIDATION_ERROR")
        try:
            request_key = str(uuid.UUID(str(payload.get("request_key") or "")))
        except (ValueError, AttributeError, TypeError) as exc:
            raise AppError("VALIDATION_ERROR") from exc
        prepared = []
        validated_batch = []
        for item in raw_definitions:
            if not isinstance(item, dict):
                raise AppError("VALIDATION_ERROR")
            definition = dict(item)
            definition.setdefault("generation_mode", "manual")
            if str(definition.get("rule_type") or "") != "field_compare":
                raise AppError("VALIDATION_ERROR")
            validated_batch.append(self.preview_candidate(
                user, {"definition": definition}, validate_only=True, require_ai_review=True,
            ))

        # 所有方案均已绑定到文档且完成确认，才开始编译本批第一条 SQL。
        fingerprint = [item["definition"] for item in validated_batch]
        for validated in validated_batch:
            definition = validated["definition"]
            sql_text, _params = self._compile_if_possible(definition, validated["documented_identifiers"])
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
        if len(prepared) > 3 and len({item["content_sha256"] for item in prepared}) != len(prepared):
            raise AppError("VALIDATION_ERROR")
        payload_hash = hashlib.sha256(json.dumps(
            fingerprint, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        result = self.storage.save_batch(
            creator_user_id=str(user["id"]), prepared=prepared,
            request_key=request_key, payload_hash=payload_hash,
        )
        views = []
        for rule_id in result["rule_ids"]:
            view = self._require_owner(user, int(rule_id))
            version = self.storage.latest_version(int(rule_id))
            view["version_id"] = int(version["id"])
            view["version_no"] = int(version["version_no"])
            view["mapping_version"] = str(version["mapping_version"])
            view["content_sha256"] = str(version["content_sha256"])
            view["sql_text"] = str(version["sql_text"])
            view.update(saved_sql_display(version))
            views.append(view)
        return {"rules": views, "count": len(views), "reused": bool(result.get("reused"))}

    def list_rules(self, user: dict[str, Any], query: dict[str, Any]) -> dict[str, Any]:
        page_size = int(query.get("page_size") or 50)
        if page_size not in _PAGE_SIZES:
            page_size = 50
        page = max(int(query.get("page") or 1), 1)
        result = self.storage.list_rules(
            creator_user_id=None if self._is_admin(user) else str(user["id"]),
            keyword=str(query.get("keyword") or ""),
            status=str(query.get("status") or ""),
            report_category=str(query.get("report_category") or ""),
            source_id=str(query.get("source_id") or ""),
            rule_type=str(query.get("rule_type") or ""),
            page=page,
            page_size=page_size,
        )
        self._add_table_labels(result["items"])
        return result

    def _add_table_labels(self, items: list[dict[str, Any]], sources: list[dict] | None = None) -> None:
        for item in items:
            item["table_name_cn"] = ""
        if not items:
            return
        tables = self.storage.active_table_labels({item["table_name"] for item in items})
        if not tables:
            return
        try:
            if sources is None:
                sources = self.list_sources()
        except Exception:
            logging.getLogger(__name__).warning("规则列表无法读取数据源目录，使用物理表名")
            return
        counts = Counter(source["name"] for source in sources)
        source_names = {str(source["id"]): source["name"] for source in sources if counts[source["name"]] == 1}
        categories = self.list_report_categories()
        by_table = defaultdict(list)
        for table in tables:
            by_table[(table["data_source_name"], table["table_name"])].append(table)
        for item in items:
            matches = by_table.get((source_names.get(item["source_id"]), item["table_name"]), [])
            category = item["report_category"]
            if category:
                scoped = self._category_tables(matches, {category}, categories)
                if scoped:
                    matches = scoped
                elif any(self._doc_category_scope(table, categories) for table in matches):
                    matches = []
            labels = {table["table_name_cn"].strip() for table in matches}
            if len(labels) == 1:
                item["table_name_cn"] = labels.pop()

    def rule_stats(self, user: dict[str, Any]) -> dict[str, Any]:
        scope = None if self._is_admin(user) else str(user["id"])
        base = self.storage.stats(scope)
        grouped = {item["report_category"]: item for item in self.storage.category_stats(scope)}
        keys = ("total", "enabled", "draft", "disabled")
        pbc_counts = [grouped.pop(code, {}) for code in (*PBC_REPORT_CATEGORIES, PBC_SHARED_CATEGORY)]
        grouped[PBC_SHARED_CATEGORY] = {key: sum(int(counts.get(key) or 0) for counts in pbc_counts) for key in keys}
        categories = []
        for process in self.list_report_categories():
            counts = grouped.pop(process["code"], {})
            categories.append({
                "code": process["code"], "name": process["name"],
                **{key: int(counts.get(key) or 0) for key in keys},
            })
        unclassified = {"total": 0, "enabled": 0, "draft": 0, "disabled": 0}
        for counts in grouped.values():
            for key in unclassified:
                unclassified[key] += int(counts.get(key) or 0)
        return {**base, "categories": categories, "unclassified": unclassified}

    def list_report_categories(self) -> list[dict[str, str]]:
        categories = []
        pbc_present = False
        for item in self._report_processes():
            if item["code"] in PBC_REPORT_CATEGORIES:
                if not pbc_present:
                    categories.append({"code": PBC_SHARED_CATEGORY, "name": PBC_SHARED_CATEGORY_NAME})
                    pbc_present = True
            else:
                categories.append(item)
        return categories

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
        rule = self._require_visible_rule(user, rule_id)
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
            **saved_sql_display(version),
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

    def _complete_json(self, prompt: str, model_id: str, *, stage: str = "generate_rule",
                       cancel_event: threading.Event | None = None) -> dict[str, Any]:
        raw = complete_text(
            self.model, str(model_id or ""), prompt,
            stage=stage, timeout=SYNC_GENERATION_TIMEOUT_SECONDS if cancel_event is None else None,
            cancel_event=cancel_event,
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

    def _project_driver_tables(
        self, table: dict[str, Any], tables: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Project lineage must stay within the base table's source and report category."""
        categories = self.list_report_categories()
        category = document_category(self._doc_category_scope(table, categories), categories)
        if category:
            return self._category_tables(tables, {category["code"]}, categories)
        return tables

    def _bind_new_project_driver(
        self,
        candidate: dict[str, Any],
        table: dict[str, Any],
        fields: list[dict[str, Any]],
        tables: list[dict[str, Any]],
        fields_by_table: dict[int, list[dict[str, Any]]],
    ) -> tuple[list[dict[str, Any]], list[str], bool] | None:
        """Bind only a newly generated/re-generated candidate, never a stored legacy version."""
        # The current workbench uses semantic protocol 2.  Keep the retired
        # protocol's definitions reproducible; an explicit marker opts it in.
        if candidate.get("analysis_protocol") != 2 and "project_driver" not in candidate:
            return None
        required = self._project_required(candidate, table, fields)
        binding = bind_project_driver(
            candidate, table, fields, self._project_driver_tables(table, tables), fields_by_table,
            required=required,
        )
        if not binding["involved"]:
            return None
        candidate.clear()
        candidate.update(binding["definition"])
        unsupported = merge(candidate.get("unsupported_requirements") or [], binding["unsupported_requirements"])
        candidate["unsupported_requirements"] = unsupported
        issues = list(binding["uncertainties"])
        if candidate.get("project_driver"):
            align_project_driver_semantics(candidate, binding["field_mapping"])
            if not issues and not unsupported:
                resolved = {"join.relationship_confirmed", "join.unmatched_policy", "join.report_date_field", "project_context.confirmed"}
                candidate["questions"] = [q for q in candidate.get("questions") or [] if q.get("id") not in resolved]
            candidate["project_columns"] = self._doc_columns(binding["project_fields"])
            if candidate["project_driver"]["table_role"] == "related":
                candidate["related_columns"] = self._doc_columns(binding["project_fields"])
                candidate.update(document_display(table, binding["project_table"]))
        else:
            # A failed new binding must never silently execute as the old detail query.
            candidate.pop("project_driver", None)
            candidate["preview"] = None
            candidate["can_enable"] = False
            candidate["status"] = "needs_clarification"
            candidate["preview_error"] = (issues or unsupported or ["项目驱动无法由当前文档唯一证明。"])[0]
        return [], issues, True

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
        if "project_driver" in definition:
            resolved = resolve_project_driver(
                definition, table, fields, self._project_driver_tables(table, tables), fields_by_table,
            )
            return (
                resolved["context"], self._doc_columns(resolved["project_fields"]), [], [], True,
            )
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
            return PBC_REPORT_CATEGORIES
        prefix, separator, _ = sheet.partition("_")
        if separator:
            def normalize(text: str) -> str:
                return re.sub(r"\s+", "", text).casefold()

            names = frozenset(item["code"] for item in categories if normalize(item["name"]) == normalize(prefix))
            if names:
                return names
            if normalize(prefix) in {"人行大集中报送", "资管产品模板、逐笔"}:
                return frozenset({PBC_SHARED_CATEGORY})
        return PBC_REPORT_CATEGORIES if is_pbc_report_sheet(sheet) else None

    def _doc_table_context(self, tables: list[dict[str, Any]], categories: list[dict[str, str]]) -> str:
        lines = []
        for table in tables:
            desc = str(table.get("source_desc") or "").strip()
            if len(desc) > 120:
                desc = desc[:120] + "…"
            scope = str(table.get("scope") or "")[:160]
            category_scope = self._doc_category_scope(table, categories)
            names = [item["name"] for item in categories if category_scope is not None and item["code"] in category_scope]
            if category_scope and category_scope <= PBC_REPORT_CATEGORIES:
                names = [PBC_SHARED_CATEGORY_NAME]
            family = f"|文档报送分类:{' / '.join(names)}" if names else ""
            lines.append(f"{table['table_name']}|{table.get('table_name_cn') or ''}|{desc}|范围:{scope}{family}")
        return "\n".join(lines)

    def _category_tables(self, tables: list[dict], codes: set[str], categories: list[dict]) -> list[dict]:
        codes = {PBC_SHARED_CATEGORY if code in PBC_REPORT_CATEGORIES else code for code in codes}
        return [item for item in tables if (category := document_category(self._doc_category_scope(item, categories), categories))
                and category["code"] in codes]

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
            period = _report_period(period).isoformat()
        category = task_results.category_code((query or {}).get("report_category"))
        tasks = self.storage.list_tasks(None if self._is_admin(user) else str(user["id"]), period, category)
        with self.storage.database.connect() as connection:
            return execution_queries.summaries(connection, tasks, category)

    def _task_snapshots(self, ids: list[int]) -> dict[int, list[dict]]:
        groups: dict[int, list[dict]] = defaultdict(list)
        for item in self.storage.task_rule_snapshots(ids):
            groups[item.pop("task_id")].append(task_results.rule_view(item))
        return groups

    def task_detail(self, user: dict[str, Any], task_id: int, query: dict) -> dict:
        return execution_queries.detail(self.storage, self._require_task_owner(user, task_id), query)

    def task_progress(self, user: dict, query: dict) -> list[dict]:
        return execution_queries.progress(self.storage, str(user["id"]), query)

    def copy_rule(self, user: dict[str, Any], rule_id: int) -> dict[str, Any]:
        rule = self._require_visible_rule(user, rule_id)
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
            copy_from=rule_id,
        )
        created["version_no"] = 1
        created["current_version_id"] = None
        return created

    def disable_rule(self, user: dict[str, Any], rule_id: int, *, expected_rule: dict | None = None) -> dict[str, Any]:
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
        self.storage.set_status(rule_id, "disabled", history=history, expected_rule=expected_rule)
        return self.storage.get_rule(rule_id)

    def delete_rule(self, user: dict[str, Any], rule_id: int) -> dict[str, Any]:
        self._require_owner(user, rule_id, allow_deleted=True)
        return self.storage.delete_rule(rule_id, user)

    def test_model(self, user: dict[str, Any], model_id: str) -> dict[str, Any]:
        """测试所选模型是否真正可用：发起一次最小对话请求，不保存任何规则。"""
        if self.model is None:
            raise AppError("MODEL_UNAVAILABLE")
        complete_text(
            self.model, str(model_id or ""), "可用性测试：请仅回复 ok",
            stage="test_model", timeout=10,
        )
        return {"available": True, "model_id": str(model_id or "")}

    def preview_candidate(self, user: dict[str, Any], payload: dict[str, Any], *,
                          preserve_result_fields: bool = False, return_questions: bool = False,
                          validate_only: bool = False, require_ai_review: bool = False) -> dict[str, Any]:
        """Preview an unsaved definition against the active document, never client SQL/columns."""
        if "definition" in payload and not isinstance(payload["definition"], dict):
            raise AppError("VALIDATION_ERROR")
        definition = dict(payload.get("definition", payload))
        if return_questions and "review_only" in payload and type(payload["review_only"]) is not bool:
            raise AppError("VALIDATION_ERROR")
        review_only = return_questions and payload.get("review_only") is True
        if return_questions:
            definition["generation_mode"] = "ai"
        definition.setdefault("generation_mode", "ai")
        ai_candidate = require_ai_review or definition["generation_mode"] == "ai"
        semantic = definition.get("analysis_protocol") == 2
        if semantic != ("semantic_intent" in definition) or (semantic and not isinstance(definition["semantic_intent"], dict)):
            raise AppError("VALIDATION_ERROR")
        if semantic:
            ai_candidate = True
            definition["generation_mode"] = "ai"
        source_id = str(definition.get("source_id") or "")
        analysis_input = None
        previous = None
        if (return_questions and all(payload.get(k) for k in ("analysis_id", "analysis_context", "analysis_request_text"))
                and "model_id" in payload):
            previous = self.analyses.completed_result(user, str(payload["analysis_id"]))
            analysis_input = {"source_id": source_id, "model_id": payload["model_id"],
                              "request_text": payload["analysis_request_text"],
                              "reasoning_enabled": payload.get("reasoning_enabled", (previous or {}).get("reasoning_enabled", False)),
                              "clarification_answers": payload.get("clarification_answers", (previous or {}).get("clarification_answers", []))}
            if semantic or (previous and previous.get("analysis_protocol") == 2):
                analysis_input["analysis_protocol"] = 2
            previous_request = (previous or {}).get("analysis_request_text", (previous or {}).get("description"))
            if previous and (previous.get("analysis_context") != payload["analysis_context"]
                             or previous.get("source_id") != source_id
                             or (previous_request and previous_request.strip() != str(analysis_input["request_text"]).strip())):
                raise AppError("ANALYSIS_CONTEXT_CHANGED")
            if previous and previous.get("analysis_protocol") == 2:
                candidates = [entry["candidate"] for entry in previous.get("candidate_options") or []] or [previous]
                candidates.extend(item["definition"] for item in previous.get("ai_suggestions") or [] if item.get("definition"))
                if not semantic or not any(
                    candidate.get("table_name") == definition.get("table_name")
                    and candidate.get("semantic_intent") == definition["semantic_intent"]
                    and (not candidate.get("report_category") or candidate["report_category"] == definition.get("report_category"))
                    for candidate in candidates
                ):
                    raise AppError("ANALYSIS_CONTEXT_CHANGED")
            self._check_preview_context(user, analysis_input, payload["analysis_context"])
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
        categories = self.list_report_categories()
        matches = [item for item in source_tables if item["table_name"] == definition.get("table_name")]
        category = definition.get("report_category")
        if category is not None and not isinstance(category, str):
            raise AppError("VALIDATION_ERROR")
        specified = requested_category_codes(str(definition.get("description") or ""), categories) if ai_candidate and not semantic else set()
        has_document_category = any(document_category(self._doc_category_scope(item, categories), categories) for item in matches)
        if has_document_category and (category or specified):
            if category and specified and (PBC_SHARED_CATEGORY if category in PBC_REPORT_CATEGORIES else category) not in specified:
                raise AppError("VALIDATION_ERROR")
            matches = self._category_tables(matches, {category} if category else specified, categories)
        if len(matches) != 1:
            if len(matches) > 1 and not category and return_questions:
                available = {cat["code"]: cat["name"] for item in matches if (cat := document_category(self._doc_category_scope(item, categories), categories))}
                if len(available) == len(matches):
                    question = {"id": "report_category", "text": "按哪个报送分类的文档口径核查？",
                                "options": [{"value": code, "label": name} for code, name in available.items()]}
                    return {"status": "needs_confirmation", "persisted": False, **({"ready": False} if review_only else {}),
                            "definition": candidate_definition(definition),
                            "questions": [question], "uncertainties": list(definition.get("uncertainties") or []), "columns": []}
            raise AppError("VALIDATION_ERROR")
        table = matches[0]
        if not category and specified:
            selected_category = document_category(self._doc_category_scope(table, categories), categories)
            if selected_category:
                definition["report_category"] = category = selected_category["code"]
        fields_by_table = self._source_document_fields(source_tables)
        related_columns = None
        related_fields_raw = []
        related = None
        raw_join = definition.get("join")
        if raw_join is not None:
            if not isinstance(raw_join, dict):
                raise AppError("VALIDATION_ERROR")
            related_matches = [item for item in source_tables if item["table_name"] == raw_join.get("table_name")]
            if len(related_matches) > 1:
                related_matches = self._category_tables(related_matches, {category}, categories)
            if len(related_matches) != 1 or related_matches[0]["id"] == table["id"]:
                raise AppError("VALIDATION_ERROR")
            related = related_matches[0]
            related_fields_raw = fields_by_table.get(int(related["id"])) or []
            related_columns = self._doc_columns(related_fields_raw)
        fields = list(fields_by_table.get(int(table["id"])) or [])
        columns = self._doc_columns(fields)
        request_text = "" if semantic else check_without_category_prefix(str(definition.get("description") or "").strip(), categories)
        missing_check = ai_candidate and not semantic and bool(_bare_metric_choices(request_text, fields))
        if missing_check and not return_questions:
            raise AppError("VALIDATION_ERROR")
        context, project_columns, context_questions, context_uncertainties, required = self._resolve_project_context(
            definition, table, fields, source_tables, fields_by_table,
        )
        if semantic and required and "project_driver" not in definition and not preserve_result_fields:
            # Clearing a draft's questions cannot turn a failed new binding into
            # an old detail-driven query. Frozen stored versions remain reproducible.
            context = None
            context_questions = []
            context_uncertainties = merge(context_uncertainties, ["尚未核实项目主表及明细关联，请重新分析。"])
        context_pending = (context is None and required) or (ai_candidate and bool(context_questions or context_uncertainties))
        if context_pending and not return_questions:
            raise AppError("PROJECT_CONTEXT_REQUIRED")
        if context is not None:
            definition["project_context"] = context
        elif not context_pending:
            definition.pop("project_context", None)
        # Recheck numeric types and bind the selected policy; supplied evidence never replaces validation.
        if raw_join and raw_join.get("right_aggregate") == "sum":
            expected = documented_aggregate_join(table, fields, related, related_fields_raw)
            owner_day = resolve_report_date(fields)[0]
            if (not expected or raw_join.get("report_date_field") != expected["report_date_field"]
                    or definition.get("report_date_field") != owner_day):
                raise AppError("VALIDATION_ERROR")
            keys = raw_join.get("on")
            period_pair = {"left": owner_day, "right": expected["report_date_field"]}
            if isinstance(keys, list) and keys.count(period_pair) == 1:
                keys = [pair for pair in keys if pair != period_pair]
            if keys != expected["on"]:
                raise AppError("VALIDATION_ERROR")
        if semantic:
            intent = definition["semantic_intent"]
            if "expected_null_policy" in intent:
                policy = intent["expected_null_policy"]
                if policy not in ("unresolved", "skip", "violate", "empty_string_as_null", "review", "zero"):
                    raise AppError("VALIDATION_ERROR")
                definition["null_policy"] = policy
            elif (not preserve_result_fields and definition.get("null_policy") == "zero"
                  and isinstance(intent.get("expected_expression"), dict)
                  and intent["expected_expression"] != definition.get("expression")):
                # Older choices retained only the bound policy. Ask for a new decision if changing the
                # field removes the document basis for zero. Stored versions recheck their frozen inputs.
                unbound = {**definition, "null_policy": "unresolved"}
                before = {**unbound, "expression": intent["expected_expression"]}
                if (infer_numeric_null_handling(before, columns, related_columns)["null_policy"] == "zero"
                        and infer_numeric_null_handling(unbound, columns, related_columns)["null_policy"] != "zero"):
                    raise AppError("ANALYSIS_CONTEXT_CHANGED")
        definition = apply_numeric_null_policy(
            definition, columns, related_columns,
            request_text=(str(definition.get("description") or "")
                          if not semantic and definition.get("generation_mode") == "ai" and definition.get("null_policy") == "unresolved"
                          else ""),
        )
        definition.update({"source_id": source_id, "dialect": str(source.get("dialect") or ""), "mapping_version": mapping})

        def needs_confirmation(questions: list[dict[str, Any]], uncertainties: list[str]) -> dict[str, Any]:
            return {
                "status": "needs_confirmation", "persisted": False, **({"ready": False} if review_only else {}),
                "definition": candidate_definition(definition),
                "questions": questions, "uncertainties": uncertainties, "columns": columns,
                "related_columns": related_columns or [], "project_columns": project_columns or [],
                "project_table": (context or {}).get("table_name"),
            }

        if return_questions:
            validate_review(definition)
            if ai_candidate and not semantic and definition.get("uncertainties") and payload.get("pending_dictionary_questions"):
                apply_dictionary_filter_answers(definition, payload["pending_dictionary_questions"], table["table_name"], fields)
            if (ai_candidate and not semantic and definition.get("uncertainties") and not definition.get("questions")
                    and not raw_join and query_ready(definition)):
                dimension = str(table.get("dimension") or "")
                check = (category_numeric_check(request_text, fields, dictionary_options, dimension=dimension)
                         or conditional_null_check(request_text, fields, dictionary_options, dimension=dimension)
                         or plain_null_check(request_text, fields))
                if check and check.measures:
                    evidence = BoundReviewEvidence(check, fields, table["table_name"], str(table.get("scope") or ""))
                    evidence.apply_answers(definition)
            questions = definition.get("questions") or []
            if not isinstance(questions, list) or any(not isinstance(q, dict) or not isinstance(q.get("id"), str)
                                                       for q in questions):
                raise AppError("VALIDATION_ERROR")
            questions = list({q["id"]: q for q in [*questions, *context_questions]}.values())
            if missing_check and not any(q["id"] == "check_requirement" for q in questions):
                questions.insert(0, _check_requirement(request_text))
            if is_unary(definition):
                definition.setdefault("null_policy", "violate")
                definition.setdefault("equality_policy", "allow_equal")
            elif (definition.get("null_policy", "unresolved") == "unresolved"
                  and not any(q["id"] in {"null_policy", "expression.left", "expression.right"} for q in questions)):
                questions.append(self._null_policy_question())
            if context_pending or questions or ai_review_pending(definition):
                uncertainties = merge(definition.get("uncertainties") or [], context_uncertainties)
                if not (questions or uncertainties or definition.get("unsupported_requirements")):
                    uncertainties = query_unresolved_reasons(definition) or ["请补充校验口径后重新分析。"]
                return needs_confirmation(questions, uncertainties)
        if semantic:
            from .semantic_grounding import semantic_coverage_issue
            issue = semantic_coverage_issue(definition, definition["semantic_intent"], fields, related_fields_raw)
            if issue:
                if return_questions:
                    return needs_confirmation([], merge(definition.get("uncertainties") or [], [issue]))
                raise AppError("VALIDATION_ERROR")
        elif ai_candidate and definition.get("description"):
            query = validate_query_spec(definition)
            scope_issues = [scope_dimension_issue(request_text, query["filters"], table, fields, source_tables, fields_by_table)]
            if raw_join:
                scope_issues.append(scope_dimension_issue(request_text, query["filters"], related, related_fields_raw,
                                                         source_tables, fields_by_table, role="related"))
                binding = metric_scope_binding(request_text, table, fields, related, related_fields_raw)
                expected = (binding or {}).get("join")
                if expected and (any(query["join"][key] != expected[key] for key in ("on", "report_date_field"))
                                 or definition.get("report_date_field") != resolve_report_date(fields)[0]):
                    raise AppError("VALIDATION_ERROR")
            scope_issues.append(check_request_coverage({**definition, "description": request_text, "filters": query["filters"]}, fields, related_fields_raw,
                                                      scope_confirmed=_document_covers_active_scope(table),
                                                      dimension=str(table.get("dimension") or "")))
            if any(scope_issues):
                if return_questions:
                    return needs_confirmation([], merge(scope_issues))
                raise AppError("VALIDATION_ERROR")
        preview = preview_definition(
            definition, columns, related_columns, project_columns,
            preserve_result_fields=preserve_result_fields, validate_only=validate_only or review_only, require_ai_review=ai_candidate,
        )
        if context_questions:
            all_questions = [*(preview.get("questions") or []), *context_questions]
            preview["questions"] = list({question["id"]: question for question in all_questions}.values())
        if context_uncertainties:
            preview["uncertainties"] = merge(preview.get("uncertainties") or [], context_uncertainties)
        if review_only:
            if analysis_input:
                self._check_preview_context(user, analysis_input, payload["analysis_context"])
            return {"status": "ready", "ready": True, "persisted": False, **document_display(table, related), "definition": preview["definition"],
                    "questions": [], "uncertainties": []}
        if analysis_input and preview.get("sql_preview"):
            context = self._check_preview_context(user, analysis_input, payload["analysis_context"])
            if previous and previous.get("description") and not preview.get("questions"):
                baseline = selected_baseline(previous, preview["definition"], fields)
                if baseline:
                    self.storage.remember_analysis_memory(context, previous["description"], baseline)
        if return_questions:
            preview.update(document_display(table, related))
        return preview

    def _check_preview_context(self, user, analysis_input, expected):
        try:
            current = self._analysis_inputs(user, analysis_input)["context"]
        except AppError as exc:
            if exc.code in {"SOURCE_UNAVAILABLE", "VALIDATION_ERROR"}:
                raise AppError("ANALYSIS_CONTEXT_CHANGED") from exc
            raise
        if digest(current) != expected:
            raise AppError("ANALYSIS_CONTEXT_CHANGED")
        return current

    def test_candidate(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        definition = payload.get("definition", payload)
        if not isinstance(definition, dict):
            raise AppError("VALIDATION_ERROR")
        preview = self.preview_candidate(user, {**definition, "generation_mode": "ai"})
        expected_hash = payload.get("expected_hash")
        if expected_hash is not None and expected_hash != preview["content_sha256"]:
            raise AppError("CONFLICT_VERSION")
        return run_preview_cases(preview, payload.get("cases"))

    @staticmethod
    def _null_policy_question() -> dict[str, Any]:
        return {"id": "null_policy", "text": "比较字段缺值时，是否跳过该条记录？",
                "options": [{"value": "skip", "label": "仅比较两侧都有值的记录"}]}

    # ---- 临时分析任务：内存快照、owner 隔离、协作取消 -------------------

    def start_analysis(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        if self.model is None:
            raise AppError("MODEL_UNAVAILABLE")
        return self.analyses.start(user, payload, await_first_poll=payload.get("await_first_poll") is True)

    def get_analysis(self, user: dict[str, Any], analysis_id: str) -> dict[str, Any]:
        return self.analyses.get(user, analysis_id)

    def cancel_analysis(self, user: dict[str, Any], analysis_id: str) -> dict[str, Any]:
        return self.analyses.cancel(user, analysis_id)

    def _execute_analysis(
        self,
        user: dict[str, Any],
        payload: dict[str, Any],
        progress: Callable[[dict[str, Any]], None],
        cancel_event: threading.Event,
    ) -> dict[str, Any]:
        return self.parse_rule_request(user, payload, progress=progress, cancel_event=cancel_event)

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

    def _document_candidate_details(self, refined, table, fields, tables, fields_by_table, *, model_business_key=None):
        columns = refined["columns"]
        if model_business_key not in (None, "") and (not isinstance(model_business_key, str)
                or model_business_key not in {field["field_name"] for field in fields}):
            raise AppError("VALIDATION_ERROR")
        refined["business_key"] = model_business_key or _documented_business_key(fields)
        # 新生成先核实项目驱动；纯非项目规则才沿用原项目投影推断。
        resolution = self._bind_new_project_driver(refined, table, fields, tables, fields_by_table)
        if resolution is not None:
            context_questions, context_uncertainties, context_required = resolution
        else:
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
        if not refined.get("project_context") and context_required and context_uncertainties:
            refined["preview_error"] = context_uncertainties[0]
        if not refined["business_key"]:
            primary = [item for item in columns if item.get('is_pk') == 'Y']
            identifiers = primary or [item for item in columns if not item.get('dictionary') and (
                re.search(r"编号|编码|代码|标识", str(item.get("comment") or ""))
                or re.search(r"(^id$|_id$|_code$)", item["column_name"], re.I))]
            refined["questions"].append(business_key_question([
                business_key_option(item["column_name"], item.get("comment"))
                for item in (identifiers or columns)[:20]
            ]))
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
        return context_uncertainties

    def _materialize_candidate_option(
        self,
        *,
        other: dict[str, Any],
        other_fields: list[dict[str, Any]],
        left_match: dict[str, Any],
        right_match: dict[str, Any] | None,
        refined: dict[str, Any],
        request_text: str,
        option_number: int,
        match_reason: str,
        tables: list[dict[str, Any]],
        fields_by_table: dict[int, list[dict[str, Any]]],
        scope_binding: dict[str, Any] | None = None,
        scope_fields: list[dict[str, Any]] | None = None,
        bound_expression: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """按当前表重新绑定候选；各方案的问题收齐后再统一编译。"""
        alternative = copy.deepcopy(refined)
        alternative.pop("candidate_options", None)
        alternative.pop("comparison_suggestions", None)
        # 换表后旧对象的项目身份/建议一律作废，必须按替代对象真实文档重绑。
        alternative.pop("project_context", None)
        alternative.pop("project_driver", None)
        alternative.pop("project_columns", None)
        alternative.pop("project_table", None)
        alternative["preview"] = None
        alternative.pop("preview_error", None)
        if alternative.get("null_policy") == "zero":
            # The original table's derived zero policy is not a decision for another metric.
            alternative["null_policy"] = "unresolved"
        alternative.pop("null_handling", None)
        alternative.pop("null_evidence", None)
        alternative.pop("ai_suggestions", None)
        columns = self._doc_columns(other_fields)
        expression = copy.deepcopy(alternative.get("expression") or {})
        if bound_expression is not None:
            expression = copy.deepcopy(bound_expression)
        else:
            expression["left"] = left_match["field_name"]
        if bound_expression is None and str(expression.get("right_type") or "field") == "field" and right_match is not None:
            expression["right"] = right_match["field_name"]
            expression.pop("right_table", None)
        alternative["expression"] = expression
        alternative["table_name"] = str(other["table_name"])
        alternative["columns"] = columns
        alternative["related_columns"] = []
        alternative.pop("join", None)
        alternative["business_key"] = _documented_business_key(other_fields)
        chosen_date, date_options = resolve_report_date(columns)
        alternative["report_date_field"] = chosen_date
        kept_questions = [
            item for item in alternative.get("questions", [])
            if item.get("id") not in {"business_key", "report_date_field", "expression.left", "expression.right"}
            and not str(item.get("id") or "").startswith("project_context.")
        ]
        alternative["questions"] = kept_questions
        if not alternative["business_key"]:
            alternative["questions"].append(business_key_question([
                business_key_option(field["field_name"], field.get("field_cn"))
                for field in other_fields if field.get("is_pk") == "Y"
            ] or [
                business_key_option(col["column_name"], col.get("comment"))
                for col in columns[:20]
            ]))
        if not chosen_date:
            if date_options:
                alternative["questions"].append({
                    "id": "report_date_field", "text": "按哪个日期检查这批记录？",
                    "options": [{"value": col["column_name"], "label": col.get("comment") or col["column_name"]}
                                for col in date_options],
                })
            else:
                alternative["preview_error"] = "文档缺少可按期校验的业务日期，请补充文档。"
        alternative = apply_numeric_null_policy(alternative, columns, request_text=request_text)
        # 换表后绝不沿用旧对象派生口径：筛选/关联清零；数值常量与单位需重新确认。
        had_filters = bool(alternative.get("filters"))
        alternative["filters"] = []
        alternative.pop("join", None)
        extra_uncertainties: list[str] = []
        if scope_binding:
            alternative["filters"] = [scope_binding["filter"]]
            if scope_binding.get("question"):
                question = scope_binding["question"]
                alternative["questions"].append(question)
                extra_uncertainties.append(question["uncertainty"])
            if scope_binding.get("join"):
                alternative["join"] = scope_binding["join"]
                alternative["related_columns"] = self._doc_columns(scope_fields or [])
        elif had_filters:
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
        # 替代对象的项目驱动和身份独立重核，不沿用主表投影。
        resolution = self._bind_new_project_driver(alternative, other, other_fields, tables, fields_by_table)
        if resolution is not None:
            _context_questions, context_uncertainties, context_required = resolution
            context = alternative.get("project_context")
            context_questions = []
        else:
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
        alternative["description"] = request_text
        # 每个方案按当前真实对象/字段独立命名与提示，绝不沿用原对象的口径标题。
        option_field_label = str(left_match.get("field_cn") or left_match["field_name"])
        alternative["rule_name"] = f"{table_label}·{option_field_label}校验"
        alternative["violation_message"] = (
            f"{option_field_label}（{other['table_name']}）命中异常条件，请人工核实"
        )
        if context is None and context_required:
            alternative["preview_error"] = context_uncertainties[0] if context_uncertainties else ""
        alternative["can_enable"] = False
        alternative["_option_meta"] = {
            "document_table_id": other["id"],
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
        candidate["preview"] = None
        candidate["can_enable"] = False
        if candidate.get("preview_error") or candidate.get("sql_status") == "rejected" or ai_review_pending(candidate):
            return candidate
        definition = {
            **candidate,
            "name": candidate.get("rule_name") or candidate.get("table_name") or "未命名规则",
            "generation_mode": "ai",
        }
        try:
            preview = self.preview_candidate(user, definition)
        except AppError as exc:
            if exc.code != "VALIDATION_ERROR":
                raise
            candidate["preview_error"] = "还不能生成 SQL，请核对本方案的文档字段和业务口径。"
            return candidate
        return self._apply_candidate_preview(candidate, preview)

    @staticmethod
    def _apply_candidate_preview(candidate: dict[str, Any], preview: dict[str, Any]) -> dict[str, Any]:
        candidate.update({
            key: value for key, value in preview["definition"].items()
            if key in {
                "source_id", "dialect", "mapping_version", "report_category", "table_name",
                "business_key", "report_date_field", "expression", "violation_message",
                "null_policy", "null_handling", "null_evidence", "equality_policy", "filters", "join", "generation_mode",
                "project_context", "project_driver",
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
        base_context_uncertainties: list[str] | None = None,
        categories: list[dict] | None = None,
    ) -> dict[str, Any]:
        """按文档独立绑定不同报送口径，并保留既有同分类的候选方案。"""
        if refined.get("join") is not None or refined.get("status") == "needs_clarification":
            return refined
        expression = refined.get("expression") or {}
        grouped = bool(expression.get("conditions"))
        first_part = expression["conditions"][0] if grouped else expression
        categories = categories or []
        doc_categories = {item["id"]: document_category(self._doc_category_scope(item, categories), categories) for item in tables}
        base_category = doc_categories.get(table["id"])
        named_categories = requested_category_codes(request_text, categories)
        check_text = check_without_category_prefix(request_text, categories)
        explicit_table = any(re.search(r"(?<![a-zA-Z_0-9])" + re.escape(item["table_name"]) + r"(?![a-zA-Z_0-9])", request_text, re.I) for item in tables)
        right_type = str(expression.get("right_type") or "field")
        base_fields = fields_by_table.get(int(table["id"]), [])
        scoped = bool(refined.get("filters"))
        numeric = category_numeric_check(check_text, base_fields, dictionary_options, dimension=str(table.get("dimension") or "")) if scoped else None
        conditional = None if numeric else conditional_null_check(check_text, base_fields, dictionary_options,
                                             dimension=str(table.get("dimension") or ""))
        binding = None
        base_scope_question = None
        if conditional:
            if len(conditional.measures) != 1 or conditional.coverage_issue(refined):
                return refined
            base_scope_question = next((q for q in refined.get("questions", []) if q["id"] == "filters.0"), None)
            if not refined["filters"][0].get("confirmed") and not base_scope_question:
                return refined
        elif numeric:
            if numeric.coverage_issue(refined):
                return refined
            if not grouped:
                binding = documented_scope_comparison(check_text, base_fields)
        elif scoped:
            binding = documented_scope_comparison(request_text, base_fields)
            if (not binding or binding["entity"] != str(table.get("dimension") or "").strip()
                    or refined["filters"] != [binding["filter"]] or expression != binding["expression"]):
                return refined
        base_left = next((field for field in base_fields if field["field_name"] == first_part.get("left")), None)
        if base_left is None:
            return refined
        base_right = None
        if right_type == "field" and expression.get("right"):
            base_right = next((field for field in base_fields if field["field_name"] == expression.get("right")), None)
            if base_right is None:
                return refined

        alternative_seed = {
            **refined,
            "questions": [q for q in refined.get("questions", []) if q is not base_scope_question],
            "uncertainties": [
                issue for issue in refined.get("uncertainties", [])
                if issue not in (base_context_uncertainties or ())
                and not (base_scope_question and issue == base_scope_question.get("uncertainty"))
            ],
            "uncertainty_resolutions": [],
        }
        pool: list[dict[str, Any]] = []
        pending_locator: list[dict[str, Any]] = []
        cross_category_pool: list[dict[str, Any]] = []
        for other in tables:
            if int(other["id"]) == int(table["id"]):
                continue
            other_category = doc_categories[other["id"]]
            cross = other_category != base_category
            if not cross and (len(pool) >= 2 or grouped or (numeric and not binding)):
                continue
            other_fields = fields_by_table.get(int(other["id"]))
            if other_fields is None:
                other_fields = self.storage.doc_fields(int(other["id"]))
            if not other_fields:
                continue
            scope_binding = None
            bound_expression = None
            if cross:
                if (not base_category or not other_category or (explicit_table and other["table_name"] != table["table_name"])
                        or (named_categories and other_category["code"] not in named_categories)):
                    continue
                bound_expression = other_category_expression(expression, base_fields, other_fields, request_text)
                if not bound_expression:
                    continue
            if numeric and cross:
                check = category_numeric_check(check_text, other_fields, dictionary_options, dimension=str(other.get("dimension") or ""))
                if not check or len(check.scope.selections) != 1 or check.expression_issue(bound_expression):
                    continue
                scope_binding = {"filter": check.scope.selections[0], "term": check.term, "entity": check.scope.scope_text}
            if conditional:
                check = conditional_null_check(check_text, other_fields, dictionary_options,
                                              dimension=str(other.get("dimension") or ""))
                if not check or not check.selections or len(check.measures) != 1:
                    continue
                expression_on_table = {"op": "is_null", "left": check.measures[0]["field_name"]}
                question = check.scope_question(other_fields)
                selected = {**check.selections[0], "confirmed": len(check.selections) == 1}
                if check.coverage_issue({"filters": [selected], "expression": expression_on_table}):
                    continue
                scope_binding = {"expression": expression_on_table, "filter": selected, "question": question}
                left_matches = check.measures
            elif scoped and not (numeric and cross):
                scope_binding = metric_scope_binding(request_text, other, other_fields, table, base_fields)
                if not scope_binding:
                    continue
                left_matches = [item for item in other_fields if item["field_name"] == scope_binding["expression"]["left"]]
            elif bound_expression:
                first = bound_expression["conditions"][0] if grouped else bound_expression
                left_matches = [field for field in other_fields if field["field_name"] == first["left"]]
            else:
                left_matches = counterpart_fields(other_fields, base_left)
            if len(left_matches) != 1:
                continue
            left_match = left_matches[0]
            right_match = None
            if base_right is not None and not bound_expression:
                right_matches = counterpart_fields(other_fields, base_right)
                if len(right_matches) != 1:
                    continue
                right_match = right_matches[0]
            if conditional:
                match_reason = (f"本表字典提供「{check.scope_text}」的筛选取值，"
                                f"按「{field_label(left_match)}」逐行检查空值。")
            elif scope_binding:
                owner = table if scope_binding.get("join") else other
                match_reason = (f"本表字段说明对应“{scope_binding['term']}”；按"
                                f"{owner['table_name']}.{scope_binding['filter']['field']}筛选"
                                f"{scope_binding['entity']}，逐行检查本表指标。")
            else:
                core = semantic_core(field_label(base_left), field_label(left_match))
                match_reason = f"共同业务语义“{core}”；规模/余额等限定不同，需确认口径（{other['table_name']}）"
            alternative = self._materialize_candidate_option(
                other=other, other_fields=other_fields, left_match=left_match, right_match=right_match,
                refined=alternative_seed, request_text=request_text, option_number=len(pool) + len(pending_locator) + len(cross_category_pool) + 1,
                match_reason=match_reason, tables=tables, fields_by_table=fields_by_table,
                scope_binding=scope_binding, scope_fields=base_fields, bound_expression=bound_expression,
            )
            if cross:
                alternative.update(report_category=other_category["code"], report_category_name=other_category["name"])
                cross_category_pool.append(alternative)
            elif alternative["business_key"] and alternative["report_date_field"]:
                pool.append(alternative)
            elif len(pending_locator) < 3:
                pending_locator.append(alternative)
        pool.extend(pending_locator[:2 - len(pool)])
        pool.extend(cross_category_pool)
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
        base_copy["description"] = request_text
        entries = [{
            "meta": {
                "document_table_id": table["id"],
                "option_number": 0, "table_label": base_label, "grain": base_grain,
                "field_label": base_field_label,
                "match_reason": f"模型选表结果：{table['table_name']}",
            },
            "candidate": base_copy,
        }] + [
            {"meta": alternative.pop("_option_meta"), "candidate": alternative}
            for alternative in pool
        ]

        if named_categories:
            entries = [entry for entry in entries if entry["candidate"].get("report_category") in named_categories]
            if len(entries) == 1:
                return self._refresh_candidate_preview(user, entries[0]["candidate"])
            if not entries:
                return refined

        category_choice = len({entry["candidate"].get("report_category") for entry in entries}) > 1
        grains = [str(entry["meta"].get("grain") or "") for entry in entries]
        recommended = None if category_choice else recommended_index(grains, request_text)
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
            if conditional:
                # 选定目标表只解决对象问题，本表上尚未回答的字段口径继续参与确认。
                cleaned = merge(cleaned, [q["uncertainty"] for q in candidate.get("questions", []) if q.get("uncertainty")])
            if cleaned != original_uncertainties:
                candidate["uncertainties"] = cleaned
                candidate["uncertainty_resolutions"] = [""] * len(cleaned)
            if category_choice:
                owner = next(t for t in tables if t["id"] == entry["meta"]["document_table_id"])
                confirm_option_category(candidate, entry["meta"], doc_categories[owner["id"]], owner)

        refreshed: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for entry in entries:
            candidate = copy.deepcopy(entry["candidate"])
            candidate.pop("candidate_options", None)
            candidate.pop("comparison_suggestions", None)
            candidate.pop("ai_suggestions", None)
            refreshed.append((entry, self._refresh_candidate_preview(user, candidate)))
        primary = copy.deepcopy(refreshed[0][1])
        options = []
        for entry, candidate in refreshed:
            differences = difference_lines(
                str(entry["meta"].get("table_label") or ""), str(entry["meta"].get("grain") or ""),
                str(entry["meta"].get("field_label") or ""), "" if scoped else base_field_label,
            )
            if binding and candidate["table_name"] != table["table_name"]:
                differences.append(f"按本表记录逐行比较；不会汇总为{binding['entity']}合计。")
            options.append({
                "id": option_id(
                    str(source["id"]), str(candidate.get("table_name") or ""), str((candidate["expression"].get("conditions") or [candidate["expression"]])[0]["left"]),
                    request_text, str(candidate.get("mapping_version") or ""),
                    json.dumps([candidate.get("report_category"), candidate["expression"]], ensure_ascii=False, sort_keys=True),
                ),
                "label": f"{entry['meta'].get('table_label') or candidate.get('table_name')} · {entry['meta'].get('field_label') or base_field_label}",
                "recommended": bool(entry.get("recommended")),
                "match_reason": str(entry["meta"].get("match_reason") or "当前文档存在相关指标"),
                "grain": str(entry["meta"].get("grain") or ""),
                "table_label": str(entry["meta"].get("table_label") or ""),
                "field_label": str(entry["meta"].get("field_label") or ""),
                "differences": differences,
                "candidate": candidate,
            })
        if options:
            primary["candidate_options"] = options
            primary["comparison_suggestions"] = []
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
                  "null_policy": "unresolved", "equality_policy": "allow_equal", "parallel_check": True,
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
            common["preview_error"] = project_issues[0]
            common["uncertainties"] = merge(common["uncertainties"], project_issues)
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
        resolution = self._bind_new_project_driver(common, table, fields, [table], {int(table["id"]): fields})
        if resolution is not None:
            _driver_questions, driver_issues, _driver_required = resolution
            if driver_issues:
                common["uncertainties"] = merge(common["uncertainties"], driver_issues)
        options = []
        for item in plan["checks"]:
            term, field = item["term"], item["field"]
            candidate = copy.deepcopy(common)
            name = f"项目{term}检查"
            candidate.update(rule_name=name, name=name, violation_message=f"{term}不符合要求，需核实。",
                             expression={"left": field["field_name"] if field else "", "op": plan["op"],
                                         "right_type": "value", "right": plan["constant"]})
            candidate = apply_numeric_null_policy(candidate, columns, request_text=request_text)
            if not field:
                if item["options"]:
                    candidate["questions"].append({"id": "expression.left", "text": f"这里的“{term}”指哪个项目字段？",
                        "options": [{"value": col["field_name"], "label": f"{col['field_cn']}（{col['field_name']}）",
                                     "description": col.get("logic") or "活动文档中的项目字段"} for col in item["options"]]})
                else:
                    candidate["preview_error"] = f"活动文档没有核实到“{term}”的项目字段，请单独明确这一项。"
            if candidate.get("preview_error"):
                candidate["parallel_blocked"] = candidate["preview_error"]
            elif not ai_review_pending(candidate):
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
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Recheck the active analysis inputs before publishing or remembering any result."""
        cancel_event = self.analyses.request_control(cancel_event)
        cancel_event.check()
        self._emit_progress(progress, "semantics", "running", "正在解析业务语义与选表范围")
        if self.model is None:
            raise AppError("MODEL_UNAVAILABLE")
        current = self._analysis_inputs(user, payload)
        for _attempt in range(3):
            cancel_event.check()
            cache_writes = []
            try:
                result = self._analyze_request(user, payload, current, progress, cancel_event, cache_writes=cache_writes)
            except AppError as exc:
                if exc.code in {"MODEL_TIMEOUT", "ANALYSIS_TIMEOUT", "ANALYSIS_ROUND_LIMIT", "ANALYSIS_OUTPUT_LIMIT"}:
                    raise
                cancel_event.check()
                latest = self._analysis_inputs(user, payload)
                cancel_event.check()
                if current["context"] == latest["context"]:
                    raise
            else:
                cancel_event.check()
                latest = self._analysis_inputs(user, payload)
                cancel_event.check()
                if current["context"] == latest["context"]:
                    result["analysis_context"] = digest(current["context"])
                    result["reasoning_enabled"] = current["reasoning_enabled"]
                    request_text = str(payload.get("request_text") or "")
                    result["analysis_request_text"] = request_text
                    result["clarification_answers"] = current["clarification_answers"]
                    table = self._memory_table(result, current["tables"], current["categories"])
                    baseline = None
                    if table and result.get("rule_type") == "field_compare":
                        if not (payload.get("revision_of") and "revised_definition" in payload):
                            fields = current["fields_by_table"].get(int(table["id"]), [])
                            baseline = analysis_baseline(result, fields)
                        if not result.get("parallel_check"):
                            self.storage.audit(rule_id=None, task_id=None, action_code="ai_parse", operator_user_id=str(user["id"]),
                                               detail={"error_code": result.get("error_code") or "", "doc_version": result["doc_version"]})
                    def publish():
                        self.storage.publish_analysis(current["context"], request_text, baseline, cache_writes)

                    self.analyses.publish_result(cancel_event, result, publish)
                    return result
            self._emit_progress(progress, "semantics", "running", "分析依据已更新，正在按最新文档和报送分类重新核对")
            current = latest
        raise AppError("CONFLICT_VERSION")

    def _source_document_fields(self, tables: list[dict]) -> dict[int, list[dict]]:
        ids = [int(table["id"]) for table in tables]
        fields = {}
        for start in range(0, len(ids), _TABLE_SHORTLIST_LIMIT):
            fields.update(self.storage.doc_fields_for_tables(ids[start:start + _TABLE_SHORTLIST_LIMIT]))
        return fields

    def _memory_table(self, candidate: dict, tables: list[dict], categories: list[dict]) -> dict | None:
        matches = [t for t in tables if t["table_name"] == candidate.get("table_name")]
        if len(matches) == 1:
            return matches[0]
        code = candidate.get("report_category")
        if not code:
            return None
        if code in PBC_REPORT_CATEGORIES:
            code = PBC_SHARED_CATEGORY
        matches = [t for t in matches if (document_category(self._doc_category_scope(t, categories), categories) or {}).get("code") == code]
        return matches[0] if len(matches) == 1 else None

    def _analysis_inputs(self, user: dict, payload: dict) -> dict:
        if "reasoning_enabled" in payload and type(payload["reasoning_enabled"]) is not bool:
            raise AppError("VALIDATION_ERROR")
        reasoning_enabled = payload.get("reasoning_enabled", False)
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
        categories = self.list_report_categories()
        request_text = str(payload.get("request_text") or "")
        answers = payload.get("clarification_answers", [])
        if "clarification_answers" not in payload and isinstance(payload.get("revision_of"), str):
            previous = self.analyses.completed_result(user, payload["revision_of"])
            if (previous and previous.get("source_id") == source_id
                    and previous.get("analysis_request_text", previous.get("description")) == request_text):
                answers = previous.get("clarification_answers", [])
        if not isinstance(answers, list) or len(answers) > 100:
            raise AppError("VALIDATION_ERROR")
        clarification_answers = []
        for item in answers:
            if not isinstance(item, dict):
                raise AppError("VALIDATION_ERROR")
            row = {}
            for key, limit in (("question_id", 256), ("context", 2000), ("question", 2000), ("answer", 4000)):
                value = item.get(key, "")
                if not isinstance(value, str) or len(value) > limit or (key in {"question", "answer"} and not value.strip()):
                    raise AppError("VALIDATION_ERROR")
                row[key] = value.strip()
            clarification_answers.append(row)
        knowledge_revision = self.storage.active_knowledge_revision()
        knowledge_prefix, knowledge_context = self.knowledge.context(
            str(user["id"]), source_id, str(source["name"]),
            f"{document['id']}:{document['content_sha256']}", request_text,
        )
        shortlist = shortlist_tables(tables, request_text, _TABLE_SHORTLIST_LIMIT)
        semantic = payload.get("analysis_protocol") == 2
        project_target = None if semantic else project_mart_target(str(source["name"]), tables, request_text)
        if project_target is not None:
            shortlist = [project_target, *(item for item in shortlist if item["id"] != project_target["id"])][:_TABLE_SHORTLIST_LIMIT]
        fields_by_table = self._source_document_fields(tables)
        prompts = {stage: self._prompt_text(stage) for stage in ("select_table", "generate_rule", "business_scope")}
        model_id = str(payload.get("model_id") or "")
        available_models = self.list_models()
        current_model = next((m for m in available_models if str(m["id"]) == model_id
                              or (not model_id and m["is_default"])), {})
        # The active source, including fields outside this request's shortlist, determines compatibility.
        # Batch reads are shared with grounding; the prompt still receives only its bounded selection.
        source_rules = [(r["sheet_prefix"], r["data_source_name"]) for r in self.list_source_rules()]
        protocol_contracts = []
        if semantic:
            from .prompt_defaults import (
                SEMANTIC_CALL_OPTIONS, SEMANTIC_MAX_BUDGET_UNITS, SEMANTIC_TOTAL_OUTPUT_TOKENS, SEMANTIC_ANALYSIS_REVISION,
                SEMANTIC_SELECTION_CONTRACT, SEMANTIC_OUTPUT_CONTRACT, SEMANTIC_COMBINED_EXAMPLE, semantic_budget_instruction,
            )
            from .semantic_generation import SEMANTIC_MEMORY_CONTRACT
            protocol_contracts = [SEMANTIC_SELECTION_CONTRACT, SEMANTIC_OUTPUT_CONTRACT, SEMANTIC_MEMORY_CONTRACT, SEMANTIC_COMBINED_EXAMPLE,
                                  {**SEMANTIC_CALL_OPTIONS, "reasoning_effort": "low" if reasoning_enabled else "none",
                                   "max_budget_units": SEMANTIC_MAX_BUDGET_UNITS,
                                   "question_output_limit": SEMANTIC_TOTAL_OUTPUT_TOKENS},
                                  {"analysis_revision": SEMANTIC_ANALYSIS_REVISION},
                                  *[semantic_budget_instruction(SEMANTIC_CALL_OPTIONS["max_tokens"],
                                                               SEMANTIC_TOTAL_OUTPUT_TOKENS, stage)
                                    for stage in ("select_and_generate", "generate_rule")]]
        if clarification_answers:
            protocol_contracts.append({"clarification_answers": clarification_answers})
        memory_context = {
            "source_id": source_id, "source_name": str(source["name"]), "dialect": str(source.get("dialect") or ""),
            "doc_sha256": str(document["content_sha256"]), "doc_version": int(document["version_no"]), "model_id": model_id,
            "prompt_fingerprint": digest([prompts, SELECT_OUTPUT_CONTRACT, RULE_OUTPUT_CONTRACT, MEMORY_CONTRACT, *protocol_contracts, current_model,
                                          sorted((c["code"], c["name"]) for c in categories), source_rules, tables, fields_by_table]),
            "knowledge_fingerprint": digest([knowledge_revision, knowledge_prefix]),
        }
        return {"source": source, "document": document, "tables": tables, "categories": categories, "shortlist": shortlist,
                "project_target": project_target, "fields_by_table": fields_by_table, "prompts": prompts,
                "knowledge_prefix": knowledge_prefix, "knowledge_context": knowledge_context, "context": memory_context,
                "reasoning_enabled": reasoning_enabled, "clarification_answers": clarification_answers}

    def _analyze_request(self, user, payload, inputs, progress, cancel_event, *, cache_writes=None):
        source, document, tables = inputs["source"], inputs["document"], inputs["tables"]
        categories, shortlist, project_target = inputs["categories"], inputs["shortlist"], inputs["project_target"]
        fields_by_table, prompts = inputs["fields_by_table"], inputs["prompts"]
        knowledge_prefix, knowledge_context = inputs["knowledge_prefix"], inputs["knowledge_context"]
        memory_context = inputs["context"]
        source_id, model_id = memory_context["source_id"], memory_context["model_id"]
        request_text = str(payload.get("request_text") or "")
        semantic = payload.get("analysis_protocol") == 2
        check_text = "" if semantic else check_without_category_prefix(request_text, categories)
        if knowledge_context:
            reused = knowledge_context["summary_reused"] or knowledge_context["catalog_reused"]
            self._emit_progress(progress, "semantics", "running",
                                "已复用业务知识，正在解析需求" if reused else "已加载业务知识，正在解析需求")
        existing = []
        for rule in self.storage.visible_rules(str(user["id"])):
            version = self.storage.latest_version(int(rule["id"]))
            existing.append({"rule_code": rule["rule_code"], "definition": version["definition"]})
        context_stamp = digest(memory_context)
        previous = None
        if isinstance(payload.get("revision_of"), str):
            previous = self.analyses.completed_result(user, payload["revision_of"])
            if previous and previous.get("analysis_context") != context_stamp:
                previous = None
        history = self.storage.find_analysis_memories(memory_context, request_text)
        known_names = {item["table_name"] for item in shortlist}
        baselines, previous_requests, explicit_choices = [], [], []
        old_table = (self._memory_table(previous, tables, categories)
                     if previous and previous.get("table_name") in known_names else None)
        if old_table:
            old_fields = fields_by_table[int(old_table["id"])]
            previous_text = str(previous.get("description") or "")
            if semantic:
                explicit_choices = reviewed_semantic_choices(previous, payload.get("revised_definition"))
            baseline = safe_example(previous_text, analysis_baseline(previous, old_fields))
            if baseline:
                baselines.append(baseline)
                previous_requests.append(previous_text[:1000])
                if not semantic:
                    old_check = {**previous, "description": check_without_category_prefix(previous_text, categories)}
                    explicit_choices = owner_selections(old_check, payload.get("revised_definition"), old_fields,
                                                        str(old_table.get("dimension") or ""))
        for row in history:
            baseline = row["baseline"]
            if (baseline["table_name"] in known_names
                    and (baseline, row["request_text"][:1000]) not in zip(baselines, previous_requests)):
                baselines.append(baseline)
                previous_requests.append(row["request_text"][:1000])
        if semantic:
            examples = [{**item, "previous_request": text} for item, text in zip(baselines, previous_requests)]
            analysis = SemanticAnalysis(self, user, inputs, request_text, progress, cancel_event)
            result = analysis.run(examples, explicit_choices, existing,
                                  reuse_result=not payload.get("revision_of") and "revised_definition" not in payload)
            if cache_writes is not None and analysis.reusable_response is not None:
                cache_writes.append(analysis.reusable_response)
            return result
        decision, memory_draft = "", None
        if project_target is not None:
            project_fields = fields_by_table.get(int(project_target["id"]), [])
            plan = project_parallel_checks(request_text, project_fields)
            if plan is not None and not baselines:
                result = self._project_parallel_result(
                    user, source, document, project_target, project_fields, plan, request_text, knowledge_context, progress,
                )
                return result
        selector_tables = self._doc_table_context(shortlist, categories)
        if project_target is not None:
            selector_tables = (f"本需求为集市层项目维度，主表固定为 {project_target['table_name']}。"
                               "其他表仅在有独立的关联需求和真实文档依据时作为关联表。\n" + selector_tables)
        hints = field_profiles(shortlist, fields_by_table, check_text)
        if hints:
            selector_tables += "\n完整字典映射已按各字段的全部条目核实；其他相关字段供选表参考。\n" + hints
        select_prompt = self._render(prompts["select_table"], {
            "request_text": str(payload.get("request_text") or ""),
            "source_name": str(source["name"]),
            "tables": selector_tables,
            "categories": json.dumps(
                [{"code": item["code"], "name": item["name"]} for item in categories], ensure_ascii=False,
            ),
        })
        business_scope_text = prompts["business_scope"]
        business_scope = "通用校验口径（由校验设置维护）：\n" + business_scope_text + "\n"
        selection_prompt = knowledge_prefix + business_scope + select_prompt + "\n" + SELECT_OUTPUT_CONTRACT
        if baselines:
            context_tables = set(item["table_name"] for item in baselines)
            owners = [t for t in tables if t["table_name"] in context_tables]
            evidence = []
            for meta in owners:
                brief, _ = self._field_context(fields_by_table[int(meta["id"])], request_text,
                                              limit=max(1, _FIELD_CONTEXT_LIMIT // len(owners)))
                evidence.append({"table": meta["table_name"], "report_category": document_category(self._doc_category_scope(meta, categories), categories),
                                 "sheet": meta.get("sheet_name"), "scope": meta.get("scope"), "dimension": meta.get("dimension"), "fields": brief})
            examples = [{**baseline, "previous_request": text} for baseline, text in zip(baselines, previous_requests)]
            combined = {"current_request": request_text, "memories": examples, "current_owner_choices": explicit_choices}
            generation_template = self._render(prompts["generate_rule"], {
                "request_text": request_text, "table": "、".join(sorted(context_tables)), "fields": json.dumps(evidence, ensure_ascii=False),
            })
            response = self._complete_json(selection_prompt + "\n" + generation_template + "\n" + RULE_OUTPUT_CONTRACT
                                           + "\n" + MEMORY_CONTRACT + json.dumps(combined, ensure_ascii=False),
                                           model_id, stage="select_table", cancel_event=cancel_event)
            decision, memory_draft = memory_choice(response, baselines)
            selection = {key: value for key, value in response.items() if key != "draft"}
            if not (selection.get("target") or selection.get("table") or selection.get("result_type")):
                selection = self._complete_json(selection_prompt, model_id, stage="select_table", cancel_event=cancel_event)
        else:
            selection = self._complete_json(selection_prompt, model_id, stage="select_table", cancel_event=cancel_event)
        judgments = {"select_table": model_judgment(selection, stage="select_table")}
        selection_issues = merge(judgments["select_table"]["uncertainties"], request_reviews(request_text))
        selection_unsupported = judgments["select_table"]["unsupported_requirements"]
        context = {
            "source_id": source_id, "dialect": str(source.get("dialect") or ""),
            "doc_version": int(document["version_no"]), "doc_sha256": str(document["content_sha256"]),
            "model_judgments": judgments,
        }
        if knowledge_context:
            context["knowledge_context"] = knowledge_context
        target = selection.get("target") if isinstance(selection.get("target"), dict) else {}
        if category_scope_only(check_text):
            # A scope is useful evidence for selecting a table, but cannot specify a violation.
            target_name = str(target.get("table") or "").strip().rsplit(".", 1)[-1]
            selected = next((item for item in shortlist if item["table_name"] == target_name), None)
            scope_note = f"已指定「{request_text.strip()}」的范围，请补充要检查的字段和异常条件。"
            if selected:
                fields = fields_by_table[int(selected["id"])]
                check = conditional_null_check(check_text, fields, dictionary_options, dimension=str(selected.get("dimension") or ""))
                if check and check.selections:
                    labels = {f["field_name"]: f.get("field_cn") or f["field_name"] for f in fields}
                    matches = []
                    for item in check.selections:
                        codes = item["value"] if item["op"] == "in" else [item["value"]]
                        matches.append(f"{labels[item['field']]}（{item['field']}，取值 {'、'.join(map(str, codes))}）")
                    scope_note = f"「{check.scope_text}」在本表字典中对应{'、'.join(matches)}。请补充要检查的字段和异常条件。"
            self._emit_progress(progress, "generation", "needs_confirmation", "请补充要检查的字段和异常条件")
            return clarification_candidate(merge([scope_note], selection_issues), selection_unsupported,
                                           table_name=selected["table_name"] if selected else "",
                                           preview=None, **context)
        selection_state = str(selection.get("result_type") or selection.get("status") or "").strip().lower()
        clarification_requested = selection_state in {"clarification", "needs_clarification"}
        recovered_selection = False
        if (clarification_requested and not selection_unsupported and not selection.get("related_target")
                and not selection.get("target_ambiguities") and not selection.get("candidates")):
            selected_name = str(target.get("table") or selection.get("table") or "").rsplit(".", 1)[-1]
            cited_tables = {name for note in selection_issues for name in
                            re.findall(r"(?<![\w.])([A-Za-z_][A-Za-z_0-9]*)\.[A-Za-z_][A-Za-z_0-9]*", note, re.ASCII)}
            grounded_tables = []
            for item in shortlist:
                if selected_name and selected_name not in (item["table_name"], item.get("table_name_cn")):
                    continue
                if not selected_name and cited_tables and cited_tables != {item["table_name"]}:
                    continue
                item_fields = fields_by_table[int(item["id"])]
                dimension = str(item.get("dimension") or "")
                numeric = category_numeric_check(check_text, item_fields, dictionary_options, dimension=dimension)
                named_null = conditional_null_check(check_text, item_fields, dictionary_options, dimension=dimension)
                named_table = selected_name or cited_tables
                if ((numeric and numeric.measures and (numeric.scope.selections or named_table))
                        or (named_null and named_null.measures and (named_null.selections or named_table))
                        or plain_null_check(check_text, item_fields)
                        or selector_field_choices(selection, item_fields, check_text, item["table_name"])):
                    grounded_tables.append(item)
            if len(grounded_tables) == 1 and (selected_name or cited_tables or len(shortlist) == len(tables)):
                target = {"table": grounded_tables[0]["table_name"]}
                clarification_requested = False
                recovered_selection = True
        if clarification_requested and not selection_unsupported:
            selected_name = str(target.get("table") or selection.get("table") or "")
            metric_tables = [item for item in shortlist
                             if (not selected_name or selected_name in (item["table_name"], item.get("table_name_cn")))
                             and _bare_metric_choices(check_text, fields_by_table.get(int(item["id"]), []))]
            if len(metric_tables) == 1 and (selected_name or len(shortlist) == len(tables)):
                target = {"table": metric_tables[0]["table_name"]}
                clarification_requested = False  # The check can now be clarified against actual fields.
        if project_target is not None and not selection_unsupported:
            target = {"table": project_target["table_name"]}
            clarification_requested = False
        documented_choice = None
        if project_target is None and not selection_unsupported and not selection.get("related_target") and len(shortlist) == len(tables):
            # 全量文档中只有一张同粒度表能同时证明筛选和指标，才修正模型选表。
            matches = []
            for item in shortlist:
                binding = documented_scope_comparison(check_text, fields_by_table[int(item["id"])])
                if binding and binding["entity"] == str(item.get("dimension") or "").strip():
                    matches.append((item, binding))
            if len(matches) == 1:
                documented_choice = matches[0]
                target = {"table": documented_choice[0]["table_name"]}
                clarification_requested = False
                selection_issues = [issue for issue in selection_issues
                                    if not re.fullmatch(r"(?:无法|尚未|不能)(?:唯一)?确定(?:校验)?目标表", issue.rstrip("。 "))]
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
        table_matches = [item for item in shortlist if str(item["table_name"]).lower() == raw_table.lower()]
        if not table_matches:
            table_matches = [item for item in shortlist if str(item.get("table_name_cn") or "") == raw_table]
        if not table_matches:
            raise failure("MODEL_RESPONSE_INVALID", "select_table")
        category_hint = requested_category_codes(request_text, categories) or {str(selection.get("report_category") or "")}
        table = (self._category_tables(table_matches, category_hint, categories) or table_matches)[0]
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
        documented_join = None
        if not documented_choice and not selection_unsupported:
            # 仅在已选指标表上查找请求维度的状态。维度、关联键或期间证据不唯一时不替模型确认。
            eligible = [related_table] if related_table else shortlist
            bindings = []
            for owner in eligible:
                if owner["id"] == table["id"] or self._doc_category_scope(owner, categories) != category_scope:
                    continue
                owner_fields = fields_by_table.get(int(owner["id"]), [])
                bound = metric_scope_binding(request_text, table, fields_by_table[int(table["id"])], owner, owner_fields)
                if bound and bound.get("join"):
                    bindings.append((owner, owner_fields, bound))
            if len(bindings) == 1:
                related_table, related_fields, binding = bindings[0]
                documented_choice = (table, binding)
                documented_join = binding["join"]
        category_pool = [item for item in categories if item["code"] in category_scope] if category_scope is not None else categories
        category_code = str(selection.get("report_category") or "")
        if category_code in PBC_REPORT_CATEGORIES:
            category_code = PBC_SHARED_CATEGORY
        category = self._doc_category(category_pool, category_code)
        if ((category_scope and category_scope <= (PBC_REPORT_CATEGORIES | {PBC_SHARED_CATEGORY}))
                or (category and category["code"] == PBC_SHARED_CATEGORY)):
            category = {"code": PBC_SHARED_CATEGORY, "name": PBC_SHARED_CATEGORY_NAME}
            selection_issues = [item for item in selection_issues if not _classification_only(item)]
            selection_unsupported = [item for item in selection_unsupported if not _classification_only(item)]
        elif category_scope is not None and category is None and len(category_pool) == 1:
            category = category_pool[0]
        selection_notices = []
        if category is None:
            if selection.get("report_category") and category_scope is None:
                raise failure("MODEL_RESPONSE_INVALID", "select_table")
            category = {"code": "", "name": "未分类"}
            selection_notices = [item for item in selection_issues if re.search(r"报送.*分类|报送类型|无法.*分类", item)]
            selection_issues = [item for item in selection_issues if item not in selection_notices]

        qualifier = GENERAL_QUALIFIER.search(request_text)
        general_reviews = ([item for item in request_reviews(request_text) if item.startswith("需求包含一般")]
                           if qualifier and not EXPLICIT_EXCLUSION.search(request_text) else [])
        selection_issues = [item for item in selection_issues if item not in general_reviews]
        if qualifier and general_reviews:
            selection_notices.append(f"“{qualifier[0]}”保留合理例外，命中记录应先人工核实。")
        scope_confirmed = _document_covers_active_scope(table)
        if scope_confirmed:
            selection_issues = [item for item in selection_issues if item not in request_reviews("存续")]
        fields = fields_by_table.get(int(table["id"]), [])
        if not fields:
            raise AppError("VALIDATION_ERROR")
        numeric_check = None if related_table else category_numeric_check(
            check_text, fields, dictionary_options, dimension=str(table.get("dimension") or ""),
        )
        scope = numeric_check.scope if numeric_check else None
        if scope is None and not related_table:
            scope = conditional_null_check(check_text, fields, dictionary_options, dimension=str(table.get("dimension") or ""))
        dictionary_evidence = {"table": table_name, "fields": scope.dictionary_entries if scope else (),
                               "category": scope.label if scope else ""}
        selection_judgment = judgments["select_table"]
        if selection_judgment.get("dictionary_questions"):
            answered = set(selection_judgment["uncertainties"]) - set(pending_judgment_reviews(selection_judgment, **dictionary_evidence))
            selection_issues = [issue for issue in selection_issues if issue not in answered]
        verified_category_filter = None
        context_issues = selection_issues
        if scope and len(scope.selections) == 1:
            field = scope.selections[0]["field"]
            verified_category_filter = {"category": scope.label, "field": field, "entries": scope.dictionary_entries[field]}
            if selection_issues:
                evidence = BoundReviewEvidence(scope, fields, table_name, str(table.get("scope") or ""))
                context_issues = [remaining for issue in selection_issues if (remaining := evidence.remaining_dictionary_review(issue))]
        lookup_answers = []
        answered_texts = set()
        lookup_budget = 16000
        for question in selection_judgment.get("dictionary_questions", []):
            entries = documented_dictionary_entries(question, table_name, fields)
            if entries:
                if not (verified_category_filter and verified_category_filter["field"] == question["field"]
                        and verified_category_filter["category"] == question["category"]):
                    answer = {**question, "entries": entries}
                    size = len(json.dumps(answer, ensure_ascii=False)) + 2
                    if size > lookup_budget:
                        continue
                    lookup_answers.append(answer)
                    lookup_budget -= size
                answered_texts.add(dictionary_question_text(question))
        if answered_texts:
            answered_texts.difference_update(selection_judgment["text_uncertainties"])
            context_issues = [note for note in context_issues if note not in answered_texts]
        select_choices = [] if related_table else selector_field_choices(selection, fields, request_text, table_name)
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
        generate_prompt = self._render(prompts["generate_rule"], {
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
            "uncertainties": context_issues, "unsupported_requirements": selection_unsupported,
            "table_scope": str(table.get("scope") or ""),
            "related_target": {"table": str(related_table["table_name"])} if related_table else {},
            **({"documented_field_choices": select_choices} if select_choices else {}),
            **({"verified_category_filter": verified_category_filter} if verified_category_filter else {}),
            **({"documented_dictionary_answers": lookup_answers} if lookup_answers else {}),
            **({"documented_numeric_fields": [
                {"field": f["field_name"], "label": f["field_cn"]} for f in numeric_check.measures],
                "documented_scope_choices": numeric_check.scope.selections} if numeric_check else {}),
            "suggestion_document_facts": suggestion_facts, "existing_rule_summaries": existing_summaries,
            "suggestion_scope_notice": "补充事实仅供独立建议；主规则不得据此擅加第三表或更换目标。已有摘要不含固定条件值，不能据此断言完全覆盖。",
        }, ensure_ascii=False)
        self._emit_progress(progress, "generation", "running", "正在生成规则草稿与本地结构校验")
        if memory_draft is not None:
            try:
                proposal = refine_candidate(memory_draft, columns=self._doc_columns(fields), dialect=memory_context["dialect"],
                                            existing=[], related_columns=self._doc_columns(related_fields), request_text=request_text)
                mismatch = (numeric_check.expression_issue(proposal["expression"]) if numeric_check else
                            check_request_coverage({**memory_draft, "description": check_text, "expression": proposal["expression"]},
                                                   fields, related_fields, dimension=str(table.get("dimension") or "")))
            except (AppError, TypeError, KeyError, ValueError):
                mismatch = True
            model_table = self._memory_table({"table_name": selection["target"]["table"],
                                              "report_category": selection.get("report_category")}, tables, categories)
            if mismatch or not model_table or table["id"] != model_table["id"]:
                decision, memory_draft = "fresh", None
        draft = memory_draft or self._complete_json(
            knowledge_prefix + business_scope + generate_prompt + "\n选表阶段上下文（核实仍有效的事项）：" + review_context + "\n" + RULE_OUTPUT_CONTRACT,
            str(payload.get("model_id") or ""), stage="generate_rule", cancel_event=cancel_event,
        )
        if "expression" in draft:
            draft["expression"] = model_expression(draft["expression"])
        judgment = judgments["generate_rule"] = model_judgment(draft, stage="generate_rule")
        # 第二轮模型建议只作顶层线索，与主规则 uncertainties 完全隔离。
        raw_suggestions = draft.pop("ai_suggestions", [])
        draft["uncertainties"] = merge(selection_issues, pending_judgment_reviews(judgment, **dictionary_evidence))
        draft["unsupported_requirements"] = merge(selection_unsupported, judgment["unsupported_requirements"])
        if category["code"] == PBC_SHARED_CATEGORY:
            for key in ("uncertainties", "unsupported_requirements"):
                draft[key] = [item for item in draft[key] if not _classification_only(item)]
        draft.pop("uncertainty", None)  # 旧键的原话已合并进该阶段判断。
        bind_selector_choices(draft, select_choices, fields, table_name)
        if numeric_check and numeric_check.measures and not draft.get("join") and draft.get("rule_type") in (None, "field_compare"):
            proposed = model_expression(draft.get("expression"))
            if numeric_check.expression_issue(proposed):
                proposed = numeric_check.expression(numeric_check.measures[0]["field_name"])
            draft.update(rule_type="field_compare", expression=proposed, field_choices=[], equality_policy="allow_equal")
            draft.setdefault("rule_name", f"{numeric_check.term}校验")
            draft.setdefault("violation_message", f"{numeric_check.term}不符合要求，请核实。")
        bare_fields = _bare_metric_choices(check_text, fields)
        model_field = None
        explicit_check = None
        recovered_null = (conditional_null_check(check_text, fields, dictionary_options,
                          dimension=str(table.get("dimension") or "")) if recovered_selection else None)
        if recovered_null and not recovered_null.measures:
            recovered_null = None
        if not bare_fields and draft.get("rule_type") is None and not (draft["unsupported_requirements"] or draft.get("join")):
            explicit_check = recovered_null or plain_null_check(check_text, fields)
        if bare_fields or explicit_check:
            # A bare term still requires a check; an explicit nonempty request only needs its operands.
            choices = bare_fields or explicit_check.measures
            term = check_text.strip() if bare_fields else explicit_check.term
            raw_expression = draft.get("expression")
            proposed = raw_expression.get("left") if isinstance(raw_expression, dict) else None
            field_choices = draft.get("field_choices") if isinstance(draft.get("field_choices"), list) else []
            if not proposed:
                proposed = next((choice.get("recommended") for choice in field_choices if isinstance(choice, dict)
                                 and choice.get("side") == "left" and isinstance(choice.get("recommended"), str)), None)
            model_field = next((f for f in choices if proposed in (f["field_name"], f.get("field_cn"))), None)
            draft = {
                "rule_type": "field_compare", "rule_name": f"{term}校验",
                "expression": {"left": (model_field or choices[0])["field_name"], "op": "is_null"},
                "violation_message": f"{term}为空，请核实。", "field_choices": field_choices,
                "null_policy": "violate", "equality_policy": "allow_equal",
                "uncertainties": [] if bare_fields else draft["uncertainties"], "unsupported_requirements": [],
            }
            related_table, related_fields = None, []
        if documented_choice and draft.get("rule_type") is None and not draft["unsupported_requirements"] and not draft.get("join"):
            binding = documented_choice[1]
            expression = binding["expression"]
            # 阈值为 0 不依赖金额计量单位。其他阈值仍须经模型确认业务单位。
            if expression["right"] == 0:
                draft.update(rule_type="field_compare", expression=expression, filters=[binding["filter"]],
                             rule_name=f"{binding['term']}校验", violation_message=f"{binding['term']}不符合要求，请核实。",
                             null_policy="unresolved", equality_policy="allow_equal")
                draft["uncertainties"] = [
                    issue for issue in draft["uncertainties"]
                    if not (_MISSING_COMPARISON_FIELDS.fullmatch(issue.rstrip("。 "))
                            and binding["term"] in issue and not re.search(r"单位|币种|期间|关联|粒度|例外|汇总|聚合", issue))
                ]
                selection_notices.append("已按当前文档核实筛选与比较字段，生成校验条件。")
        if (documented_join and not draft["unsupported_requirements"]
                and draft.get("expression") == documented_choice[1]["expression"]):
            # 有界的单指标请求已证明筛选表与完整关联，在模型输出有效后采用文档规格。
            draft["join"] = documented_join
            draft["filters"] = [documented_choice[1]["filter"]]
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
                candidates=[clarification], request_text=request_text, existing_rules=existing, actionable_only=True,
                model_only=True, limit=MAX_SUGGESTIONS,
                select_category_tables=lambda tables, codes: self._category_tables(tables, codes, categories),
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
            not unary and not is_condition_group(draft)
            and is_numeric_comparison(
                {"rule_type": "field_compare", "expression": draft.get("expression") or {}},
                base_types, related_types or None,
            )
        )
        if not unary and not is_condition_group(draft) and draft.get("null_policy") == "violate" and not numeric_binary:
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
            request_text=request_text,
        )
        if "project_driver" in draft:
            refined["project_driver"] = copy.deepcopy(draft["project_driver"])
        # 请求全文仅含已由文档证明的同表范围和零值比较时，模型原话留在分析判断中。
        # 结构化字段、筛选、项目身份和日期仍参与后续核验。其它请求继续保留模型待确认事项。
        verified_request = documented_choice[1]["expression"] if documented_choice else {}
        resolved_request = (
            verified_request.get("right") == 0 and refined["expression"] == verified_request
            and not draft.get("join") and not refined["unsupported_requirements"]
        )
        original_review = refined["uncertainties"]
        if resolved_request:
            model_notes = set(judgments["select_table"]["uncertainties"] + judgment["uncertainties"])
            refined["uncertainties"] = [issue for issue in original_review if issue not in model_notes]
        fields_grounded = ground_candidate_query(
            refined, draft, fields, related_fields, (check_text.strip() + "不得为空") if bare_fields else check_text,
            scope_confirmed=scope_confirmed, documented_join=documented_join, dimension=str(table.get("dimension") or ""),
            document_scope=str(table.get("scope") or ""),
        )
        if general_reviews and fields_grounded and not refined.get("preview_error"):
            refined["uncertainties"] = remaining_qualifier_reviews(
                request_text, refined["expression"], refined["uncertainties"],
                fields=fields, subject=numeric_check.subject if numeric_check else check_text,
            )
        dimension_issue = scope_dimension_issue(request_text, refined.get("filters") or [], table, fields,
                                               shortlist, fields_by_table)
        if related_table and not dimension_issue:
            dimension_issue = scope_dimension_issue(request_text, refined.get("filters") or [], related_table,
                                                    related_fields, shortlist, fields_by_table, role="related")
        if dimension_issue:
            refined["uncertainties"] = merge(refined["uncertainties"], [dimension_issue])
            refined["preview_error"] = dimension_issue
            refined["status"] = "needs_clarification"
        if resolved_request and not fields_grounded:
            refined["uncertainties"] = merge(original_review, refined["uncertainties"])
        if len(tables) > len(shortlist):
            refined["uncertainties"].append(
                f"数据源文档表数量 {len(tables)} 超过单次选表上限 {len(shortlist)}，已按需求相关性筛选 {len(shortlist)} 张候选表，请人工核对目标表。"
            )
        refined.update({
            "table_name": table_name,
            "report_category": category["code"],
            "report_category_name": category["name"],
            "source_id": source_id,
            "dialect": str(source.get("dialect") or ""),
            "columns": columns,
            "related_columns": related_columns,
            "generation_mode": "ai",
            "description": request_text,
            "mapping_version": f"doc-v{int(document['version_no'])}-{str(document['content_sha256'])[:12]}",
            "doc_version": int(document["version_no"]),
            "doc_sha256": str(document["content_sha256"]),
            "model_judgments": judgments,
        })
        # In AI output op is the violation predicate; samples must not silently override its equality.
        grouped = is_condition_group(refined)
        implied_equality = ("reject_equal" if refined["expression"].get("op") in ("eq", "lte", "gte")
                            and refined["expression"].get("right_type") != "value" else "allow_equal")
        if (not grouped and refined["expression"].get("right_type") != "value"
                and refined.get("equality_policy") not in ("unresolved", implied_equality)):
            refined["uncertainties"].append("模型对相等情况的判断与比较条件不一致，请明确边界要求后重新分析。")
        refined["equality_policy"] = implied_equality
        refined["scope_description"] = "存续项目" if scope_confirmed else str(table.get("table_name_cn") or "所选项目数据")
        if knowledge_context:
            refined["knowledge_context"] = knowledge_context
            reuse_label = "（复用）" if reused else ""
            selection_notices.append(f"业务知识 v{knowledge_context['revision']}{reuse_label}："
                                     + "、".join(knowledge_context["topics"]))
        refined["notices"] = selection_notices
        refined["preview"] = None
        refined.setdefault("questions", [])
        if (refined["null_policy"] == "unresolved" and not numeric_binary and not unary
                and not any(q["id"] in {"null_policy", "expression.left", "expression.right"} for q in refined["questions"])):
            refined["questions"].append(self._null_policy_question())
        context_uncertainties = self._document_candidate_details(refined, table, fields, tables, fields_by_table)
        # 独立单候选已确定期间日期时，消除模型伪“未指定业务日期”追问；范围/截止/跨期等真未决保留。
        if refined.get("uncertainties"):
            cleaned = resolve_uncertainty_clauses(
                list(refined["uncertainties"]), has_candidates=False,
                has_period=bool(refined.get("report_date_field")),
            )
            if cleaned != list(refined["uncertainties"]):
                refined["uncertainties"] = cleaned
                refined["uncertainty_resolutions"] = [""] * len(cleaned)
        if context_uncertainties:
            refined["uncertainties"] = merge(refined["uncertainties"], context_uncertainties)
            refined["uncertainty_resolutions"] = [""] * len(refined["uncertainties"])
        original_text = {note for stage in judgments.values() for note in stage.get("text_uncertainties", stage["uncertainties"])}
        pending_refs = []
        for stage in judgments.values():
            for question in stage.get("dictionary_questions", []):
                if (question["table"] == table_name and scope and question["category"] == scope.label
                        and question["field"] in scope.dictionary_entries):
                    continue
                note = dictionary_question_text(question)
                if note not in refined["uncertainties"]:
                    refined["uncertainties"].append(note)
                if note not in original_text and question not in pending_refs:
                    pending_refs.append(question)
        if pending_refs:
            pending_refs = apply_dictionary_filter_answers(refined, pending_refs, table_name, fields)
            if pending_refs:
                refined["pending_dictionary_questions"] = pending_refs
        for role, count, truncated in (("目标表", len(fields), fields_truncated),
                                       ("关联表", len(related_fields), related_truncated)):
            if truncated:
                refined["notices"].append(
                    f"{role}字段数量为 {count}，模型上下文按相关性提供其中 {_FIELD_CONTEXT_LIMIT} 个。字段核对使用完整文档。"
                )
        if (bare_fields or explicit_check) and not model_field:
            for question in refined["questions"]:
                if question["id"] == "expression.left":
                    for option in question["options"]:
                        option.pop("tag", None)
        if bare_fields:
            question = _check_requirement(check_text.strip())
            refined["questions"].insert(0, question)
            refined["uncertainties"] = merge(refined["uncertainties"], [question["uncertainty"]])
            refined["uncertainty_resolutions"] = [""] * len(refined["uncertainties"])
        # 已明确集市层项目粒度时，不再将合同/账户等同义指标作为主表替代方案。
        choosing_metric = any(q["id"] == "expression.left" for q in refined["questions"])
        if project_target is None and not bare_fields and not (choosing_metric and plain_null_check(request_text, fields)):
            peer_tables = [item for item in tables if self._doc_category_scope(item, categories) == category_scope
                           or (category_scope and document_category(self._doc_category_scope(item, categories), categories))]
            refined = self._attach_candidate_options(
                user=user, source=source, tables=peer_tables, fields_by_table=fields_by_table,
                table=table, refined=refined, request_text=request_text,
                base_context_uncertainties=context_uncertainties, categories=categories,
            )
        if memory_draft is not None and explicit_choices and response.get("memory_index") == 0:
            apply_owner_selections(refined, explicit_choices)
        named_categories = requested_category_codes(request_text, categories)
        if category_scope and named_categories and refined.get("report_category") not in named_categories:
            names = "、".join(item["name"] for item in categories if item["code"] in named_categories)
            issue = f"需求指定了「{names}」，请核对该报送分类的目标表和字段。"
            refined["uncertainties"] = merge(refined.get("uncertainties") or [], [issue])
            refined["preview_error"] = issue
            refined["preview"] = None
        if not refined.get("candidate_options"):
            self._refresh_candidate_preview(user, refined)
        # 通用 AI 补充建议：只来自文档事实与当前候选，且只挂顶层，不进主定义/hash。
        flattened_candidates = [refined] + [
            option["candidate"] for option in refined.get("candidate_options", [])
        ]
        refined["ai_suggestions"] = build_ai_suggestions(
            raw_suggestions, tables=tables, fields_by_table=fields_by_table,
            candidates=flattened_candidates, request_text=request_text,
            existing_rules=existing, actionable_only=True,
            model_only=True, limit=MAX_SUGGESTIONS,
            select_category_tables=lambda tables, codes: self._category_tables(tables, codes, categories),
            default_business_scope=business_scope_text == DEFAULT_PROMPTS["business_scope"],
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
        if decision:
            refined["memory_decision"] = decision
            refined["analysis_reused"] = memory_draft is not None
        return refined

    def run_tests(self, user: dict[str, Any], rule_id: int, version_no: int, cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        self._require_owner(user, rule_id)
        version = self.storage.get_version(rule_id, version_no)
        definition = version["definition"]
        if is_new_spec(definition) or definition.get("analysis_protocol") == 2:
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
            preview = self.preview_candidate(user, {"definition": definition}, preserve_result_fields=True)
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

    def confirm_rule(self, user: dict[str, Any], rule_id: int, version_no: int, expected_hash: str, *, expected_rule: dict | None = None) -> dict[str, Any]:
        rule = self._require_owner(user, rule_id)
        version = self.storage.get_version(rule_id, version_no)
        definition = version["definition"]
        if (definition.get("null_policy") == "unresolved" or definition.get("equality_policy") == "unresolved"
                or not review_ready(definition) or not query_ready(definition)):
            raise AppError("VALIDATION_ERROR")
        if (version["content_sha256"] != expected_hash
                or int(self.storage.latest_version(rule_id)["id"]) != int(version["id"])):
            raise AppError("CONFLICT_VERSION")
        if is_new_spec(definition) or definition.get("analysis_protocol") == 2:
            preview = self.preview_candidate(user, {"definition": definition}, preserve_result_fields=True)
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
        self.storage.set_status(rule_id, "enabled", int(version["id"]), history=history, expected_rule=expected_rule, confirmation={
            "rule_id": rule_id, "version_no": version_no, "version_id": int(version["id"]),
            "content_sha256": version["content_sha256"], "confirmer_user_id": str(user["id"]),
            "passed_count": passed, "failed_count": failed, "not_run_count": 0,
        })
        updated = self.storage.get_rule(rule_id)
        updated["current_version_id"] = int(version["id"])
        return updated

    def preview_batch(self, user: dict[str, Any], rule_ids: list[int]) -> dict[str, Any]:
        rules = [self.storage.get_rule(rule_id) for rule_id in rule_ids]
        enabled = [rule for rule in rules if rule["status"] == "enabled" and self._visible(user, rule)]
        return {"count": len(enabled), "rule_ids": [int(rule["id"]) for rule in enabled]}

    def execution_selection(self, user: dict, query: dict) -> dict:
        return self.storage.execution_selection(None if self._is_admin(user) else str(user["id"]), query)

    def start_task(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        rule_ids = task_results.selected_rule_ids(payload.get("rule_ids"))
        period = _report_period(payload.get("report_period")).isoformat()
        candidates = self.storage.execution_candidates(rule_ids)
        skipped = []
        selected = []
        for rule_id in rule_ids:
            rule = candidates.get(rule_id)
            if rule is None:
                raise AppError("RULE_NOT_FOUND")
            if not self._visible(user, rule):
                self._deny(user, rule_id)
            if rule["status"] == "deleted":
                raise AppError("RULE_DELETED")
            if rule["status"] != "enabled" or not rule.get("current_version_id"):
                skipped.append({"rule_id": rule_id, "reason": "规则未启用"})
                continue
            if rule["version_id"] is None:
                raise AppError("CONFLICT_VERSION")
            rule["report_category"] = task_results.category_code(rule["report_category"])
            selected.append(rule)
        if not selected and skipped:
            raise AppError("VALIDATION_ERROR")
        if selected:
            try:
                sources = self.list_sources()
            except Exception:
                logging.getLogger(__name__).warning("创建批次时无法读取数据源目录，未采集名称")
                sources = []
            labels = {(item["source_id"], item["table_name"], item["report_category"]): item for item in selected}
            self._add_table_labels(list(labels.values()), sources)
            names = {str(s["id"]): s["name"] for s in sources}
            categories = {c["code"]: c["name"] for c in self.list_report_categories()}
            for item in selected:
                item["table_name_cn"] = labels[item["source_id"], item["table_name"], item["report_category"]]["table_name_cn"]
                item["source_name"] = names.get(item["source_id"])
                item["report_category_name"] = item["report_category_name"] or categories.get(item["report_category"])
        task = self.storage.create_task(
            creator_user_id=str(user["id"]),
            source_id=str(payload.get("source_id") or ""),
            report_period=period,
            params={**dict(payload), "report_period": period},
            rules=selected,
        )
        response = {key: value for key, value in task.items() if key != "params_json"}
        response["status"] = "queued"
        response["skipped"] = skipped
        self._dispatch_execution(int(task["id"]))
        return response

    def _dispatch_execution(self, task_id: int, generation: int = 0, *, resume: bool = False) -> None:
        if self._executions.executor is not None:
            self._executions.submit(task_id, generation, self._run_task, resume=resume)
            return

        def run():
            self._run_task(task_id, generation)
            self.storage.transition_task(task_id, ("pausing",), "paused", generation=generation)

        if self.inline:
            run()
        else:
            thread = threading.Thread(target=run, daemon=True)
            self._threads.append(thread)
            thread.start()

    def cancel_task(self, user: dict[str, Any], task_id: int) -> dict[str, Any]:
        self._require_task_owner(user, task_id)
        self._executions.interrupt(task_id, pause=False)
        return self.storage.get_task(task_id, with_params=False)

    def pause_task(self, user: dict, task_id: int) -> dict:
        self._require_task_owner(user, task_id)
        self._executions.interrupt(task_id, pause=True)
        return self.storage.get_task(task_id, with_params=False)

    def resume_task(self, user: dict, task_id: int) -> dict:
        self._require_task_owner(user, task_id)
        generation = self.storage.resume_generation(task_id)
        if generation is not None:
            self._dispatch_execution(task_id, generation, resume=True)
        return self.storage.get_task(task_id, with_params=False)

    def retry_failed(self, user: dict[str, Any], task_id: int) -> dict[str, Any]:
        task = self._require_task_owner(user, task_id)
        if task["status"] in {"queued", "running", "pausing", "paused"}:
            return task
        claimed = self.storage.claim_failed_task_rules(task_id, queue=True)
        if claimed:
            self._dispatch_execution(task_id, claimed[0]["execution_generation"])
        return self.storage.get_task(task_id, with_params=False)

    def export_issues(self, user: dict[str, Any], task_id: int, file_type: str, query: dict | None = None) -> dict[str, Any]:
        task = self._require_task_owner(user, task_id)
        scope = query or {}
        export = IssueExport()
        for page in range(1, 51):
            batch = task_results.issue_page(self.storage, task, scope, page, 100)
            if not export.extend(batch["items"]) or len(export.rows) >= batch["total"] or not batch["items"]:
                break
        task["truncated"] = batch["truncated"] or len(export.rows) < batch["total"]
        return export.render(task, file_type)

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
            {"id": item.id, "name": item.name, "model_name": item.model_name, "is_default": item.is_default,
             "configuration_fingerprint": getattr(item, "configuration_fingerprint", "")}
            for item in self.model.list_enabled()
        ]

    def list_task_issues(self, user: dict[str, Any], task_id: int, query: dict[str, Any] | None = None) -> dict[str, Any]:
        task = self._require_task_owner(user, task_id)
        query = query or {}
        return task_results.issue_page(self.storage, task, query, int(query.get("page") or 1), int(query.get("page_size") or 50))

    def join(self) -> None:
        if self._executions.executor is not None:
            self._executions.close()
        for thread in self._threads:
            thread.join(timeout=3)
        # 模块停止/服务回收时协作取消未结束的临时分析，并等待线程退出。
        self.analyses.close(timeout=3)

    def _run_task(self, task_id: int, generation: int = 0) -> None:
        if self.gate is not None:
            self.gate.wait(2)
        after = 0
        while not self._executions.stopping.is_set():
            rows = self.storage.queued_task_rules(task_id, after, generation)
            if not rows:
                break
            for item in rows:
                claimed = self.storage.claim_execution_rule(task_id, item["id"], generation)
                if claimed is None or self._executions.stopping.is_set():
                    self.storage.refresh_task_status(task_id, generation=generation)
                    return
                if claimed:
                    self._execute_task_rule(item)
            after = rows[-1]["id"]
        self.storage.refresh_task_status(task_id, generation=generation)

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
        matches = [item for item in tables if item["table_name"] == definition.get("table_name")]
        if len(matches) > 1:
            matches = self._category_tables(matches, {definition.get("report_category")}, self.list_report_categories())
            if len(matches) != 1:
                raise AppError("VALIDATION_ERROR")
        if not matches:
            return known_required
        table = matches[0]
        return known_required or self._project_required(definition, table, self.storage.doc_fields(int(table["id"])))

    def _execute_task_rule(self, item: dict[str, Any]) -> None:
        version = self.storage.get_version_by_id(int(item["version_id"]))
        run: RuleRun | None = None
        if self.metadata is None:
            result_status, error_code, count, truncated = "ERROR", "SOURCE_UNAVAILABLE", 0, False
        else:
            try:
                task = self.storage.get_task(int(item["task_id"]), with_params=False)
                run = execute_version(
                    version,
                    {"max_rows": 200, "report_date": _report_period(task.get("report_period"))},
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
        for index, row in enumerate(getattr(run, "rows", ())):
            issue = {
                "business_key": row.get("business_key"),
                "project_code": row.get("project_code"),
                "project_name": row.get("project_name"),
                "project_name_status": row.get("project_name_status") or "not_required",
                "message": row.get("violation_message") or str(version["definition"].get("violation_message") or ""),
                "query_result": run.query_results[index] if run.query_results else None,
            }
            if row.get("issue_kind"):
                issue["issue_kind"] = row["issue_kind"]
            issues.append(issue)
        self.storage.record_rule_result(
            int(item["id"]), status=result_status, error_code=error_code,
            violation_count=count, truncated=bool(truncated), issues=issues,
            execution_generation=item["execution_generation"],
        )

    def _refresh_task_status(self, task_id: int) -> dict[str, Any]:
        self.storage.refresh_task_status(task_id)
        return self.storage.get_task(task_id)

    def _result_alias_columns(self, definition: dict[str, Any]) -> list[dict[str, Any]]:
        document = self.storage.active_document()
        if document:
            source = next((item for item in self.list_selectable_sources()
                           if str(item["id"]) == str(definition.get("source_id"))), None)
            if source:
                tables = self.storage.doc_tables(document["id"], data_source_name=source["name"])
                table = self._memory_table(definition, tables, self.list_report_categories())
                if table:
                    return self._doc_columns(self.storage.doc_fields(table["id"]))
            return []
        if (definition.get("generation_mode") != "ai" and definition.get("table_name")
                and callable(getattr(self.metadata, "describe_table", None))):
            try:
                return self._definition_columns(definition)
            except AppError as exc:
                if exc.code != "SOURCE_UNAVAILABLE":
                    raise
        return []

    def _compile_if_possible(self, definition: dict[str, Any],
                             documented_identifiers: list[str] | None = None) -> tuple[str, dict[str, Any]]:
        if definition.get("generation_mode") == "ai" and ai_review_pending(definition):
            return "", {}
        if documented_identifiers is not None:
            return compile_checked_definition(definition, documented_identifiers)
        if definition.get("rule_type") == "custom_sql":
            return str(definition.get("sql") or ""), dict(definition.get("params") or {})
        try:
            definition["result_aliases"] = build_result_aliases(definition, self._result_alias_columns(definition))
            return compile_rule({"definition": definition})
        except (AppError, KeyError):
            # Invalid constants must not silently become drafts with empty SQL.
            if is_condition_group(definition) or (definition.get("expression") or {}).get("right_type") == "value":
                raise AppError("VALIDATION_ERROR")
            return "", {}

    def _require_owner(self, user: dict[str, Any], rule_id: int, *, allow_deleted: bool = False) -> dict[str, Any]:
        rule = self.storage.get_rule(rule_id)
        if str(rule["creator_user_id"]) != str(user["id"]):
            self._deny(user, rule_id)
        if rule["status"] == "deleted" and not allow_deleted:
            raise AppError("RULE_DELETED")
        return rule

    def _require_visible_rule(self, user: dict[str, Any], rule_id: int) -> dict[str, Any]:
        rule = self.storage.get_rule(rule_id)
        if not self._visible(user, rule):
            self._deny(user, rule_id)
        if rule["status"] == "deleted":
            raise AppError("RULE_DELETED")
        return rule

    def _require_task_owner(self, user: dict[str, Any], task_id: int) -> dict[str, Any]:
        try:
            task = self.storage.get_task(task_id, with_params=False)
        except KeyError as exc:
            raise AppError("TASK_NOT_FOUND") from exc
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


def _report_period(value: Any) -> date:
    if not isinstance(value, str):
        raise AppError("VALIDATION_ERROR")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise AppError("VALIDATION_ERROR") from None
    if parsed.isoformat() != value:
        raise AppError("VALIDATION_ERROR")
    return parsed
