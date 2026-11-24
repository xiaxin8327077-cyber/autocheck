from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "src" / "auto_check" / "modules" / "data_validation" / "web"


def read(relative: str) -> str:
    return (WEB / relative).read_text(encoding="utf-8")


def scripts() -> dict[str, str]:
    return {path.relative_to(WEB).as_posix(): path.read_text(encoding="utf-8") for path in WEB.rglob("*.js")}


def test_frontend_is_split_by_responsibility_and_uses_menu_routes() -> None:
    files = scripts()
    for relative in (
        "index.js", "state.js", "runtime.js", "api.js", "pages/rules.js", "pages/workbench.js",
        "pages/results.js", "pages/settings.js", "components/rule_table.js", "components/rule_form.js",
        "components/test_panel.js", "components/task_dialog.js",
        "components/pagination.js", "components/dialog.js", "components/history_dialog.js",
    ):
        assert relative in files
    index = files["index.js"]
    for lifecycle in ("mount", "activate", "deactivate", "unmount"):
        assert f"export function {lifecycle}" in index or f"export async function {lifecycle}" in index
    # 页内 Tab 已移除：规则页与结果页由顶部菜单路由区分。
    assert "dv-tabs" not in index and "dv-tab" not in index
    assert "data-validation-results" in index and "routePage" in index
    assert "dv-rules-header" in files["pages/rules.js"]
    assert "dv-main-card" in index and "dv-page-header" in files["components/page_header.js"]
    assert "业务中心 / 数据校验" not in "".join(files.values())
    assert "dv-breadcrumb" not in "".join(files.values())
    assert "← 返回规则列表" not in files["pages/workbench.js"]
    assert "dv-workbench-header" not in files["pages/workbench.js"]
    assert "createDialog" in files["pages/workbench.js"]
    assert "dv-workbench-dialog" in files["pages/workbench.js"]
    assert "shell.append(workbench.element)" not in index
    assert "dv-single-page" in files["pages/workbench.js"]
    # 校验设置：文档导入 / 提示词 / 映射规则三块。
    settings = files["pages/settings.js"]
    for text_value in ("导入文档", "生成提示词", "数据源映射规则", "恢复默认"):
        assert text_value in settings
    api_js = files["api.js"]
    for path in ("/settings/documents", "/settings/prompts", "/settings/source-rules"):
        assert path in api_js
    assert "data-validation-settings" in index and "createSettingsPage" in index
    assert "dv-workbench-grid" not in files["pages/workbench.js"]
    assert len(index.splitlines()) < 280, "生命周期入口不应重新堆积全部页面实现"


def test_full_height_management_list_and_shared_pagination_contract() -> None:
    css = read("styles.css")
    rules = read("pages/rules.js")
    pagination = read("components/pagination.js")
    state = read("state.js")
    for selector in (".dv-page", ".dv-browser", ".dv-main-card", ".dv-panels-host", ".dv-tab-panel"):
        assert selector in css
    assert "flex: 1 1 auto" in css
    assert "min-height: 0" in css
    assert ".dv-table-wrap" in css and "overflow: auto" in css
    for name in ("pagination", "pagination-info", "pagination-controls", "page-btn", "page-current", "pagination-jump"):
        assert name in pagination
    for text in ("上一页", "下一页", "跳至"):
        assert text in pagination  # 图标按钮以 aria-label 提供可读文案
    # 条/页选择使用模块自有下拉，不能再用会被平台全局增强接管的原生 select。
    assert "dv-page-size-trigger" in pagination and "dv-page-size-panel" in pagination
    assert "select(" not in pagination
    assert '"暂无数据"' in state
    assert "`共 ${total} 条，第 ${page} / ${pages} 页`" in state
    assert "page_size: 50" in state
    assert "PAGE_SIZES = [20, 50, 100]" in state
    assert "createPagination" in rules
    assert "setRulePageSize" in rules and "updateRuleFilter" in rules
    # 筛选栏控件宽度必须显式限制：全局 input/select 的 width:100% 会把筛选行撑成竖排。
    assert ".dv-filters .dv-select" in css and "width: 160px" in css
    # 空态/加载/错误提示独占列表区域，不允许与空表头、空表体同时出现。
    assert ".dv-table-feedback:not(:empty)" in css
    rule_table = read("components/rule_table.js")
    assert "feedback.hidden = !hasFeedback" in rule_table
    assert "table.hidden = hasFeedback" in rule_table
    task_list = read("components/task_list.js")
    assert "tableWrap.hidden = hasFeedback" in task_list
    results = read("pages/results.js")
    assert "issueWrap.hidden = hasIssueFeedback" in results


def test_enabled_rule_dialog_has_independent_server_paging_and_bounded_selection() -> None:
    dialog = read("components/task_dialog.js")
    state = read("state.js")
    assert "newEnabledRuleQuery" in dialog
    assert 'status: "enabled"' in state and 'status: "enabled"' in dialog
    assert "state.ruleQuery" not in dialog
    assert "state.rules.items.filter" not in dialog
    assert "loadConvergedPage" in dialog
    assert "updateBoundedSelection" in dialog
    assert "MAX_TASK_RULES = 100" in state
    assert "跨页已选" in dialog
    assert "单个任务最多选择" in state
    # 状态列渲染真实 rule.status，不得写死「已启用」文本。
    assert "labelFor(rule.status, RULE_STATUS_LABELS)" in dialog
    assert 'text: "已启用"' not in dialog


def test_confirmation_requires_real_evidence_and_does_not_auto_test_or_start_task() -> None:
    workbench = read("pages/workbench.js")
    constants = read("constants.js")
    state = read("state.js")
    assert "confirmationReadiness" in state
    for constraint in ("failed_count", "passed_count", "not_run_count", "content_sha256", "version_no", "unresolved"):
        assert constraint in state
    confirm_handler = workbench.split("async function confirmCurrent()", 1)[1].split("function viewModel()", 1)[0]
    assert "api.confirm" in confirm_handler
    assert "api.test" not in confirm_handler
    assert "api.startTask" not in confirm_handler
    assert "detail.content_sha256" in confirm_handler
    assert "passed_count" in workbench
    assert "api.rule(saved.id" in workbench, "保存后必须读取真实 detail"
    assert "visibleSql(detail)" in read("components/test_panel.js")
    assert "confirmFromPage" in workbench
    assert "confirmAction?." in workbench, "确认启用必须经过宿主二次确认"
    assert "createConfirmPanel" not in workbench and "openConfirmDialog" not in workbench
    assert workbench.count("createDialog(") == 1, "手动与 AI 各自打开各自的大弹窗，工厂只有一个弹窗入口"

    # 单页结构：不再有步骤条、步骤门禁、步骤索引与步骤副作用。
    assert "WIZARD_STEPS" not in workbench and "WIZARD_GATES" not in workbench
    assert "stepIndex" not in workbench and "dv-steps" not in workbench
    assert "dv-step-view" not in workbench and "effectKey" not in workbench
    assert "WIZARD" not in constants, "constants 不再维护向导步骤"
    assert "dv-single-page" in workbench and "dv-page-section" in workbench

    # 确认启用按钮按 readiness 启用；测试/确认不得在确认动作里被隐式调用。
    assert "confirmButton.disabled = busy || work.readOnly || !readiness.ready" in workbench

    # 字典唯一来源；字典未命中时回退后端原始 code，不显示空白或编造文案。
    assert "export function labelFor" in constants
    assert "labels[key] : key" in constants
    assert "sql_preview" in read("components/ai_candidate.js")
    assert "复制 SQL" in read("components/ai_candidate.js")
    assert "TEST_CASE_STATUS_LABELS" in read("components/test_panel.js")
    assert "OPERATOR_OPTIONS" in read("components/rule_form.js")


def test_disabled_primary_button_uses_readable_theme_colors() -> None:
    css = read("styles.css")
    scope = '.auto-check-module[data-module="data_validation"] '
    disabled = css.split(scope + 'button:disabled {', 1)[1].split('}', 1)[0]
    primary = css.split(scope + '.dv-button-primary:disabled {', 1)[1].split('}', 1)[0]
    assert "background: var(--dv-disabled)" in disabled
    assert "color: var(--dv-muted)" in primary
    assert "opacity: 1" in primary


def test_ai_inline_picker_styles_cover_platform_enhanced_controls() -> None:
    css = read("styles.css")
    scope = '.auto-check-module[data-module="data_validation"] .dv-ai-request-meta '
    assert scope + '.custom-select-shell {' in css
    trigger = css.split(scope + '.custom-select-trigger {', 1)[1].split('}', 1)[0]
    for declaration in ('height: 22px', 'font-size: 12px', 'border: 0', 'background: transparent', 'box-shadow: none', 'backdrop-filter: none'):
        assert declaration in trigger
    assert scope + '.custom-select-trigger::after {' in css
    assert scope + '.custom-select-trigger:focus-visible {' in css
    shell = css.split(scope + '.custom-select-shell {', 1)[1].split('}', 1)[0]
    assert 'width: auto' in shell and 'min-width: 0' in shell
    assert 'width: auto' in trigger and 'white-space: nowrap' in trigger
    assert scope + '.custom-select-shell.dv-ai-source-select {' not in css
    popup = css.split('.rsp-compact-select-dropdown {', 1)[1].split('}', 1)[0]
    assert 'min-width: 180px' in popup
    dropdown = css.split('.rsp-compact-select-dropdown .custom-select-option {', 1)[1].split('}', 1)[0]
    for declaration in ('font-size: 12px', 'line-height: 1.35', 'padding: 6px 10px'):
        assert declaration in dropdown


def test_manual_and_ai_creation_are_separate_single_page_dialogs() -> None:
    """手动与 AI 各自独立弹窗；均为单页分区，②配置区与③测试区初始隐藏、随操作出现。"""
    constants = read("constants.js")
    form = read("components/rule_form.js")
    workbench = read("pages/workbench.js")
    candidate = read("components/ai_candidate.js")
    rules_page = read("pages/rules.js")

    # 无步骤、无弹内模式切换。
    assert "WIZARD" not in constants
    assert "AI 解析 / 手工配置" not in workbench
    assert "dv-mode-switch" not in form and "dv-mode-button" not in form
    assert "setMode(" not in form and ".setMode" not in form and "setMode:" not in form
    assert "AI 解析与手工配置共用此说明" not in form

    # 单页分区：①②③；配置与测试区初始 hidden，随操作显示。
    assert "dv-single-page" in workbench
    assert "dv-page-section dv-config-section" in workbench and "hidden: true" in workbench
    assert "dv-page-section dv-testing-section" in workbench
    assert "configSection.hidden = !configVisible" in workbench
    assert "testingSection.hidden = !testingVisible" in workbench

    # AI：输入区（需求描述+数据源+模型）与结果配置区分离。
    assert "dv-form-ai-input" in form and "dv-form-ai-config" in form
    assert "groups" in form and "aiInput" in form and "aiConfig" in form
    assert "form.groups.aiInput" in workbench
    assert "form.groups.aiConfig" not in workbench, "AI results must not mount the technical configuration form"
    assert "previewCases" in workbench and "api.testCandidate" in workbench
    assert "form.groups.basics" in workbench and "form.groups.config" in workbench
    assert "createAiCandidatePanel" in workbench

    # AI 分析成功后描述折叠；可展开修改并重新分析。
    assert "descriptionCollapsed" in workbench
    assert "dv-description-collapsed" in workbench
    assert "应用修改 →" in form and "取消修改" in form
    assert "dv-ai-request-meta" in form and "form.groups.aiContext" in workbench
    assert "selectedChoice" in candidate and 'radio.type = "radio"' in candidate
    assert "确认当前口径" in workbench
    assert "item.name ||" in form and '${item.model_name}' not in form
    assert "expandDescription" in workbench
    assert "work.descriptionCollapsed = true" in workbench

    # 保存草稿、测试、确认启用都在同一页内完成。
    assert "保存草稿" in workbench and "dv-verify-actions" in workbench
    assert "dv-confirm-actions" in workbench
    # 分析中必须有明显反馈：按钮文案 + 进度条 + 输入禁用。
    assert "setAnalyzing" in workbench and "setAnalyzing" in form
    assert "AI 分析中…" in form and "dv-ai-progress" in workbench
    assert "AI 正在分析你的校验需求" in workbench
    assert "dv-ai-wait-timer" in workbench and "本次分析耗时较长" in workbench
    assert "inputSection, aiProgress, configSection" in workbench
    css = read("styles.css")
    assert "padding: 26px 32px 24px" in css
    assert "dv-ai-wait-sweep" in css and "dv-ai-wait-track" in workbench
    assert "dv-ai-wait-timer" in workbench and "startElapsed" in workbench
    # 模型可用性测试：表单按钮 + API 路由 + 工作台回传。
    assert "测试可用性" in form and "dv-model-test-status" in form
    assert "testModel" in workbench and "/models/test" in read("api.js")
    assert "测试中…" in form and "短对话可用（规则生成仍需独立校验）" in form
    # 数据源默认选中报送集市（白名单内首个可用数据源）。
    assert "监管报送集市" in form
    assert "min(800px" in read("styles.css"), "弹窗宽度应缩窄到 800px"
    assert ".dv-form-ai-input > .dv-form-grid" not in read("styles.css"), "两列栅格必须满宽以对齐右边缘"

    # 解析失败提供转手工入口，保留用户有效输入。
    assert "switchToManual" in workbench
    assert "转手工继续" in workbench or "转手工继续" in candidate
    assert "seed" in form, "转手工迁移需要表单支持 seed 预填"

    # 入口仍为两个独立按钮，分别打开各自弹窗。
    assert 'onOpenWorkbench({ mode: "manual" })' in rules_page
    assert 'onOpenWorkbench({ mode: "ai" })' in rules_page


def test_ai_creation_auto_names_rule_and_selects_table() -> None:
    """AI 创建时规则名称、目标表与监管报送分类由模型自动生成；输入区仅需求描述+数据源+模型。"""
    form = read("components/rule_form.js")
    workbench = read("pages/workbench.js")
    candidate = read("components/ai_candidate.js")
    assert 'const requestLabel = isAiMode ? "需求描述 *" : "规则说明"' in form
    assert "用一句话描述要校验什么" in form
    # AI 分析由后端读取表清单与真实列结构，前端分析前不要求表名与表结构。
    parse_validate = form.split("validateForParse()", 1)[1].split("},", 1)[0]
    assert "目标物理表名" not in parse_validate
    assert "真实表结构" not in parse_validate
    # 分析成功后自动回填 AI 生成的名称、目标表、分类；结果区可微调。
    assert "if (candidate.table_name) table.value = candidate.table_name" in form
    assert "由 AI 分析自动生成，可修改" in form
    assert "由 AI 分析自动选定，可修改" in form
    assert 'category.value = reportCategoryCode(candidate.report_category)' in form
    assert 'businessKey.value = candidate.business_key || ""' in form
    # 分析请求只携带需求、模型与数据源；表清单与列结构由后端读取。
    parse_handler = workbench.split("async function parse()", 1)[1].split("async function saveDraft()", 1)[0]
    assert "source_id: context.source_id" in parse_handler
    assert "table:" not in parse_handler
    assert "metadataColumns()" not in parse_handler
    # 分析成功后在结果 helper 中用后端返回的真实列结构建映射，再应用候选并折叠描述。
    result_helper = workbench.split("function applyAnalysisResult(", 1)[1].split("function analysisFailure(", 1)[0]
    assert ("page.form.setMetadata({\n"
            "        columns: result.columns, related_columns: result.related_columns || [],\n"
            "        project_columns: result.project_columns || null, project_table: result.project_table || null,\n"
            "        mapping_version: result.mapping_version,\n"
            "      })") in result_helper
    assert "page.form.applyCandidate(result, { regenerate: false })" in result_helper and "work.descriptionCollapsed = true" in result_helper
    # AI 结果呈现业务结论和后端 SQL，不再把内部字段映射做成技术指标面板。
    assert "candidateCondition" in candidate and "检查对象" in candidate
    assert "sql_preview" in candidate and "只读预览" in candidate
    assert 'metric("规则名称"' not in candidate
    assert "aiMark()" in workbench


def test_rules_list_layout_uses_header_card_and_content_card() -> None:
    """规则列表版式：标题+状态胶囊+操作按钮为一张顶部卡片，分类胶囊第二行；筛选与列表在内容卡片。"""
    css = read("styles.css")
    rules = read("pages/rules.js")
    table = read("components/rule_table.js")
    pagination = read("components/pagination.js")
    assert "dv-rules-header" in rules and "dv-rules-header" in css
    assert "dv-rules-header-top" in rules and "dv-rules-title" in rules
    assert "dv-panel-content" in rules and "dv-panel-content" in css
    assert "createPageHeader" not in rules, "规则页标题已并入顶部卡片"
    assert "dv-status-pill" in read("components/stats_cards.js")
    assert "dv-category-pill" in read("components/category_tabs.js")
    for label in ("报送分类", "目标数据表", "版本"):
        assert label in table
    assert "dv-category-badge" in table and "dv-more-menu" in table
    assert "pagination-pages" in pagination and "page-num" in pagination
    assert "上一页" in pagination and "下一页" in pagination


def test_no_dangling_status_or_hardcoded_display_data() -> None:
    """页面不得出现后端不存在的写死状态或写死展示数据。"""
    state = read("state.js")
    rules_page = read("pages/rules.js")
    stats = read("components/stats_cards.js")
    table = read("components/rule_table.js")
    # pending_confirm：后端从不产生该状态，前端字典/筛选/统计/色调全部删除。
    for content, name in ((state, "state.js"), (rules_page, "pages/rules.js"),
                          (stats, "components/stats_cards.js"), (table, "components/rule_table.js")):
        assert "pending_confirm" not in content, f"{name} 不得保留悬空状态 pending_confirm"
    assert "待确认" not in rules_page and "待确认" not in stats
    # 状态胶囊 + 分类胶囊：分类名与数量均来自后端，前端不写死分类。
    category_tabs = read("components/category_tabs.js")
    assert "categories" in category_tabs and "unclassified" in category_tabs
    assert "report_category" in state and "report_category" in rules_page
    for hardcoded in ("人行大集中", "1104", "East5", "中信登"):
        assert hardcoded not in stats and hardcoded not in category_tabs, "胶囊不得写死任何报送分类名"
    # 规则类型字典收敛为实际支持的 field_compare；其余类型回退显示后端原始 code。
    assert 'field_compare: "字段比较"' in state
    for removed_type in ("not_null", "unique", "enum", "amount_equation", "cross_table_exists", "custom_sql"):
        assert f"{removed_type}:" not in state.split("RULE_TYPE_LABELS", 1)[1].split("}", 1)[0]
    # 统计卡初始文案不得写死数字，未就绪时显示「—」。
    assert "草稿 0" not in stats and "待确认 —" not in stats


def test_rule_history_is_real_paginated_expandable_audit_view() -> None:
    history = read("components/history_dialog.js")
    api = read("api.js")
    table = read("components/rule_table.js")
    assert 'action("修改记录", rule, "history",' in table
    assert "ruleHistory" in api and "/history${queryString" in api
    assert "api.ruleHistory(rule.id, requestQuery" in history
    assert "loadConvergedPage" in history and "page_size: 20" in history
    for field in ("operator_name", "operator_user_id", "action_code", "version_no", "summary", "created_at", "changes"):
        assert field in history
    for label in ("变更项", "修改前", "修改后", "展开 ▼", "收起 ▲"):
        assert label in history
    assert "JSON.stringify(value, null, 2)" in history
    assert "修改记录加载失败" in history and "暂无数据" in history
    assert "createDialog" in history


def test_results_only_use_real_task_and_issue_fields_and_poll_can_stop() -> None:
    results = read("pages/results.js")
    for status in ("queued", "running", "completed", "partial_failed", "failed", "cancelled"):
        assert status in read("state.js")
    for field in ("rule_id", "version_no", "created_at", "violation_count", "queryColumns", "queryValue"):
        assert field in results
    for forbidden in ("scanned", "duration", "ai_suggestion", "scan_count", "执行耗时"):
        assert forbidden not in results
    assert "api.cancelTask" in results and "api.retryTask" in results and "api.exportIssues" in results
    assert "taskIssueNotice" in results
    assert "不能据此判定通过" in read("state.js")
    assert "stopPolling" in results and "clearTimer" in results
    index = read("index.js")
    assert "results.stopPolling()" in index
    assert 'target !== "results"' in index


def test_permissions_ownership_and_errors_are_explicit() -> None:
    files = scripts()
    state = files["state.js"]
    assert 'user?.role === "admin"' in state
    for capability in ("dv.view", "dv.manage", "dv.ai_use", "dv.test", "dv.confirm", "dv.run", "dv.view_results", "dv.export"):
        assert capability in state or any(capability in content for content in files.values())
    # 确认启用按钮必须显式携带 dv.confirm 能力码。
    assert 'capability: "dv.confirm"' in files["pages/workbench.js"]
    assert "ownsResource" in files["components/rule_table.js"]
    assert "ownsResource" in files["pages/results.js"]
    assert "sourcesStatus = \"error\"" in files["index.js"]
    assert "modelsStatus = \"error\"" in files["index.js"]
    assert ".catch(() => [])" not in files["index.js"]
    assert "不会将其显示为“未配置”" in files["index.js"]
    assert "data-capability" not in files["components/dom.js"]  # 使用 dataset.capability 输出真实属性
    assert "dataset: { ...dataset, ...(capability ? { capability } : {}) }" in files["components/dom.js"]


def test_no_external_dependencies_mock_data_or_unsafe_dynamic_html() -> None:
    for relative, content in scripts().items():
        # SVG namespace is an identifier passed to createElementNS, not an external request.
        content = content.replace("http://www.w3.org/2000/svg", "SVG_NAMESPACE")
        for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "https://", "http://", "tailwind", "googleapis", "mock", "simulateAi", "resultDetailsMap"):
            assert forbidden not in content, f"{relative}: {forbidden}"
        assert "document.body" not in content
        assert "document.querySelector" not in content
    assert "cdn" not in read("styles.css").lower()


def test_css_is_scoped_light_token_based_and_has_dual_scrollbars() -> None:
    css = read("styles.css")
    scope = '.auto-check-module[data-module="data_validation"]'
    assert css.replace('@import url("./results-replica.css");', "", 1).lstrip().startswith(scope)
    for line in css.splitlines():
        stripped = line.strip()
        if stripped and "{" in stripped and not stripped.startswith("@"):
            assert scope in stripped.split("{", 1)[0], f"unscoped selector: {stripped}"
    for token in (
        "--ui-page-surface", "--ui-panel-surface", "--ui-subsection-surface", "--ui-disabled-surface",
        "--ui-content-border", "--ui-radius", "--ui-thin-scrollbar-size", "--ui-thin-scrollbar-thumb",
    ):
        assert token in css
    assert "#3466D9" in css and "#6AA4FF" in css
    assert css.count("linear-gradient(") == 1, "Logo 蓝渐变只能用于实心主操作"
    assert ".dv-button-primary" in css
    assert "scrollbar-width: thin" in css and "scrollbar-color:" in css
    assert "::-webkit-scrollbar" in css and "::-webkit-scrollbar-thumb" in css
    assert "[data-theme" not in css
    assert not re.search(r"background(?:-color)?\s*:\s*#(?:fff|ffffff|f4f7fb|f1f5f9)\b", css, re.I)


def test_dialog_overlay_close_is_not_wired_and_cleanup_uses_abort_and_generation() -> None:
    dialog = read("components/dialog.js")
    assert 'if (event.target === overlay) event.preventDefault();' in dialog
    assert "if (event.target === overlay) close" not in dialog
    assert 'if (event.key === "Escape") event.preventDefault();' in dialog
    assert "Escape\"])" not in dialog and "Escape\") close" not in dialog
    runtime = read("runtime.js")
    assert "AbortController" in runtime and "generation" in runtime and "channelSequence" in runtime
    assert "controller.abort()" in runtime
    assert "listeners.forEach((remove) => remove())" in runtime
    assert "globalThis.clearTimeout" in runtime
    index = read("index.js")
    assert "runtime.destroy()" in index
    assert "activeHistoryDialog?.close()" in index
    assert "context.root.replaceChildren()" in index
    assert index.index("runtime.destroy()") < index.index("instance = null", index.index("runtime.destroy()"))
