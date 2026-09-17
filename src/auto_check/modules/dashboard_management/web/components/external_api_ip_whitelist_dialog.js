import { button, node } from "./dom.js";

const CLASS_ROOT = "dm-ip-whitelist-dialog";
const MAX_ALLOWED_IPS = 100;
const FOCUSABLE = 'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

function closeButton(label, className, onClick, options = {}) {
  const element = button(label, className, onClick, options);
  if (options.ariaLabel) element.setAttribute("aria-label", options.ariaLabel);
  return element;
}

export function openIpWhitelistDialog({ host, policy, onSave, onClose }) {
  const initial = policy || {};
  const overlay = node("div", { className: `${CLASS_ROOT}__overlay` });
  const dialog = node("div", {
    className: `${CLASS_ROOT}__dialog`,
    attrs: { role: "dialog", "aria-modal": "true", "aria-labelledby": `${CLASS_ROOT}-title` },
  });
  let closed = false;
  let saving = false;

  const close = () => {
    if (closed) return;
    closed = true;
    overlay.removeEventListener("keydown", handleKeydown);
    if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    if (typeof onClose === "function") onClose();
  };

  const handleKeydown = (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== "Tab") return;
    const nodes = Array.from(dialog.querySelectorAll(FOCUSABLE)).filter((element) => element.offsetParent !== null);
    if (nodes.length === 0) return;
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  overlay.addEventListener("keydown", handleKeydown);

  const header = node("header", { className: `${CLASS_ROOT}__header` });
  header.append(node("h3", { className: `${CLASS_ROOT}__title`, text: "IP 白名单配置", attrs: { id: `${CLASS_ROOT}-title` } }));
  header.append(closeButton("×", `dm-button dm-button-plain ${CLASS_ROOT}__close`, close, { ariaLabel: "关闭" }));
  dialog.append(header);

  const switchField = node("label", { className: `${CLASS_ROOT}__switch` });
  const toggle = node("input", { className: `${CLASS_ROOT}__switch-input`, attrs: { type: "checkbox" } });
  toggle.checked = Boolean(initial.enabled);
  toggle.setAttribute("aria-label", "启用 IP 白名单");
  switchField.append(toggle, node("span", { className: `${CLASS_ROOT}__switch-text`, text: "启用 IP 白名单" }));
  dialog.append(switchField);

  const field = node("label", { className: `${CLASS_ROOT}__field` });
  field.append(node("span", { className: `${CLASS_ROOT}__field-label`, text: "IP 地址（每行一个）" }));
  const textarea = node("textarea", { className: `${CLASS_ROOT}__textarea`, attrs: { rows: "8", placeholder: "192.168.1.10" } });
  textarea.setAttribute("aria-label", "IP 地址列表");
  const initialIps = Array.isArray(initial.allowed_ips) ? initial.allowed_ips : [];
  textarea.value = initialIps.map((item) => String(item)).join("\n");
  field.append(textarea);
  dialog.append(field);

  dialog.append(node("p", {
    className: `${CLASS_ROOT}__hint`,
    text: "未启用时不限制来源 IP。启用后，仅白名单中的 IP 和运行 AutoCheck 的本机可以访问两个外部接口；未填写 IP 时仅允许本机访问。",
  }));

  const feedback = node("p", { className: `${CLASS_ROOT}__error` });
  feedback.hidden = true;
  dialog.append(feedback);

  const actions = node("div", { className: `${CLASS_ROOT}__actions` });
  const cancelBtn = closeButton("取消", `dm-button dm-button-secondary ${CLASS_ROOT}__cancel`, close);
  const saveBtn = closeButton("保存", `dm-button dm-button-primary ${CLASS_ROOT}__save`, () => { submit(); });
  actions.append(cancelBtn, saveBtn);
  dialog.append(actions);

  async function submit() {
    if (saving || closed) return;
    feedback.hidden = true;
    feedback.textContent = "";
    const allowedIps = textarea.value
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.length > 0);
    if (allowedIps.length > MAX_ALLOWED_IPS) {
      feedback.textContent = "最多只能配置 100 个 IP 地址，请删除多余地址后再保存。";
      feedback.hidden = false;
      return;
    }
    saving = true;
    saveBtn.disabled = true;
    cancelBtn.disabled = true;
    const payload = {
      enabled: Boolean(toggle.checked),
      allowed_ips: allowedIps,
    };
    try {
      await onSave(payload);
    } catch (error) {
      // 保存失败保留弹窗与输入内容，只展示安全错误说明。
      saving = false;
      saveBtn.disabled = false;
      cancelBtn.disabled = false;
      feedback.textContent = error?.payload?.error?.message || error?.message || "保存 IP 白名单失败";
      feedback.hidden = false;
      return;
    }
    close();
  }

  overlay.append(dialog);
  host.appendChild(overlay);
  textarea.focus();

  return { element: overlay, close };
}
