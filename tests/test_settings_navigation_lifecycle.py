"""Exercise real settings loaders and navigation with pending Node requests."""

from pathlib import Path
import json
import re
import subprocess

import pytest


APP_JS = Path(__file__).resolve().parents[1] / "src/auto_check/web/app.js"


def run_scenario(scenario: str, *, real_flow_status: bool = False) -> None:
    source = APP_JS.read_text(encoding="utf-8")
    functions = []
    names = [
        "loadPageSection", "loadSettingsPageData", "switchPage",
        "loadReconcileSchemaSettings", "loadConfigList", "loadSystemInfo",
        "loadDbValidationSettings", "loadDbValidationMappingPayload", "loadFlowSettings",
        "loadInterfaceRadiusPreference", "resetInterfaceRadiusForAuthChange",
        "applyReauthenticatedSession", "discardAuthenticatedSession", "exitExpiredSession",
        "saveInterfaceRadiusPreference", "captureInterfaceRadiusPreference",
        "restoreInterfaceRadiusPreference", "ensureAuthenticated", "logout",
    ]
    if real_flow_status:
        names.append("loadFlowToastStatus")
    for name in names:
        match = re.search(rf"(?:async )?function {name}\([^\n]*\) \{{.*?\n\}}", source, re.S)
        assert match, name
        functions.append(match.group())
    scope = re.search(r"// Settings page load scope start(.*?)// Settings page load scope end", source, re.S)
    harness = r"""
const assert = require('node:assert/strict');
let page = 'home';
let observer;
const effects = [];
const calls = [];
const pending = [];
const timers = new Map();
let timerId = 0;
globalThis.setTimeout = (fn) => { timers.set(++timerId, fn); return timerId; };
globalThis.clearTimeout = (id) => timers.delete(id);
globalThis.MutationObserver = class {
  constructor(fn) { observer = fn; }
  observe() {}
};
const root = {
  dataset: {},
  getAttribute: () => page,
  setAttribute: (_, value) => { page = value; },
};
const document = { documentElement: root, getElementById: () => ({ textContent: '' }) };
const window = {
  setTimeout, clearTimeout,
  location: { href: '/' },
  AutoCheckModuleHost: { deactivate: async () => { page = ''; } },
};
const location = { hash: '' };
const authState = { user: { id: 'alice', username: 'alice' } };
const DEFAULT_INTERFACE_PREFERENCES = { radiusPx: 4, lineChartStyle: 'straight' };
const INTERFACE_RADIUS_LOAD_TIMEOUT_MS = 10000;
const interfaceRadiusState = {
  authRevision: 1, loadRequestId: 0, saveRequestId: 0, editRevision: 0,
  serverMutationRevision: 0, loaded: false, loadFailed: false, saving: false,
  draftPreferences: { ...DEFAULT_INTERFACE_PREFERENCES },
  savedPreferences: { ...DEFAULT_INTERFACE_PREFERENCES },
};
function interfacePreferencesMatch(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
function copyInterfacePreferences(p) { return { ...p }; }
function readInterfacePreferencesPayload(p) { return p.preferences || DEFAULT_INTERFACE_PREFERENCES; }
function cacheAuthenticatedInterfacePreferences(p) { effects.push(['interface-cache', p]); }
function applyInterfacePreferences(p) { effects.push(['interface-apply', p]); }
function syncInterfaceRadiusDirtyStatus() {}
function renderInterfaceRadiusPreference() { effects.push('interface-render'); }
const reconcileSchemaForm = {};
const reconcileSchemaStatus = { textContent: '' };
const runDate = { value: '2026-10-01' };
const configList = { innerHTML: '' };
const toolCardDbValidation = {};
const dbValidationMetadataSource = {};
let allConfigs = [];
let dbValidationMappingPayload = {};
let flowSettings = {};
let flowDataSources = [];
let selectedFlowChainIds = [];
let flowDefinitions = [];
let flowDefinitionsLoaded = true;
let flowDefinitionSearchItems = [];
let flowToastStarted = true, flowToastSeenJobId = '', flowToastDismissed = false, flowToastJob = null;
let flowPollRunning = true;
function renderFlowToast() { effects.push('global-flow-render'); }
function startFlowToastPollIfNeeded() { flowPollRunning = true; }
function stopFlowToastPoll() { flowPollRunning = false; }
const flowSource = {};
const toolCardFlow = {};
const flowExecuteUrl = {}, flowFlowTable = {}, flowTaskTable = {}, flowPollInterval = {}, flowStepTimeout = {};
function api(path, options = {}) {
  calls.push({ path, options });
  return new Promise((resolve, reject) => pending.push({ path, resolve, reject }));
}
function hasCapability() { return true; }
function showToast() { effects.push('toast'); }
function syncNavState() {}
function discardUnsavedInterfaceRadius() { effects.push('discard'); }
function applySettingsRoleAccess() { effects.push('role'); }
function applyCapabilityAccess() { effects.push('capability'); }
function renderReconcileSchemaForm(schema) { effects.push(['schema', schema]); }
function renderConfigList() { effects.push(['configs', allConfigs]); }
function sortConfigsForDisplay(values) { return values; }
function serverSettingsToClient(v) { return v; }
function userDisplayName(v) { return v.username; }
function renderDbValidationSettingsLoading() { effects.push('db-loading'); }
function renderDbValidationSettings(v) { effects.push(['db', v]); }
function renderDbValidationSettingsError(v) { effects.push(['db-error', v]); }
function updateDbValidationMappingEntryDots() { effects.push(['mapping', dbValidationMappingPayload]); }
function fillFlowSourceSelect() { effects.push('flow-source'); }
function renderFlowDefinitionLimitHint() {}
function renderFlowChainSettings(v) { effects.push(['flow', v]); }
function renderFlowChainPicker() {}
async function loadFlowToastStatus() { effects.push('flow-poll'); }
function renderFlowSettingsLoadError(v) { effects.push(['flow-error', v]); }
function updateCurrentUsername() {}
function applyRoleAccess() {}
function clearReportNavigationCache() {}
const sessionStorage = { removeItem() {} };
const USER_AVATAR_SESSION_KEY = 'avatar';
async function fetch() { return {
  ok: true,
  json: async () => ({ authenticated: true, user: { id: 'bob', username: 'bob' } }),
}; }
let confirmResult = true;
async function showConfirm() { return confirmResult; }
function activateThemeUserStorage() {}
function applySavedUserTheme() {}
function revealAuthenticatedApp() {}
async function loadUsers() {}
async function loadRolePermissions() {}
async function loadDictionaries() {}
async function loadScheduledTasks() {}
async function loadReportNavigation() {}
async function flush() { for (let i = 0; i < 12; i++) await Promise.resolve(); }
async function start() {
  await switchPage('settings');
  const work = [...timers.values()]; timers.clear(); work.forEach(fn => fn());
  await flush();
}
function resolveAll(value = {}) { pending.splice(0).forEach(p => p.resolve(value)); }
__SOURCE__
(async () => {
__SCENARIO__
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
"""
    script = harness.replace("__SOURCE__", (scope.group(1) if scope else "") + "\n" + "\n".join(functions)).replace("__SCENARIO__", scenario)
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("destination", ["users", "role-permissions", "dictionaries"])
def test_late_success_cannot_render_after_leaving_settings(destination):
    run_scenario(f"""
await start();
await switchPage({json.dumps(destination)});
const before = effects.length;
resolveAll({{ schema: {{ marker: 'stale' }}, configs: [{{ id: 'stale' }}] }});
await flush();
assert.equal(effects.length, before, 'old settings success must not render or reapply permissions');
assert.ok(calls.every(c => c.options.signal?.aborted), 'settings GETs must be aborted');
assert.equal(allConfigs.length, 0, 'old settings success must not mutate shared state');
""")


def test_late_failure_cannot_replace_status_after_leaving_settings():
    run_scenario("""
await start();
await switchPage('users');
const before = effects.length;
pending.splice(0).forEach(p => p.reject(new Error('late failure')));
await flush();
assert.equal(effects.length, before);
assert.equal(reconcileSchemaStatus.textContent, '');
assert.equal(configList.innerHTML, '');
""")


def test_settings_timer_is_cancelled_before_requests_start():
    run_scenario("""
await switchPage('settings');
await switchPage('users');
const work = [...timers.values()]; timers.clear(); work.forEach(fn => fn());
await flush();
assert.equal(calls.length, 0);
assert.equal(timers.size, 0);
assert.ok(effects.includes('discard'), 'capture settings page before module deactivate clears data-page');
""")


def test_fast_return_and_repeated_entry_ignore_the_old_generation():
    run_scenario("""
await start();
const old = pending.splice(0);
await switchPage('users');
await start();
const before = effects.length;
old.forEach(p => p.resolve({ schema: { marker: 'old' }, configs: [{ id: 'old' }] }));
await flush();
assert.equal(effects.length, before);
await switchPage('settings');
assert.ok(calls.every(c => c.options.signal?.aborted));
""")


def test_direct_module_navigation_cleans_the_settings_scope():
    run_scenario("""
await start();
page = 'module-report';
observer?.([{ attributeName: 'data-page' }]);
const before = effects.length;
resolveAll({ schema: { marker: 'stale' } });
await flush();
assert.equal(effects.length, before);
assert.ok(calls.every(c => c.options.signal?.aborted));
assert.ok(effects.includes('discard'));
""")


def test_account_change_ignores_old_results_but_same_account_recovery_remains_valid():
    run_scenario("""
await start();
await applyReauthenticatedSession({ user: { id: 'bob', username: 'bob' } });
const before = effects.length;
resolveAll({ schema: { marker: 'stale' } });
await flush();
assert.equal(effects.length, before);
authState.user = { id: 'alice', username: 'alice' };
await start();
await applyReauthenticatedSession({ user: { id: 'alice', username: 'alice', role: 'admin' } });
resolveAll({ schema: { marker: 'current' } });
await flush();
assert.ok(effects.some(e => Array.isArray(e) && e[0] === 'schema' && e[1].marker === 'current'));
""")


@pytest.mark.parametrize("boundary", ["resetInterfaceRadiusForAuthChange()", "await discardAuthenticatedSession({})", "exitExpiredSession()"])
def test_auth_boundaries_abort_settings_requests(boundary):
    run_scenario(f"""
window.location = {{ href: '/' }};
await start();
{boundary};
const before = effects.length;
resolveAll({{ schema: {{ marker: 'old' }} }});
await flush();
assert.ok(calls.every(c => c.options.signal?.aborted));
assert.equal(effects.length, before);
""")


def test_secondary_config_and_mapping_requests_cannot_write_after_leaving():
    run_scenario("""
runDate.value = '';
await start();
const configs = pending.find(p => p.path === '/api/configs');
const db = pending.find(p => p.path === '/api/tools/db-validation/settings');
configs.resolve({ configs: [] });
db.resolve({ settings: {} });
await flush();
assert.ok(calls.some(c => c.path === '/api/config'));
assert.ok(calls.some(c => c.path === '/api/tools/db-validation/field-mapping'));
await switchPage('users');
const before = effects.length;
resolveAll({ default_run_date: 'stale', tables: [{ id: 'stale' }] });
await flush();
assert.equal(runDate.value, '');
assert.equal(effects.length, before);
assert.deepEqual(dbValidationMappingPayload, {});
assert.ok(calls.every(c => c.options.signal?.aborted));
""")


def test_current_failure_still_renders_and_ordinary_loaders_keep_working_off_settings():
    run_scenario("""
await start();
pending.splice(0).forEach(p => p.reject(new Error('current failure')));
await flush();
assert.equal(reconcileSchemaStatus.textContent, 'current failure');
assert.ok(configList.innerHTML.includes('加载失败'));
assert.ok(effects.includes('toast'));
assert.ok(effects.some(e => Array.isArray(e) && e[0] === 'db-error'));
await switchPage('users');
const ordinary = loadConfigList();
assert.equal(calls.at(-1).options.signal, undefined);
resolveAll({ configs: [{ id: 'ordinary' }] });
await ordinary;
assert.equal(allConfigs[0].id, 'ordinary');
""")


def test_navigation_does_not_cancel_silent_radius_loading_or_flow_status_refresh():
    run_scenario("""
await start();
await switchPage('users');
const radius = loadInterfaceRadiusPreference({ silent: true });
const radiusCall = calls.at(-1);
await switchPage('dictionaries');
assert.equal(radiusCall.options.signal.aborted, false);
resolveAll({ preferences: { radiusPx: 8, lineChartStyle: 'straight' } });
await radius;
assert.equal(interfaceRadiusState.savedPreferences.radiusPx, 8);
assert.equal(effects.filter(e => e === 'flow-poll').length, 0, 'obsolete settings must not trigger the global status request');
await loadFlowToastStatus();
assert.equal(effects.filter(e => e === 'flow-poll').length, 1);
""")


@pytest.mark.parametrize("failure", [False, True])
def test_cancelled_interface_get_keeps_draft_and_does_not_set_load_failed(failure):
    run_scenario(f"""
await start();
interfaceRadiusState.draftPreferences = {{ radiusPx: 9, lineChartStyle: 'smooth' }};
interfaceRadiusState.editRevision += 1;
cancelSettingsPageLoad();
const before = effects.length;
pending.splice(0).forEach(p => p.{'reject(new Error("late failure"))' if failure else 'resolve({ preferences: { radiusPx: 2 } })'});
await flush();
assert.equal(interfaceRadiusState.draftPreferences.radiusPx, 9);
assert.equal(interfaceRadiusState.loadFailed, false);
assert.equal(effects.length, before);
assert.equal(timers.size, 0, 'settled cancelled interface request must release its timeout');
""")


def test_navigation_does_not_abort_an_interface_save_already_in_progress():
    run_scenario("""
await start();
const old = pending.splice(0);
interfaceRadiusState.draftPreferences = { radiusPx: 9, lineChartStyle: 'smooth' };
const saving = saveInterfaceRadiusPreference();
const saveCall = calls.at(-1);
assert.equal(saveCall.options.method, 'POST');
await switchPage('users');
assert.equal(saveCall.options.signal, undefined);
assert.equal(interfaceRadiusState.saving, true);
old.forEach(p => p.reject(new Error('cancelled GET')));
resolveAll({ preferences: { radiusPx: 9, lineChartStyle: 'smooth' } });
assert.equal(await saving, true);
assert.equal(interfaceRadiusState.savedPreferences.radiusPx, 9);
assert.equal(interfaceRadiusState.saving, false);
assert.equal(interfaceRadiusState.loadFailed, false);
""")


def test_real_logout_cancels_settings_gets_before_logout_completes():
    run_scenario("""
await start();
const old = pending.splice(0);
const exiting = logout();
await flush();
assert.ok(calls.filter(c => c.options.method !== 'POST').every(c => c.options.signal?.aborted));
const before = effects.length;
old.forEach(p => p.resolve({ schema: { marker: 'old' } }));
await flush();
assert.equal(effects.length, before);
resolveAll({});
await exiting;
assert.equal(window.location.href, '/login.html');
""")


def test_failed_logout_reloads_cancelled_sections_without_losing_the_unsaved_draft():
    run_scenario("""
await start();
const old = pending.splice(0);
interfaceRadiusState.draftPreferences = { radiusPx: 9, lineChartStyle: 'smooth' };
const exiting = logout();
await flush();
const logoutRequest = pending.find(p => p.path === '/api/auth/logout');
logoutRequest.reject(new Error('logout unavailable'));
await exiting;
await flush();
const replacement = pending.filter(p => p.path !== '/api/auth/logout');
assert.ok(replacement.some(p => p.path === '/api/settings/reconcile-schema'), 'logout failure must reload the cancelled settings sections');
assert.ok(replacement.some(p => p.path === '/api/tools/db-validation/settings'));
assert.equal(interfaceRadiusState.draftPreferences.radiusPx, 9);
assert.equal(interfaceRadiusState.draftPreferences.lineChartStyle, 'smooth');
assert.equal(authState.user.id, 'alice');
old.forEach(p => p.resolve({ schema: { marker: 'old' } }));
replacement.forEach(p => p.resolve({ schema: { marker: 'restored' }, preferences: { radiusPx: 6, lineChartStyle: 'straight' } }));
await flush();
assert.equal(interfaceRadiusState.draftPreferences.radiusPx, 9);
assert.equal(interfaceRadiusState.draftPreferences.lineChartStyle, 'smooth');
assert.equal(interfaceRadiusState.savedPreferences.radiusPx, 6);
assert.ok(effects.some(e => Array.isArray(e) && e[0] === 'schema' && e[1].marker === 'restored'));
assert.ok(!effects.some(e => Array.isArray(e) && e[0] === 'schema' && e[1].marker === 'old'));
""")


@pytest.mark.parametrize("change", ["await switchPage('users')", "await applyReauthenticatedSession({ user: { id: 'bob', username: 'bob' } })"])
def test_failed_logout_does_not_restart_settings_after_page_or_account_change(change):
    run_scenario(f"""
await start();
const exiting = logout();
await flush();
{change};
const before = calls.length;
pending.find(p => p.path === '/api/auth/logout').reject(new Error('logout unavailable'));
await exiting;
await flush();
assert.equal(calls.length, before, 'logout failure must not restart settings for another page or account');
resolveAll({{}});
await flush();
""")


def test_cancelling_logout_confirmation_keeps_current_settings_loading():
    run_scenario("""
await start();
confirmResult = false;
const before = calls.length;
await logout();
assert.equal(calls.length, before);
assert.ok(calls.every(c => !c.options.signal.aborted));
resolveAll({ schema: { marker: 'current' } });
await flush();
assert.ok(effects.some(e => Array.isArray(e) && e[0] === 'schema' && e[1].marker === 'current'));
""")


def test_real_initial_authentication_invalidates_old_settings_and_keeps_silent_get():
    run_scenario("""
await start();
const old = pending.splice(0);
const authenticating = ensureAuthenticated();
await flush();
assert.equal(authState.user.id, 'bob');
assert.ok(calls.slice(0, -1).every(c => c.options.signal?.aborted));
assert.equal(calls.at(-1).options.signal.aborted, false);
const before = effects.length;
old.forEach(p => p.resolve({ schema: { marker: 'old' } }));
await flush();
assert.equal(effects.length, before);
resolveAll({ preferences: { radiusPx: 6, lineChartStyle: 'straight' } });
await authenticating;
assert.equal(interfaceRadiusState.savedPreferences.radiusPx, 6);
""")


def test_started_global_flow_status_request_survives_settings_navigation():
    run_scenario("""
await start();
pending.find(p => p.path === '/api/tools/flow/settings').resolve({ settings: { chains: [] } });
await flush();
const statusRequest = pending.find(p => p.path === '/api/flow-chain/status');
assert.ok(statusRequest, 'current flow settings should refresh status');
const statusCall = calls.find(c => c.path === '/api/flow-chain/status');
assert.equal(statusCall.options.signal, undefined, 'global flow polling must not inherit the navigation signal');
await switchPage('users');
assert.equal(flowPollRunning, true);
statusRequest.resolve({ job: { id: 'running-job', status: 'running' } });
await flush();
assert.equal(flowToastJob.id, 'running-job');
assert.equal(flowPollRunning, true);
assert.ok(effects.includes('global-flow-render'));
resolveAll({});
await flush();
assert.equal(flowPollRunning, true);
""", real_flow_status=True)
