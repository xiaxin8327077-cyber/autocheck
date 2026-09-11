import { element } from "./dom.js";

const OPERATOR_LABELS = {
  "=": "等于",
  "<>": "不等于",
  ">": "大于",
  ">=": "大于等于",
  "<": "小于",
  "<=": "小于等于",
  LIKE: "模糊匹配",
  IN: "属于多个值（IN）",
  "IS NULL": "为空",
  "IS NOT NULL": "不为空",
};

function displayText(value) {
  const text = String(value ?? "").trim();
  return text || "—";
}

export function readonlyField(documentRef, label, value, className = "") {
  return element(documentRef, "div", {
    className: `rsp-readonly-info-item ${className}`.trim(),
  }, [
    element(documentRef, "span", { className: "rsp-readonly-info-label", text: label }),
    element(documentRef, "span", {
      className: "rsp-readonly-info-value",
      text: displayText(value),
      "aria-label": `${label}值`,
    }),
  ]);
}

export function readonlyTextBlock(documentRef, label, value, className = "") {
  return element(documentRef, "div", {
    className: `rsp-readonly-text-block ${className}`.trim(),
    text: displayText(value),
    "aria-label": `${label}值`,
  });
}

function previewTable(documentRef, ariaLabel, headers, rows) {
  const bodyRows = rows.length ? rows : [["暂无数据"]];
  return element(documentRef, "div", { className: "rsp-preview-table-wrap" }, [
    element(documentRef, "table", {
      className: "rsp-preview-table",
      "aria-label": ariaLabel,
    }, [
      element(documentRef, "thead", {}, [
        element(documentRef, "tr", {}, headers.map((header) => element(documentRef, "th", { text: header }))),
      ]),
      element(documentRef, "tbody", {}, bodyRows.map((row) => element(documentRef, "tr", {}, (
        row.length === 1 && headers.length > 1
          ? [element(documentRef, "td", { text: displayText(row[0]), colspan: String(headers.length) })]
          : row.map((value) => element(documentRef, "td", { text: displayText(value) }))
      )))),
    ]),
  ]);
}

function conditionRows(table) {
  return (Array.isArray(table?.conditions) ? table.conditions : [])
    .filter((condition) => condition?.column_name || condition?.operator || (condition?.values || []).length)
    .map((condition) => {
      const operator = String(condition?.operator || "=").trim().toUpperCase();
      return [
        condition?.column_name,
        OPERATOR_LABELS[operator] || operator,
        Array.isArray(condition?.values) ? condition.values.join("、") : condition?.value,
      ];
    });
}

function fieldRows(table) {
  return (Array.isArray(table?.fields) ? table.fields : [])
    .filter((field) => field?.column_name || field?.chinese_column_name)
    .map((field) => [
      field?.column_name,
      field?.chinese_column_name || field?.column_name,
      field?.value_before,
      field?.value_after,
    ]);
}

export function createStructuredContentPreview(documentRef, options = {}) {
  const content = options.initial && typeof options.initial === "object" ? options.initial : {};
  const tables = Array.isArray(content.tables) ? content.tables : [];
  const root = element(documentRef, "div", {
    className: "rsp-config-preview",
    "aria-label": "数据源与处理表字段预览",
  });

  tables.forEach((table, index) => {
    const datasourceName = String(
      table?.datasource_name || options.datasourceNameSnapshot || table?.datasource_id || "",
    ).trim();
    const physicalTable = String(table?.table_name || "").trim();
    const titleMeta = [datasourceName, physicalTable].filter(Boolean).join(" / ");
    const card = element(documentRef, "section", { className: "rsp-config-preview-card" }, [
      element(documentRef, "div", { className: "rsp-config-preview-card-title" }, [
        element(documentRef, "strong", { text: `处理表 ${index + 1}` }),
        element(documentRef, "span", { text: titleMeta }),
      ]),
      element(documentRef, "div", { className: "rsp-config-preview-card-body" }, [
        element(documentRef, "div", { className: "rsp-preview-table-info" }, [
          readonlyField(documentRef, "数据源", datasourceName),
          readonlyField(documentRef, "英文表名", physicalTable),
          readonlyField(documentRef, "中文表名", table?.chinese_table_name),
        ]),
        element(documentRef, "div", { className: "rsp-config-preview-section" }, [
          element(documentRef, "div", { className: "rsp-config-preview-section-title" }, [
            element(documentRef, "strong", { text: "处理范围" }),
            element(documentRef, "span", {
              text: `指定数据日期：${table?.limit_report_period === false ? "否" : "是"}`,
            }),
          ]),
          previewTable(
            documentRef,
            "处理范围预览表",
            ["条件字段", "条件类型", "条件值"],
            conditionRows(table),
          ),
        ]),
        element(documentRef, "div", { className: "rsp-config-preview-section" }, [
          element(documentRef, "div", { className: "rsp-config-preview-section-title" }, [
            element(documentRef, "strong", { text: "修改字段" }),
          ]),
          previewTable(
            documentRef,
            "修改字段预览表",
            ["英文字段名", "中文字段名", "修改前", "修改后"],
            fieldRows(table),
          ),
        ]),
      ]),
    ]);
    root.append(card);
  });

  if (!tables.length) {
    root.append(element(documentRef, "div", { className: "rsp-preview-empty", text: "暂无特殊处理内容" }));
  }
  return root;
}

export function createLegacyContentPreview(documentRef, record = {}) {
  return element(documentRef, "section", { className: "rsp-config-preview-card rsp-config-preview-legacy" }, [
    element(documentRef, "div", { className: "rsp-config-preview-card-title" }, [
      element(documentRef, "strong", { text: "历史处理内容" }),
    ]),
    element(documentRef, "div", { className: "rsp-config-preview-card-body" }, [
      previewTable(documentRef, "历史特殊处理内容预览表", ["处理表", "修改字段", "修改前", "修改后"], [[
        record.table_name,
        record.field_name,
        record.value_before,
        record.value_after,
      ]]),
    ]),
  ]);
}
