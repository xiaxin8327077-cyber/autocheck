import { errorMessage, isAbortError } from "../runtime.js";
import { button, element } from "./dom.js";

let nextDialogId = 1;

export function createDialog({ host, title, icon = null, subtitle = "", className = "", onClose, onError }) {
  const id = `dv-dialog-${nextDialogId++}`;
  const restoreFocus = document.activeElement;
  const listeners = new Set();
  let closed = false;
  const body = element("div", { className: "dv-dialog-body" });
  const footer = element("div", { className: "dv-dialog-footer" });
  const heading = element("h2", { className: "dv-dialog-title", text: title, attrs: { id } });
  const closeButton = button("×", {
    className: "dv-dialog-close", ariaLabel: "关闭弹窗",
  });
  bind(closeButton, "click", () => close());
  const dialog = element("section", {
    className: `dv-dialog ${className}`.trim(),
    attrs: { role: "dialog", "aria-modal": "true", "aria-labelledby": id, tabindex: "-1" },
  }, element("header", { className: "dv-dialog-header" }, icon, heading, subtitle ? element("span", { className: "dv-dialog-subtitle", text: subtitle }) : null, closeButton), body, footer);
  const overlay = element("div", { className: "dv-overlay" }, dialog);

  function bind(target, type, handler) {
    const wrapped = async (event) => {
      if (closed) return;
      try {
        await handler(event);
      } catch (error) {
        if (!closed && !isAbortError(error)) onError?.(errorMessage(error), error);
      }
    };
    target.addEventListener(type, wrapped);
    const remove = () => target.removeEventListener(type, wrapped);
    listeners.add(remove);
    return remove;
  }

  function close() {
    if (closed) return;
    closed = true;
    listeners.forEach((remove) => remove());
    listeners.clear();
    overlay.remove();
    onClose?.();
    if (restoreFocus?.isConnected && typeof restoreFocus.focus === "function") restoreFocus.focus();
  }

  // 遮罩与 Esc 都不关闭；只有显式关闭、取消或确认按钮可以关闭弹窗。
  bind(overlay, "click", (event) => {
    if (event.target === overlay) event.preventDefault();
  });
  bind(overlay, "keydown", (event) => {
    if (event.key === "Escape") event.preventDefault();
  });
  host.append(overlay);
  dialog.focus?.();
  return {
    element: overlay, dialog, body, footer, closeButton, bind, close,
    setTitle: (value) => { heading.textContent = String(value || ""); },
    isClosed: () => closed,
  };
}
