import { button, node } from "./dom.js";

function focusable(dialog) {
  return [...dialog.querySelectorAll('button:not(:disabled), [tabindex]:not([tabindex="-1"])')];
}

function dialogShell(root, { title, className, trigger }) {
  const titleId = `dm-board-preview-title-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const overlay = node("div", { className: "dm-dialog-overlay", attrs: { role: "presentation" } });
  const dialog = node("section", { className: `dm-dialog ${className}`, attrs: { role: "dialog", "aria-modal": "true", "aria-labelledby": titleId, tabindex: "-1" } });
  const heading = node("div", { className: "dm-dialog-heading" });
  heading.append(node("h2", { text: title, attrs: { id: titleId } }));
  let onKeydown = null;
  const close = () => {
    if (onKeydown) dialog.removeEventListener("keydown", onKeydown);
    const currentTab = trigger?.closest?.(".dm-tabs")?.querySelector?.('.dm-tab[aria-selected="true"]');
    overlay.remove();
    if (currentTab) currentTab.focus?.();
    else trigger?.blur?.();
  };
  heading.append(button("关闭", "dm-button dm-button-plain", close));
  dialog.append(heading); overlay.append(dialog); root.append(overlay);
  onKeydown = (event) => {
    if (event.key === "Escape") { event.preventDefault(); close(); return; }
    if (event.key !== "Tab") return;
    const controls = focusable(dialog); if (!controls.length) return;
    const first = controls[0]; const last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  };
  dialog.addEventListener("keydown", onKeydown); dialog.focus();
  return { dialog, overlay };
}

export function openBoardPreviewDialog(root, { board, endpoint, loadPreview, trigger = document.activeElement }) {
  const { dialog, overlay } = dialogShell(root, { title: `${board.name} · 接口数据`, className: "dm-board-preview-dialog", trigger });
  const content = node("div", { className: "dm-board-preview-content" });
  const endpointRow = node("div", { className: "dm-api-endpoint" });
  endpointRow.append(node("span", { text: "GET" }), node("code", { text: endpoint }));
  const code = node("pre", { className: "dm-api-preview-code", text: "正在读取接口数据…", attrs: { "aria-live": "polite" } });
  content.append(endpointRow, code); dialog.append(content);
  Promise.resolve(loadPreview()).then((payload) => {
    if (overlay.isConnected) code.textContent = JSON.stringify(payload, null, 2);
  }).catch((error) => {
    if (overlay.isConnected) code.textContent = JSON.stringify({ error: { message: error?.payload?.error?.message || error?.message || "接口数据读取失败" } }, null, 2);
  });
}

export function openBoardScreenPreviewDialog(root, { board, screenUrl, trigger = document.activeElement }) {
  const { dialog, overlay } = dialogShell(root, { title: `${board.name} · 看板页面`, className: "dm-board-screen-dialog", trigger });
  const content = node("div", { className: "dm-board-screen-content" });
  const loading = node("p", { className: "dm-board-screen-loading", text: "正在加载看板页面…", attrs: { "aria-live": "polite" } });
  const frame = node("iframe", { className: "dm-board-screen-frame", attrs: { title: `${board.name}页面预览`, sandbox: "allow-scripts allow-same-origin" } });
  frame.hidden = true; content.append(loading, frame); dialog.append(content);
  fetch(screenUrl, { headers: { Accept: "text/html" } }).then((response) => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.text();
  }).then((html) => {
    if (!overlay.isConnected) return;
    frame.srcdoc = html; frame.hidden = false; loading.hidden = true;
  }).catch((error) => {
    if (overlay.isConnected) loading.textContent = `看板页面加载失败：${error.message}`;
  });
}
