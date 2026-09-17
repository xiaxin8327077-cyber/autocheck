import { button, node } from "./dom.js";
import { openTokenDialog } from "./external_api_token_dialog.js";

const BOARD_NAMES = Object.freeze({
  report_submission: "金融监管报表报送大屏",
  reporting_process: "金融监管报送流程大屏",
});

const STATUS_TEXT = Object.freeze({
  success: "成功",
  partial: "部分成功",
  error: "失败",
});

const TOKEN_SOURCE_TEXT = Object.freeze({
  managed: "系统生成",
  environment: "环境变量兼容",
  none: "未配置",
});

export function monitorBoardName(value) {
  return BOARD_NAMES[value] || value || "-";
}

export function monitorStatusText(value) {
  return STATUS_TEXT[value] || value || "-";
}

export function formatMonitorDateTime(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "-";
  const pad = (part) => String(part).padStart(2, "0");
  return `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())} ${pad(parsed.getHours())}:${pad(parsed.getMinutes())}:${pad(parsed.getSeconds())}`;
}

function tokenSourceText(value) {
  return TOKEN_SOURCE_TEXT[value] || "未知";
}

export function monitorIpWhitelistText(summary) {
  const enabled = Boolean(summary?.ip_whitelist_enabled);
  const count = Number(summary?.ip_whitelist_count || 0);
  // 状态标签只展示启用状态和数量，绝不展示具体 IP。
  return enabled ? `IP 白名单：已启用（${count} 个）` : "IP 白名单：未启用";
}

function monitorFilterField(labelText, control) {
  const field = node("label", { className: "dm-monitor-filter-field" });
  field.append(node("span", { text: labelText }), control);
  return field;
}

export function renderExternalApiMonitor(options) {
  const { state, onBack, onFilterChange, onSearch, onClear, onPageChange, onRetry, onGenerateToken, canManageToken, onConfigureIpWhitelist, canManageIpWhitelist } = options;
  const page = node("section", { className: "dm-monitor-page" });
  const card = node("section", { className: "dm-management-card dm-monitor-card" });

  const header = node("header", { className: "dm-monitor-header" });
  const backBtn = button("返回看板管理", "dm-button dm-button-secondary", onBack);
  backBtn.setAttribute("aria-label", "返回看板管理");
  header.append(backBtn);
  header.append(node("h2", { text: "接口监控" }));
  const refreshBtn = button("刷新", "dm-button dm-button-secondary dm-monitor-refresh", onRetry, { disabled: state.monitorLoading });
  refreshBtn.setAttribute("aria-label", "刷新监控数据");
  header.append(refreshBtn);
  card.append(header);

  if (state.monitorError) {
    const feedback = node("section", { className: "dm-monitor-feedback is-error" });
    feedback.append(node("p", { text: state.monitorError }));
    feedback.append(button("重新加载", "dm-button dm-button-secondary", onRetry, { disabled: state.monitorLoading }));
    card.append(feedback);
  } else if (state.monitorLoading && !state.monitorSummary && !state.monitorCalls) {
    card.append(node("section", { className: "dm-monitor-feedback is-loading", text: "正在加载接口监控…" }));
  }

  const statusSection = node("section", { className: "dm-monitor-status-section" });
  const summary = state.monitorSummary;
  if (summary) {
    const statusText = summary.enabled ? "接口已启用" : "接口未启用";
    const overview = node("div", { className: "dm-monitor-status-overview" });
    const badges = node("div", { className: "dm-monitor-status-badges" });
    badges.append(
      node("span", { className: `dm-monitor-status-badge ${summary.enabled ? "is-enabled" : "is-disabled"}`, text: statusText }),
      node("span", {
        className: `dm-monitor-status-badge dm-monitor-ip-whitelist-badge ${summary.ip_whitelist_enabled ? "is-enabled" : "is-disabled"}`,
        text: monitorIpWhitelistText(summary),
      }),
      node("span", { className: `dm-monitor-status-badge ${summary.token_source ? "has-source" : "no-source"}`, text: `来源：${tokenSourceText(summary.token_source)}` }),
      ...(summary.token_source === "managed" && summary.token_generated_at
        ? [node("span", { className: "dm-monitor-token-generated-at", text: `生成时间：${formatMonitorDateTime(summary.token_generated_at)}` })]
        : []),
      node("span", { className: "dm-monitor-retention", text: `记录保留 ${summary.retention_days} 天` }),
    );
    overview.append(badges);
    const showTokenAction = canManageToken && typeof onGenerateToken === "function";
    const showWhitelistAction = canManageIpWhitelist && typeof onConfigureIpWhitelist === "function";
    if (showTokenAction || showWhitelistAction) {
      const actionRow = node("div", { className: "dm-monitor-status-actions" });
      if (showTokenAction) {
        const configured = summary.token_configured;
        const actionBtn = button(
          configured ? "更新 Token" : "生成 Token",
          `dm-button ${configured ? "dm-button-secondary" : "dm-button-primary"} dm-monitor-token-action`,
          () => onGenerateToken({ configured }),
        );
        actionRow.append(actionBtn);
      }
      if (showWhitelistAction) {
        actionRow.append(button(
          "配置 IP 白名单",
          "dm-button dm-button-secondary dm-monitor-ip-whitelist-action",
          () => onConfigureIpWhitelist(),
        ));
      }
      overview.append(actionRow);
    }
    statusSection.append(overview);
    const endpointList = node("div", { className: "dm-monitor-endpoint-list" });
    (summary.endpoints || []).forEach((endpoint) => {
      const endpointRow = node("div", { className: "dm-monitor-endpoint-row" });
      endpointRow.append(
        node("span", { className: "dm-monitor-endpoint-name", text: endpoint.name }),
        node("code", { className: "dm-monitor-endpoint-path", text: endpoint.path }),
      );
      endpointList.append(endpointRow);
    });
    statusSection.append(endpointList);
  }
  card.append(statusSection);

  if (summary) {
    const metrics = node("section", { className: "dm-monitor-metrics" });
    const stats = summary.last_24_hours;
    const avgText = stats.total > 0 ? `${stats.average_duration_ms} ms` : "-";
    [
      ["近 24 小时调用", String(stats.total), "is-total"],
      ["成功", String(stats.success), "is-success"],
      ["部分成功", String(stats.partial), "is-partial"],
      ["失败", String(stats.failed), "is-failed"],
      ["平均耗时", avgText, "is-duration"],
    ].forEach(([label, value, tone]) => {
      const item = node("div", { className: `dm-monitor-metric ${tone}` });
      item.append(node("span", { className: "dm-monitor-metric-label", text: label }));
      item.append(node("span", { className: "dm-monitor-metric-value", text: value }));
      metrics.append(item);
    });
    card.append(metrics);
  }

  const filters = node("div", { className: "dm-monitor-filters" });
  const boardSelect = node("select", { className: "dm-filter-select" });
  boardSelect.append(node("option", { text: "全部看板", attrs: { value: "" } }));
  boardSelect.append(node("option", { text: "金融监管报表报送大屏", attrs: { value: "report_submission" } }));
  boardSelect.append(node("option", { text: "金融监管报送流程大屏", attrs: { value: "reporting_process" } }));
  boardSelect.value = state.monitorFilters.board_code;
  boardSelect.disabled = state.monitorLoading;
  boardSelect.addEventListener("change", () => onFilterChange("board_code", boardSelect.value));
  filters.append(monitorFilterField("看板", boardSelect));

  const statusSelect = node("select", { className: "dm-filter-select" });
  statusSelect.append(node("option", { text: "全部状态", attrs: { value: "" } }));
  statusSelect.append(node("option", { text: "成功", attrs: { value: "success" } }));
  statusSelect.append(node("option", { text: "部分成功", attrs: { value: "partial" } }));
  statusSelect.append(node("option", { text: "失败", attrs: { value: "error" } }));
  statusSelect.value = state.monitorFilters.result_status;
  statusSelect.disabled = state.monitorLoading;
  statusSelect.addEventListener("change", () => onFilterChange("result_status", statusSelect.value));
  filters.append(monitorFilterField("业务状态", statusSelect));

  const ipInput = node("input", { className: "dm-filter-input", attrs: { type: "text", placeholder: "调用方 IP" } });
  ipInput.value = state.monitorFilters.caller_ip;
  ipInput.disabled = state.monitorLoading;
  ipInput.addEventListener("input", () => onFilterChange("caller_ip", ipInput.value));
  filters.append(monitorFilterField("调用方 IP", ipInput));

  const startInput = node("input", { className: "dm-filter-input", attrs: { type: "date", "aria-label": "开始日期" } });
  startInput.value = state.monitorFilters.started_at;
  startInput.disabled = state.monitorLoading;
  startInput.addEventListener("input", () => onFilterChange("started_at", startInput.value));
  filters.append(monitorFilterField("开始日期", startInput));

  const endInput = node("input", { className: "dm-filter-input", attrs: { type: "date", "aria-label": "结束日期" } });
  endInput.value = state.monitorFilters.ended_at;
  endInput.disabled = state.monitorLoading;
  endInput.addEventListener("input", () => onFilterChange("ended_at", endInput.value));
  filters.append(monitorFilterField("结束日期", endInput));

  const searchBtn = button("查询", "dm-button dm-button-secondary", onSearch, { disabled: state.monitorLoading });
  const resetBtn = button("重置", "dm-button dm-button-secondary dm-monitor-reset", onClear, { disabled: state.monitorLoading });
  const filterActions = node("div", { className: "dm-monitor-filter-actions" });
  filterActions.append(searchBtn, resetBtn);
  filters.append(filterActions);
  card.append(filters);

  const tableWrap = node("div", { className: "dm-monitor-table-wrap" });
  const table = node("table", { className: "result-table management-list-table dm-monitor-table" });
  const thead = node("thead");
  const headerRow = node("tr");
  ["调用时间", "调用方 IP", "看板", "HTTP 状态", "业务状态", "失败区域数", "耗时", "request_id", "错误摘要"].forEach((text) => {
    headerRow.append(node("th", { text }));
  });
  thead.append(headerRow);
  table.append(thead);
  const tbody = node("tbody");
  const calls = state.monitorCalls;
  if (calls && calls.items && calls.items.length > 0) {
    calls.items.forEach((item) => {
      const row = node("tr");
      row.append(node("td", { text: formatMonitorDateTime(item.called_at) }));
      row.append(node("td", { className: "dm-monitor-ip", text: item.caller_ip || "-", attrs: { title: item.caller_ip || "-" } }));
      row.append(node("td", { text: monitorBoardName(item.board_code) }));
      row.append(node("td", { text: String(item.http_status || "-") }));
      const statusCell = node("td");
      statusCell.append(node("span", {
        className: `management-list-status dm-monitor-result-status is-${item.result_status || "unknown"}`,
        text: monitorStatusText(item.result_status),
      }));
      row.append(statusCell);
      row.append(node("td", { text: String(item.failed_region_count ?? 0) }));
      row.append(node("td", { text: item.duration_ms != null ? `${item.duration_ms} ms` : "-" }));
      row.append(node("td", { className: "dm-monitor-request-id", text: item.request_id || "-", attrs: { title: item.request_id || "-" } }));
      const errorCell = node("td", { className: "dm-monitor-error" });
      const errorText = item.error_message || "-";
      errorCell.append(node("span", { text: errorText.length > 50 ? errorText.slice(0, 50) + "…" : errorText, attrs: { title: errorText } }));
      row.append(errorCell);
      tbody.append(row);
    });
  } else if (!state.monitorLoading && !(state.monitorError && !calls)) {
    const emptyRow = node("tr");
    const emptyCell = node("td", { attrs: { colspan: "9" } });
    emptyCell.append(node("p", { className: "dm-empty", text: "暂无数据" }));
    emptyRow.append(emptyCell);
    tbody.append(emptyRow);
  } else {
    const feedbackRow = node("tr");
    const feedbackCell = node("td", { attrs: { colspan: "9" } });
    feedbackCell.append(node("p", {
      className: "dm-empty",
      text: state.monitorLoading ? "正在加载调用记录…" : "调用记录加载失败，请重新加载",
    }));
    feedbackRow.append(feedbackCell);
    tbody.append(feedbackRow);
  }
  table.append(tbody);
  tableWrap.append(table);
  card.append(tableWrap);

  const pagination = node("div", { className: "pagination" });
  const paginationInfo = node("div", { className: "pagination-info" });
  const total = calls?.total || 0;
  const totalPages = calls?.total_pages || 1;
  const currentPage = calls?.page || 1;
  paginationInfo.append(node("span", { text: total > 0 ? `共 ${total} 条，第 ${currentPage} / ${totalPages} 页` : "暂无数据" }));
  pagination.append(paginationInfo);
  const controls = node("div", { className: "pagination-controls" });
  const prevBtn = button("◀", "page-btn", () => onPageChange("prev"));
  prevBtn.setAttribute("aria-label", "上一页");
  if (state.monitorLoading || currentPage <= 1) prevBtn.disabled = true;
  controls.append(prevBtn);
  const currentSpan = node("span", { className: "page-current", text: total > 0 ? String(currentPage) : "-" });
  controls.append(currentSpan);
  const nextBtn = button("▶", "page-btn", () => onPageChange("next"));
  nextBtn.setAttribute("aria-label", "下一页");
  if (state.monitorLoading || currentPage >= totalPages) nextBtn.disabled = true;
  controls.append(nextBtn);
  const jump = node("label", { className: "pagination-jump" });
  jump.append(node("span", { text: "跳至" }));
  const jumpInput = node("input", { attrs: { type: "text", inputmode: "numeric", "aria-label": "跳转页码" } });
  jumpInput.disabled = state.monitorLoading;
  jumpInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") onPageChange("jump", jumpInput.value);
  });
  jump.append(jumpInput, node("span", { text: "页" }));
  controls.append(jump);
  pagination.append(controls);
  card.append(pagination);

  page.append(card);
  return page;
}
