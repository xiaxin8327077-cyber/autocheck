from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "src" / "auto_check" / "modules" / "dashboard_management" / "web"


def _copy_web_modules(tmp_path: Path) -> None:
    for source in WEB.rglob("*.js"):
        target = tmp_path / source.relative_to(WEB)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target.with_suffix(".mjs"))
    for target in tmp_path.rglob("*.mjs"):
        content = target.read_text(encoding="utf-8")
        target.write_text(content.replace(".js\"", ".mjs\"").replace(".js'", ".mjs'"), encoding="utf-8")


def _run_scenario(tmp_path: Path) -> dict:
    _copy_web_modules(tmp_path)
    scenario = tmp_path / "scenario.mjs"
    scenario.write_text(
        """
import assert from "node:assert/strict";
import {
  activateLifecycle, applyCatalog, createState, currentDraft, hasPermission, markSqlChanged,
  beginPending, captureRequest, discardDraft, endPending, isTokenCurrent, markDatasourceChanged, markSaved,
  markPreviewFailed, previewRows, recordPreview, requestLeave, selectBoard, selectRegion, setSourceMode,
  startRequest, stopRequests, SELECTION_STORAGE_KEY,
  enterMonitorView, leaveMonitorView, resetMonitorFilters,
} from "./state.mjs";
import { createApi } from "./api.mjs";
import { sourceTestStatusText } from "./components/source_editor.mjs";
import { formatPreviewValue } from "./components/preview_table.mjs";
import { formatMonitorDateTime, monitorBoardName, monitorStatusText } from "./components/external_api_monitor.mjs";
const { confirmAndRotateToken } = await import("./index.mjs");

const catalog = {
  boards: [
    { code: "report_submission", name: "金融监管报表报送大屏" },
    { code: "reporting_process", name: "金融监管报送流程大屏" },
  ],
  regions: [
    { id: 11, region_code: "monthly_trust_projects", name: "月度信托项目数量", shape: "list", system_supported: false,
      fields: [{ alias: "month", name: "月份", enabled: true }],
      source_config: { source_mode: "sql", datasource_id: "dws", sql_text: "SELECT month FROM trust" } },
  ],
};
const processCatalog = {
  boards: catalog.boards,
  regions: [
    { id: 21, region_code: "regulatory_report_count", name: "监管报送报表数量", shape: "list", system_supported: false,
      fields: [{ alias: "report_type", name: "报表类型", enabled: true }],
      source_config: { source_mode: "sql", datasource_id: "dws", sql_text: "SELECT report_type, COUNT(*) AS report_count FROM report_source GROUP BY report_type" } },
    { id: 22, region_code: "monthly_regulatory_report_time", name: "当月监管报送报表时间", shape: "list", system_supported: true,
      fields: [], source_config: { source_mode: "system" } },
    { id: 23, region_code: "report_validation_statistics", name: "报表校验统计", shape: "list", system_supported: false,
      fields: [], source_config: { source_mode: "sql", sql_text: "SELECT 1" } },
  ],
};
const storedValues = new Map([[SELECTION_STORAGE_KEY, JSON.stringify({
  activeBoardCode: "reporting_process",
  selectedRegionByBoard: { report_submission: 11, reporting_process: 23 },
})]]);
const sessionStore = {
  getItem: (key) => storedValues.get(key) || null,
  setItem: (key, value) => storedValues.set(key, value),
};
const restoredState = createState(sessionStore);
assert.equal(restoredState.activeBoardCode, "reporting_process");
applyCatalog(restoredState, "report_submission", catalog);
applyCatalog(restoredState, "reporting_process", processCatalog);
assert.equal(currentDraft(restoredState).region_id, 23);
selectRegion(restoredState, 22);
const refreshedState = createState(sessionStore);
applyCatalog(refreshedState, "report_submission", catalog);
applyCatalog(refreshedState, "reporting_process", processCatalog);
assert.equal(refreshedState.activeBoardCode, "reporting_process");
assert.equal(currentDraft(refreshedState).region_id, 22);

const state = createState();
assert.equal(state.activeBoardCode, "report_submission");
applyCatalog(state, "report_submission", catalog);
applyCatalog(state, "reporting_process", processCatalog);
selectRegion(state, 11);
assert.equal(currentDraft(state).sql_text, "SELECT month FROM trust");

// Token 轮换必须等待确认结果；取消时不得调用生成接口，确认后才执行一次。
let rotationCalls = 0;
const cancelled = await confirmAndRotateToken({
  configured: true,
  confirm: async () => false,
  rotate: async () => { rotationCalls += 1; },
});
assert.equal(cancelled, false);
assert.equal(rotationCalls, 0);
const continued = await confirmAndRotateToken({
  configured: true,
  confirm: async () => true,
  rotate: async () => { rotationCalls += 1; },
});
assert.equal(continued, true);
assert.equal(rotationCalls, 1);
assert.equal(state.dirtyRegions.has("report_submission:11"), false);
markDatasourceChanged(state, "other");
assert.equal(state.dirtyRegions.has("report_submission:11"), true);
markDatasourceChanged(state, "dws");
assert.equal(state.dirtyRegions.has("report_submission:11"), false);
markSqlChanged(state, "SELECT changed then restored");
assert.equal(state.dirtyRegions.has("report_submission:11"), true);
markSqlChanged(state, "SELECT month FROM trust");
assert.equal(state.dirtyRegions.has("report_submission:11"), false);
let unnecessaryConfirmationCount = 0;
assert.equal(await requestLeave(state, async () => { unnecessaryConfirmationCount += 1; return false; }), true);
assert.equal(unnecessaryConfirmationCount, 0);
selectBoard(state, "reporting_process");
assert.deepEqual(state.catalogs.get(state.activeBoardCode).regions.map((region) => region.name), ["监管报送报表数量", "当月监管报送报表时间", "报表校验统计"]);
assert.equal(currentDraft(state).sql_text, "SELECT report_type, COUNT(*) AS report_count FROM report_source GROUP BY report_type");
selectRegion(state, 22);
assert.equal(currentDraft(state).source_mode, "system");
assert.equal(setSourceMode(state, "sql").source_mode, "sql");
assert.equal(state.dirtyRegions.has("reporting_process:22"), true);
assert.equal(setSourceMode(state, "system").source_mode, "system");
assert.equal(state.dirtyRegions.has("reporting_process:22"), false);
selectBoard(state, "report_submission");
assert.equal(state.selectedRegionByBoard.get("report_submission"), 11);
assert.equal(currentDraft(state).sql_text, "SELECT month FROM trust");
markSqlChanged(state, "SELECT changed");
assert.equal(currentDraft(state).testStatus, "idle");
assert.equal(currentDraft(state).testError, "");
const failedToken = captureRequest(state);
assert.ok(markPreviewFailed(state, failedToken, "查询失败：数据表不存在：missing_table"));
assert.equal(currentDraft(state).testStatus, "failed");
assert.equal(currentDraft(state).testError, "查询失败：数据表不存在：missing_table");
assert.equal(sourceTestStatusText("failed", "sql", currentDraft(state).testError), "当前 SQL 有问题：查询失败：数据表不存在：missing_table");
const failedSaveToken = captureRequest(state);
assert.ok(markSaved(state, failedSaveToken, { row_version: 7, source_mode: "sql" }));
assert.equal(currentDraft(state).testStatus, "failed");
assert.equal(currentDraft(state).testError, "查询失败：数据表不存在：missing_table");
markSqlChanged(state, "SELECT changed again");
assert.equal(currentDraft(state).testError, "");
const warningToken = captureRequest(state);
assert.ok(markSaved(state, warningToken, { row_version: 8, source_mode: "sql", sql_warning: "只允许单条只读查询" }));
assert.equal(currentDraft(state).testStatus, "failed");
assert.equal(currentDraft(state).testError, "只允许单条只读查询");
assert.equal(sourceTestStatusText("failed", "sql", currentDraft(state).testError), "当前 SQL 有问题：只允许单条只读查询");
assert.equal(formatPreviewValue("2026-07-02T12:00:47", { value_type: "datetime" }), "2026-07-02 12:00:47");
assert.equal(formatPreviewValue("2026-07-02T12:00:47.123+08:00", { value_type: "datetime" }), "2026-07-02 12:00:47");
assert.equal(formatPreviewValue("2026-07", { value_type: "string" }), "2026-07");
assert.deepEqual(previewRows([{ n: 1 }, { n: 2 }, { n: 3 }, { n: 4 }, { n: 5 }, { n: 6 }, { n: 7 }, { n: 8 }, { n: 9 }, { n: 10 }, { n: 11 }]), Array.from({ length: 10 }, (_, index) => ({ n: index + 1 })));
markSqlChanged(state, "SELECT needs confirmation");
assert.equal(await requestLeave(state, async () => false), false);
assert.equal(await requestLeave(state, async () => true), true);
assert.equal(hasPermission({ capabilities: ["dashboard_management.view"] }, "dashboard_management.manage"), false);
assert.equal(hasPermission({ capabilities: ["dashboard_management.manage"] }, "dashboard_management.manage"), true);
const controllers = [];
const context = { api: async (_path, options) => { controllers.push(options.signal); return { data: {} }; } };
const api = startRequest(state, context, "/datasources");
stopRequests(state);
await api;
assert.equal(controllers.length, 1);
assert.equal(controllers[0].aborted, true);
activateLifecycle(state);

// 请求归属在发出时固定：切换当前视图后，测试结果只能回写原区域草稿。
selectRegion(state, 11);
const token = captureRequest(state);
selectBoard(state, "reporting_process");
assert.equal(isTokenCurrent(state, token), false);
recordPreview(state, token, { rows: [{ month: "2024-01" }], columns: ["month"], row_version: 9 });
assert.equal(state.drafts.get("report_submission:11").row_version, 9);
assert.equal(state.drafts.get("report_submission:11").testStatus, "passed");
assert.equal(state.drafts.get("report_submission:11").testError, "");
assert.equal(currentDraft(state).region_id, 22);
assert.equal(currentDraft(state).preview, null);
markSaved(state, token, { row_version: 10, source_mode: "sql" });
assert.equal(state.drafts.get("report_submission:11").row_version, 10);
assert.equal(state.dirtyRegions.has("report_submission:11"), false);
// 草稿变化后，旧 revision 的响应不得覆盖新 SQL 草稿。
selectBoard(state, "report_submission");
selectRegion(state, 11);
const staleToken = captureRequest(state);
markSqlChanged(state, "SELECT newer revision");
assert.equal(recordPreview(state, staleToken, { rows: [{ stale: true }], row_version: 19 }), null);
assert.equal(currentDraft(state).sql_text, "SELECT newer revision");

// SQL 测试回写的版本必须成为紧随其后的保存请求版本，并在成功后清理 dirty。
selectBoard(state, "report_submission");
selectRegion(state, 11);
markSqlChanged(state, "SELECT persist");
const saveToken = captureRequest(state);
recordPreview(state, saveToken, { rows: [], columns: [], row_version: 20 });
const savedRequests = [];
const saveApi = createApi({ api: async (path, options) => { savedRequests.push({ path, payload: JSON.parse(options.body) }); return { data: { row_version: 21, source_mode: "sql" } }; } }, state);
markSaved(state, saveToken, await saveApi.saveSource(saveToken.regionId, { source_mode: "sql", datasource_id: "dws", sql_text: "SELECT persist", row_version: state.drafts.get(saveToken.key).row_version }));
assert.equal(savedRequests[0].payload.row_version, 20);
assert.equal(state.drafts.get(saveToken.key).row_version, 21);
assert.equal(state.dirtyRegions.has(saveToken.key), false);
await saveApi.createRegion("report_submission", { name: "一次创建", shape: "list", enabled: true, display_order: 99, description: "", fields: [{ field_alias: "initial_value", name: "初始字段", value_type: "string", nullable: false, enabled: true, display_order: 10, description: "" }] });
assert.equal(savedRequests.at(-1).path, "/api/modules/dashboard-management/boards/report_submission/regions");
assert.equal(savedRequests.at(-1).payload.fields.length, 1);
await saveApi.deleteRegion(11, { row_version: 7 });
assert.equal(savedRequests.at(-1).path, "/api/modules/dashboard-management/regions/11");
assert.equal(savedRequests.at(-1).payload.row_version, 7);

// 放弃未保存改动必须恢复服务端快照，并使区域仍然可在以后独立编辑。
selectBoard(state, "report_submission");
selectRegion(state, 11);
markSqlChanged(state, "SELECT discarded");
discardDraft(state, captureRequest(state));
assert.equal(currentDraft(state).sql_text, "SELECT persist");
assert.equal(state.dirtyRegions.has("report_submission:11"), false);

// 字段维护后的强制目录刷新只重建受影响区域的服务端草稿，不影响其它看板草稿。
markSqlChanged(state, "SELECT local change");
const revisionBeforeRefresh = currentDraft(state).revision;
applyCatalog(state, "report_submission", { ...catalog, regions: [{ ...catalog.regions[0], source_config: { source_mode: "sql", datasource_id: "fresh", sql_text: "SELECT fresh", row_version: 7 } }] }, { resetRegionIds: [11] });
assert.equal(currentDraft(state).sql_text, "SELECT fresh");
assert.equal(currentDraft(state).row_version, 7);
assert.equal(currentDraft(state).testStatus, "idle");
assert.ok(currentDraft(state).revision > revisionBeforeRefresh);
assert.equal(state.drafts.get("reporting_process:22").source_mode, "system");

assert.equal(beginPending(state, "save:report_submission:11"), true);
assert.equal(beginPending(state, "save:report_submission:11"), false);
endPending(state, "save:report_submission:11");
assert.equal(beginPending(state, "save:report_submission:11"), true);

// 监控视图：进入/退出不丢失草稿，筛选和分页独立
markSqlChanged(state, "SELECT unsaved before monitor");
const before = currentDraft(state);
enterMonitorView(state, 128);
assert.equal(state.viewMode, "monitor");
leaveMonitorView(state);
assert.equal(state.viewMode, "management");
assert.equal(currentDraft(state), before);
assert.equal(currentDraft(state).sql_text, "SELECT unsaved before monitor");
assert.equal(state.managementScrollTop, 128);

// 监控筛选变化/清除回第一页
state.monitorFilters = { board_code: "report_submission", result_status: "success", caller_ip: "", started_at: "", ended_at: "" };
state.monitorPage = 3;
resetMonitorFilters(state);
assert.equal(state.monitorPage, 1);
assert.deepEqual(state.monitorFilters, { board_code: "", result_status: "", caller_ip: "", started_at: "", ended_at: "" });

// 监控请求参数编码
const monitorRequests = [];
const monitorContext = { api: async (path, options) => { monitorRequests.push({ path, query: options.body ? JSON.parse(options.body) : Object.fromEntries(new URLSearchParams(path.split("?")[1] || "")) }); return { data: {} }; } };
const monitorApi = createApi(monitorContext, state);
await monitorApi.monitorSummary();
await monitorApi.monitorCalls({ board_code: "report_submission", result_status: "success", started_at: "2026-09-16", ended_at: "2026-09-17", page: "2", page_size: "10" });
assert.equal(monitorRequests[0].path, "/api/modules/dashboard-management/external-api/monitor/summary");
assert.ok(monitorRequests[1].path.startsWith("/api/modules/dashboard-management/external-api/monitor/calls?"));
assert.equal(monitorRequests[1].query.page, "2");
assert.equal(monitorRequests[1].query.page_size, "10");
assert.equal(monitorRequests[1].query.board_code, "report_submission");
assert.equal(monitorRequests[1].query.result_status, "success");
assert.equal(monitorRequests[1].query.started_at, new Date("2026-09-16T00:00:00.000").toISOString());
assert.equal(monitorRequests[1].query.ended_at, new Date("2026-09-17T23:59:59.999").toISOString());

// stopRequests 会中止监控请求
const monitorControllers = [];
const abortContext = { api: async (_path, options) => { monitorControllers.push(options.signal); return { data: {} }; } };
const abortApi = createApi(abortContext, state);
const pendingSummary = abortApi.monitorSummary();
stopRequests(state);
await pendingSummary;
assert.equal(monitorControllers.length, 1);
assert.equal(monitorControllers[0].aborted, true);

// 监控页面返回不清空草稿
activateLifecycle(state);
selectBoard(state, "report_submission");
selectRegion(state, 11);
markSqlChanged(state, "SELECT unsaved for return test");
enterMonitorView(state, 256);
assert.equal(state.viewMode, "monitor");
leaveMonitorView(state);
assert.equal(state.viewMode, "management");
assert.equal(currentDraft(state).sql_text, "SELECT unsaved for return test");
assert.equal(state.managementScrollTop, 256);

// 监控列表使用中文名称、中文状态和统一的本地时间格式。
assert.equal(monitorBoardName("report_submission"), "金融监管报表报送大屏");
assert.equal(monitorBoardName("reporting_process"), "金融监管报送流程大屏");
assert.equal(monitorBoardName("unknown"), "unknown");
assert.equal(monitorStatusText("success"), "成功");
assert.equal(monitorStatusText("partial"), "部分成功");
assert.equal(monitorStatusText("error"), "失败");
assert.equal(formatMonitorDateTime("2026-09-16T01:02:03"), "2026-09-16 01:02:03");
assert.equal(formatMonitorDateTime("invalid"), "-");

console.log(JSON.stringify({ ok: true }));
""".strip(),
        encoding="utf-8",
    )
    completed = subprocess.run(
        ["node", str(scenario)], cwd=tmp_path, text=True, capture_output=True, check=True,
    )
    return json.loads(completed.stdout)


def test_dashboard_management_state_keeps_boards_drafts_permissions_and_requests_isolated(tmp_path: Path) -> None:
    assert _run_scenario(tmp_path) == {"ok": True}
