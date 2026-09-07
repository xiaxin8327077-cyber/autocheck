import { element } from "./dom.js";

/* 记录附件编辑与快照组件。
 *
 * - createRecordAttachmentSection：新建/编辑抽屉中的“附件（选填）”区域，
 *   支持点击上传与剪贴板粘贴，输出 record_attachments 变更 payload。
 * - renderRecordAttachmentSnapshot：详情/操作记录中的只读附件卡片，
 *   支持图片预览与全部类型下载；审计双栏通过 change 标记渲染
 *   “新增/移除/保留”标签（标签只来自审计自身的 old/new 集合）。
 *
 * 约束：未保存附件只存在于内存（当前标签页），不写 localStorage /
 * sessionStorage / 磁盘；Base64 只在提交时生成；最终校验以后端为准。
 */

const IMAGE_EXTENSIONS = new Set([".png", ".jpg", ".jpeg", ".webp"]);
const DEFAULT_ALLOWED_EXTENSIONS = [
  ".png", ".jpg", ".jpeg", ".webp", ".xls", ".xlsx", ".doc", ".docx", ".zip",
];
const DEFAULT_LIMITS = Object.freeze({
  max_count: 10,
  max_file_bytes: 10 * 1024 * 1024,
  max_total_bytes: 30 * 1024 * 1024,
  allowed_extensions: DEFAULT_ALLOWED_EXTENSIONS,
});
const IMAGE_MIME_BY_EXTENSION = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
};
const ACCEPT_MIME_TYPES = [
  "image/png",
  "image/jpeg",
  "image/webp",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/zip",
];
const PASTE_IMAGE_EXTENSION_BY_MIME = {
  "image/png": ".png",
  "image/jpeg": ".jpg",
  "image/webp": ".webp",
};

export function attachmentExtensionOf(fileName) {
  const name = String(fileName || "");
  const dot = name.lastIndexOf(".");
  if (dot <= 0 || dot === name.length - 1) return "";
  return name.slice(dot).toLowerCase();
}

export function attachmentKind(extension, contentType = "") {
  const ext = String(extension || "").toLowerCase();
  if (IMAGE_EXTENSIONS.has(ext) || String(contentType).startsWith("image/")) return "image";
  if (ext === ".xls" || ext === ".xlsx") return "excel";
  if (ext === ".doc" || ext === ".docx") return "word";
  if (ext === ".zip") return "zip";
  return "file";
}

const KIND_LABELS = { image: "图片", excel: "表格", word: "文档", zip: "压缩包", file: "文件" };
// 超过该体积的图片不自动拉取缩略图（避免列表一打开就传输大正文），保留点击预览。
const THUMB_AUTOLOAD_MAX_BYTES = 4 * 1024 * 1024;

export function formatAttachmentSize(bytes) {
  const size = Number(bytes) || 0;
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function normalizeLimits(limits) {
  const source = limits && typeof limits === "object" ? limits : {};
  const allowed = Array.isArray(source.allowed_extensions) && source.allowed_extensions.length
    ? source.allowed_extensions.map((item) => String(item).toLowerCase())
    : DEFAULT_ALLOWED_EXTENSIONS;
  return {
    max_count: Number(source.max_count) || DEFAULT_LIMITS.max_count,
    max_file_bytes: Number(source.max_file_bytes) || DEFAULT_LIMITS.max_file_bytes,
    max_total_bytes: Number(source.max_total_bytes) || DEFAULT_LIMITS.max_total_bytes,
    allowed_extensions: allowed,
  };
}

function viewOf(documentRef) {
  return documentRef?.defaultView || globalThis;
}

function readBlobAsBase64(documentRef, file) {
  const view = viewOf(documentRef);
  return new Promise((resolve, reject) => {
    if (typeof view.FileReader === "function") {
      const reader = new view.FileReader();
      reader.onload = () => {
        const url = String(reader.result || "");
        const comma = url.indexOf(",");
        resolve(comma >= 0 ? url.slice(comma + 1) : "");
      };
      reader.onerror = () => reject(new Error("附件读取失败"));
      reader.readAsDataURL(file);
      return;
    }
    Promise.resolve(file.arrayBuffer())
      .then((buffer) => {
        const bytes = new Uint8Array(buffer);
        let binary = "";
        bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
        resolve(view.btoa(binary));
      })
      .catch(() => reject(new Error("附件读取失败")));
  });
}

async function computeSha256(documentRef, file) {
  const view = viewOf(documentRef);
  try {
    if (!view.crypto?.subtle?.digest) return null;
    const buffer = await file.arrayBuffer();
    const digest = await view.crypto.subtle.digest("SHA-256", buffer);
    return Array.from(new Uint8Array(digest))
      .map((byte) => byte.toString(16).padStart(2, "0"))
      .join("");
  } catch (_) {
    return null;
  }
}

function pasteTimestamp(now = new Date()) {
  const pad = (value) => String(value).padStart(2, "0");
  return (
    `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`
    + `-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
  );
}

function isImageMeta(meta) {
  return String(meta?.content_type || "").startsWith("image/");
}

async function downloadAttachmentBlob(documentRef, options, meta) {
  const { recordId, fetchAttachment, notify } = options;
  if (typeof fetchAttachment !== "function" || !recordId) {
    notify?.("附件下载不可用", "error");
    return null;
  }
  try {
    const result = await fetchAttachment(recordId, meta.id);
    if (!result?.blob?.size) {
      notify?.("附件内容为空", "error");
      return null;
    }
    return result;
  } catch (error) {
    if (error?.name !== "AbortError") notify?.(error?.message || "附件下载失败", "error");
    return null;
  }
}

function triggerBlobDownload(documentRef, blob, filename) {
  const view = viewOf(documentRef);
  const url = view.URL.createObjectURL(blob);
  const anchor = element(documentRef, "a", { href: url, download: filename || "attachment" });
  anchor.style?.setProperty?.("display", "none");
  (documentRef.body || documentRef.documentElement)?.append?.(anchor);
  anchor.click?.();
  anchor.remove?.();
  view.URL.revokeObjectURL(url);
}

function kindBadge(documentRef, kind) {
  return element(documentRef, "span", {
    className: `rsp-attachment-kind rsp-attachment-kind-${kind}`,
    text: KIND_LABELS[kind] || KIND_LABELS.file,
    "aria-hidden": "true",
  });
}

async function fetchThumbBlob(documentRef, options, meta) {
  const { recordId, fetchAttachment } = options;
  if (typeof fetchAttachment !== "function" || !recordId) return null;
  try {
    const result = await fetchAttachment(recordId, meta.id);
    return result?.blob ? result : null;
  } catch (_) {
    // 缩略图加载失败静默回退占位，不打扰用户；下载按钮仍可用。
    return null;
  }
}

function fillThumb(button, documentRef, url, meta) {
  const img = element(documentRef, "img", { src: url, alt: String(meta.file_name || "") });
  if (typeof button.replaceChildren === "function") {
    button.replaceChildren(img);
  } else {
    button.textContent = "";
    button.append(img);
  }
}

/* 图片缩略图按钮：优先显示已缓存/自动加载的缩略图；
 * 超阈值或加载失败时保留“图片”占位，点击仍可下载预览。
 * object URL 记入 options.thumbCache（抽屉级），由抽屉关闭时统一释放。 */
function imageThumbButton(documentRef, options, meta) {
  const button = element(documentRef, "button", {
    type: "button",
    className: "rsp-attachment-thumb",
    "aria-label": `预览图片 ${meta.file_name}`,
    text: "图片",
    onClick: async () => {
      const result = await downloadAttachmentBlob(documentRef, options, meta);
      if (!result) return;
      const view = viewOf(documentRef);
      const url = view.URL.createObjectURL(result.blob);
      if (typeof options.previewImage === "function") {
        options.previewImage(url);
      } else {
        view.URL.revokeObjectURL(url);
      }
    },
  });
  const byteSize = Number(meta.byte_size) || 0;
  if (byteSize > THUMB_AUTOLOAD_MAX_BYTES) return button;
  const cache = options.thumbCache instanceof Map ? options.thumbCache : null;
  const cached = cache ? cache.get(meta.id) : null;
  if (cached) {
    fillThumb(button, documentRef, cached, meta);
    return button;
  }
  Promise.resolve()
    .then(() => fetchThumbBlob(documentRef, options, meta))
    .then((result) => {
      if (!result) return;
      const url = viewOf(documentRef).URL.createObjectURL(result.blob);
      if (cache) cache.set(meta.id, url);
      fillThumb(button, documentRef, url, meta);
    })
    .catch(() => {});
  return button;
}

function changeBadge(documentRef, change) {
  const labels = { added: "新增", removed: "移除", retained: "保留" };
  if (!labels[change]) return null;
  return element(documentRef, "span", {
    className: `rsp-attachment-change rsp-attachment-change-${change}`,
    text: labels[change],
  });
}

/* ===== 只读快照（详情 / 审计双栏） ===== */

export function renderRecordAttachmentSnapshot(documentRef, options = {}) {
  const attachments = Array.isArray(options.attachments) ? options.attachments : [];
  const container = element(documentRef, "div", { className: "rsp-attachment-snapshot" });
  if (!attachments.length) {
    container.append(element(documentRef, "p", {
      className: "rsp-attachment-empty",
      text: "无附件",
    }));
    return container;
  }
  attachments.forEach((meta) => {
    const kind = attachmentKind(meta.file_extension, meta.content_type);
    const children = [];
    if (meta.change) {
      const badge = changeBadge(documentRef, meta.change);
      if (badge) children.push(badge);
    }
    if (isImageMeta(meta)) {
      children.push(imageThumbButton(documentRef, options, meta));
    } else {
      children.push(kindBadge(documentRef, kind));
    }
    children.push(element(documentRef, "div", { className: "rsp-attachment-meta" }, [
      element(documentRef, "span", { className: "rsp-attachment-name", text: String(meta.file_name || ""), title: String(meta.file_name || "") }),
      element(documentRef, "span", { className: "rsp-attachment-size", text: formatAttachmentSize(meta.byte_size) }),
    ]));
    children.push(element(documentRef, "button", {
      type: "button",
      className: "rsp-button rsp-button-secondary rsp-attachment-download",
      text: "下载",
      "aria-label": `下载附件 ${meta.file_name}`,
      onClick: async () => {
        const result = await downloadAttachmentBlob(documentRef, options, meta);
        if (!result) return;
        triggerBlobDownload(documentRef, result.blob, result.filename || meta.file_name);
      },
    }));
    container.append(element(documentRef, "div", {
      className: `rsp-attachment-card${meta.change ? ` is-${meta.change}` : ""}`,
      dataset: { attachmentId: String(meta.id ?? "") },
    }, children));
  });
  return container;
}

/* ===== 编辑区域（新建 / 编辑抽屉） ===== */

export function createRecordAttachmentSection(documentRef, options = {}) {
  const limits = normalizeLimits(options.limits);
  const notify = typeof options.notify === "function" ? options.notify : () => {};
  const recordId = options.recordId ?? null;
  const editable = options.editable !== false;
  const initialAttachments = (Array.isArray(options.initialAttachments) ? options.initialAttachments : [])
    .map((item) => ({ ...item }));
  const initialIds = initialAttachments.map((item) => Number(item.id));

  let persisted = [...initialAttachments];
  let locals = [];
  let clientSeq = 0;
  let destroyed = false;
  const objectUrls = new Set();

  const fileInput = element(documentRef, "input", {
    type: "file",
    className: "rsp-attachment-input",
    multiple: "multiple",
    hidden: "hidden",
    accept: [...limits.allowed_extensions, ...ACCEPT_MIME_TYPES].join(","),
    "aria-label": "选择附件文件",
    tabIndex: "-1",
    onChange: (event) => {
      const files = Array.from(event.target?.files || []);
      event.target.value = "";
      if (files.length) addFiles(files);
    },
  });
  const uploadButton = element(documentRef, "button", {
    type: "button",
    className: "rsp-button rsp-button-secondary rsp-attachment-upload",
    text: "上传附件",
    "aria-label": "上传附件",
    disabled: !editable,
    onClick: () => fileInput.click?.(),
  });
  const listNode = element(documentRef, "div", { className: "rsp-attachment-list" });
  const hint = element(documentRef, "p", {
    className: "rsp-attachment-hint",
    text: `支持直接粘贴，或点击上传；最多 ${limits.max_count} 个，单个 ${formatAttachmentSize(limits.max_file_bytes)}，总计 ${formatAttachmentSize(limits.max_total_bytes)}`,
  });
  const root = element(documentRef, "div", { className: "rsp-attachment-section" }, [
    element(documentRef, "div", { className: "rsp-attachment-head" }, [
      element(documentRef, "span", { className: "rsp-field-label", text: "附件（选填）" }),
      uploadButton,
      fileInput,
    ]),
    hint,
    listNode,
  ]);

  function trackObjectUrl(url) {
    if (url) objectUrls.add(url);
    return url;
  }

  function revokeObjectUrl(url) {
    if (!url || !objectUrls.has(url)) return;
    objectUrls.delete(url);
    try {
      viewOf(documentRef).URL.revokeObjectURL(url);
    } catch (_) {}
  }

  function currentTotalBytes() {
    const persistedBytes = persisted.reduce((total, item) => total + (Number(item.byte_size) || 0), 0);
    const localBytes = locals.reduce((total, item) => total + (Number(item.byte_size) || 0), 0);
    return persistedBytes + localBytes;
  }

  function knownHashes() {
    const hashes = new Set();
    persisted.forEach((item) => {
      if (item.content_sha256) hashes.add(String(item.content_sha256));
    });
    locals.forEach((item) => {
      if (item.hash) hashes.add(item.hash);
    });
    return hashes;
  }

  function renderCard(item) {
    if (item.local) {
      const kind = attachmentKind(item.extension, item.contentType);
      const children = [];
      if (kind === "image" && item.previewUrl) {
        children.push(element(documentRef, "span", { className: "rsp-attachment-thumb" }, [
          element(documentRef, "img", { src: item.previewUrl, alt: item.fileName }),
        ]));
      } else {
        children.push(kindBadge(documentRef, kind));
      }
      children.push(element(documentRef, "div", { className: "rsp-attachment-meta" }, [
        element(documentRef, "span", { className: "rsp-attachment-name", text: item.fileName, title: item.fileName }),
        element(documentRef, "span", { className: "rsp-attachment-size", text: `${formatAttachmentSize(item.byteSize)} · 待保存` }),
      ]));
      children.push(element(documentRef, "button", {
        type: "button",
        className: "rsp-attachment-remove",
        text: "×",
        "aria-label": `删除附件 ${item.fileName}`,
        onClick: () => {
          locals = locals.filter((entry) => entry.clientId !== item.clientId);
          revokeObjectUrl(item.previewUrl);
          render();
        },
      }));
      return element(documentRef, "div", {
        className: "rsp-attachment-card is-local",
        dataset: { clientId: item.clientId },
      }, children);
    }
    const kind = attachmentKind(item.file_extension, item.content_type);
    const children = [];
    if (isImageMeta(item)) {
      children.push(imageThumbButton(documentRef, options, item));
    } else {
      children.push(kindBadge(documentRef, kind));
    }
    children.push(element(documentRef, "div", { className: "rsp-attachment-meta" }, [
      element(documentRef, "span", { className: "rsp-attachment-name", text: String(item.file_name || ""), title: String(item.file_name || "") }),
      element(documentRef, "span", { className: "rsp-attachment-size", text: formatAttachmentSize(item.byte_size) }),
    ]));
    children.push(element(documentRef, "button", {
      type: "button",
      className: "rsp-button rsp-button-secondary rsp-attachment-download",
      text: "下载",
      "aria-label": `下载附件 ${item.file_name}`,
      onClick: async () => {
        const result = await downloadAttachmentBlob(documentRef, options, item);
        if (!result) return;
        triggerBlobDownload(documentRef, result.blob, result.filename || item.file_name);
      },
    }));
    if (editable) {
      children.push(element(documentRef, "button", {
        type: "button",
        className: "rsp-attachment-remove",
        text: "×",
        "aria-label": `删除附件 ${item.file_name}`,
        onClick: () => {
          persisted = persisted.filter((entry) => Number(entry.id) !== Number(item.id));
          render();
        },
      }));
    }
    return element(documentRef, "div", {
      className: "rsp-attachment-card is-persisted",
      dataset: { attachmentId: String(item.id ?? "") },
    }, children);
  }

  function render() {
    if (destroyed) return;
    listNode.replaceChildren();
    if (!editable) {
      uploadButton.disabled = true;
      fileInput.disabled = true;
    }
    if (!persisted.length && !locals.length) {
      listNode.append(element(documentRef, "p", {
        className: "rsp-attachment-empty",
        text: "暂无附件",
      }));
      return;
    }
    persisted.forEach((item) => listNode.append(renderCard(item)));
    locals.forEach((item) => listNode.append(renderCard(item)));
  }

  async function addFiles(rawFiles) {
    if (destroyed || !editable) return;
    const files = Array.from(rawFiles || []);
    if (!files.length) return;
    const hashes = knownHashes();
    for (const file of files) {
      const fileName = String(file?.name || "").trim();
      let extension = attachmentExtensionOf(fileName);
      const mime = String(file?.type || "").toLowerCase();
      if (!extension && mime.startsWith("image/")) {
        extension = PASTE_IMAGE_EXTENSION_BY_MIME[mime] || "";
      }
      if (!extension || !limits.allowed_extensions.includes(extension)) {
        notify(`不支持的附件类型：${fileName || mime || "未知文件"}`, "error");
        continue;
      }
      const byteSize = Number(file?.size) || 0;
      if (!byteSize) {
        notify("不能添加空文件", "error");
        continue;
      }
      if (byteSize > limits.max_file_bytes) {
        notify(`单个附件最大 ${formatAttachmentSize(limits.max_file_bytes)}`, "error");
        continue;
      }
      if (persisted.length + locals.length >= limits.max_count) {
        notify(`每条记录最多 ${limits.max_count} 个附件`, "error");
        continue;
      }
      if (currentTotalBytes() + byteSize > limits.max_total_bytes) {
        notify(`附件总大小最大 ${formatAttachmentSize(limits.max_total_bytes)}`, "error");
        continue;
      }
      // 前端哈希去重只是即时反馈；浏览器不支持时由后端最终拦截。
      const hash = await computeSha256(documentRef, file);
      if (hash && hashes.has(hash)) {
        notify("该附件已添加", "warning");
        continue;
      }
      let displayName = fileName;
      if (!displayName) {
        const seq = locals.filter((item) => item.pasted).length + 1;
        displayName = `粘贴图片-${pasteTimestamp()}-${seq}${extension}`;
      }
      const contentType = IMAGE_EXTENSIONS.has(extension)
        ? (IMAGE_MIME_BY_EXTENSION[extension] || mime || "application/octet-stream")
        : (mime || "application/octet-stream");
      clientSeq += 1;
      let previewUrl = "";
      if (IMAGE_EXTENSIONS.has(extension)) {
        try {
          previewUrl = trackObjectUrl(viewOf(documentRef).URL.createObjectURL(file));
        } catch (_) {
          previewUrl = "";
        }
      }
      const local = {
        local: true,
        clientId: `local-${clientSeq}`,
        file,
        fileName: displayName,
        extension,
        contentType,
        byteSize,
        hash: hash || "",
        previewUrl,
        pasted: !fileName,
      };
      locals.push(local);
      if (hash) hashes.add(hash);
    }
    render();
  }

  function handlePaste(event) {
    if (destroyed || !editable) return false;
    const clipboard = event?.clipboardData;
    if (!clipboard) return false;
    const files = [];
    if (clipboard.files?.length) {
      Array.from(clipboard.files).forEach((file) => files.push(file));
    }
    if (!files.length && clipboard.items) {
      Array.from(clipboard.items).forEach((item) => {
        if (item.kind === "file") {
          const file = item.getAsFile?.();
          if (file) files.push(file);
        }
      });
    }
    if (!files.length) return false;
    // 只有剪贴板包含文件时才拦截；纯文字粘贴不受影响。
    event.preventDefault?.();
    addFiles(files);
    return true;
  }

  function hasChanges() {
    if (locals.length) return true;
    const currentIds = persisted.map((item) => Number(item.id));
    if (currentIds.length !== initialIds.length) return true;
    return currentIds.some((id, index) => id !== initialIds[index]);
  }

  async function buildChangePayload() {
    if (destroyed || !hasChanges()) return null;
    const newFiles = [];
    for (const local of locals) {
      const dataBase64 = await readBlobAsBase64(documentRef, local.file);
      if (!dataBase64) {
        notify(`附件读取失败：${local.fileName}`, "error");
        throw new Error("attachment read failed");
      }
      newFiles.push({
        client_id: local.clientId,
        file_name: local.fileName,
        content_type: local.contentType,
        data_base64: dataBase64,
      });
    }
    return {
      retained_ids: persisted.map((item) => Number(item.id)),
      new_files: newFiles,
    };
  }

  function destroy() {
    destroyed = true;
    objectUrls.forEach((url) => {
      try {
        viewOf(documentRef).URL.revokeObjectURL(url);
      } catch (_) {}
    });
    objectUrls.clear();
    locals.forEach((item) => { item.file = null; });
    locals = [];
    listNode.replaceChildren();
    fileInput.removeEventListener?.("change", () => {});
  }

  render();

  return Object.freeze({
    element: root,
    addFiles,
    handlePaste,
    buildChangePayload,
    hasPendingWork: () => locals.length > 0,
    hasChanges,
    destroy,
  });
}
