import {
  formatDateTime, hasCapability, ownsResource, RULE_STATUS_LABELS, RULE_TYPE_LABELS,
} from "../state.js";
import { button, element, emptyState, statusBadge } from "./dom.js";

const STATUS_TONES = { enabled: "success", disabled: "neutral", draft: "info" };
const CATEGORY_TONES = ["accent", "teal", "orange", "purple", "slate"];

function action(label, rule, name, { hidden = false, disabled = false, title = "", capability = "", danger = false } = {}) {
  return button(label, {
    className: `dv-table-action${danger ? " is-danger" : ""}`,
    dataset: { action: name, ruleId: rule.id }, hidden, disabled, title, capability,
  });
}

function ruleRow(rule, user, selected, { categoryNames = {}, categoryTones = {} } = {}) {
  const owner = ownsResource(user, rule);
  const manage = hasCapability(user, "dv.manage");
  const run = hasCapability(user, "dv.run");
  const checkbox = element("input", { dataset: { selectRule: rule.id }, attrs: { "aria-label": `选择规则 ${rule.rule_code}` } });
  checkbox.type = "checkbox";
  checkbox.checked = selected;
  const categoryName = categoryNames[rule.report_category] || rule.report_category || "—";
  const categoryTone = CATEGORY_TONES[Number(categoryTones[rule.report_category]) || 0] || "accent";
  const tone = STATUS_TONES[rule.status] || "neutral";
  const menu = element("div", { className: "dv-more-menu", hidden: true },
    action("修改记录", rule, "history"),
    action("复制", rule, "copy", { hidden: !manage, capability: "dv.manage" }),
    action("停用", rule, "disable", {
      hidden: !manage, capability: "dv.manage", danger: true,
      disabled: !owner || rule.status !== "enabled",
      title: !owner ? "仅规则创建人可停用" : rule.status !== "enabled" ? "仅已启用规则可停用" : "停用规则",
    }));
  const row = element("tr", { dataset: { ruleId: rule.id } },
    element("td", { className: "dv-select-cell" }, checkbox),
    element("td", { className: "dv-code", text: rule.rule_code }),
    element("td", {}, element("span", { className: `dv-category-badge is-${categoryTone}`, text: categoryName })),
    element("td", {
      className: "dv-rule-name", title: rule.description || "",
    }, element("strong", { text: rule.name })),
    element("td", { className: "dv-rule-table-name", text: rule.table_name || "—" }),
    element("td", { text: RULE_TYPE_LABELS[rule.rule_type] || rule.rule_type || "—" }),
    element("td", { className: "dv-version", text: rule.version_no ? `v${rule.version_no}` : "—" }),
    element("td", {}, statusBadge(RULE_STATUS_LABELS[rule.status] || rule.status || "未知", tone)),
    element("td", { className: "dv-date", text: formatDateTime(rule.updated_at) }),
    element("td", { className: "dv-row-actions" },
      action(owner ? "编辑 / 测试" : "查看", rule, "edit"),
      action("执行", rule, "execute", {
        hidden: !run, capability: "dv.run", disabled: rule.status !== "enabled",
        title: rule.status === "enabled" ? "新建单规则校验任务" : "仅已启用规则可执行",
      }),
      element("span", { className: "dv-row-more" },
        button("更多 ▾", { className: "dv-table-action dv-more-toggle", dataset: { moreToggle: rule.id } }),
        menu)));
  return { row, menu };
}

export function createRuleTable({ listen, user, onAction, onSelect }) {
  const body = element("tbody");
  const selectAll = element("input", { attrs: { "aria-label": "选择当前页全部规则" } });
  selectAll.type = "checkbox";
  const head = element("thead", {}, element("tr", {},
    element("th", { className: "dv-select-cell" }, selectAll),
    ...["规则编号", "报送分类", "规则名称", "目标数据表", "校验类型", "版本", "状态", "更新时间", "操作"].map((label) => element("th", { text: label }))));
  const table = element("table", { className: "dv-table dv-rule-table" }, head, body);
  const feedback = element("div", { className: "dv-table-feedback" });
  const wrap = element("div", { className: "dv-table-wrap dv-scroll" }, feedback, table);
  let page = { items: [], total: 0, page: 1, page_size: 50 };
  let selectedRules = new Map();
  let menus = new Map();

  function closeMenus() {
    menus.forEach((menu) => { menu.hidden = true; });
  }

  function toggleMenu(ruleId) {
    menus.forEach((menu, id) => {
      menu.hidden = !(Number(id) === Number(ruleId) && menu.hidden);
    });
  }

  listen(wrap, "click", (event) => {
    const toggle = event.target.closest("[data-more-toggle]");
    if (toggle) {
      toggleMenu(toggle.dataset.moreToggle);
      return;
    }
    const target = event.target.closest("[data-action]");
    if (!target || target.disabled) return;
    closeMenus();
    const rule = page.items.find((item) => String(item.id) === String(target.dataset.ruleId));
    onAction(target.dataset.action, rule);
  });
  listen(wrap, "change", (event) => {
    const target = event.target;
    if (target.dataset.selectRule) {
      const rule = page.items.find((item) => String(item.id) === String(target.dataset.selectRule));
      onSelect(rule, target.checked);
    }
  });
  listen(selectAll, "change", () => {
    closeMenus();
    page.items.forEach((rule) => onSelect(rule, selectAll.checked));
  });

  return {
    element: wrap,
    update(payload, selection, { status = "success", error = "", categoryNames = {}, categoryTones = {} } = {}) {
      page = payload || { items: [], total: 0, page: 1, page_size: 50 };
      selectedRules = selection || new Map();
      menus = new Map();
      body.replaceChildren();
      feedback.replaceChildren();
      if (status === "loading") feedback.append(emptyState("正在加载规则…", "正在读取服务端分页数据"));
      else if (status === "error") feedback.append(emptyState("规则加载失败", error || "请检查网络后重试"));
      else if (!page.items?.length) feedback.append(emptyState("暂无数据", "可调整筛选条件，或手工 / AI 新建规则"));
      // 加载、失败与空数据只显示一块居中提示，不在提示下方再留一个空表头和大片空白表格区。
      const hasFeedback = Boolean(feedback.children.length);
      feedback.hidden = !hasFeedback;
      table.hidden = hasFeedback;
      (page.items || []).forEach((rule) => {
        const { row, menu } = ruleRow(rule, user, selectedRules.has(Number(rule.id)), { categoryNames, categoryTones });
        menus.set(rule.id, menu);
        body.append(row);
      });
      const selectedOnPage = (page.items || []).filter((rule) => selectedRules.has(Number(rule.id))).length;
      selectAll.checked = Boolean(page.items?.length && selectedOnPage === page.items.length);
      selectAll.indeterminate = selectedOnPage > 0 && selectedOnPage < page.items.length;
      selectAll.disabled = !page.items?.length || status === "loading";
    },
  };
}