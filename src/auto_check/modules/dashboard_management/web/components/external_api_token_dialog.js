const CLASS_ROOT = "dm-token-dialog";
const FOCUSABLE = 'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

function node(tag, attributes, text) {
  const element = document.createElement(tag);
  Object.entries(attributes || {}).forEach(([name, value]) => element.setAttribute(name, String(value)));
  if (text !== undefined) element.textContent = String(text);
  return element;
}

function button(label, className, onClick, options = {}) {
  const element = node("button", { class: className, type: "button" }, label);
  if (options.disabled) element.disabled = true;
  if (options.title) element.title = options.title;
  element.addEventListener("click", onClick);
  return element;
}

export function openTokenDialog({ host, token, rotated, onClose }) {
  let secret = String(token || "");
  token = "";
  const overlay = node("div", { class: `${CLASS_ROOT}__overlay` });
  const dialog = node("div", { class: `${CLASS_ROOT}__dialog`, role: "dialog", "aria-modal": "true", "aria-labelledby": `${CLASS_ROOT}-title` });
  const focusables = [];
  let closed = false;
  let copyResetTimer = null;

  const close = () => {
    if (closed) return;
    closed = true;
    if (copyResetTimer) clearTimeout(copyResetTimer);
    tokenInput.value = "";
    secret = "";
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
    const nodes = Array.from(dialog.querySelectorAll(FOCUSABLE)).filter((el) => el.offsetParent !== null);
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

  const title = node("h3", { id: `${CLASS_ROOT}-title`, class: `${CLASS_ROOT}__title` }, rotated ? "Token 已更新" : "Token 已生成");
  dialog.append(title);

  const banner = node("div", { class: `${CLASS_ROOT}__banner` }, "该 Token 仅适用于「金融监管报表报送大屏」和「金融监管报送流程大屏」两个接口。关闭后无法再次查看，请立即保存。");
  dialog.append(banner);

  const tokenField = node("div", { class: `${CLASS_ROOT}__token-field` });
  const tokenInput = node("input", { class: `${CLASS_ROOT}__token-value`, type: "text", readonly: "readonly", value: secret, "aria-label": "Token 值" });
  tokenField.append(tokenInput);
  dialog.append(tokenField);

  const copyBtn = button("复制", `dm-button dm-button-secondary ${CLASS_ROOT}__copy`, async () => {
    try {
      await navigator.clipboard.writeText(secret);
      copyBtn.textContent = "已复制";
      copyResetTimer = setTimeout(() => { copyBtn.textContent = "复制"; }, 2000);
    } catch {
      tokenInput.select();
      copyBtn.textContent = "复制失败";
      copyResetTimer = setTimeout(() => { copyBtn.textContent = "复制"; }, 2000);
    }
  });
  focusables.push(copyBtn);

  const actions = node("div", { class: `${CLASS_ROOT}__actions` });
  const savedBtn = button("我已保存", `dm-button dm-button-primary ${CLASS_ROOT}__close`, close);
  focusables.push(savedBtn);
  actions.append(copyBtn, savedBtn);
  dialog.append(actions);

  overlay.append(dialog);
  host.appendChild(overlay);
  if (focusables[0]) focusables[0].focus();

  return { element: overlay, close };
}
