"""Node 场景测试：报表特殊处理记录附件前端组件。

覆盖上传/粘贴进入同一状态、前端限制、SHA-256 去重、payload 序列化、
只读快照与审计变化标签、Blob URL 释放等行为。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "src" / "auto_check" / "modules" / "report_special_processing" / "web"


# 打包 builder 镜像的 Node 16 没有浏览器/Node20+ 的全局 `File`，也没有全局 `crypto`。
# 组件按 duck-typing 消费 File（name/type/size/arrayBuffer/slice），这里补最小实现；
# crypto 走 node:crypto 的 webcrypto（自带 subtle.digest），两者都只在宿主缺失时兜底。
GLOBAL_FILE_POLYFILL = r"""
import { webcrypto } from "node:crypto";
if (typeof globalThis.crypto === "undefined") {
  globalThis.crypto = webcrypto;
}
if (typeof globalThis.File === "undefined") {
  class FilePolyfill {
    constructor(parts, name, options = {}) {
      const buffers = [];
      for (const part of parts || []) {
        if (part instanceof ArrayBuffer) buffers.push(Buffer.from(part));
        else if (ArrayBuffer.isView(part)) buffers.push(Buffer.from(part.buffer, part.byteOffset, part.byteLength));
        else if (part && typeof part.arrayBuffer === "function") buffers.push(Buffer.from(part));
        else buffers.push(Buffer.from(String(part), "utf8"));
      }
      this._buffer = Buffer.concat(buffers);
      this.name = String(name);
      this.type = String(options.type || "");
      this.size = this._buffer.length;
      this.lastModified = typeof options.lastModified === "number" ? options.lastModified : 0;
    }
    arrayBuffer() {
      const copy = this._buffer.slice();
      return Promise.resolve(copy.buffer.slice(copy.byteOffset, copy.byteOffset + copy.byteLength));
    }
    text() { return Promise.resolve(this._buffer.toString("utf8")); }
    slice(start, end) {
      const from = start < 0 ? Math.max(this.size + start, 0) : start;
      const to = end === undefined ? this.size : (end < 0 ? this.size + end : Math.min(end, this.size));
      return new FilePolyfill([this._buffer.subarray(from, to)], this.name, { type: this.type });
    }
  }
  globalThis.File = FilePolyfill;
}
"""

PREAMBLE = r"""
import assert from "node:assert/strict";
import {
  createRecordAttachmentSection,
  renderRecordAttachmentSnapshot,
} from "./record_attachments.js";

function makeElement(tagName) {
  const node = {
    tagName: String(tagName || "div").toUpperCase(),
    children: [],
    parentNode: null,
    attributes: {},
    dataset: {},
    style: { setProperty() {}, removeProperty() {} },
    className: "",
    textContent: "",
    value: "",
    disabled: false,
    hidden: false,
    tabIndex: 0,
    _listeners: {},
    append(...items) {
      items.filter(Boolean).forEach((item) => {
        if (typeof item === "string") {
          const text = makeElement("#text");
          text.textContent = item;
          this.children.push(text);
          return;
        }
        item.parentNode = this;
        this.children.push(item);
      });
      return this;
    },
    appendChild(child) { return this.append(child); },
    replaceChildren(...items) {
      this.children = [];
      if (items.length) this.append(...items);
    },
    remove() {
      if (this.parentNode) {
        this.parentNode.children = this.parentNode.children.filter((item) => item !== this);
      }
    },
    addEventListener(type, handler) {
      (this._listeners[type] = this._listeners[type] || []).push(handler);
    },
    removeEventListener(type, handler) {
      this._listeners[type] = (this._listeners[type] || []).filter((item) => item !== handler);
    },
    dispatchEvent(event) {
      const evt = Object.assign({ target: this, preventDefault() {}, stopPropagation() {} }, event);
      (this._listeners[evt.type] || []).slice().forEach((handler) => handler.call(this, evt));
      return true;
    },
    click() { this.dispatchEvent({ type: "click" }); },
    setAttribute(name, value) {
      this.attributes[name] = String(value);
      if (name === "disabled") this.disabled = true;
      if (name === "hidden") this.hidden = true;
    },
    getAttribute(name) {
      return Object.prototype.hasOwnProperty.call(this.attributes, name) ? this.attributes[name] : null;
    },
    removeAttribute(name) { delete this.attributes[name]; },
    querySelector(selector) { return findAll(this, selector)[0] || null; },
    querySelectorAll(selector) { return findAll(this, selector); },
  };
  return node;
}

function findAll(root, selector) {
  // 支持 "tag"、".class" 与 ".class-a.class-b" 极简选择器。
  const matches = [];
  const parts = selector.split(".");
  const tag = parts[0] ? parts[0].toUpperCase() : null;
  const classes = parts.slice(1);
  const test = (node) => {
    if (tag && node.tagName !== tag) return false;
    if (!classes.length) return Boolean(tag);
    const nodeClasses = String(node.className || "").split(/\s+/);
    return classes.every((cls) => nodeClasses.includes(cls));
  };
  const walk = (node) => {
    (node.children || []).forEach((child) => {
      if (test(child)) matches.push(child);
      walk(child);
    });
  };
  walk(root);
  return matches;
}

function collectText(root) {
  let text = String(root.textContent || "");
  (root.children || []).forEach((child) => { text += collectText(child); });
  return text;
}

const createdUrls = [];
const revokedUrls = [];

class FakeFileReader {
  readAsDataURL(file) {
    Promise.resolve(file.arrayBuffer())
      .then((buffer) => {
        this.result = "data:application/octet-stream;base64,"
          + Buffer.from(new Uint8Array(buffer)).toString("base64");
        this.onload && this.onload();
      })
      .catch(() => this.onerror && this.onerror());
  }
}

function makeDocumentRef() {
  const body = makeElement("body");
  const documentRef = {
    body,
    documentElement: makeElement("html"),
    createElement: (tag) => makeElement(tag),
    defaultView: {
      FileReader: FakeFileReader,
      crypto: globalThis.crypto,
      btoa: (value) => Buffer.from(value, "binary").toString("base64"),
      URL: {
        createObjectURL: () => {
          const url = `blob:fake/${createdUrls.length + 1}`;
          createdUrls.push(url);
          return url;
        },
        revokeObjectURL: (url) => revokedUrls.push(url),
      },
    },
  };
  return documentRef;
}

const PNG_BYTES = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 1, 2, 3, 4]);
const PNG_BYTES_ALT = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 9, 9, 9, 9]);

function pngFile(name = "new.png", bytes = PNG_BYTES) {
  return new File([bytes], name, { type: "image/png" });
}

function makeNotify() {
  const calls = [];
  const notify = (message, tone) => calls.push({ message, tone });
  notify.calls = calls;
  return notify;
}

const DEFAULT_LIMITS = { max_count: 10, max_file_bytes: 10485760, max_total_bytes: 31457280 };
"""

# File 兜底与 webcrypto 导入必须在场景脚本最前部求值。
PREAMBLE = GLOBAL_FILE_POLYFILL + PREAMBLE


def _run_scenario(tmp_path: Path, scenario: str, name: str) -> subprocess.CompletedProcess:
    workdir = tmp_path / name
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    shutil.copy(WEB / "components" / "dom.js", workdir / "dom.js")
    shutil.copy(WEB / "components" / "record_attachments.js", workdir / "record_attachments.js")
    script = (
        PREAMBLE
        + "\nasync function runScenario() {\n"
        + scenario
        + "\n}\nrunScenario().then(() => console.log(\"OK\"), (error) => { console.error(error && error.stack || error); process.exitCode = 1; });\n"
    )
    (workdir / "scenario.js").write_text(script, encoding="utf-8")
    return subprocess.run(
        ["node", "scenario.js"],
        cwd=workdir,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def _assert_ok(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0, f"node scenario failed\n{result.stdout}\n{result.stderr}"
    assert "OK" in result.stdout


def test_section_adds_files_and_builds_change_payload(tmp_path: Path) -> None:
    scenario = """
  const documentRef = makeDocumentRef();
  const notify = makeNotify();
  const section = createRecordAttachmentSection(documentRef, {
    recordId: 7,
    initialAttachments: [{ id: 12, file_name: "old.xlsx", file_extension: ".xlsx", content_type: "application/x-ole-storage", byte_size: 10 }],
    editable: true,
    limits: DEFAULT_LIMITS,
    notify,
  });
  // 未变化时不产生 payload。
  assert.equal(await section.buildChangePayload(), null);
  await section.addFiles([pngFile()]);
  const payload = await section.buildChangePayload();
  assert.deepEqual(payload.retained_ids, [12]);
  assert.equal(payload.new_files.length, 1);
  assert.equal(payload.new_files[0].file_name, "new.png");
  assert.equal(payload.new_files[0].content_type, "image/png");
  assert.equal(payload.new_files[0].client_id, "local-1");
  assert.equal(
    payload.new_files[0].data_base64,
    Buffer.from(PNG_BYTES).toString("base64"),
    "只保留纯 Base64 数据",
  );
  assert.ok(!payload.new_files[0].data_base64.startsWith("data:"));
  // 卡片渲染：已保存附件 + 待保存附件。
  const cards = section.element.querySelectorAll(".rsp-attachment-card");
  assert.equal(cards.length, 2);
  assert.equal(section.hasPendingWork(), true);
"""
    _assert_ok(_run_scenario(tmp_path, scenario, "build_payload"))


def test_section_removes_persisted_and_local_entries(tmp_path: Path) -> None:
    scenario = """
  const documentRef = makeDocumentRef();
  const section = createRecordAttachmentSection(documentRef, {
    recordId: 7,
    initialAttachments: [{ id: 12, file_name: "old.xlsx", file_extension: ".xlsx", content_type: "application/x-ole-storage", byte_size: 10 }],
    editable: true,
    limits: DEFAULT_LIMITS,
    notify: makeNotify(),
  });
  await section.addFiles([pngFile()]);
  // 删除待保存附件。
  const localCard = section.element.querySelector(".rsp-attachment-card.is-local");
  localCard.querySelector(".rsp-attachment-remove").dispatchEvent({ type: "click" });
  // 删除已保存附件。
  const persistedCard = section.element.querySelector(".rsp-attachment-card.is-persisted");
  persistedCard.querySelector(".rsp-attachment-remove").dispatchEvent({ type: "click" });
  const payload = await section.buildChangePayload();
  assert.deepEqual(payload.retained_ids, []);
  assert.deepEqual(payload.new_files, []);
  assert.equal(section.hasPendingWork(), false);
"""
    _assert_ok(_run_scenario(tmp_path, scenario, "remove_entries"))


def test_section_rejects_duplicate_content_and_allows_same_name(tmp_path: Path) -> None:
    scenario = """
  const documentRef = makeDocumentRef();
  const notify = makeNotify();
  const section = createRecordAttachmentSection(documentRef, {
    recordId: null,
    initialAttachments: [],
    editable: true,
    limits: DEFAULT_LIMITS,
    notify,
  });
  await section.addFiles([pngFile("a.png"), pngFile("b.png")]);
  const locals = section.element.querySelectorAll(".rsp-attachment-card.is-local");
  assert.equal(locals.length, 1, "相同内容只保留一个");
  assert.ok(notify.calls.some((call) => call.message === "该附件已添加"));
  // 同名不同内容允许。
  await section.addFiles([pngFile("a.png", PNG_BYTES_ALT)]);
  const after = section.element.querySelectorAll(".rsp-attachment-card.is-local");
  assert.equal(after.length, 2);
  const payload = await section.buildChangePayload();
  assert.deepEqual(payload.new_files.map((item) => item.file_name), ["a.png", "a.png"]);
"""
    _assert_ok(_run_scenario(tmp_path, scenario, "duplicate_hash"))


def test_section_paste_only_intercepts_files(tmp_path: Path) -> None:
    scenario = """
  const documentRef = makeDocumentRef();
  const section = createRecordAttachmentSection(documentRef, {
    recordId: null,
    initialAttachments: [],
    editable: true,
    limits: DEFAULT_LIMITS,
    notify: makeNotify(),
  });
  let textPrevented = false;
  const textHandled = section.handlePaste({
    clipboardData: { files: [], items: [] },
    preventDefault() { textPrevented = true; },
  });
  assert.equal(textHandled, false, "纯文字粘贴不拦截");
  assert.equal(textPrevented, false);
  let filePrevented = false;
  const fileHandled = section.handlePaste({
    clipboardData: { files: [new File([PNG_BYTES], "", { type: "image/png" })], items: null },
    preventDefault() { filePrevented = true; },
  });
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(fileHandled, true, "剪贴板含文件时拦截");
  assert.equal(filePrevented, true);
  const locals = section.element.querySelectorAll(".rsp-attachment-card.is-local");
  assert.equal(locals.length, 1);
  const name = locals[0].querySelector(".rsp-attachment-name").textContent;
  assert.match(name, /^粘贴图片-\\d{8}-\\d{6}-1\\.png$/, "无名截图自动命名");
"""
    _assert_ok(_run_scenario(tmp_path, scenario, "paste"))


def test_section_enforces_count_and_size_limits(tmp_path: Path) -> None:
    scenario = """
  const documentRef = makeDocumentRef();
  const notify = makeNotify();
  const section = createRecordAttachmentSection(documentRef, {
    recordId: null,
    initialAttachments: [{ id: 1, file_name: "a.png", file_extension: ".png", content_type: "image/png", byte_size: 100 }],
    editable: true,
    limits: { max_count: 2, max_file_bytes: 100, max_total_bytes: 150 },
    notify,
  });
  // 超过单文件大小。
  await section.addFiles([new File([new Uint8Array(101)], "big.png", { type: "image/png" })]);
  assert.equal(section.element.querySelectorAll(".rsp-attachment-card.is-local").length, 0);
  assert.ok(notify.calls.some((call) => call.message.includes("单个附件最大")));
  // 数量上限（1 已保存 + 上限 2）。
  await section.addFiles([pngFile("one.png", PNG_BYTES)]);
  await section.addFiles([pngFile("two.png", PNG_BYTES_ALT)]);
  const locals = section.element.querySelectorAll(".rsp-attachment-card.is-local");
  assert.equal(locals.length, 1, "第 2 个新文件超出数量上限被拒绝");
  assert.ok(notify.calls.some((call) => call.message.includes("最多 2 个附件")));
  // 总量上限（100 + 12 已达 112，再加 12 超过 150？ 112+12=124 < 150，
  // 因此换一个更大的组合验证总量：先移除数量限制影响，用总量更小的限制。
  const section2 = createRecordAttachmentSection(makeDocumentRef(), {
    recordId: null,
    initialAttachments: [{ id: 1, file_name: "a.png", file_extension: ".png", content_type: "image/png", byte_size: 140 }],
    editable: true,
    limits: { max_count: 10, max_file_bytes: 1000, max_total_bytes: 150 },
    notify,
  });
  await section2.addFiles([pngFile("small.png")]);
  assert.equal(section2.element.querySelectorAll(".rsp-attachment-card.is-local").length, 0);
  assert.ok(notify.calls.some((call) => call.message.includes("附件总大小最大")));
"""
    _assert_ok(_run_scenario(tmp_path, scenario, "limits"))


def test_section_destroy_revokes_object_urls(tmp_path: Path) -> None:
    scenario = """
  const documentRef = makeDocumentRef();
  const section = createRecordAttachmentSection(documentRef, {
    recordId: null,
    initialAttachments: [],
    editable: true,
    limits: DEFAULT_LIMITS,
    notify: makeNotify(),
  });
  await section.addFiles([pngFile()]);
  assert.ok(createdUrls.length >= 1, "图片预览创建了 object URL");
  section.destroy();
  createdUrls.forEach((url) => assert.ok(revokedUrls.includes(url), `destroy 应释放 ${url}`));
  assert.equal(await section.buildChangePayload(), null, "destroy 后不再产生 payload");
"""
    _assert_ok(_run_scenario(tmp_path, scenario, "destroy"))


def test_snapshot_is_readonly_and_uses_audit_change_labels(tmp_path: Path) -> None:
    scenario = """
  const documentRef = makeDocumentRef();
  const snapshot = renderRecordAttachmentSnapshot(documentRef, {
    recordId: 7,
    attachments: [
      { id: 1, file_name: "a.png", file_extension: ".png", content_type: "image/png", byte_size: 10, removed: true, change: "retained" },
      { id: 2, file_name: "b.xlsx", file_extension: ".xlsx", content_type: "application/x-ole-storage", byte_size: 20, change: "removed" },
      { id: 3, file_name: "c.png", file_extension: ".png", content_type: "image/png", byte_size: 30, change: "added" },
    ],
    notify: makeNotify(),
  });
  const text = collectText(snapshot);
  assert.ok(text.includes("保留"), "change 标签优先于 removed 元数据");
  assert.ok(text.includes("移除"));
  assert.ok(text.includes("新增"));
  assert.equal(snapshot.querySelectorAll(".rsp-attachment-remove").length, 0, "只读快照没有删除控件");
  assert.equal(snapshot.querySelectorAll(".rsp-attachment-download").length, 3);
  assert.equal(snapshot.querySelectorAll(".rsp-attachment-upload").length, 0);
"""
    _assert_ok(_run_scenario(tmp_path, scenario, "snapshot"))


# ---------------------------------------------------------------------------
# 模块 API raw 下载、authPreflight 声明与审计附件模型（Node 场景）
# ---------------------------------------------------------------------------

def _run_api_scenario(tmp_path: Path, scenario: str, name: str) -> subprocess.CompletedProcess:
    workdir = tmp_path / name
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    shutil.copy(WEB / "api.js", workdir / "api.js")
    script = (
        'import assert from "node:assert/strict";\n'
        'import { createApi } from "./api.js";\n'
        "async function runScenario() {\n"
        + scenario
        + '\n}\nrunScenario().then(() => console.log("OK"), (error) => { console.error(error && error.stack || error); process.exitCode = 1; });\n'
    )
    (workdir / "scenario.js").write_text(script, encoding="utf-8")
    return subprocess.run(
        ["node", "scenario.js"],
        cwd=workdir,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def test_fetch_record_attachment_uses_platform_raw_api(tmp_path: Path) -> None:
    scenario = """
  const contextCalls = [];
  const expectedBytes = new Uint8Array([80, 75, 3, 4, 9, 9]);
  const context = {
    api: async (path, options) => {
      contextCalls.push({ path, options });
      return {
        ok: true,
        status: 200,
        headers: {
          get: (name) => (name === "Content-Disposition"
            ? "attachment; filename*=UTF-8''%E5%A4%84%E7%90%86%E4%BE%9D%E6%8D%AE.xlsx"
            : null),
        },
        blob: async () => ({ size: expectedBytes.length }),
      };
    },
  };
  const api = createApi(context);
  const result = await api.fetchRecordAttachment(7, 14);
  assert.equal(contextCalls[0].path, "/api/modules/report-special-processing/records/7/attachments/14");
  assert.equal(contextCalls[0].options.responseType, "raw");
  assert.equal(contextCalls[0].options.method, "GET");
  assert.ok(contextCalls[0].options.signal, "AbortController signal 必须传入");
  assert.equal(result.filename, "处理依据.xlsx");
  assert.equal(result.blob.size, expectedBytes.length);
  // 不使用原生 fetch、不跳登录页。
  const source = await import("node:fs").then((fs) => fs.promises.readFile(new URL("./api.js", import.meta.url), "utf8"));
  assert.ok(!source.includes("window.location"));
  assert.ok(!source.includes("response.status === 401"));
"""
    _assert_ok(_run_api_scenario(tmp_path, scenario, "fetch_attachment"))


def test_create_update_declare_auth_preflight_only_with_attachments(tmp_path: Path) -> None:
    scenario = """
  const contextCalls = [];
  const context = {
    api: async (path, options) => {
      contextCalls.push({ path, options });
      return { data: { id: 1 } };
    },
  };
  const api = createApi(context);
  await api.createRecord({ table_name: "t", record_attachments: { retained_ids: [], new_files: [] } });
  assert.equal(contextCalls[0].options.authPreflight, true);
  assert.equal(typeof contextCalls[0].options.body, "string");
  await api.createRecord({ table_name: "t" });
  assert.equal("authPreflight" in contextCalls[1].options, false);
  await api.updateRecord(3, { row_version: 1, record_attachments: { retained_ids: [1], new_files: [] } });
  assert.equal(contextCalls[2].options.authPreflight, true);
  assert.equal(contextCalls[2].path, "/api/modules/report-special-processing/records/3");
  await api.updateRecord(3, { row_version: 1 });
  assert.equal("authPreflight" in contextCalls[3].options, false);
  // 其他动作接口不声明预检。
  await api.changeStatus(3, { row_version: 2, target_status: "completed" });
  assert.equal("authPreflight" in contextCalls[4].options, false);
"""
    _assert_ok(_run_api_scenario(tmp_path, scenario, "auth_preflight"))


def _drawer_helpers_source() -> str:
    source = (WEB / "components" / "record_drawer.js").read_text(encoding="utf-8")
    lines = [line for line in source.splitlines() if not line.startswith("import ")]
    body = "\n".join(lines)
    return body[: body.index("export function createRecordDrawer")]


def test_describe_audit_entry_builds_attachment_diff_model(tmp_path: Path) -> None:
    workdir = tmp_path / "audit_model"
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    scenario = (
        'import assert from "node:assert/strict";\n'
        + _drawer_helpers_source()
        + """
async function runScenario() {
  const entry = describeAuditEntry({
    action_code: "update",
    changed_fields: {
      record_attachments: {
        changed: true,
        old: [
          { id: 1, file_name: "a.png", file_extension: ".png", content_type: "image/png", byte_size: 5, removed: true, change: "removed" },
          { id: 2, file_name: "b.xlsx", file_extension: ".xlsx", content_type: "application/x-ole-storage", byte_size: 6, removed: true, change: "retained" },
        ],
        new: [
          { id: 2, file_name: "b.xlsx", file_extension: ".xlsx", content_type: "application/x-ole-storage", byte_size: 6, removed: true, change: "retained" },
          { id: 3, file_name: "c.png", file_extension: ".png", content_type: "image/png", byte_size: 7, removed: false, change: "added" },
        ],
        old_ids: [1, 2],
        new_ids: [2, 3],
        added_ids: [3],
        removed_ids: [1],
      },
    },
    action_summary: "修改附件（新增 1 个，移除 1 个）",
  }, 7);
  assert.equal(entry.paired.length, 0, "附件不进入普通字符串对照");
  assert.ok(entry.attachmentDiff, "生成专用 attachmentDiff");
  assert.deepEqual(entry.attachmentDiff.old.map((x) => [x.id, x.change]), [[1, "removed"], [2, "retained"]]);
  assert.deepEqual(entry.attachmentDiff.new.map((x) => [x.id, x.change]), [[2, "retained"], [3, "added"]]);
  assert.equal(entry.recordId, 7);
  assert.equal(entry.summary, "修改附件（新增 1 个，移除 1 个）");
  // 后续软删除不改变历史标签：change 由审计自身集合决定。
  const retainedButRemoved = entry.attachmentDiff.new.find((x) => x.id === 2);
  assert.equal(retainedButRemoved.removed, true);
  assert.equal(retainedButRemoved.change, "retained");
  // 创建审计的 {count, ids} 不生成 attachmentDiff。
  const createEntry = describeAuditEntry({
    action_code: "create",
    changed_fields: { record_attachments: { count: 2, ids: [1, 2] } },
  }, 7);
  assert.equal(createEntry.attachmentDiff, null);
}
runScenario().then(() => console.log("OK"), (error) => { console.error(error && error.stack || error); process.exitCode = 1; });
"""
    )
    (workdir / "scenario.js").write_text(scenario, encoding="utf-8")
    result = subprocess.run(["node", "scenario.js"], cwd=workdir, text=True, capture_output=True)
    _assert_ok(result)


# ---------------------------------------------------------------------------
# 抽屉重复提交回归：在途保存期间重复点击只创建一条记录
# ---------------------------------------------------------------------------

DRAWER_HARNESS = r"""
const drawerCreatedUrls = [];
const drawerRevokedUrls = [];

function makeDrawerDocument() {
  const created = [];
  function makeNode(tagName) {
    const classes = new Set();
    const node = {
      tagName: String(tagName || "div").toUpperCase(),
      children: [],
      parentNode: null,
      attributes: {},
      dataset: {},
      style: { setProperty() {}, removeProperty() {} },
      classList: {
        add: (...names) => names.forEach((name) => classes.add(name)),
        remove: (...names) => names.forEach((name) => classes.delete(name)),
        contains: (name) => classes.has(name),
        toggle: (name, enabled) => {
          if (enabled === undefined) {
            if (classes.has(name)) classes.delete(name);
            else classes.add(name);
          } else if (enabled) classes.add(name);
          else classes.delete(name);
          return classes.has(name);
        },
      },
      className: "",
      textContent: "",
      value: "",
      disabled: false,
      hidden: false,
      tabIndex: 0,
      _listeners: {},
      append(...items) {
        items.filter(Boolean).forEach((item) => {
          if (typeof item === "string") {
            const text = makeNode("#text");
            text.textContent = item;
            node.children.push(text);
            return;
          }
          item.parentNode = node;
          node.children.push(item);
        });
        return node;
      },
      appendChild(child) { return node.append(child); },
      replaceChildren(...items) {
        node.children = [];
        if (items.length) node.append(...items);
      },
      remove() {
        if (node.parentNode) {
          node.parentNode.children = node.parentNode.children.filter((item) => item !== node);
        }
      },
      addEventListener(type, handler) {
        (node._listeners[type] = node._listeners[type] || []).push(handler);
      },
      removeEventListener(type, handler) {
        node._listeners[type] = (node._listeners[type] || []).filter((item) => item !== handler);
      },
      dispatchEvent(event) {
        const evt = Object.assign({ target: node, preventDefault() {}, stopPropagation() {} }, event);
        (node._listeners[evt.type] || []).slice().forEach((handler) => handler.call(node, evt));
        return true;
      },
      click() { node.dispatchEvent({ type: "click" }); },
      setAttribute(name, value) {
        node.attributes[name] = String(value);
        if (name === "disabled") node.disabled = true;
        if (name === "hidden") node.hidden = true;
      },
      getAttribute(name) {
        return Object.prototype.hasOwnProperty.call(node.attributes, name) ? node.attributes[name] : null;
      },
      removeAttribute(name) { delete node.attributes[name]; },
      focus() {},
      select() {},
    };
    node.ownerDocument = documentRef;
    return node;
  }
  const documentRef = {
    body: null,
    documentElement: null,
    _listeners: {},
    createElement: (tag) => {
      const node = makeNode(tag);
      created.push(node);
      return node;
    },
    createTextNode: (text) => {
      const node = makeNode("#text");
      node.textContent = String(text);
      return node;
    },
    addEventListener(type, handler) {
      (documentRef._listeners[type] = documentRef._listeners[type] || []).push(handler);
    },
    removeEventListener(type, handler) {
      documentRef._listeners[type] = (documentRef._listeners[type] || []).filter((item) => item !== handler);
    },
    dispatchEvent(event) {
      const evt = Object.assign({ target: documentRef, preventDefault() {}, stopPropagation() {} }, event);
      (documentRef._listeners[evt.type] || []).slice().forEach((handler) => handler(evt));
      return true;
    },
    defaultView: {
      innerWidth: 1280,
      innerHeight: 800,
      crypto: globalThis.crypto,
      btoa: (value) => Buffer.from(value, "binary").toString("base64"),
      URL: {
        createObjectURL: () => {
          const url = `blob:drawer/${drawerCreatedUrls.length + 1}`;
          drawerCreatedUrls.push(url);
          return url;
        },
        revokeObjectURL: (url) => drawerRevokedUrls.push(url),
      },
    },
  };
  documentRef.body = makeNode("body");
  documentRef.documentElement = makeNode("html");
  return documentRef;
}

function walkAll(root, visit) {
  (root.children || []).forEach((child) => {
    visit(child);
    walkAll(child, visit);
  });
}

function findByAriaLabel(root, label) {
  let found = null;
  walkAll(root, (node) => {
    if (!found && node.getAttribute && node.getAttribute("aria-label") === label) found = node;
  });
  return found;
}

function findButtonByText(root, text) {
  let found = null;
  walkAll(root, (node) => {
    if (!found && node.tagName === "BUTTON" && node.textContent === text) found = node;
  });
  return found;
}

function makeDrawerActions(createRecord) {
  return {
    catalog: async () => ({}),
    createRecord,
    updateRecord: async () => ({ data: { id: 1 } }),
    changeStatus: async () => ({ data: { id: 1 } }),
    audit: async () => ({ data: { items: [], total: 0, page: 1, total_pages: 0 } }),
    fetchRecordAttachment: async () => ({ blob: { size: 1 }, filename: "x.png" }),
    getRecord: async () => ({ data: {} }),
  };
}

const DRAWER_STRUCTURED_RECORD = {
  id: 1, record_no: "RSP-20260907-1", can_edit: true, status: "draft", row_version: 3,
  report_process_codes: ["pbc"], record_attachments: [],
  table_name: "客户信息表｜t_customer", field_name: "客户状态｜customer_status",
  value_before: "正常", value_after: "冻结", datasource_name_snapshot: "TCMP生产库",
  structured_content: {
    datasource_id: "ds1", datasource_type: "postgresql",
    tables: [{
      schema: "public", table_name: "t_customer", chinese_table_name: "客户信息表", table_name_source: "DATABASE",
      projects: ["P001"], contracts: ["HT001"],
      fields: [{ column_name: "customer_status", chinese_column_name: "客户状态", column_name_source: "DATABASE", value_before: "正常", value_after: "冻结" }],
    }],
  },
};
const DRAWER_LEGACY_RECORD = {
  id: 2, record_no: "RSP-20260907-2", can_edit: true, status: "draft", row_version: 1,
  report_process_codes: ["pbc"], record_attachments: [],
  table_name: "演示表｜t_demo", field_name: "金额｜amt",
};

const drawerScriptCalls = [];
const DRAWER_SCRIPT_ACTIONS = {
  generateScript: async (payload) => {
    drawerScriptCalls.push(payload);
    return { data: { script: "UPDATE t_customer\nSET status = 'ok';" } };
  },
};

function baseDrawerOptions(actions, hooks) {
  return {
    catalog: {
      report_processes: [],
      users: [],
      dimensions: [],
      governance_owner_candidates_by_dimension: {},
      statuses: [],
      limits: { record_attachments: { max_count: 10, max_file_bytes: 100, max_total_bytes: 200 } },
      capabilities: {},
    },
    catalogAvailable: true,
    record: undefined,
    mode: "create",
    user: { id: "1", username: "admin", display_name: "管理员", role: "admin" },
    actions,
    notify: () => {},
    confirm: async () => true,
    onClose: () => { hooks.closed += 1; },
    onSaved: async () => { hooks.saved += 1; },
    onConflict: async () => {},
  };
}
"""


def _run_drawer_scenario(tmp_path: Path, scenario: str, name: str) -> subprocess.CompletedProcess:
    workdir = tmp_path / name
    (workdir / "components").mkdir(parents=True, exist_ok=True)
    (workdir / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    for js in ("dom.js", "record_table.js", "process_multi_select.js", "record_attachments.js", "record_drawer.js", "bilingual_name_list.js", "table_field_groups.js", "structured_content_editor.js", "metadata_picker.js"):
        shutil.copy(WEB / "components" / js, workdir / "components" / js)
    shutil.copy(WEB / "api.js", workdir / "api.js")
    script = (
        'import assert from "node:assert/strict";\n'
        'import { createRecordDrawer } from "./components/record_drawer.js";\n'
        'globalThis.window = { innerWidth: 1280, innerHeight: 800 };\n'
        + GLOBAL_FILE_POLYFILL
        + DRAWER_HARNESS
        + "\nconst sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));\n"
        + "async function runScenario() {\n"
        + scenario
        + '\n}\nrunScenario().then(() => console.log("OK"), (error) => { console.error(error && error.stack || error); process.exitCode = 1; });\n'
    )
    (workdir / "scenario.js").write_text(script, encoding="utf-8")
    return subprocess.run(
        ["node", "scenario.js"],
        cwd=workdir,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def test_drawer_ignores_repeated_save_clicks_while_request_in_flight(tmp_path: Path) -> None:
    scenario = """
  const documentRef = makeDrawerDocument();
  const updateCalls = [];
  const hooks = { saved: 0, closed: 0 };
  const actions = makeDrawerActions(async () => ({ data: { id: 101 } }));
  actions.updateRecord = async (id, payload) => {
    updateCalls.push(payload);
    await sleep(80);
    return { data: { id: 1 } };
  };
  const overlay = createRecordDrawer(documentRef, {
    ...baseDrawerOptions(actions, hooks), mode: "edit", record: DRAWER_STRUCTURED_RECORD,
  });
  const saveButton = findButtonByText(overlay, "保存修改");
  assert.ok(saveButton, "存在保存修改按钮");
  saveButton.click();
  assert.equal(saveButton.disabled, true, "在途期间保存按钮禁用");
  saveButton.click();
  saveButton.click();
  await sleep(200);
  assert.equal(updateCalls.length, 1, "重复点击只提交一次保存请求");
  assert.equal(updateCalls[0].structured_content.tables[0].table_name, "t_customer", "提交完整结构化内容");
  assert.equal(updateCalls[0].structured_content.tables[0].fields[0].value_before, "正常", "字段级修改前随结构化内容提交");
  assert.equal(hooks.saved, 1, "onSaved 只触发一次");
"""
    _assert_ok(_run_drawer_scenario(tmp_path, scenario, "drawer_double_save"))


def test_drawer_reenables_save_after_failure_for_retry(tmp_path: Path) -> None:
    scenario = """
  const documentRef = makeDrawerDocument();
  const updateCalls = [];
  const hooks = { saved: 0, closed: 0 };
  const actions = makeDrawerActions(async () => ({ data: { id: 1 } }));
  actions.updateRecord = async (id, payload) => {
    updateCalls.push(payload);
    await sleep(20);
    throw new Error("保存失败");
  };
  const overlay = createRecordDrawer(documentRef, {
    ...baseDrawerOptions(actions, hooks), mode: "edit", record: DRAWER_STRUCTURED_RECORD,
  });
  const saveButton = findButtonByText(overlay, "保存修改");
  saveButton.click();
  saveButton.click();
  await sleep(120);
  assert.equal(updateCalls.length, 1, "失败前的重复点击不产生第二次请求");
  assert.equal(saveButton.disabled, false, "失败后恢复可点击以便重试");
  saveButton.click();
  await sleep(120);
  assert.equal(updateCalls.length, 2, "失败后允许用户主动重试");
  assert.equal(hooks.saved, 0);
"""
    _assert_ok(_run_drawer_scenario(tmp_path, scenario, "drawer_retry_after_failure"))


def test_legacy_bilingual_value_is_preserved_until_user_edits_it(tmp_path: Path) -> None:
    scenario = """
  const documentRef = makeDrawerDocument();
  const hooks = { saved: 0, closed: 0 };
  const base = baseDrawerOptions(makeDrawerActions(async () => ({ data: { id: 1 } })), hooks);
  const overlay = createRecordDrawer(documentRef, {
    ...base, mode: "edit", record: { ...DRAWER_LEGACY_RECORD, table_name: "t_legacy", field_name: "f_legacy" },
  });
  const groups = findByAriaLabel(overlay, "处理表与关联字段");
  assert.equal(groups.tableValue, "t_legacy", "未编辑历史值时保留原格式");
  assert.equal(groups.fieldValue, "f_legacy", "未编辑历史字段值时保留原格式");
  assert.equal(findByAriaLabel(overlay, "处理表中文名").value, "t_legacy", "历史值以普通输入行展示");
  assert.equal(findByAriaLabel(overlay, "表1字段中文").value, "f_legacy", "历史字段挂到首张表下");
  assert.equal(findButtonByText(overlay, "改为中英文录入"), null, "不再显示历史格式升级按钮");
  const englishName = findByAriaLabel(overlay, "处理表英文名");
  englishName.value = "table_legacy";
  englishName.dispatchEvent({ type: "input" });
  assert.equal(groups.tableValue, "t_legacy｜table_legacy", "编辑后才使用双语规范格式");
  assert.equal(groups.fieldValue, "f_legacy｜", "编辑后字段升级为分组格式并提示补全英文名");
"""
    _assert_ok(_run_drawer_scenario(tmp_path, scenario, "drawer_legacy_bilingual_value"))


def test_table_field_groups_add_delete_confirm_and_limits(tmp_path: Path) -> None:
    scenario = """
  const documentRef = makeDrawerDocument();
  const hooks = { saved: 0, closed: 0 };
  const confirmCalls = [];
  const base = baseDrawerOptions(makeDrawerActions(async () => ({ data: { id: 1 } })), hooks);
  const overlay = createRecordDrawer(documentRef, {
    ...base,
    mode: "edit",
    record: DRAWER_LEGACY_RECORD,
    confirm: async (title, message) => { confirmCalls.push({ title, message }); return true; },
  });
  const groups = findByAriaLabel(overlay, "处理表与关联字段");
  const collectByClass = (className) => {
    const found = [];
    walkAll(groups, (node) => {
      if (String(node.className || "").split(/\\s+/).includes(className)) found.push(node);
    });
    return found;
  };
  // 新建默认一张表卡片，含一个空字段行
  assert.equal(collectByClass("rsp-tf-card").length, 1);
  assert.equal(collectByClass("rsp-tf-field-row").length, 1);
  // 顶部添加表
  const addTable = findButtonByText(overlay, "+ 添加表");
  addTable.click();
  assert.equal(collectByClass("rsp-tf-card").length, 2, "添加表新建分组卡片");
  addTable.click(); addTable.click(); addTable.click();
  assert.equal(collectByClass("rsp-tf-card").length, 5, "最多五张表");
  assert.equal(addTable.disabled, true, "达到上限后禁用添加表");
  // 表内添加字段，只作用于当前表
  const addField = findButtonByText(overlay, "+ 添加字段");
  addField.click();
  assert.equal(collectByClass("rsp-tf-field-row").length, 2, "首表新增一个字段行");
  // 删除含字段的表需二次确认，提示关联字段一并删除
  let removeTableButtons = collectByClass("rsp-tf-remove-table");
  removeTableButtons[0].click();
  await sleep(20);
  assert.equal(confirmCalls.length, 1, "删除含字段的表弹出二次确认");
  assert.ok(String(confirmCalls[0].message).includes("2 个关联字段"), "确认文案提示关联字段数量");
  assert.equal(collectByClass("rsp-tf-card").length, 4, "确认后删除该表");
  assert.equal(collectByClass("rsp-tf-field-row").length, 0, "表下关联字段一并删除");
  // 删除无字段的表不弹确认
  removeTableButtons = collectByClass("rsp-tf-remove-table");
  removeTableButtons[0].click();
  await sleep(20);
  assert.equal(confirmCalls.length, 1, "无字段的表直接删除");
  assert.equal(collectByClass("rsp-tf-card").length, 3);
  // 字段单独删除
  const addField2 = findButtonByText(overlay, "+ 添加字段");
  addField2.click();
  const fieldRowsBefore = collectByClass("rsp-tf-field-row").length;
  const fieldRemove = collectByClass("rsp-tf-field-row")[0].children.find((node) => String(node.className || "").includes("rsp-bilingual-remove"));
  fieldRemove.click();
  assert.equal(collectByClass("rsp-tf-field-row").length, fieldRowsBefore - 1, "字段可单独删除");
  // 标题显示表序号与字段数量，折叠开关可切换展开状态
  const titled = collectByClass("rsp-tf-card-title").map((node) => node.textContent);
  assert.ok(titled.some((text) => /表\\d+（\\d+个字段）/.test(text)), "标题显示表序号与字段数");
  const toggle = collectByClass("rsp-tf-toggle")[0];
  const cardBody = collectByClass("rsp-tf-card-body")[0];
  const hiddenBefore = Boolean(cardBody.hidden);
  toggle.click();
  assert.equal(Boolean(cardBody.hidden), !hiddenBefore, "折叠开关切换展开状态");
  assert.equal(String(toggle.getAttribute("aria-expanded")), hiddenBefore ? "true" : "false", "aria-expanded 同步");
"""
    _assert_ok(_run_drawer_scenario(tmp_path, scenario, "drawer_table_field_groups"))


LEDGER_HARNESS_EXTRA = r"""
const LEDGER_PNG_BYTES = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 1, 2, 3, 4]);
function pngFile(name = "new.png", bytes = LEDGER_PNG_BYTES) {
  return new File([bytes], name, { type: "image/png" });
}

function countByClass(root, cls) {
  let count = 0;
  walkAll(root, (node) => {
    if (String(node.className || "").split(/\s+/).includes(cls)) count += 1;
  });
  return count;
}

function findByClass(root, cls) {
  let found = null;
  walkAll(root, (node) => {
    if (!found && String(node.className || "").split(/\s+/).includes(cls)) found = node;
  });
  return found;
}
"""


def _run_ledger_scenario(tmp_path: Path, scenario: str, name: str) -> subprocess.CompletedProcess:
    workdir = tmp_path / name
    (workdir / "components").mkdir(parents=True, exist_ok=True)
    (workdir / "pages").mkdir(parents=True, exist_ok=True)
    (workdir / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    for js in (
        "dom.js",
        "record_table.js",
        "process_multi_select.js",
        "record_attachments.js",
        "record_drawer.js",
        "filters.js",
        "bilingual_name_list.js",
        "table_field_groups.js",
        "structured_content_editor.js",
        "metadata_picker.js",
    ):
        shutil.copy(WEB / "components" / js, workdir / "components" / js)
    shutil.copy(WEB / "api.js", workdir / "api.js")
    shutil.copy(WEB / "state.js", workdir / "state.js")
    shutil.copy(WEB / "pages" / "ledger.js", workdir / "pages" / "ledger.js")
    script = (
        'import assert from "node:assert/strict";\n'
        'import { createLedgerPage } from "./pages/ledger.js";\n'
        'import { createState } from "./state.js";\n'
        'globalThis.window = { innerWidth: 1280, innerHeight: 800 };\n'
        + GLOBAL_FILE_POLYFILL
        + DRAWER_HARNESS
        + LEDGER_HARNESS_EXTRA
        + "\nconst sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));\n"
        + "async function runScenario() {\n"
        + scenario
        + '\n}\nrunScenario().then(() => console.log("OK"), (error) => { console.error(error && error.stack || error); process.exitCode = 1; });\n'
    )
    (workdir / "scenario.js").write_text(script, encoding="utf-8")
    return subprocess.run(
        ["node", "scenario.js"],
        cwd=workdir,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


LEDGER_SETUP = r"""
  const documentRef = makeDrawerDocument();
  const root = documentRef.createElement("div");
  documentRef.body.append(root);
  const state = createState();
  let getRecordCalls = 0;
  let updateCalls = 0;
  const baseRecord = {
    id: 1,
    record_no: "RSP-20260907-1",
    can_edit: true,
    status: "draft",
    row_version: 3,
    report_process_codes: ["pbc"],
    record_attachments: [],
    table_name: "old_table",
    field_name: "old_field",
  };
  const conflict = new Error("记录已被其他人更新，请刷新后重试");
  conflict.status = 409;
  conflict.code = "record_version_conflict";
  conflict.refreshRequired = true;
  conflict.fields = {};
  const api = {
    catalog: async () => ({ data: {
      report_processes: [{ code: "pbc", name: "人行报送", order: 1, active: true }],
      users: [{ id: "1", username: "admin", display_name: "管理员" }],
      dimensions: [],
      governance_owner_candidates_by_dimension: {},
      statuses: [],
      limits: { record_attachments: { max_count: 10, max_file_bytes: 10485760, max_total_bytes: 31457280 } },
      capabilities: {},
    } }),
    listRecords: async () => ({ data: { items: [], total: 0, page: 1, page_size: 10, total_pages: 0 } }),
    summary: async () => ({ data: { by_report_process: [] } }),
    getRecord: async () => { getRecordCalls += 1; return { data: { ...baseRecord } }; },
    updateRecord: async () => { updateCalls += 1; throw conflict; },
    createRecord: async () => ({ data: { id: 2 } }),
    audit: async () => ({ data: { items: [], total: 0, page: 1, total_pages: 0 } }),
    fetchRecordAttachment: async () => ({ blob: { size: 1 }, filename: "x.png" }),
    cancelAll: () => {},
  };
  const page = createLedgerPage({
    root,
    api,
    state,
    user: { id: "1", username: "admin", display_name: "管理员", role: "admin" },
    notify: () => {},
    confirm: async () => true,
    prompt: async () => "",
    navigate: () => {},
  });
  await page.activate({ query: {} });
  await page.openDetailOverlay("1");
  const overlay = findByClass(root, "rsp-record-modal-overlay");
  assert.ok(overlay, "编辑抽屉已打开");
  [["处理表中文名", "演示表"], ["处理表英文名", "t_demo"], ["表1字段中文", "金额"], ["表1字段英文", "amt"]].forEach(([label, value]) => {
    const input = findByAriaLabel(overlay, label);
    input.value = value;
    input.dispatchEvent({ type: "input" });
  });
  [["修改前", "旧值"], ["修改后", "新值"]].forEach(([label, value]) => {
    const input = findByAriaLabel(overlay, label);
    input.value = value;
    input.dispatchEvent({ type: "input" });
  });
  overlay.dispatchEvent({
    type: "paste",
    clipboardData: { files: [pngFile()], items: null },
    preventDefault() {},
    stopPropagation() {},
  });
  await sleep(60);
  assert.equal(countByClass(overlay, "rsp-attachment-card"), 1, "粘贴附件已加入");
"""


def test_structured_editor_datasource_table_field_flow(tmp_path: Path) -> None:
    scenario = """
  const documentRef = makeDrawerDocument();
  const hooks = { saved: 0, closed: 0 };
  const actions = makeDrawerActions(async () => ({ data: { id: 9 } }));
  actions.listDatasources = async () => ({ data: { items: [
    { id: "ds1", name: "TCMP生产库", db_type: "postgresql", database: "tcmp", schema: "public" },
  ] } });
  actions.listTables = async () => ({ data: { items: [
    { table_name: "t_customer", table_comment: "客户信息表", schema: "public" },
    { table_name: "tmp_data", table_comment: "", schema: "public" },
  ], total: 2, page: 1, total_pages: 1, schema: "public" } });
  actions.listColumns = async () => ({ data: { items: [
    { column_name: "customer_status", column_comment: "客户状态", data_type: "varchar" },
    { column_name: "customer_type", column_comment: "", data_type: "varchar" },
  ], total: 2, page: 1, total_pages: 1 } });
  const overlay = createRecordDrawer(documentRef, baseDrawerOptions(actions, hooks));
  await sleep(60);
  const editor = findByAriaLabel(overlay, "数据源与处理表字段");
  assert.ok(editor, "新建弹窗渲染行内表单编辑器");
  const collectByAriaLabel = (root, label) => {
    const out = [];
    walkAll(root, (node) => {
      if (node.getAttribute && node.getAttribute("aria-label") === label) out.push(node);
    });
    return out;
  };
  const collectComboOptions = () => {
    const out = [];
    walkAll(overlay, (node) => {
      const classes = String(node.className || "").split(/\s+/);
      if (!classes.includes("rsp-sc-combo-option")) return;
      // 只收集当前可见候选面板中的选项（隐藏面板的旧候选不参与）。
      let parent = node.parentNode;
      while (parent) {
        const pcls = String(parent.className || "").split(/\s+/);
        if (pcls.includes("rsp-sc-combo-panel")) {
          if (!parent.hidden) out.push(node);
          return;
        }
        parent = parent.parentNode;
      }
    });
    return out;
  };
  // 新建默认一张空表；未选数据源时校验定位到数据源
  assert.equal(collectByAriaLabel(overlay, "数据源").length, 1, "默认一张表一行数据源");
  assert.equal(editor.validate({ formal: false }).message, "请选择数据源");
  const dsSelect = collectByAriaLabel(overlay, "数据源")[0];
  dsSelect.value = "ds1";
  dsSelect.dispatchEvent({ type: "change" });
  await sleep(60);
  assert.equal(editor.validate({ formal: false }).message, "请选择处理表");
  // 英文表名：输入关键字实时搜索（防抖），候选在当前弹窗内展开，不弹二级窗
  const tableCombo = collectByAriaLabel(overlay, "请选择表（支持中文/英文模糊搜索）")[0];
  tableCombo.value = "客户";
  tableCombo.dispatchEvent({ type: "input" });
  await sleep(400);
  let options = collectComboOptions();
  assert.ok(options.length >= 2, "表候选渲染（英文名+中文备注）");
  const collectComboCells = (root, cls) => {
    const out = [];
    walkAll(root, (node) => {
      const classes = String(node.className || "").split(/\s+/);
      if (classes.includes(cls)) out.push(node);
    });
    return out;
  };
  const primaryCells = collectComboCells(options[0], "rsp-sc-combo-primary");
  const secondaryCells = collectComboCells(options[0], "rsp-sc-combo-secondary");
  assert.ok(primaryCells.length === 1 && primaryCells[0].textContent === "t_customer", "候选英文名在前");
  assert.ok(secondaryCells.length === 1 && secondaryCells[0].textContent === "客户信息表", "候选中文备注在后");
  options[0].click();
  await sleep(60);
  // 中文表名自动带出 comment，恒可编辑
  const tableZh = collectByAriaLabel(overlay, "中文表名")[0];
  assert.equal(tableZh.value, "客户信息表", "选表自动带出中文表名");
  tableZh.value = "客户主表";
  tableZh.dispatchEvent({ type: "input" });
  assert.equal(editor.getStructured().tables[0].chinese_table_name, "客户主表", "中文表名允许修改");
  // 新表自动生成一行空字段
  assert.ok(collectByAriaLabel(overlay, "请选择字段").length >= 1, "字段区保留空字段行");
  assert.equal(editor.validate({ formal: false }).message, "请至少为“客户主表”选择一个关联字段");
  // 英文字段名：搜索并选择，中文字段名自动带出
  const fieldCombo = collectByAriaLabel(overlay, "请选择字段")[0];
  fieldCombo.value = "客户状态";
  fieldCombo.dispatchEvent({ type: "input" });
  await sleep(400);
  options = collectComboOptions();
  assert.ok(options.length >= 2, "字段候选渲染");
  options[0].click();
  await sleep(60);
  const fieldZh = collectByAriaLabel(overlay, "中文字段名")[0];
  assert.equal(fieldZh.value, "客户状态", "选字段自动带出中文字段名");
  // 添加第二个字段（无 comment 字段），手动补充中文名
  findButtonByText(overlay, "+ 添加字段").click();
  await sleep(60);
  const fieldCombos = collectByAriaLabel(overlay, "请选择字段");
  assert.equal(fieldCombos.length, 2, "添加字段新增一行");
  fieldCombos[1].value = "类型";
  fieldCombos[1].dispatchEvent({ type: "input" });
  await sleep(400);
  options = collectComboOptions();
  assert.ok(options.length >= 2);
  options[1].click();
  await sleep(60);
  const fieldZhs = collectByAriaLabel(overlay, "中文字段名");
  assert.equal(fieldZhs[1].value, "", "无 comment 字段中文名为空");
  fieldZhs[1].value = "客户类型";
  fieldZhs[1].dispatchEvent({ type: "input" });
  // 处理范围：项目/合同至少填一项；多值用“、”分隔解析去重
  const projectInput = collectByAriaLabel(overlay, "项目")[0];
  projectInput.value = "金牛1号、金牛2号；金牛1号";
  projectInput.dispatchEvent({ type: "input" });
  const contractInput = collectByAriaLabel(overlay, "合同")[0];
  contractInput.value = "HT001";
  contractInput.dispatchEvent({ type: "input" });
  const scoped = editor.getStructured();
  assert.deepEqual(scoped.tables[0].projects, ["金牛1号", "金牛2号"], "项目多值分隔解析并去重");
  assert.deepEqual(scoped.tables[0].contracts, ["HT001"]);
  // 修改前/修改后属于具体字段
  const beforeInputs = collectByAriaLabel(overlay, "修改前");
  const afterInputs = collectByAriaLabel(overlay, "修改后");
  beforeInputs[0].value = "正常";
  beforeInputs[0].dispatchEvent({ type: "input" });
  afterInputs[0].value = "冻结";
  afterInputs[0].dispatchEvent({ type: "input" });
  const structured = editor.getStructured();
  assert.equal(structured.tables.length, 1);
  assert.equal(structured.tables[0].table_name, "t_customer");
  assert.equal(structured.tables[0].chinese_table_name, "客户主表");
  assert.equal(structured.tables[0].fields.length, 2);
  assert.equal(structured.tables[0].fields[0].column_name, "customer_status");
  assert.equal(structured.tables[0].fields[1].column_name, "customer_type");
  assert.equal(structured.tables[0].fields[1].chinese_column_name, "客户类型");
  assert.equal(structured.tables[0].fields[0].value_before, "正常");
  assert.equal(structured.tables[0].fields[0].value_after, "冻结");
  assert.equal(structured.tables[0].fields[1].value_before, "", "新字段修改前默认留空");
  assert.equal(structured.tables[0].fields[1].value_after, "", "新字段修改后默认留空");
  assert.equal(structured.datasource_id, "ds1");
  assert.equal(structured.tables[0].datasource_id, "ds1", "表级数据源随结构化内容提交");
  assert.equal(editor.validate({ formal: true }).message, "客户类型：请输入修改前内容");
  const strings = editor.getStrings();
  assert.equal(strings.table_name, "客户主表｜t_customer");
  assert.equal(strings.field_name, "客户状态｜customer_status；客户类型｜customer_type");
  // 删除最后一个字段恢复空选行，字段区永不为空
  const removeFieldButtons = [];
  walkAll(overlay, (node) => {
    const classes = String(node.className || "").split(/\s+/);
    if (classes.includes("rsp-sc-remove-field")) removeFieldButtons.push(node);
  });
  removeFieldButtons[0].click();
  removeFieldButtons[1].click();
  await sleep(60);
  assert.equal(editor.validate({ formal: false }).message, "请至少为“客户主表”选择一个关联字段", "字段清空后仍保留空选行");
"""
    _assert_ok(_run_drawer_scenario(tmp_path, scenario, "structured_editor_flow"))


def test_structured_editor_tables_have_own_datasources(tmp_path: Path) -> None:
    scenario = """
  const documentRef = makeDrawerDocument();
  const hooks = { saved: 0, closed: 0 };
  const base = baseDrawerOptions(makeDrawerActions(async () => ({ data: { id: 1 } })), hooks);
  const actions = { ...base.actions };
  actions.listDatasources = async () => ({ data: { items: [
    { id: "ds1", name: "生产库", db_type: "postgresql", schema: "public" },
    { id: "ds2", name: "核算库", db_type: "mysql", schema: "acc" },
  ] } });
  actions.listTables = async () => ({ data: { items: [
    { table_name: "t_customer", table_comment: "客户信息表", schema: "public" },
  ], total: 1, page: 1, total_pages: 1, schema: "public" } });
  actions.listColumns = async () => ({ data: { items: [], total: 0, page: 1, total_pages: 1 } });
  const overlay = createRecordDrawer(documentRef, {
    ...base, actions, mode: "edit", record: DRAWER_STRUCTURED_RECORD,
  });
  await sleep(60);
  const editor = findByAriaLabel(overlay, "数据源与处理表字段");
  assert.ok(editor, "编辑弹窗渲染行内表单编辑器");
  assert.equal(editor.getStructured().tables.length, 1, "编辑回显结构化表");
  assert.equal(editor.getStructured().tables[0].fields[0].value_before, "正常", "字段级修改前回显");
  assert.equal(editor.getStructured().tables[0].datasource_id, "ds1", "表级数据源回显");
  const collectByAriaLabel = (root, label) => {
    const out = [];
    walkAll(root, (node) => {
      if (node.getAttribute && node.getAttribute("aria-label") === label) out.push(node);
    });
    return out;
  };
  const dsSelects = collectByAriaLabel(overlay, "数据源");
  assert.equal(dsSelects.length, 1, "回显只有一张表");
  assert.equal(dsSelects[0].value, "ds1", "回显数据源选中");
  // 添加第二张表：各自独立数据源
  findButtonByText(overlay, "+ 添加表").click();
  await sleep(60);
  const dsSelects2 = collectByAriaLabel(overlay, "数据源");
  assert.equal(dsSelects2.length, 2, "添加表新增一行");
  dsSelects2[1].value = "ds2";
  dsSelects2[1].dispatchEvent({ type: "change" });
  await sleep(60);
  assert.equal(dsSelects2[0].value, "ds1", "第一张表数据源不受影响");
  assert.equal(dsSelects2[1].value, "ds2", "第二张表数据源独立");
  // 第二张表未选处理表：校验定位到第二张表
  assert.equal(editor.validate({ formal: false }).message, "请选择处理表");
  // 已完成的首表数据源不因第二张表变化而改变
  assert.equal(editor.getStructured().tables[0].datasource_id, "ds1");
"""
    _assert_ok(_run_drawer_scenario(tmp_path, scenario, "structured_multi_datasource"))


def test_drawer_generates_script_with_confirm_before_overwrite(tmp_path: Path) -> None:
    scenario = """
  const documentRef = makeDrawerDocument();
  const hooks = { saved: 0, closed: 0 };
  const base = baseDrawerOptions(makeDrawerActions(async () => ({ data: { id: 1 } })), hooks);
  const actions = { ...base.actions, ...DRAWER_SCRIPT_ACTIONS };
  const context = { confirmCalls: [], generateCalls: [] };
  const overlay = createRecordDrawer(documentRef, {
    ...base, actions, mode: "edit", record: DRAWER_STRUCTURED_RECORD,
    confirm: async (title, message) => { context.confirmCalls.push({ title, message }); return false; },
  });
  await sleep(60);
  // 生成脚本按钮在结构化模式下可用；无脚本时复制按钮禁用
  const generateButton = findButtonByText(overlay, "生成脚本");
  assert.ok(generateButton, "存在生成脚本按钮");
  const copyButton = findButtonByText(overlay, "复制脚本");
  assert.equal(copyButton.disabled, true, "无脚本时复制禁用");
  generateButton.click();
  await sleep(80);
  assert.equal(drawerScriptCalls.length, 1, "点击生成脚本调用接口");
  const payload = drawerScriptCalls[0];
  assert.equal(payload.structured_content.tables[0].table_name, "t_customer", "生成脚本携带结构化内容");
  assert.deepEqual(payload.structured_content.tables[0].projects, ["P001"], "生成脚本携带处理范围");
  const textarea = findByAriaLabel(overlay, "处理脚本");
  console.log("SCRIPT_VAL", JSON.stringify(textarea.value));
  assert.equal(textarea.value, "UPDATE t_customer\\nSET status = 'ok';", "生成结果写入处理脚本框");
  assert.equal(findButtonByText(overlay, "重新生成") != null, true, "生成后按钮变为重新生成");
  assert.equal(findButtonByText(overlay, "复制脚本").disabled, false, "有脚本后复制可用");
  // 用户手工修改脚本后再重新生成必须确认
  textarea.value = "手工修改的脚本";
  textarea.dispatchEvent({ type: "input" });
  findButtonByText(overlay, "重新生成").click();
  await sleep(80);
  assert.equal(context.confirmCalls.length, 1, "重新生成前需确认覆盖");
  assert.ok(String(context.confirmCalls[0].message).includes("覆盖当前处理脚本内容"));
  assert.equal(textarea.value, "手工修改的脚本", "用户取消后保留当前脚本");
  assert.equal(drawerScriptCalls.length, 1, "取消后不重新生成");
  // 确认后重新生成并覆盖
  const overlay2 = createRecordDrawer(documentRef, {
    ...base, actions, mode: "edit", record: DRAWER_STRUCTURED_RECORD,
    confirm: async () => true,
  });
  await sleep(60);
  findButtonByText(overlay2, "生成脚本").click();
  await sleep(80);
  const textarea2 = findByAriaLabel(overlay2, "处理脚本");
  assert.equal(textarea2.value, "UPDATE t_customer\\nSET status = 'ok';", "第二次生成写入处理脚本框");
  // 用户修改后点“重新生成”，确认通过则整体覆盖
  textarea2.value = "手工修改的脚本";
  textarea2.dispatchEvent({ type: "input" });
  findButtonByText(overlay2, "重新生成").click();
  await sleep(80);
  assert.equal(textarea2.value, "UPDATE t_customer\\nSET status = 'ok';", "确认后脚本被重新生成覆盖");
"""
    _assert_ok(_run_drawer_scenario(tmp_path, scenario, "drawer_generate_script"))


def test_version_conflict_keeps_drawer_and_requires_explicit_reload(tmp_path: Path) -> None:
    scenario = (
        LEDGER_SETUP
        + """
  const saveButton = findButtonByText(overlay, "保存修改");
  assert.ok(saveButton, "存在保存修改按钮");
  saveButton.click();
  await sleep(80);
  // 冲突后：抽屉不重建、字段与附件保留、不自动拉取服务器记录。
  const overlayAfter = findByClass(root, "rsp-record-modal-overlay");
  assert.equal(overlayAfter, overlay, "冲突不得重建抽屉");
  assert.equal(updateCalls, 1);
  assert.equal(getRecordCalls, 1, "用户确认前不得自动刷新记录");
  assert.equal(findByAriaLabel(overlay, "处理表与关联字段").tableValue, "演示表｜t_demo", "字段值保留");
  assert.equal(findByAriaLabel(overlay, "处理表与关联字段").fieldValue, "金额｜amt", "字段值保留");
  assert.equal(countByClass(overlay, "rsp-attachment-card"), 1, "附件保留");
  const conflictBar = findByClass(overlay, "rsp-conflict-bar");
  assert.ok(conflictBar, "显示冲突提示条");
  assert.equal(conflictBar.hidden, false);
  const reloadButton = findButtonByText(overlay, "加载最新记录");
  assert.ok(reloadButton, "提供显式加载最新记录按钮");
  // 显式点击后才重建抽屉并拉取服务器记录。
  reloadButton.click();
  await sleep(80);
  assert.equal(getRecordCalls, 2, "点击后才加载最新记录");
  const rebuilt = findByClass(root, "rsp-record-modal-overlay");
  assert.ok(rebuilt && rebuilt !== overlay, "显式刷新后抽屉重建");
"""
    )
    _assert_ok(_run_ledger_scenario(tmp_path, scenario, "ledger_conflict_keep"))


def test_persisted_image_cards_load_thumbnails_and_share_cache(tmp_path: Path) -> None:
    scenario = """
  const documentRef = makeDocumentRef();
  const fetchCalls = [];
  const fetchAttachment = async (recordId, id) => {
    fetchCalls.push([recordId, id]);
    await new Promise((resolve) => setTimeout(resolve, 5));
    return { blob: { size: 8 }, filename: "image.png" };
  };
  const thumbCache = new Map();
  const meta = { id: 11, file_name: "image.png", file_extension: ".png", content_type: "image/png", byte_size: 4096, content_sha256: "aa" };
  const section = createRecordAttachmentSection(documentRef, {
    recordId: 7,
    initialAttachments: [meta],
    editable: true,
    limits: DEFAULT_LIMITS,
    notify: makeNotify(),
    fetchAttachment,
    thumbCache,
  });
  await new Promise((resolve) => setTimeout(resolve, 30));
  const cards = findAll(section.element, ".rsp-attachment-card");
  assert.equal(cards.length, 1);
  const thumbs = findAll(cards[0], ".rsp-attachment-thumb");
  assert.equal(thumbs.length, 1, "已存图片渲染缩略图容器");
  const imgs = findAll(thumbs[0], "img");
  assert.equal(imgs.length, 1, "缩略图加载后渲染 img");
  assert.ok(String(imgs[0].attributes.src || "").startsWith("blob:fake/"), "img 使用 object URL");
  assert.equal(fetchCalls.length, 1, "自动加载只下载一次");

  const snap = renderRecordAttachmentSnapshot(documentRef, {
    recordId: 7,
    attachments: [meta],
    fetchAttachment,
    thumbCache,
  });
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.equal(fetchCalls.length, 1, "同 ID 附件复用缓存不重复下载");
  const snapThumbs = findAll(snap, ".rsp-attachment-thumb");
  assert.equal(findAll(snapThumbs[0], "img").length, 1, "只读快照同样显示缩略图");
  section.destroy();
"""
    _assert_ok(_run_scenario(tmp_path, scenario, "thumb_persisted_cache"))


def test_thumbnail_autoload_skips_oversize_and_silent_failure(tmp_path: Path) -> None:
    scenario = """
  const documentRef = makeDocumentRef();
  const fetchCalls = [];
  const notify = makeNotify();
  const fetchAttachment = async (recordId, id) => {
    fetchCalls.push([recordId, id]);
    if (id === 21) throw new Error("下载失败");
    return { blob: { size: 8 }, filename: "x.png" };
  };
  const oversize = { id: 20, file_name: "big.png", file_extension: ".png", content_type: "image/png", byte_size: 5 * 1024 * 1024, content_sha256: "bb" };
  const broken = { id: 21, file_name: "broken.png", file_extension: ".png", content_type: "image/png", byte_size: 1024, content_sha256: "cc" };
  const snap = renderRecordAttachmentSnapshot(documentRef, {
    recordId: 7,
    attachments: [oversize, broken],
    fetchAttachment,
    notify,
    thumbCache: new Map(),
  });
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.deepEqual(fetchCalls.map((call) => call[1]), [21], "超阈值图片不自动下载");
  const thumbs = findAll(snap, ".rsp-attachment-thumb");
  assert.equal(thumbs.length, 2);
  assert.equal(findAll(thumbs[0], "img").length, 0, "超阈值保持占位");
  assert.ok(collectText(thumbs[0]).includes("图片"), "超阈值保留图片占位文案");
  assert.equal(findAll(thumbs[1], "img").length, 0, "下载失败回退占位");
  assert.ok(collectText(thumbs[1]).includes("图片"));
  assert.equal(notify.calls.length, 0, "缩略图加载失败静默回退不打扰用户");
"""
    _assert_ok(_run_scenario(tmp_path, scenario, "thumb_skip_oversize"))


def test_drawer_revokes_thumbnail_urls_on_close(tmp_path: Path) -> None:
    scenario = """
  const documentRef = makeDrawerDocument();
  const hooks = { saved: 0, closed: 0 };
  const fetchCalls = [];
  const actions = makeDrawerActions(async () => ({ data: { id: 1 } }));
  actions.fetchRecordAttachment = async (recordId, id) => {
    fetchCalls.push([recordId, id]);
    return { blob: { size: 8 }, filename: "image.png" };
  };
  const options = baseDrawerOptions(actions, hooks);
  options.mode = "edit";
  options.record = {
    id: 5,
    record_attachments: [
      { id: 31, file_name: "image.png", file_extension: ".png", content_type: "image/png", byte_size: 2048, content_sha256: "dd" },
    ],
  };
  const overlay = createRecordDrawer(documentRef, options);
  await sleep(60);
  assert.equal(fetchCalls.length, 1, "编辑抽屉已存图片自动加载缩略图");
  assert.ok(drawerCreatedUrls.length >= 1, "缩略图创建了 object URL");
  const closeButton = findByAriaLabel(overlay, "关闭");
  assert.ok(closeButton, "存在关闭按钮");
  closeButton.click();
  await sleep(10);
  assert.equal(hooks.closed, 1);
  drawerCreatedUrls.forEach((url) => {
    assert.ok(drawerRevokedUrls.includes(url), `关闭抽屉释放缩略图 URL：${url}`);
  });
"""
    _assert_ok(_run_drawer_scenario(tmp_path, scenario, "thumb_revoke_on_close"))


def test_thumbnail_autoload_source_markers() -> None:
    source = (WEB / "components" / "record_attachments.js").read_text(encoding="utf-8")
    assert "THUMB_AUTOLOAD_MAX_BYTES" in source
    assert "thumbCache" in source
    drawer = (WEB / "components" / "record_drawer.js").read_text(encoding="utf-8")
    assert "thumbCache" in drawer
    assert "revokeObjectURL" in drawer
