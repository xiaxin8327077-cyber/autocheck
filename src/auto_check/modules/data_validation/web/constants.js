// 模块前端唯一字典与配置源：选项文案、状态字典、向导步骤与门禁均在此维护。
// 字典未命中时必须回退显示后端原始 code，不得显示空白或编造文案。

export const BLANK_COLUMN_FIELD = [["", "请选择真实字段"]];

export const OPERATOR_OPTIONS = [
  ["lt", "< 早于 / 小于"],
  ["lte", "≤"],
  ["gt", "> 晚于 / 大于"],
  ["gte", "≥"],
  ["eq", "= 等于"],
  ["neq", "≠ 不等于"],
];

export const NULL_POLICY_OPTIONS = [
  ["unresolved", "未确认（保存草稿，禁止确认）"],
  ["skip", "空值跳过"],
  ["violate", "空值计为违规"],
  ["empty_string_as_null", "空串按空值处理"],
];

export const EQUALITY_POLICY_OPTIONS = [
  ["unresolved", "未确认（保存草稿，禁止确认）"],
  ["allow_equal", "相等允许"],
  ["reject_equal", "相等计为违规"],
];

export const SQL_STATUS_LABELS = {
  candidate: "候选（未编译）",
  rejected: "未通过编译",
};

export const TEST_CASE_STATUS_LABELS = {
  passed: "通过",
  failed: "失败",
  not_run: "未运行",
};

export const TEST_CASE_STATUS_TONES = {
  passed: "success",
  failed: "danger",
  not_run: "neutral",
};

const hasOwn = (source, key) => Object.prototype.hasOwnProperty.call(source, key);

export function labelFor(code, labels, fallback = "") {
  if (code === undefined || code === null) return fallback;
  const key = String(code);
  if (!key) return fallback;
  return hasOwn(labels, key) ? labels[key] : key;
}

export function toneFor(code, tones, fallback = "neutral") {
  return hasOwn(tones, String(code ?? "")) ? tones[String(code)] : fallback;
}
