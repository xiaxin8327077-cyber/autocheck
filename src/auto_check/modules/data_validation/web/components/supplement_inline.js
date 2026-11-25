import { button, element } from "./dom.js";

export function createSupplementInline({ host, listen, onClose }) {
  const body = element("div", { className: "dv-ai-supplement-inline-body" });
  const footer = element("div", { className: "dv-ai-supplement-inline-footer" });
  const region = element("section", { className: "dv-ai-supplement-inline", attrs: { role: "region" } }, body, footer);
  const closeButton = button("取消", { className: "dv-button dv-dialog-close" });
  let closed = false;
  host.append(region);

  return {
    element: region, dialog: region, body, footer, closeButton, bind: listen,
    setTitle: (title) => region.setAttribute("aria-label", title),
    close() {
      if (closed) return;
      closed = true;
      region.remove();
      onClose?.();
    },
  };
}
