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
    for js in ("dom.js", "record_table.js", "process_multi_select.js", "record_attachments.js", "record_drawer.js"):
        shutil.copy(WEB / "components" / js, workdir / "components" / js)
    shutil.copy(WEB / "api.js", workdir / "api.js")
    script = (
        'import assert from "node:assert/strict";\n'
        'import { createRecordDrawer } from "./components/record_drawer.js";\n'
        'globalThis.window = { innerWidth: 1280, innerHeight: 800 };\n'
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
  const createCalls = [];
  const hooks = { saved: 0, closed: 0 };
  const actions = makeDrawerActions(async (payload) => {
    createCalls.push(payload);
    await sleep(80);
    return { data: { id: 101 } };
  });
  const overlay = createRecordDrawer(documentRef, baseDrawerOptions(actions, hooks));
  findByAriaLabel(overlay, "处理表名").value = "t_demo";
  findByAriaLabel(overlay, "处理字段名").value = "amt";
  const saveButton = findButtonByText(overlay, "保存记录");
  assert.ok(saveButton, "存在保存记录按钮");
  saveButton.click();
  assert.equal(saveButton.disabled, true, "在途期间保存按钮禁用");
  saveButton.click();
  saveButton.click();
  await sleep(200);
  assert.equal(createCalls.length, 1, "重复点击只创建一条记录");
  assert.equal(hooks.saved, 1, "onSaved 只触发一次");
"""
    _assert_ok(_run_drawer_scenario(tmp_path, scenario, "drawer_double_save"))


def test_drawer_reenables_save_after_failure_for_retry(tmp_path: Path) -> None:
    scenario = """
  const documentRef = makeDrawerDocument();
  const createCalls = [];
  const hooks = { saved: 0, closed: 0 };
  const actions = makeDrawerActions(async (payload) => {
    createCalls.push(payload);
    await sleep(20);
    throw new Error("保存失败");
  });
  const overlay = createRecordDrawer(documentRef, baseDrawerOptions(actions, hooks));
  findByAriaLabel(overlay, "处理表名").value = "t_demo";
  findByAriaLabel(overlay, "处理字段名").value = "amt";
  const saveButton = findButtonByText(overlay, "保存记录");
  saveButton.click();
  saveButton.click();
  await sleep(120);
  assert.equal(createCalls.length, 1, "失败前的重复点击不产生第二次请求");
  assert.equal(saveButton.disabled, false, "失败后恢复可点击以便重试");
  saveButton.click();
  await sleep(120);
  assert.equal(createCalls.length, 2, "失败后允许用户主动重试");
  assert.equal(hooks.saved, 0);
"""
    _assert_ok(_run_drawer_scenario(tmp_path, scenario, "drawer_retry_after_failure"))


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
  findByAriaLabel(overlay, "处理表名").value = "t_demo";
  findByAriaLabel(overlay, "处理字段名").value = "amt";
  overlay.dispatchEvent({
    type: "paste",
    clipboardData: { files: [pngFile()], items: null },
    preventDefault() {},
    stopPropagation() {},
  });
  await sleep(60);
  assert.equal(countByClass(overlay, "rsp-attachment-card"), 1, "粘贴附件已加入");
"""


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
  assert.equal(findByAriaLabel(overlay, "处理表名").value, "t_demo", "字段值保留");
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
