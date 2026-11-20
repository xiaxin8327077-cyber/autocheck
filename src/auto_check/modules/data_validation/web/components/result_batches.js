import { button, element, emptyState, input } from "./dom.js";
import { createDialog } from "./dialog.js";
import { formatDateTime } from "../state.js";
import { taskStatus } from "./task_list.js";
import { resultIcon } from "./result_icons.js";

const BATCH_HEADERS = ["批次号", "执行时间", "覆盖条线", "异常数", "较前批变化"];

// 批次导航和趋势独立于规则内容，模式切换不会重新创建列表或明细节点。
export function createResultBatches({ listen, host, onSelect, onModeChange }) {
  let values = [];
  let activeId = null;
  let mode = "compact";
  let currentPeriod = "";
  let updateStatus = "success";
  let allDialog = null;

  const context = element("span", { className: "dv-batch-context dv-code" });
  const compact = button("", {
    listen, className: "dv-view-mode", ariaLabel: "精简快切", onClick: () => switchMode("compact"),
  });
  compact.append(element("span", { className: "dv-view-mode-label", text: "精简快切" }));
  const review = button("", {
    listen, className: "dv-view-mode", ariaLabel: "趋势审阅", onClick: () => switchMode("trend"),
  });
  review.append(element("span", { className: "dv-view-mode-label", text: "趋势审阅" }));
  const modes = element("div", { className: "dv-view-modes", attrs: { role: "group", "aria-label": "视图模式" } }, compact, review);
  const feedback = element("p", { className: "dv-batch-feedback", hidden: true, attrs: { role: "status" } });
  const heading = element("div", { className: "dv-results-workspace-heading" },
    element("div", { className: "dv-workspace-context" },
      element("strong", { text: "批次与规则核查" }),
      element("span", { className: "dv-workspace-slash", text: "/" }),
      context),
    element("div", { className: "dv-view-controls" }, element("span", { className: "dv-view-label", text: "视图模式" }), modes), feedback);

  const batchId = element("span", { className: "dv-batch-id dv-code" });
  const latestTag = element("span", { className: "dv-batch-latest", text: "最新" });
  const batchTime = element("span", { className: "dv-batch-time dv-code" });
  const batchScope = element("span", { className: "dv-batch-scope" });
  const batchAnomalies = element("span", { className: "dv-batch-anomalies dv-code" });
  const batchChevron = element("span", { className: "dv-batch-chevron", attrs: { "aria-hidden": "true" } }, resultIcon("chevron"));
  const batchSeparator = element("span", { className: "dv-batch-separator", text: "|", attrs: { "aria-hidden": "true" } });
  const trigger = button("", {
    listen, className: "dv-batch-trigger", ariaLabel: "选择执行批次", onClick: togglePopup,
  });
  trigger.append(batchId, latestTag, batchTime, batchScope, batchAnomalies, batchChevron);
  trigger.setAttribute("aria-haspopup", "dialog");
  trigger.setAttribute("aria-expanded", "false");
  trigger.setAttribute("title", "展开批次列表");

  const search = input({ placeholder: batchSearchPlaceholder(), className: "dv-input dv-batch-search" });
  search.setAttribute("aria-label", "搜索执行批次");
  const searchCount = element("span", { className: "dv-batch-match-count dv-code", text: "0/0" });
  const choices = element("div", { className: "dv-batch-choices dv-scroll" });
  const popup = element("div", { className: "dv-batch-popup", hidden: true, attrs: { role: "dialog", "aria-label": "选择执行批次" } },
    element("div", { className: "dv-batch-search-bar" }, element("div", { className: "dv-batch-search-wrap" }, resultIcon("search"), search), searchCount), choices);

  const previous = button("< 上一批", {
    listen, ariaLabel: "上一批次", className: "dv-batch-step", title: "切换到时间更早的上一批", onClick: () => step(1),
  });
  const next = button("下一批 >", {
    listen, ariaLabel: "下一批次", className: "dv-batch-step", title: "切换到时间更新的下一批", onClick: () => step(-1),
  });
  const stepper = element("div", { className: "dv-batch-steps", attrs: { role: "group", "aria-label": "批次步进" } }, previous, next);
  const allCount = element("span", { className: "dv-batch-count dv-code", text: "(0)" });
  const all = button("", {
    listen, className: "dv-button dv-button-plain dv-batch-all", ariaLabel: "查看全部批次", onClick: openAll,
  });
  all.append(element("span", { className: "dv-batch-all-label", text: "全部批次" }), allCount);
  const picker = element("div", { className: "dv-batch-picker", dataset: { resultBatchPicker: "true" } }, trigger, popup);
  const navigator = element("div", { className: "dv-batch-navigator" }, picker, stepper, all);
  const outsideTarget = host.ownerDocument?.addEventListener ? host.ownerDocument : host;
  listen(outsideTarget, "click", event => {
    if (!event.target.closest?.("[data-result-batch-picker]")) closePopup();
  });
  listen(search, "input", () => renderChoices(search.value));
  listen(search, "change", () => renderChoices(search.value));
  listen(choices, "click", selectFromEvent);
  listen(popup, "keydown", (event) => {
    if (event.key !== "Escape") return;
    event.preventDefault();
    closePopup();
    trigger.focus?.();
  });

  const trendCount = element("span", { className: "dv-trend-count-badge dv-code", text: "0 批次" });
  const trendSummary = element("div", { className: "dv-trend-summary", attrs: { "aria-label": "当前批次摘要" } });
  const trendHeading = element("div", { className: "dv-trend-heading" },
    element("div", { className: "dv-trend-heading-left" },
      element("strong", { className: "dv-trend-title", text: "同报送期批次异常趋势" }),
      trendCount), trendSummary);
  const trendStepPrevious = button("< 上一批", { listen, className: "dv-batch-step", ariaLabel: "趋势上一批次", onClick: () => step(1) });
  const trendStepNext = button("下一批 >", { listen, className: "dv-batch-step", ariaLabel: "趋势下一批次", onClick: () => step(-1) });
  trendHeading.append(element("div", { className: "dv-trend-navigation dv-batch-navigator" },
    element("div", { className: "dv-batch-steps" }, trendStepPrevious, trendStepNext),
    button("全部批次", { listen, className: "dv-button dv-button-plain", ariaLabel: "查看趋势全部批次", onClick: openAll })));
  const chart = element("div", { className: "dv-trend-scroll dv-scroll" });
  const trend = element("section", {
    className: "dv-result-trend", hidden: true, attrs: { "aria-label": "同报送期批次异常趋势" },
  }, trendHeading, chart);
  listen(chart, "click", selectFromEvent);

  function batchSearchPlaceholder() { return `搜索批次号、时间或条线（共 ${values.length} 批次）...`; }
  function periodLabel() { return currentPeriod || values[0]?.report_period || "—"; }
  function currentTask() { return values.find((task) => Number(task.id) === Number(activeId)) || null; }
  function isActive(task) { return Number(task.id) === Number(activeId); }
  function isExplicitFull(task) { return task?.execution_scope === "all" || task?.is_full === true; }
  function isTruncated(task) { return task?.summary?.truncated === true; }
  function anomalyCount(task) {
    const raw = task?.summary?.issue_count;
    if (raw === null || raw === undefined || raw === "") return null;
    const count = Number(raw);
    return Number.isFinite(count) ? Math.max(0, count) : null;
  }
  function categoryName(category) {
    if (typeof category === "string") return category;
    return String(category?.name || category?.label || category?.code || "未命名条线");
  }
  function timeOfDay(task) {
    const text = formatDateTime(task?.created_at);
    const match = /\d{1,2}:\d{2}:\d{2}/.exec(text);
    return match ? match[0].padStart(8, "0") : "—";
  }
  function unknownScopeTag() { return element("span", { className: "dv-batch-scope-pill is-unknown", text: "未采集" }); }
  function scopeNodes(task) {
    const categories = task?.categories || [];
    if (isExplicitFull(task)) {
      return [element("span", {
        className: "dv-batch-scope-pill is-full", text: `全量 (${categories.length}条线)`,
        attrs: { title: "服务端明确标记的全量执行范围" },
      })];
    }
    if (!categories.length) return [unknownScopeTag()];
    return categories.map((category) => element("span", { className: "dv-batch-scope-pill", text: categoryName(category) }));
  }
  function anomalyText(task) {
    const count = anomalyCount(task);
    if (count === null) return "异常未采集";
    return `${count}${isTruncated(task) ? "+" : ""} 异常`;
  }
  function partialText(task) {
    if (isTruncated(task)) return "结果截断";
    if (Number(task?.summary?.failed_count) > 0) return "有未成功项";
    if (task?.status !== "completed") return taskStatus(task).label;
    if (anomalyCount(task) === null) return "摘要未采集";
    return "";
  }
  function deltaInfo(task) {
    const summary = task?.summary;
    const coverage = item => (item.categories || []).map(c => typeof c === "string" ? c : c.code || c.name).sort().join("\u001f");
    const previous = values.find(item => Number(item.id) < Number(task.id) && item.report_period === task.report_period
      && coverage(task) && coverage(item) === coverage(task) && item.status === "completed"
      && !item.summary?.truncated && !Number(item.summary?.failed_count));
    const delta = typeof task.comparison_delta === "number" ? task.comparison_delta
      : previous && anomalyCount(task) !== null && anomalyCount(previous) !== null ? anomalyCount(task) - anomalyCount(previous) : null;
    if (!summary || summary.truncated === true || task.status !== "completed" || Number(summary.failed_count)) {
      return { text: "—", tone: "unknown", title: "较前批变化未提供或不具备可比条件" };
    }
    if (delta === null) return { text: isExplicitFull(task) ? "基准" : "首跑", tone: "baseline", title: "当前记录中尚无更早的同覆盖条线批次" };
    const detail = previous ? `较前次同覆盖条线 #${previous.id}（${formatDateTime(previous.created_at)}，${previous.summary.rule_count} 条规则，异常 ${anomalyCount(previous)} 条）` : "较前次同范围批次";
    if (delta === 0) return { text: "持平", tone: "flat", title: "较前批无变化" };
    return {
      text: `${delta > 0 ? "+" : ""}${delta}`,
      tone: delta > 0 ? "up" : "down",
      title: `${detail}${delta > 0 ? "增加" : "减少"} ${Math.abs(delta)} 条；当前 ${summary.rule_count} 条规则，变化不直接代表修复数量。`,
    };
  }
  function searchText(task) {
    const categories = (task.categories || []).flatMap((category) => [
      categoryName(category), typeof category === "object" ? category?.code : "",
    ]).filter(Boolean);
    const parts = [String(task.id), `#${task.id}`, formatDateTime(task.created_at), timeOfDay(task), ...categories];
    if (isExplicitFull(task)) parts.push("全量", `全量 ${(task.categories || []).length}条线`);
    return parts.join(" ").toLowerCase();
  }
  function filterBatches(keyword) {
    const query = String(keyword || "").trim().toLowerCase();
    return query ? values.filter((task) => searchText(task).includes(query)) : values;
  }

  function closePopup() {
    popup.hidden = true;
    trigger.setAttribute("aria-expanded", "false");
  }
  function togglePopup() {
    if (!values.length) { closePopup(); return; }
    popup.hidden = !popup.hidden;
    trigger.setAttribute("aria-expanded", String(!popup.hidden));
    if (!popup.hidden) {
      renderChoices(search.value);
      search.focus?.();
    }
  }
  function switchMode(value) {
    mode = value;
    trend.hidden = mode !== "trend";
    compact.classList.toggle("is-active", mode === "compact");
    review.classList.toggle("is-active", mode === "trend");
    compact.setAttribute("aria-pressed", String(mode === "compact"));
    review.setAttribute("aria-pressed", String(mode === "trend"));
    compact.setAttribute("aria-selected", String(mode === "compact"));
    review.setAttribute("aria-selected", String(mode === "trend"));
    onModeChange?.(mode);
  }
  function selectFromEvent(event) {
    const target = event.target.closest?.("[data-result-batch]");
    if (!target) return;
    closePopup();
    allDialog?.close();
    return onSelect(Number(target.dataset.resultBatch));
  }
  function step(direction) {
    const index = values.findIndex((task) => Number(task.id) === Number(activeId));
    const task = values[index + direction];
    if (task) return onSelect(task.id);
  }

  function renderTrigger() {
    const selected = currentTask();
    const latest = values[0];
    batchId.textContent = selected
      ? `批次 #${selected.id}`
      : updateStatus === "loading" ? "正在加载批次…" : updateStatus === "error" ? "批次加载失败" : "暂无执行批次";
    const isLatest = Boolean(selected && latest && Number(selected.id) === Number(latest.id));
    latestTag.hidden = false;
    latestTag.textContent = "最新";
    trigger.replaceChildren(batchId, ...(isLatest ? [latestTag] : []), batchSeparator, batchTime, batchScope, batchAnomalies, batchChevron);
    batchTime.textContent = selected ? formatDateTime(selected.created_at) : "—";
    batchAnomalies.textContent = selected ? anomalyText(selected) : "异常未采集";
    batchScope.replaceChildren(...(selected ? scopeNodes(selected) : [unknownScopeTag()]));
    trigger.disabled = !values.length;
    trigger.setAttribute("aria-expanded", String(!popup.hidden && Boolean(values.length)));
  }

  function batchRow(task) {
    const active = isActive(task);
    const latest = values[0];
    const open = button(`#${task.id}`, {
      className: `dv-batch-open dv-code${active ? " is-active" : ""}`,
      dataset: { resultBatch: task.id },
      ariaLabel: `选择批次 #${task.id}`,
    });
    if (active) open.setAttribute("aria-current", "true");
    const numberCell = element("td", { className: "dv-batch-cell dv-batch-number-cell dv-code" }, open);
    if (latest && Number(task.id) === Number(latest.id)) {
      numberCell.append(" ", element("span", { className: "dv-batch-latest", text: "最新" }));
    }
    const count = anomalyCount(task);
    const delta = deltaInfo(task);
    const anomalyCell = element("td", {
      className: `dv-batch-cell dv-batch-anomaly-count dv-code${count === null ? "" : count > 0 ? " is-warning" : " is-zero"}${isTruncated(task) ? " is-truncated" : ""}`,
      text: count === null ? "—" : `${count}${isTruncated(task) ? "+" : ""}`,
      attrs: { title: count === null ? "异常数未采集" : isTruncated(task) ? "异常数至少为该值，结果已截断" : `异常 ${count} 条` },
    });
    return element("tr", {
      className: `dv-batch-entry${active ? " is-active" : ""}`,
      dataset: { resultBatch: task.id },
      attrs: { "aria-selected": String(active) },
    },
    numberCell,
    element("td", { className: "dv-batch-cell dv-batch-time-cell dv-code", text: formatDateTime(task.created_at) }),
    element("td", { className: "dv-batch-cell dv-batch-scope-cell" },
      element("div", { className: "dv-batch-scope" }, ...scopeNodes(task))),
    anomalyCell,
    element("td", { className: "dv-batch-cell dv-batch-delta-cell" }, element("span", { className: `dv-batch-delta dv-code is-${delta.tone}`, text: `${delta.tone === "down" ? "↓ " : delta.tone === "up" ? "↑ " : ""}${delta.text}`, attrs: { title: delta.title } })));
  }

  function renderBatchTable(container, keyword, emptyTitle = "未找到匹配的批次") {
    const filtered = filterBatches(keyword);
    const body = element("tbody", { className: "dv-batches-body" });
    if (!filtered.length) {
      body.append(element("tr", {}, element("td", {
        className: "dv-batches-empty", text: emptyTitle, attrs: { colspan: "5" },
      })));
    } else {
      filtered.forEach((task) => body.append(batchRow(task)));
    }
    const table = element("table", { className: "dv-batch-table" },
      element("thead", { className: "dv-batches-head" }, element("tr", {},
        ...BATCH_HEADERS.map((label, index) => element("th", {
          className: `dv-batches-th${index >= 3 ? " is-numeric" : ""}`, text: label, attrs: { scope: "col" },
        })))),
      body);
    container.replaceChildren(table);
    return filtered.length;
  }

  function renderChoices(keyword = search.value) {
    const matched = renderBatchTable(choices, keyword,
      String(keyword || "").trim() ? "未找到匹配的批次" : updateStatus === "loading" ? "正在加载执行批次…" : updateStatus === "error" ? "批次加载失败" : "暂无执行批次");
    searchCount.textContent = `${matched}/${values.length}`;
  }

  function renderChart() {
    const tasks = [...values].reverse();
    trendCount.textContent = `${tasks.length} 批次`;
    chart.replaceChildren();
    if (!tasks.length) {
      chart.append(emptyState("暂无可展示的批次", "执行校验后可在此查看各批次异常数"));
      return;
    }

    const maximum = Math.max(1, ...tasks.map((task) => anomalyCount(task) ?? 0));
    const plot = element("div", { className: "dv-trend-plot" });
    plot.setAttribute("style", `min-width: ${Math.max(1, tasks.length) * 140}px`);
    const canvas = element("div", { className: "dv-trend-canvas" });
    const grid = element("div", { className: "dv-trend-gridlines", attrs: { "aria-hidden": "true" } },
      element("span", { className: "dv-trend-gridline" }),
      element("span", { className: "dv-trend-gridline" }),
      element("span", { className: "dv-trend-gridline" }));
    const columns = element("div", { className: "dv-trend-columns" });
    const line = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    line.classList.add("dv-trend-line");
    line.setAttribute("aria-hidden", "true");
    line.setAttribute("viewBox", `0 0 ${Math.max(100, tasks.length * 100)} 100`);
    line.setAttribute("preserveAspectRatio", "none");
    let points = [];
    const flushSegment = () => {
      if (points.length > 1) {
        const segment = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
        segment.setAttribute("points", points.join(" "));
        segment.setAttribute("fill", "none");
        segment.setAttribute("stroke", "currentColor");
        segment.setAttribute("stroke-width", "1.75");
        segment.setAttribute("stroke-linejoin", "round");
        segment.setAttribute("stroke-linecap", "round");
        segment.setAttribute("vector-effect", "non-scaling-stroke");
        line.append(segment);
      }
      points = [];
    };

    tasks.forEach((task, index) => {
      const count = anomalyCount(task);
      const height = count === null ? 0 : count === 0 ? 4 : Math.max(10, Math.round((count / maximum) * 82));
      if (count === null) flushSegment();
      else points.push(`${index * 100 + 50},${100 - height}`);

      const info = taskStatus(task);
      const partial = partialText(task);
      const active = isActive(task);
      const point = element("button", {
        className: `dv-trend-point${active ? " is-active" : ""}${partial ? " is-partial" : ""}`,
        dataset: { resultBatch: task.id },
        attrs: {
          type: "button",
          "aria-pressed": String(active),
          "aria-label": `批次 #${task.id}，${info.label}，${count === null ? "摘要未采集" : `异常 ${count}${isTruncated(task) ? " 以上" : ""} 条`}`,
          title: `${formatDateTime(task.created_at)} · ${info.label}\n${task.summary?.rule_count ?? "—"} 条规则；异常 ${count ?? "—"}${isTruncated(task) ? "+（截断）" : ""}`,
        },
      });
      if (active) point.append(element("span", { className: "dv-trend-column-bg", attrs: { "aria-hidden": "true" } }));
      const barWrap = element("span", { className: "dv-trend-bar-wrap" });
      barWrap.setAttribute("style", `height: ${height}%`);
      barWrap.append(element("strong", {
        className: "dv-trend-count dv-code", text: count === null ? "—" : `${count}${isTruncated(task) ? "+" : ""}`,
      }));
      if (count !== null) {
        barWrap.append(element("span", { className: "dv-trend-dot" }), element("span", { className: "dv-trend-bar" }));
      }
      point.append(barWrap);
      if (partial) point.append(element("span", { className: "dv-trend-state", text: partial }));
      columns.append(point);
    });
    flushSegment();
    canvas.append(grid, line, columns);
    plot.append(canvas);

    const axis = element("div", { className: "dv-trend-axis" });
    tasks.forEach((task) => {
      const active = isActive(task);
      axis.append(element("button", {
        className: `dv-trend-axis-item${active ? " is-active" : ""}`,
        dataset: { resultBatch: task.id },
        attrs: { type: "button", "aria-label": `查看批次 #${task.id}，${timeOfDay(task)}` },
      },
      element("span", { className: "dv-trend-axis-id dv-code", text: `#${task.id}` }),
      element("span", { className: "dv-trend-axis-time dv-code", text: formatDateTime(task.created_at) })));
    });
    plot.append(axis);
    chart.append(plot);

    const first = tasks[0];
    const last = tasks[tasks.length - 1];
    chart.append(element("p", {
      className: "dv-trend-range dv-code",
      text: tasks.length === 1 ? `批次 #${first.id} · ${formatDateTime(first.created_at)}` : `批次 #${first.id}–#${last.id} · ${formatDateTime(first.created_at)}–${formatDateTime(last.created_at)}`,
    }));
  }

  function renderState() {
    const selected = currentTask();
    context.textContent = `${periodLabel()} · 共 ${values.length} 批次${selected ? ` · 当前 #${selected.id}` : ""}`;
    renderTrigger();
    search.placeholder = batchSearchPlaceholder();
    allCount.textContent = `(${values.length})`;
    all.disabled = !values.length;
    searchCount.textContent = `0/${values.length}`;
    const index = values.findIndex((task) => Number(task.id) === Number(activeId));
    previous.disabled = index < 0 || index >= values.length - 1;
    next.disabled = index <= 0;
    trendStepPrevious.disabled = previous.disabled; trendStepNext.disabled = next.disabled;
    trendSummary.replaceChildren();
    if (selected) {
      const data = selected.summary || {}, delta = deltaInfo(selected);
      const group = (label, ...content) => element("div", { className: "dv-trend-summary-group" }, element("span", { className: "dv-trend-summary-label", text: label }), ...content);
      trendSummary.append(
        group("当前批次", element("strong", { className: "dv-code", text: `#${selected.id}` }), element("span", { className: "dv-code dv-muted", text: formatDateTime(selected.created_at) })),
        group("规则执行", element("strong", { className: "dv-code", text: `${Number(data.completed_count || 0) + Number(data.failed_count || 0)}/${data.rule_count ?? "—"}` }), element("span", { className: "dv-muted", text: `已完成 · 未成功 ${data.failed_count ?? 0}` })),
        group("异常总数", element("strong", { className: "dv-trend-summary-anomalies dv-code", text: `${anomalyCount(selected) ?? "—"}${isTruncated(selected) ? "+" : ""} 条` }),
          element("span", { className: `dv-batch-delta dv-code is-${delta.tone}`, text: `${delta.tone === "down" ? "↓ " : delta.tone === "up" ? "↑ " : ""}${delta.text}`, attrs: { title: delta.title } })),
        group("覆盖条线", element("span", { className: "dv-batch-scope" }, ...(selected.categories || []).map(category => element("span", { className: "dv-batch-scope-pill", text: categoryName(category) })))));
    }
    renderChoices();
    renderChart();
    allDialog?.refresh?.();
  }

  function openAll() {
    closePopup();
    if (!values.length || allDialog) return;
    const dialog = createDialog({
      host, title: "当日全部执行批次", subtitle: `${periodLabel()} · 共 ${values.length} 批次`,
      className: "dv-results-batches-drawer", onClose: () => { allDialog = null; },
    });
    allDialog = dialog;
    dialog.bind(dialog.element, "click", event => { if (event.target === dialog.element) dialog.close(); });
    const filter = input({ placeholder: batchSearchPlaceholder(), className: "dv-input dv-batches-drawer-search" });
    filter.setAttribute("aria-label", "搜索全部批次");
    const count = element("span", { className: "dv-batches-drawer-count dv-code" });
    const meta = element("p", { className: "dv-batches-drawer-meta dv-muted" });
    const list = element("div", { className: "dv-batches-drawer-list dv-scroll" });
    dialog.body.append(element("div", { className: "dv-batches-drawer-toolbar" }, filter, count), meta, list);
    const refresh = () => {
      const matched = renderBatchTable(list, filter.value, "无匹配的执行批次");
      count.textContent = `${matched}/${values.length}`;
      meta.textContent = `${periodLabel()} · 共 ${values.length} 批次（当前显示 ${matched} 条）`;
      filter.placeholder = batchSearchPlaceholder();
    };
    dialog.bind(filter, "input", refresh);
    dialog.bind(filter, "change", refresh);
    dialog.bind(list, "click", selectFromEvent);
    dialog.footer.append(button("关闭", { listen: dialog.bind, onClick: dialog.close }));
    dialog.refresh = refresh;
    refresh();
  }

  renderState();
  switchMode(mode);

  return {
    heading, navigator, trend,
    update(tasks, selectedId, { status = "success", error = "", reportPeriod = "" } = {}) {
      values = Array.isArray(tasks) ? [...tasks].sort((a, b) => Number(b.id) - Number(a.id)) : [];
      activeId = selectedId;
      updateStatus = status;
      if (reportPeriod) currentPeriod = reportPeriod;
      feedback.hidden = status !== "error";
      feedback.textContent = status === "error"
        ? `${values.length ? "批次刷新失败，当前展示上次加载的结果" : "批次加载失败"}：${error || "请稍后重试"}`
        : "";
      if (!values.length) closePopup();
      renderState();
    },
    close() {
      closePopup();
      allDialog?.close();
    },
  };
}
